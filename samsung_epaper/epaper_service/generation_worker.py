"""Worker function that executes art generation jobs.

Called by the job queue runner for each submitted generation job.
Delegates to the art generator factory, wrapping sync calls in threads.
"""

import asyncio
import json
import logging
import random
from pathlib import Path

from fastapi import FastAPI

from .asset_pipeline import ingest_asset
from .services.jobs import GenerationJob

logger = logging.getLogger(__name__)


async def execute_generation(job: GenerationJob, app: FastAPI) -> str:
    """Run a single art generation job and return the resulting asset_id.

    This is the function passed to JobQueue as the worker_fn.
    """
    from .generation.art.factory import create_art_generator, get_available_art_types

    art_type = job.art_type or "random"
    if art_type == "random":
        available = get_available_art_types()
        art_type = random.choice(available)
        logger.info(f"Random art type selected: {art_type}")

    photo_path = Path(job.photo_path) if job.photo_path else None
    if not photo_path or not photo_path.exists():
        raise ValueError(f"Input photo not found: {job.photo_path}")

    assets_dir: Path = app.state.assets_dir
    output_dir = assets_dir / "cache"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / f"{job.id}_generated.png"

    # Create the generator and run in a thread (generators are synchronous)
    config = None  # TODO: pass art-specific config if needed
    generator = create_art_generator(art_type, config)

    kwargs = {}
    if job.variant:
        kwargs["variant"] = job.variant

    logger.info(f"Generating {art_type} art from {photo_path.name}")

    generated_path = await asyncio.to_thread(
        generator.generate,
        input_images=[str(photo_path)],
        output_path=str(output_path),
        **kwargs,
    )

    # Ingest the generated image through the shared pipeline
    try:
        result = await ingest_asset(
            app,
            Path(generated_path),
            source_type="ai_art",
            title=f"AI Art: {art_type}",
            source_id=art_type,
            metadata_json=json.dumps({"art_type": art_type, "variant": job.variant or ""}),
            check_duplicate=False,  # AI output is always unique
            push_to_display=True,
            persist_original=False,  # Don't keep the generated intermediate
        )
        return result.asset_id
    finally:
        # Clean up the input photo (visitor privacy) even on failure
        photo_path.unlink(missing_ok=True)


def make_worker(app: FastAPI):
    """Return a worker function bound to the given app instance."""
    async def worker(job: GenerationJob) -> str:
        return await execute_generation(job, app)
    return worker
