"""API routes for art generation and front-page fetching.

Mounted at /api/generate/* in the main app.
"""

import asyncio
import hmac
import logging
import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile

from .asset_pipeline import ingest_asset
from .services.jobs import GenerationJob, JobQueue, JobStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/generate", tags=["generate"])

# Populated by set_generation_deps() during lifespan
_app_ref = None
_job_queue: Optional[JobQueue] = None
_auth_token: Optional[str] = None


def set_generation_deps(app, job_queue: JobQueue, auth_token: Optional[str] = None):
    global _app_ref, _job_queue, _auth_token
    _app_ref = app
    _job_queue = job_queue
    _auth_token = auth_token


def _check_auth(authorization: Optional[str] = Header(default=None)):
    """Bearer token auth for generation endpoints."""
    if not _auth_token:
        return  # Auth not configured, allow all
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(token, _auth_token):
        raise HTTPException(status_code=401, detail="Invalid token")


# --- Types / metadata ---

@router.get("/types")
async def get_generation_types():
    """Return available art types and front-page publications for the UI."""
    from .generation.art.factory import get_all_art_generators_info
    from .sources.frontpages import PUBLICATIONS

    ai_art = []
    for info in get_all_art_generators_info():
        ai_art.append({
            "key": info["type"],
            "name": info.get("name", info["type"]),
            "description": info.get("description", ""),
            "requires_photo": True,
            "variants": info.get("variants", []),
        })

    frontpage = [
        {"key": k, "name": v["name"], "requires_photo": False}
        for k, v in PUBLICATIONS.items()
    ]

    return {"ai_art": ai_art, "frontpage": frontpage}


# --- Art generation (async, photo-driven) ---

@router.post("/art", status_code=202, dependencies=[Depends(_check_auth)])
async def generate_art(
    photo: UploadFile = File(...),
    art_type: str = Form(default="random"),
    variant: Optional[str] = Form(default=None),
    priority: int = Form(default=0),
):
    """Submit an art generation job. Returns 202 with job_id for polling."""
    if _job_queue is None:
        raise HTTPException(status_code=503, detail="Job queue not initialized")

    # Validate file size (10MB max)
    MAX_SIZE = 10 * 1024 * 1024
    # Quick reject via Content-Length if available
    if photo.size and photo.size > MAX_SIZE:
        raise HTTPException(status_code=413, detail="Photo must be under 10MB")
    content = await photo.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(status_code=413, detail="Photo must be under 10MB")

    # Validate content type
    ct = photo.content_type or ""
    if not ct.startswith("image/"):
        raise HTTPException(status_code=415, detail="File must be an image")

    # Save photo to cache
    assets_dir: Path = _app_ref.state.assets_dir
    cache_dir = assets_dir / "cache"
    cache_dir.mkdir(exist_ok=True)
    tmp_name = f"{uuid.uuid4()}_input.jpg"
    photo_path = cache_dir / tmp_name
    await asyncio.to_thread(photo_path.write_bytes, content)

    # Resize large photos before queuing (save memory during generation)
    try:
        from PIL import Image
        img = await asyncio.to_thread(Image.open, photo_path)
        max_dim = 1536
        if max(img.width, img.height) > max_dim:
            img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
            await asyncio.to_thread(img.save, photo_path, format="JPEG", quality=90)
            logger.info(f"Resized input photo to {img.width}x{img.height}")
    except Exception:
        pass  # If resize fails, proceed with original

    job = await _job_queue.submit(
        source_type="ai_art",
        art_type=art_type,
        variant=variant,
        photo_path=str(photo_path),
        priority=priority,
    )

    return {
        "job_id": job.id,
        "status": job.status,
        "art_type": art_type,
    }


# --- Front page fetch (synchronous, no photo) ---

@router.post("/frontpage", dependencies=[Depends(_check_auth)])
async def generate_frontpage(
    publication: str = Form(default="smh"),
):
    """Fetch a newspaper front page and push to display."""
    from .sources.frontpages import PUBLICATIONS

    if publication not in PUBLICATIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown publication '{publication}'. Available: {list(PUBLICATIONS.keys())}",
        )

    pub = PUBLICATIONS[publication]

    from .sources import get_source
    source = get_source("frontpages")

    assets_dir: Path = _app_ref.state.assets_dir
    cache_dir = assets_dir / "cache"
    cache_dir.mkdir(exist_ok=True)

    raw_path, metadata = await source.fetch(
        {"url": pub["url"], "image_pattern": pub.get("pattern", "")},
        cache_dir,
    )

    result = await ingest_asset(
        _app_ref,
        raw_path,
        source_type="frontpages",
        title=pub["name"],
        source_id=pub["url"],
        check_duplicate=True,
        push_to_display=True,
    )

    return {
        "asset_id": result.asset_id,
        "title": pub["name"],
        "displayed": result.pushed,
        "duplicate": result.is_duplicate,
    }


# --- Job status polling ---

@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Poll for generation job status."""
    if _job_queue is None:
        raise HTTPException(status_code=503, detail="Job queue not initialized")

    job = await _job_queue.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return job.to_dict()


@router.get("/jobs")
async def list_jobs(limit: int = 20):
    """List recent generation jobs."""
    if _job_queue is None:
        raise HTTPException(status_code=503, detail="Job queue not initialized")

    jobs = await _job_queue.list_recent(limit=limit)
    return [j.to_dict() for j in jobs]
