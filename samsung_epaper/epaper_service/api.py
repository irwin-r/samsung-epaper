"""Unified FastAPI application — API routes and update orchestration."""

import asyncio
import logging
import shutil
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse

from . import __version__
from .config import AppConfig
from .content_server import router as content_router, set_dependencies
from .database import (
    AssetRepository,
    HistoryRepository,
    PresetRepository,
    init_db,
)
from .image_processor import ImageProcessor
from .mdc_client import MDCClient
from .models import (
    DisplayAssetRequest,
    PresetCreate,
    PresetUpdate,
    ServiceStatus,
    UpdateRequest,
    UpdateResponse,
)
from .sources import get_source

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = AppConfig()

    if not config.public_base_url or not config.public_base_url.startswith("http"):
        raise RuntimeError(
            "PUBLIC_BASE_URL must be set to an absolute HTTP URL "
            "(e.g., http://192.168.50.84:8000). "
            "The Samsung display needs this to fetch content."
        )

    assets_dir = Path(config.assets_dir)
    assets_dir.mkdir(parents=True, exist_ok=True)
    (assets_dir / "originals").mkdir(exist_ok=True)
    (assets_dir / "processed").mkdir(exist_ok=True)
    (assets_dir / "thumbnails").mkdir(exist_ok=True)

    db = await init_db(config.db_path)

    asset_repo = AssetRepository(db)
    history_repo = HistoryRepository(db)
    preset_repo = PresetRepository(db)

    mdc = MDCClient(config)
    processor = ImageProcessor(config.viewport_width, config.viewport_height)

    # Wire content server dependencies
    set_dependencies(config, asset_repo, history_repo, assets_dir / "processed")

    # Seed default newspaper preset if none exist
    presets = await preset_repo.list()
    if not presets:
        preset_id = await preset_repo.create(
            name="Morning Newspaper",
            source_type="frontpages",
            source_config={
                "url": config.newspaper_url,
                "image_pattern": config.newspaper_pattern,
            },
        )
        await preset_repo.activate(preset_id)
        logger.info(f"Created default preset: Morning Newspaper ({preset_id})")

    app.state.config = config
    app.state.db = db
    app.state.asset_repo = asset_repo
    app.state.history_repo = history_repo
    app.state.preset_repo = preset_repo
    app.state.mdc = mdc
    app.state.processor = processor
    app.state.assets_dir = assets_dir
    app.state.update_lock = asyncio.Lock()
    app.state.is_updating = False

    # Restore last state from history
    latest = await history_repo.get_latest()
    if latest:
        app.state.last_update = latest.displayed_at
        app.state.last_update_status = latest.status
        app.state.current_asset_id = latest.asset_id
    else:
        app.state.last_update = None
        app.state.last_update_status = None
        app.state.current_asset_id = None

    logger.info(f"Samsung ePaper service v{__version__} started")
    logger.info(f"Display: {config.display_ip}:{config.display_port}")
    logger.info(f"Public URL: {config.public_base_url}")

    yield

    await db.close()
    logger.info("Service shut down")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Samsung ePaper Display Service",
        version=__version__,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(content_router)

    # --- Health & Status ---

    @app.get("/api/health")
    async def health():
        return {"status": "healthy"}

    @app.get("/api/status")
    async def status():
        display_status = await app.state.mdc.get_status()
        active_preset = await app.state.preset_repo.get_active()
        return ServiceStatus(
            version=__version__,
            display=display_status,
            last_update=app.state.last_update,
            last_update_status=app.state.last_update_status,
            is_updating=app.state.is_updating,
            active_preset_id=active_preset.id if active_preset else None,
            active_preset_name=active_preset.name if active_preset else None,
            current_asset_id=app.state.current_asset_id,
        ).model_dump(mode="json")

    # --- Update ---

    @app.post("/api/update")
    async def trigger_update(
        request: UpdateRequest, background_tasks: BackgroundTasks
    ):
        if app.state.update_lock.locked():
            raise HTTPException(status_code=409, detail="Update already in progress")
        background_tasks.add_task(perform_update, app, request.preset_id)
        return UpdateResponse(
            status="started",
            message="Display update started in background",
            started_at=datetime.now(),
        )

    @app.post("/api/update/sync")
    async def trigger_update_sync(request: UpdateRequest):
        if app.state.update_lock.locked():
            raise HTTPException(status_code=409, detail="Update already in progress")
        try:
            asset_id = await perform_update(app, request.preset_id)
            return {
                "status": "completed",
                "message": "Display updated successfully",
                "asset_id": asset_id,
                "completed_at": datetime.now().isoformat(),
            }
        except Exception:
            logger.exception("Sync update failed")
            raise HTTPException(status_code=500, detail="Update failed")

    # Backward compat for existing HA rest_commands
    @app.post("/update")
    async def compat_update(background_tasks: BackgroundTasks):
        if app.state.update_lock.locked():
            raise HTTPException(status_code=409, detail="Update already in progress")
        background_tasks.add_task(perform_update, app, None)
        return UpdateResponse(
            status="started",
            message="Display update started in background",
            started_at=datetime.now(),
        )

    @app.post("/update/sync")
    async def compat_update_sync():
        if app.state.update_lock.locked():
            raise HTTPException(status_code=409, detail="Update already in progress")
        try:
            await perform_update(app, None)
            return {
                "status": "completed",
                "message": "Display updated successfully",
                "completed_at": datetime.now().isoformat(),
            }
        except Exception:
            logger.exception("Compat sync update failed")
            raise HTTPException(status_code=500, detail="Update failed")

    @app.get("/status")
    async def compat_status():
        return await status()

    # --- Display specific asset ---

    @app.post("/api/display")
    async def display_asset(request: DisplayAssetRequest):
        asset = await app.state.asset_repo.get(request.asset_id)
        if not asset or not asset.filename_processed:
            raise HTTPException(status_code=404, detail="Asset not found")
        await push_asset_to_display(app, asset.id)
        return {"status": "sent", "asset_id": asset.id}

    # --- Upload ---

    @app.post("/api/upload")
    async def upload_image(
        file: UploadFile = File(...),
        title: str = Query(default="Uploaded Image"),
        crop_x: int = Query(default=0, ge=0),
        crop_y: int = Query(default=0, ge=0),
        crop_width: int = Query(default=0, ge=0),
        crop_height: int = Query(default=0, ge=0),
        process: bool = Query(default=True),
    ):
        """Upload an image file and optionally push to display.

        Crop params (crop_x, crop_y, crop_width, crop_height) define a region
        to extract before resizing. If all are 0, the full image is used.
        Set process=false to skip resize/crop (push raw image as-is).
        """
        assets_dir = app.state.assets_dir
        processor = app.state.processor

        # Save uploaded file
        asset_id = str(uuid.uuid4())
        ext = Path(file.filename).suffix or ".png"
        original_name = f"{asset_id}_upload{ext}"
        original_path = assets_dir / "originals" / original_name

        content = await file.read()
        await asyncio.to_thread(original_path.write_bytes, content)

        # Create asset record
        db_asset_id = await app.state.asset_repo.create(
            source_type="upload",
            filename_original=original_name,
            title=title,
        )

        # Crop if requested
        input_path = original_path
        if crop_width > 0 and crop_height > 0:
            from PIL import Image
            img = await asyncio.to_thread(Image.open, original_path)
            cropped = img.crop((crop_x, crop_y, crop_x + crop_width, crop_y + crop_height))
            cropped_path = assets_dir / "cache" / f"{asset_id}_cropped.png"
            await asyncio.to_thread(cropped.save, cropped_path, format="PNG")
            input_path = cropped_path

        # Process for display
        processed_name = f"{asset_id}_processed.png"
        processed_path = assets_dir / "processed" / processed_name

        if process:
            info = await processor.process(input_path, processed_path)
        else:
            shutil.copy2(str(input_path), str(processed_path))
            from PIL import Image
            img = await asyncio.to_thread(Image.open, processed_path)
            from .models import ImageInfo
            info = ImageInfo(width=img.width, height=img.height, file_size=processed_path.stat().st_size)

        # Thumbnail
        thumb_name = f"{asset_id}_thumb.jpg"
        thumb_path = assets_dir / "thumbnails" / thumb_name
        await processor.generate_thumbnail(processed_path, thumb_path)

        # Update asset
        await app.state.asset_repo.update_processed(
            asset_id=db_asset_id,
            filename_processed=processed_name,
            filename_thumbnail=thumb_name,
            width=info.width,
            height=info.height,
            file_size=info.file_size,
        )

        # Push to display
        success = await push_asset_to_display(app, db_asset_id)
        if success:
            app.state.current_asset_id = db_asset_id
            app.state.last_update_status = "success"
        app.state.last_update = datetime.now()

        return {
            "status": "sent" if success else "failed",
            "asset_id": db_asset_id,
            "width": info.width,
            "height": info.height,
        }

    @app.post("/api/display_url")
    async def display_from_url(url: str = Query(...), title: str = Query(default="URL Image")):
        """Fetch an image from a URL and push to display."""
        import aiohttp
        timeout = aiohttp.ClientTimeout(total=30)
        headers = {"User-Agent": "Samsung-ePaper/1.0"}
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(url, allow_redirects=True) as resp:
                if resp.status != 200:
                    raise HTTPException(status_code=400, detail=f"Failed to fetch URL: HTTP {resp.status}")
                image_data = await resp.read()

        assets_dir = app.state.assets_dir
        asset_id = str(uuid.uuid4())
        original_name = f"{asset_id}_url.png"
        original_path = assets_dir / "originals" / original_name
        await asyncio.to_thread(original_path.write_bytes, image_data)

        db_asset_id = await app.state.asset_repo.create(
            source_type="url",
            filename_original=original_name,
            source_id=url,
            title=title,
        )

        processed_name = f"{asset_id}_processed.png"
        processed_path = assets_dir / "processed" / processed_name
        info = await app.state.processor.process(original_path, processed_path)

        thumb_name = f"{asset_id}_thumb.jpg"
        thumb_path = assets_dir / "thumbnails" / thumb_name
        await app.state.processor.generate_thumbnail(processed_path, thumb_path)

        await app.state.asset_repo.update_processed(
            asset_id=db_asset_id,
            filename_processed=processed_name,
            filename_thumbnail=thumb_name,
            width=info.width,
            height=info.height,
            file_size=info.file_size,
        )

        success = await push_asset_to_display(app, db_asset_id)
        if success:
            app.state.current_asset_id = db_asset_id
            app.state.last_update_status = "success"
        app.state.last_update = datetime.now()

        return {"status": "sent" if success else "failed", "asset_id": db_asset_id}

    # --- Assets ---

    @app.get("/api/assets")
    async def list_assets(
        limit: int = Query(default=50, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ):
        assets = await app.state.asset_repo.list(limit=limit, offset=offset)
        return [a.model_dump(mode="json") for a in assets]

    @app.get("/api/assets/{asset_id}")
    async def get_asset(asset_id: str):
        asset = await app.state.asset_repo.get(asset_id)
        if not asset:
            raise HTTPException(status_code=404, detail="Asset not found")
        return asset.model_dump(mode="json")

    @app.get("/api/assets/{asset_id}/thumbnail")
    async def get_asset_thumbnail(asset_id: str):
        asset = await app.state.asset_repo.get(asset_id)
        if not asset or not asset.filename_thumbnail:
            raise HTTPException(status_code=404, detail="Thumbnail not found")
        thumb_path = app.state.assets_dir / "thumbnails" / asset.filename_thumbnail
        if not thumb_path.exists():
            raise HTTPException(status_code=404, detail="Thumbnail file not found")
        return FileResponse(thumb_path, media_type="image/jpeg")

    # --- Presets ---

    @app.get("/api/presets")
    async def list_presets():
        presets = await app.state.preset_repo.list()
        return [p.model_dump(mode="json") for p in presets]

    @app.post("/api/presets")
    async def create_preset(request: PresetCreate):
        try:
            source = get_source(request.source_type)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown source type: {request.source_type}",
            )
        if not await source.validate_config(request.source_config):
            raise HTTPException(
                status_code=400, detail="Invalid source configuration"
            )
        try:
            preset_id = await app.state.preset_repo.create(
                name=request.name,
                source_type=request.source_type,
                source_config=request.source_config,
                image_config=request.image_config,
            )
        except Exception:
            raise HTTPException(
                status_code=409, detail=f"Preset name '{request.name}' already exists"
            )
        return {"id": preset_id, "status": "created"}

    @app.put("/api/presets/{preset_id}")
    async def update_preset(preset_id: str, request: PresetUpdate):
        preset = await app.state.preset_repo.get(preset_id)
        if not preset:
            raise HTTPException(status_code=404, detail="Preset not found")
        await app.state.preset_repo.update(
            preset_id,
            name=request.name,
            source_type=request.source_type,
            source_config=request.source_config,
            image_config=request.image_config,
        )
        return {"status": "updated"}

    @app.delete("/api/presets/{preset_id}")
    async def delete_preset(preset_id: str):
        preset = await app.state.preset_repo.get(preset_id)
        if not preset:
            raise HTTPException(status_code=404, detail="Preset not found")
        if preset.is_active:
            raise HTTPException(
                status_code=409,
                detail="Cannot delete the active preset. Activate another preset first.",
            )
        await app.state.preset_repo.delete(preset_id)
        return {"status": "deleted"}

    @app.post("/api/presets/{preset_id}/activate")
    async def activate_preset(preset_id: str):
        preset = await app.state.preset_repo.get(preset_id)
        if not preset:
            raise HTTPException(status_code=404, detail="Preset not found")
        await app.state.preset_repo.activate(preset_id)
        return {"status": "activated", "preset": preset.name}

    # --- History ---

    @app.get("/api/history")
    async def list_history(limit: int = 50):
        entries = await app.state.history_repo.list(limit=limit)
        return [e.model_dump(mode="json") for e in entries]

    return app


async def perform_update(
    app: FastAPI, preset_id: Optional[str] = None
) -> str:
    """Core update flow: fetch -> process -> store -> push to display."""
    async with app.state.update_lock:
        config: AppConfig = app.state.config
        asset_repo: AssetRepository = app.state.asset_repo
        history_repo: HistoryRepository = app.state.history_repo
        preset_repo: PresetRepository = app.state.preset_repo
        processor: ImageProcessor = app.state.processor
        assets_dir: Path = app.state.assets_dir

        try:
            app.state.is_updating = True
            logger.info("=" * 60)
            logger.info(f"Update started at {datetime.now()}")

            # 1. Resolve preset
            if preset_id:
                preset = await preset_repo.get(preset_id)
            else:
                preset = await preset_repo.get_active()

            if not preset:
                raise Exception("No preset configured")

            logger.info(f"Using preset: {preset.name} ({preset.source_type})")

            # 2. Fetch from source
            source = get_source(preset.source_type)
            cache_dir = assets_dir / "cache"
            cache_dir.mkdir(exist_ok=True)
            raw_path, metadata = await source.fetch(preset.source_config, cache_dir)

            # 3. Create asset record
            asset_id = await asset_repo.create(
                source_type=preset.source_type,
                filename_original=raw_path.name,
                source_id=metadata.get("source_id"),
                title=metadata.get("title"),
                metadata_json=metadata.get("metadata_json"),
            )

            # Move original to storage (shutil.move handles cross-filesystem)
            original_dest = assets_dir / "originals" / f"{asset_id}_{raw_path.name}"
            shutil.move(str(raw_path), str(original_dest))

            # 4. Process image
            process_mode = "color"
            if preset.image_config:
                process_mode = preset.image_config.get("process_mode", "color")

            processed_name = f"{asset_id}_processed.png"
            processed_path = assets_dir / "processed" / processed_name
            info = await processor.process(
                original_dest, processed_path, mode=process_mode
            )

            # 5. Generate thumbnail
            thumb_name = f"{asset_id}_thumb.jpg"
            thumb_path = assets_dir / "thumbnails" / thumb_name
            await processor.generate_thumbnail(processed_path, thumb_path)

            # 6. Update asset record
            await asset_repo.update_processed(
                asset_id=asset_id,
                filename_processed=processed_name,
                filename_thumbnail=thumb_name,
                width=info.width,
                height=info.height,
                file_size=info.file_size,
            )

            # 7. Push to display
            success = await push_asset_to_display(app, asset_id)

            if success:
                app.state.last_update_status = "success"
                app.state.current_asset_id = asset_id
                logger.info(f"Update completed successfully (asset: {asset_id})")
            else:
                app.state.last_update_status = "failed"
                logger.warning(f"Update completed but display push failed (asset: {asset_id})")

            return asset_id

        except Exception as e:
            app.state.last_update_status = "failed"
            logger.error(f"Update failed: {e}", exc_info=True)
            raise
        finally:
            app.state.is_updating = False
            app.state.last_update = datetime.now()
            logger.info("=" * 60)


async def push_asset_to_display(app: FastAPI, asset_id: str) -> bool:
    """Push a processed asset to the Samsung display via MDC. Returns success."""
    config: AppConfig = app.state.config
    asset_repo: AssetRepository = app.state.asset_repo
    history_repo: HistoryRepository = app.state.history_repo
    mdc: MDCClient = app.state.mdc

    asset = await asset_repo.get(asset_id)
    if not asset or not asset.filename_processed:
        raise Exception(f"Asset {asset_id} not found or not processed")

    content_id = str(uuid.uuid4())
    file_id = str(uuid.uuid4())

    history_id = await history_repo.create(
        asset_id=asset_id, content_id=content_id, file_id=file_id
    )

    base_url = config.public_base_url.rstrip("/")
    manifest_url = f"{base_url}/content/{content_id}/manifest.json"

    logger.info(f"Pushing to display: {manifest_url}")
    success = await mdc.send_content(manifest_url)

    status = "sent" if success else "failed"
    await history_repo.update_status(
        history_id, status, error_message=None if success else "MDC send failed"
    )

    if success:
        app.state.current_asset_id = asset_id

    return success
