"""Unified FastAPI application — API routes and update orchestration."""

import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse

from croniter import croniter

from . import __version__
from .config import AppConfig
from .content_server import router as content_router, set_dependencies
from .database import (
    AssetRepository,
    CollectionRepository,
    FavouriteRepository,
    HistoryRepository,
    PresetRepository,
    ScheduleRepository,
    init_db,
)
from .image_processor import ImageProcessor
from .mdc_client import MDCClient
from .models import (
    CollectionCreate,
    DisplayAssetRequest,
    FavouriteCreate,
    PresetCreate,
    PresetUpdate,
    ScheduleCreate,
    ScheduleUpdate,
    ServiceStatus,
    UpdateRequest,
    UpdateResponse,
)
from .asset_pipeline import ingest_asset, push_asset_to_display, set_display_lock
from .generation_api import router as generation_router, set_generation_deps
from .generation_worker import make_worker
from .services.jobs import JobQueue
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
    schedule_repo = ScheduleRepository(db)
    collection_repo = CollectionRepository(db)
    favourite_repo = FavouriteRepository(db)

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
    app.state.schedule_repo = schedule_repo
    app.state.collection_repo = collection_repo
    app.state.favourite_repo = favourite_repo
    app.state.mdc = mdc
    app.state.processor = processor
    app.state.assets_dir = assets_dir
    app.state.update_lock = asyncio.Lock()
    display_lock = asyncio.Lock()
    app.state.display_lock = display_lock
    set_display_lock(display_lock)
    app.state.is_updating = False

    # Initialize generation job queue
    job_queue = JobQueue(db, make_worker(app))
    await job_queue.init()
    app.state.job_queue = job_queue

    auth_token = os.environ.get("EPAPER_AUTH_TOKEN")
    set_generation_deps(app, job_queue, auth_token)

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

    # Compute initial next_run_at for all enabled schedules
    schedules = await schedule_repo.list()
    for sched in schedules:
        if sched.is_enabled and croniter.is_valid(sched.cron_expression):
            cron = croniter(sched.cron_expression, datetime.now())
            next_run = cron.get_next(datetime)
            await schedule_repo.update_last_run(
                sched.id,
                last_run_at=sched.last_run_at.isoformat() if sched.last_run_at else None,
                next_run_at=next_run.isoformat(),
            )

    # Start background scheduler and job queue
    scheduler_task = asyncio.create_task(_run_scheduler(app))
    job_queue.start()

    logger.info(f"Samsung ePaper service v{__version__} started")
    logger.info(f"Display: {config.display_ip}:{config.display_port}")
    logger.info(f"Public URL: {config.public_base_url}")

    yield

    await job_queue.stop()
    scheduler_task.cancel()
    try:
        await scheduler_task
    except asyncio.CancelledError:
        pass
    await db.close()
    logger.info("Service shut down")


async def _run_scheduler(app: FastAPI) -> None:
    """Background loop that checks enabled schedules every 60 seconds."""
    logger.info("Schedule background task started")
    try:
        while True:
            await asyncio.sleep(60)
            try:
                schedule_repo: ScheduleRepository = app.state.schedule_repo
                schedules = await schedule_repo.list()
                now = datetime.now()
                for sched in schedules:
                    if not sched.is_enabled:
                        continue
                    if not croniter.is_valid(sched.cron_expression):
                        continue
                    # Check if the schedule should fire: next_run_at <= now
                    if sched.next_run_at and sched.next_run_at <= now:
                        logger.info(
                            f"Schedule '{sched.name}' firing "
                            f"(preset_id={sched.preset_id})"
                        )
                        try:
                            await perform_update(app, preset_id=sched.preset_id)
                        except Exception:
                            logger.exception(
                                f"Schedule '{sched.name}' update failed"
                            )
                        # Compute next run
                        cron = croniter(sched.cron_expression, now)
                        next_run = cron.get_next(datetime)
                        await schedule_repo.update_last_run(
                            sched.id,
                            last_run_at=now.isoformat(),
                            next_run_at=next_run.isoformat(),
                        )
            except Exception:
                logger.exception("Scheduler tick failed")
    except asyncio.CancelledError:
        logger.info("Schedule background task stopped")
        raise


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
    app.include_router(generation_router)

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

        # Save uploaded file to cache
        tmp_id = str(uuid.uuid4())
        ext = Path(file.filename).suffix or ".png"
        cache_dir = assets_dir / "cache"
        cache_dir.mkdir(exist_ok=True)
        upload_path = cache_dir / f"{tmp_id}_upload{ext}"

        content = await file.read()
        await asyncio.to_thread(upload_path.write_bytes, content)

        # Crop if requested (modifies the file before ingestion)
        if crop_width > 0 and crop_height > 0:
            from PIL import Image
            img = await asyncio.to_thread(Image.open, upload_path)
            cropped = img.crop((crop_x, crop_y, crop_x + crop_width, crop_y + crop_height))
            cropped_path = cache_dir / f"{tmp_id}_cropped.png"
            await asyncio.to_thread(cropped.save, cropped_path, format="PNG")
            upload_path.unlink(missing_ok=True)
            upload_path = cropped_path

        # For process=false, we still go through ingest but the processor
        # handles it.  TODO: support raw pass-through in ingest_asset if needed.
        result = await ingest_asset(
            app,
            upload_path,
            source_type="upload",
            title=title,
            check_duplicate=True,
            push_to_display=True,
        )

        return {
            "status": "sent" if result.pushed else "failed",
            "asset_id": result.asset_id,
            "width": result.width,
            "height": result.height,
            "duplicate": result.is_duplicate,
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
        cache_dir = assets_dir / "cache"
        cache_dir.mkdir(exist_ok=True)
        tmp_id = str(uuid.uuid4())
        download_path = cache_dir / f"{tmp_id}_url.png"
        await asyncio.to_thread(download_path.write_bytes, image_data)

        result = await ingest_asset(
            app,
            download_path,
            source_type="url",
            title=title,
            source_id=url,
            check_duplicate=True,
            push_to_display=True,
        )

        return {
            "status": "sent" if result.pushed else "failed",
            "asset_id": result.asset_id,
            "duplicate": result.is_duplicate,
        }

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

    @app.delete("/api/assets/{asset_id}")
    async def delete_asset(asset_id: str):
        asset = await app.state.asset_repo.get(asset_id)
        if not asset:
            raise HTTPException(status_code=404, detail="Asset not found")
        # Remove files
        for subdir, fname in [
            ("originals", asset.filename_original),
            ("processed", asset.filename_processed),
            ("thumbnails", asset.filename_thumbnail),
        ]:
            if fname:
                p = app.state.assets_dir / subdir / fname
                if p.exists():
                    p.unlink()
        # Remove from DB (history entries will remain but asset gone)
        await app.state.db.execute("DELETE FROM favourites WHERE asset_id = ?", (asset_id,))
        await app.state.db.execute("DELETE FROM display_history WHERE asset_id = ?", (asset_id,))
        await app.state.db.execute("DELETE FROM assets WHERE id = ?", (asset_id,))
        await app.state.db.commit()
        return {"status": "deleted"}

    @app.get("/api/assets/{asset_id}/thumbnail")
    async def get_asset_thumbnail(asset_id: str):
        asset = await app.state.asset_repo.get(asset_id)
        if not asset or not asset.filename_thumbnail:
            raise HTTPException(status_code=404, detail="Thumbnail not found")
        thumb_path = app.state.assets_dir / "thumbnails" / asset.filename_thumbnail
        if not thumb_path.exists():
            raise HTTPException(status_code=404, detail="Thumbnail file not found")
        return FileResponse(thumb_path, media_type="image/jpeg")

    @app.get("/api/assets/{asset_id}/image")
    async def get_asset_image(asset_id: str):
        asset = await app.state.asset_repo.get(asset_id)
        if not asset or not asset.filename_processed:
            raise HTTPException(status_code=404, detail="Image not found")
        img_path = app.state.assets_dir / "processed" / asset.filename_processed
        if not img_path.exists():
            raise HTTPException(status_code=404, detail="Image file not found")
        return FileResponse(img_path, media_type="image/png")

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

    # --- Collections ---

    @app.get("/api/collections")
    async def list_collections(parent_id: Optional[str] = Query(default=None)):
        collections = await app.state.collection_repo.list(parent_id=parent_id)
        return [c.model_dump(mode="json") for c in collections]

    @app.get("/api/collections/tree")
    async def get_collection_tree():
        return await app.state.collection_repo.get_tree()

    @app.post("/api/collections")
    async def create_collection(request: CollectionCreate):
        if request.parent_id:
            parent = await app.state.collection_repo.get(request.parent_id)
            if not parent:
                raise HTTPException(status_code=404, detail="Parent collection not found")
        try:
            collection_id = await app.state.collection_repo.create(
                name=request.name,
                parent_id=request.parent_id,
            )
        except Exception:
            raise HTTPException(
                status_code=409, detail=f"Collection name '{request.name}' already exists"
            )
        return {"id": collection_id, "status": "created"}

    @app.put("/api/collections/{collection_id}")
    async def rename_collection(collection_id: str, request: CollectionCreate):
        collection = await app.state.collection_repo.get(collection_id)
        if not collection:
            raise HTTPException(status_code=404, detail="Collection not found")
        try:
            await app.state.collection_repo.rename(collection_id, request.name)
        except Exception:
            raise HTTPException(
                status_code=409, detail=f"Collection name '{request.name}' already exists"
            )
        return {"status": "updated"}

    @app.delete("/api/collections/{collection_id}")
    async def delete_collection(collection_id: str):
        collection = await app.state.collection_repo.get(collection_id)
        if not collection:
            raise HTTPException(status_code=404, detail="Collection not found")
        if await app.state.collection_repo.has_children(collection_id):
            raise HTTPException(
                status_code=409,
                detail="Cannot delete collection with child collections. Delete children first.",
            )
        if await app.state.collection_repo.has_favourites(collection_id):
            raise HTTPException(
                status_code=409,
                detail="Cannot delete collection with favourites. Remove favourites first.",
            )
        await app.state.collection_repo.delete(collection_id)
        return {"status": "deleted"}

    # --- Favourites ---

    @app.get("/api/favourites")
    async def list_favourites(collection_id: Optional[str] = Query(default=None)):
        favourites = await app.state.favourite_repo.list(collection_id=collection_id)
        return [f.model_dump(mode="json") for f in favourites]

    @app.post("/api/favourites")
    async def add_favourite(request: FavouriteCreate):
        asset = await app.state.asset_repo.get(request.asset_id)
        if not asset:
            raise HTTPException(status_code=404, detail="Asset not found")
        if request.collection_id:
            collection = await app.state.collection_repo.get(request.collection_id)
            if not collection:
                raise HTTPException(status_code=404, detail="Collection not found")
        try:
            favourite_id = await app.state.favourite_repo.add(
                asset_id=request.asset_id,
                collection_id=request.collection_id,
                name=request.name,
            )
        except Exception:
            raise HTTPException(
                status_code=409,
                detail="Asset is already in this collection",
            )
        return {"id": favourite_id, "status": "created"}

    @app.put("/api/favourites/{favourite_id}")
    async def rename_favourite(favourite_id: str, name: str = Query(...)):
        favourite = await app.state.favourite_repo.get(favourite_id)
        if not favourite:
            raise HTTPException(status_code=404, detail="Favourite not found")
        await app.state.db.execute(
            "UPDATE favourites SET name = ? WHERE id = ?", (name, favourite_id)
        )
        await app.state.db.commit()
        return {"status": "updated"}

    @app.delete("/api/favourites/{favourite_id}")
    async def remove_favourite(favourite_id: str):
        favourite = await app.state.favourite_repo.get(favourite_id)
        if not favourite:
            raise HTTPException(status_code=404, detail="Favourite not found")
        await app.state.favourite_repo.remove(favourite_id)
        return {"status": "deleted"}

    @app.post("/api/favourites/{favourite_id}/display")
    async def display_favourite(favourite_id: str):
        favourite = await app.state.favourite_repo.get(favourite_id)
        if not favourite:
            raise HTTPException(status_code=404, detail="Favourite not found")
        asset = await app.state.asset_repo.get(favourite.asset_id)
        if not asset or not asset.filename_processed:
            raise HTTPException(status_code=404, detail="Asset not found or not processed")
        await push_asset_to_display(app, asset.id)
        return {"status": "sent", "asset_id": asset.id}

    # --- Schedules ---

    @app.get("/api/schedules")
    async def list_schedules():
        schedules = await app.state.schedule_repo.list()
        return [s.model_dump(mode="json") for s in schedules]

    @app.post("/api/schedules")
    async def create_schedule(request: ScheduleCreate):
        # Validate preset exists
        preset = await app.state.preset_repo.get(request.preset_id)
        if not preset:
            raise HTTPException(
                status_code=400,
                detail=f"Preset '{request.preset_id}' not found",
            )
        # Validate cron expression
        if not croniter.is_valid(request.cron_expression):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid cron expression: '{request.cron_expression}'",
            )
        schedule_id = await app.state.schedule_repo.create(
            name=request.name,
            preset_id=request.preset_id,
            cron_expression=request.cron_expression,
        )
        # Compute initial next_run_at
        cron = croniter(request.cron_expression, datetime.now())
        next_run = cron.get_next(datetime)
        await app.state.schedule_repo.update_last_run(
            schedule_id, last_run_at=None, next_run_at=next_run.isoformat()
        )
        return {"id": schedule_id, "status": "created"}

    @app.put("/api/schedules/{schedule_id}")
    async def update_schedule(schedule_id: str, request: ScheduleUpdate):
        schedule = await app.state.schedule_repo.get(schedule_id)
        if not schedule:
            raise HTTPException(status_code=404, detail="Schedule not found")
        # Validate preset if being changed
        if request.preset_id is not None:
            preset = await app.state.preset_repo.get(request.preset_id)
            if not preset:
                raise HTTPException(
                    status_code=400,
                    detail=f"Preset '{request.preset_id}' not found",
                )
        # Validate cron if being changed
        if request.cron_expression is not None:
            if not croniter.is_valid(request.cron_expression):
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid cron expression: '{request.cron_expression}'",
                )
        await app.state.schedule_repo.update(
            schedule_id,
            name=request.name,
            preset_id=request.preset_id,
            cron_expression=request.cron_expression,
            is_enabled=request.is_enabled,
        )
        # Recompute next_run_at if cron changed or schedule re-enabled
        effective_cron = request.cron_expression or schedule.cron_expression
        if request.cron_expression is not None or request.is_enabled is True:
            cron = croniter(effective_cron, datetime.now())
            next_run = cron.get_next(datetime)
            await app.state.schedule_repo.update_last_run(
                schedule_id,
                last_run_at=schedule.last_run_at.isoformat() if schedule.last_run_at else None,
                next_run_at=next_run.isoformat(),
            )
        return {"status": "updated"}

    @app.delete("/api/schedules/{schedule_id}")
    async def delete_schedule(schedule_id: str):
        schedule = await app.state.schedule_repo.get(schedule_id)
        if not schedule:
            raise HTTPException(status_code=404, detail="Schedule not found")
        await app.state.schedule_repo.delete(schedule_id)
        return {"status": "deleted"}

    @app.post("/api/schedules/{schedule_id}/run")
    async def run_schedule(
        schedule_id: str, background_tasks: BackgroundTasks
    ):
        schedule = await app.state.schedule_repo.get(schedule_id)
        if not schedule:
            raise HTTPException(status_code=404, detail="Schedule not found")
        if app.state.update_lock.locked():
            raise HTTPException(status_code=409, detail="Update already in progress")
        background_tasks.add_task(perform_update, app, schedule.preset_id)
        return {
            "status": "started",
            "message": f"Schedule '{schedule.name}' triggered manually",
            "preset_id": schedule.preset_id,
        }

    return app


async def perform_update(
    app: FastAPI, preset_id: Optional[str] = None
) -> str:
    """Core update flow: fetch from content source -> ingest -> push."""
    async with app.state.update_lock:
        preset_repo: PresetRepository = app.state.preset_repo
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

            # 3. Determine processing mode
            process_mode = "color"
            if preset.image_config:
                process_mode = preset.image_config.get("process_mode", "color")

            # 4. Ingest through shared pipeline
            result = await ingest_asset(
                app,
                raw_path,
                source_type=preset.source_type,
                title=metadata.get("title"),
                source_id=metadata.get("source_id"),
                metadata_json=metadata.get("metadata_json"),
                process_mode=process_mode,
                check_duplicate=True,
                push_to_display=True,
            )

            if result.is_duplicate:
                logger.info(f"Reused existing asset: {result.asset_id}")
            elif result.pushed:
                logger.info(f"Update completed successfully (asset: {result.asset_id})")
            else:
                logger.warning(f"Update completed but display push failed (asset: {result.asset_id})")

            return result.asset_id

        except Exception as e:
            app.state.last_update_status = "failed"
            logger.error(f"Update failed: {e}", exc_info=True)
            raise
        finally:
            app.state.is_updating = False
            app.state.last_update = datetime.now()
            logger.info("=" * 60)
