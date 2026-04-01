"""Shared asset ingestion pipeline used by all content flows.

Every path that creates a displayable asset (preset updates, uploads, URL
fetches, and future AI generation) funnels through ``ingest_asset`` so that
hashing, dedup, processing, thumbnail generation, DB writes, and display
pushes happen in exactly one place.
"""

import asyncio
import logging
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI

from .database import AssetRepository, HistoryRepository
from .image_processor import ImageProcessor
from .mdc_client import MDCClient
from .config import AppConfig
from .models import ImageInfo

logger = logging.getLogger(__name__)

_display_lock: asyncio.Lock | None = None


def set_display_lock(lock: asyncio.Lock) -> None:
    global _display_lock
    _display_lock = lock


class IngestResult:
    """Return value from ingest_asset."""

    __slots__ = ("asset_id", "is_duplicate", "pushed", "width", "height")

    def __init__(
        self,
        asset_id: str,
        is_duplicate: bool = False,
        pushed: bool = False,
        width: int = 0,
        height: int = 0,
    ):
        self.asset_id = asset_id
        self.is_duplicate = is_duplicate
        self.pushed = pushed
        self.width = width
        self.height = height


async def ingest_asset(
    app: FastAPI,
    raw_image_path: Path,
    source_type: str,
    *,
    title: Optional[str] = None,
    source_id: Optional[str] = None,
    metadata_json: Optional[str] = None,
    process_mode: str = "color",
    check_duplicate: bool = True,
    push_to_display: bool = True,
    persist_original: bool = True,
) -> IngestResult:
    """Hash → dedup → store original → process → thumbnail → DB → push.

    Parameters
    ----------
    app:
        FastAPI instance carrying ``state`` with repos, processor, etc.
    raw_image_path:
        Path to the raw downloaded/uploaded/generated image.
    source_type:
        E.g. ``"frontpages"``, ``"upload"``, ``"url"``, ``"ai_art"``.
    title:
        Human-readable title stored in the asset record.
    source_id:
        Optional source identifier (URL, preset name, etc.).
    metadata_json:
        Optional JSON string with extra metadata.
    process_mode:
        Pillow processing mode — ``"color"``, ``"grayscale"``, or ``"bw"``.
    check_duplicate:
        If *True*, skip ingestion when an asset with the same SHA-256
        already exists and push that asset instead.
    push_to_display:
        If *True*, push the (possibly deduplicated) asset to the Samsung
        display via MDC after processing.
    persist_original:
        If *True*, move the raw image into ``originals/``.  Set to
        *False* for ephemeral inputs (e.g. visitor photos) where only the
        processed output should be kept.

    Returns
    -------
    IngestResult
        Contains ``asset_id``, ``is_duplicate``, ``pushed``, ``width``,
        ``height``.
    """
    asset_repo: AssetRepository = app.state.asset_repo
    processor: ImageProcessor = app.state.processor
    assets_dir: Path = app.state.assets_dir

    # 1. Hash the raw image
    image_hash = await processor.compute_hash(raw_image_path)

    # 2. Duplicate check
    if check_duplicate:
        existing = await asset_repo.get_by_hash(image_hash)
        if existing and existing.filename_processed:
            logger.info(f"Duplicate image detected (hash: {image_hash})")
            raw_image_path.unlink(missing_ok=True)
            pushed = False
            if push_to_display:
                pushed = await push_asset_to_display(app, existing.id)
                if pushed:
                    app.state.current_asset_id = existing.id
                    app.state.last_update_status = "success"
                app.state.last_update = datetime.now()
            return IngestResult(
                asset_id=existing.id,
                is_duplicate=True,
                pushed=pushed,
                width=existing.width or 0,
                height=existing.height or 0,
            )

    # 3. Create asset record
    asset_id = await asset_repo.create(
        source_type=source_type,
        filename_original=raw_image_path.name,
        source_id=source_id,
        title=title,
        metadata_json=metadata_json,
        sha256=image_hash,
    )

    # Steps 4-8 are wrapped in try/except to clean up on failure
    processed_name = f"{asset_id}_processed.png"
    processed_path = assets_dir / "processed" / processed_name
    thumb_name = f"{asset_id}_thumb.jpg"
    thumb_path = assets_dir / "thumbnails" / thumb_name

    try:
        # 4. Store original
        if persist_original:
            original_dest = assets_dir / "originals" / f"{asset_id}_{raw_image_path.name}"
            await asyncio.to_thread(shutil.move, str(raw_image_path), str(original_dest))
            # Update the DB with the actual stored filename
            await asset_repo.update_original_filename(asset_id, original_dest.name)
            input_for_processing = original_dest
        else:
            input_for_processing = raw_image_path

        # 5. Process image for display viewport
        info: ImageInfo = await processor.process(
            input_for_processing, processed_path, mode=process_mode
        )

        # 6. Generate thumbnail
        await processor.generate_thumbnail(processed_path, thumb_path)

        # 7. Update asset record with processed file info
        await asset_repo.update_processed(
            asset_id=asset_id,
            filename_processed=processed_name,
            filename_thumbnail=thumb_name,
            width=info.width,
            height=info.height,
            file_size=info.file_size,
        )

        # 8. Clean up ephemeral original
        if not persist_original and raw_image_path.exists():
            raw_image_path.unlink(missing_ok=True)
    except Exception:
        # Cleanup partial files and DB record
        for path in [processed_path, thumb_path]:
            if path.exists():
                path.unlink(missing_ok=True)
        await asset_repo.delete(asset_id)
        raise

    # 9. Push to display
    pushed = False
    if push_to_display:
        pushed = await push_asset_to_display(app, asset_id)
        if pushed:
            app.state.current_asset_id = asset_id
            app.state.last_update_status = "success"
        else:
            app.state.last_update_status = "failed"
        app.state.last_update = datetime.now()

    return IngestResult(
        asset_id=asset_id,
        is_duplicate=False,
        pushed=pushed,
        width=info.width,
        height=info.height,
    )


async def push_asset_to_display(app: FastAPI, asset_id: str) -> bool:
    """Push a processed asset to the Samsung display via MDC."""
    config: AppConfig = app.state.config
    asset_repo: AssetRepository = app.state.asset_repo
    history_repo: HistoryRepository = app.state.history_repo
    mdc: MDCClient = app.state.mdc

    asset = await asset_repo.get(asset_id)
    if not asset or not asset.filename_processed:
        raise Exception(f"Asset {asset_id} not found or not processed")

    content_id = str(uuid.uuid4())
    file_id = str(uuid.uuid4())

    async def _do_push() -> bool:
        history_id = await history_repo.create(
            asset_id=asset_id, content_id=content_id, file_id=file_id
        )

        base_url = config.public_base_url.rstrip("/")
        manifest_url = f"{base_url}/content/{content_id}/manifest.json"

        logger.info(f"Pushing to display: {manifest_url}")
        try:
            success = await mdc.send_content(manifest_url)
        except Exception as e:
            logger.error(f"MDC send_content raised: {e}", exc_info=True)
            await history_repo.update_status(history_id, "failed", error_message=str(e))
            return False

        status = "sent" if success else "failed"
        await history_repo.update_status(
            history_id, status, error_message=None if success else "MDC send failed"
        )

        if success:
            app.state.current_asset_id = asset_id

        return success

    if _display_lock is not None:
        async with _display_lock:
            return await _do_push()
    return await _do_push()
