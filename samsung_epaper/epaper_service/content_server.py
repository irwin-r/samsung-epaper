"""Content delivery routes — serves manifests and images to the Samsung display."""

import logging
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from .database import AssetRepository, HistoryRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/content", tags=["content"])

# These get set during app startup via set_dependencies()
_config = None
_asset_repo: AssetRepository | None = None
_history_repo: HistoryRepository | None = None
_assets_dir: Path | None = None


def set_dependencies(config, asset_repo, history_repo, assets_dir):
    global _config, _asset_repo, _history_repo, _assets_dir
    _config = config
    _asset_repo = asset_repo
    _history_repo = history_repo
    _assets_dir = assets_dir


def build_manifest(
    content_id: str,
    file_id: str,
    image_url: str,
    file_name: str,
    file_size: int,
    content_name: str = "ePaper Content",
) -> dict:
    return {
        "id": content_id,
        "program_id": "com.samsung.ios.ePaper",
        "deploy_type": "MOBILE",
        "version": 1,
        "name": content_name,
        "content_type": "ImageContent",
        "create_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "schedule": [
            {
                "start_date": "1970-01-01",
                "stop_date": "2999-12-31",
                "start_time": "00:00:00",
                "contents": [
                    {
                        "file_id": file_id,
                        "file_name": file_name,
                        "file_path": (
                            f"/home/owner/content/Downloads/vxtplayer/"
                            f"epaper/mobile/contents/{file_id}/{file_name}"
                        ),
                        "file_size": str(file_size),
                        "image_url": image_url,
                        "duration": 86400000,
                    }
                ],
            }
        ],
    }


@router.get("/{content_id}/manifest.json")
async def serve_manifest(content_id: str):
    entry = await _history_repo.get_by_content_id(content_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Content not found")

    asset = await _asset_repo.get(entry.asset_id)
    if not asset or not asset.filename_processed:
        raise HTTPException(status_code=404, detail="Asset not found")

    file_path = _assets_dir / asset.filename_processed
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Image file not found")

    base_url = _config.public_base_url.rstrip("/")
    image_url = (
        f"{base_url}/content/{content_id}/{entry.file_id}/{asset.filename_processed}"
    )

    manifest = build_manifest(
        content_id=content_id,
        file_id=entry.file_id,
        image_url=image_url,
        file_name=asset.filename_processed,
        file_size=file_path.stat().st_size,
        content_name=asset.title or "ePaper Content",
    )

    logger.info(f"Serving manifest for content_id={content_id}")
    return JSONResponse(manifest)


@router.get("/{content_id}/{file_id}/{filename}")
async def serve_image(content_id: str, file_id: str, filename: str):
    entry = await _history_repo.get_by_content_id(content_id)
    if not entry or entry.file_id != file_id:
        raise HTTPException(status_code=404, detail="Content not found")

    # Serve the asset's actual processed file, ignoring user-supplied filename
    asset = await _asset_repo.get(entry.asset_id)
    if not asset or not asset.filename_processed:
        raise HTTPException(status_code=404, detail="Asset not found")

    file_path = (_assets_dir / asset.filename_processed).resolve()
    if not file_path.is_relative_to(_assets_dir.resolve()):
        raise HTTPException(status_code=400, detail="Invalid path")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Image file not found")

    logger.info(f"Serving image: {asset.filename_processed} for content_id={content_id}")
    return FileResponse(file_path, media_type="image/png")
