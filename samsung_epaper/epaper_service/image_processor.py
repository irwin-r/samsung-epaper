"""Image processing with Pillow, run in thread pool to avoid blocking."""

import asyncio
import hashlib
import logging
from pathlib import Path

from PIL import Image, ImageOps

from .models import ImageInfo

logger = logging.getLogger(__name__)


class ImageProcessor:
    def __init__(self, viewport_width: int = 1440, viewport_height: int = 2560):
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height

    @staticmethod
    async def compute_hash(file_path: Path) -> str:
        """Return the SHA-256 hex digest of a file without blocking the event loop."""

        def _hash_sync() -> str:
            h = hashlib.sha256()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
            return h.hexdigest()

        return await asyncio.to_thread(_hash_sync)

    async def process(
        self,
        input_path: Path,
        output_path: Path,
        mode: str = "color",
    ) -> ImageInfo:
        return await asyncio.to_thread(
            self._process_sync, input_path, output_path, mode
        )

    def _process_sync(
        self, input_path: Path, output_path: Path, mode: str
    ) -> ImageInfo:
        img = Image.open(input_path)
        logger.info(f"Original size: {img.width}x{img.height}")

        canvas = ImageOps.fit(
            img,
            (self.viewport_width, self.viewport_height),
            Image.Resampling.LANCZOS,
        )

        if mode == "grayscale":
            canvas = canvas.convert("L")
        elif mode == "bw":
            canvas = canvas.convert("1", dither=Image.FLOYDSTEINBERG)

        canvas.save(output_path, format="PNG")
        file_size = output_path.stat().st_size
        logger.info(
            f"Processed: {canvas.width}x{canvas.height}, "
            f"{file_size:,} bytes, mode={mode}"
        )
        return ImageInfo(
            width=canvas.width, height=canvas.height, file_size=file_size
        )

    async def generate_thumbnail(
        self,
        input_path: Path,
        output_path: Path,
        max_size: int = 300,
    ) -> Path:
        return await asyncio.to_thread(
            self._thumbnail_sync, input_path, output_path, max_size
        )

    def _thumbnail_sync(
        self, input_path: Path, output_path: Path, max_size: int
    ) -> Path:
        img = Image.open(input_path)
        img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        img.save(output_path, format="JPEG", quality=80)
        return output_path
