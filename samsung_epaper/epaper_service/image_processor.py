"""Image processing with Pillow, run in thread pool to avoid blocking."""

import asyncio
import hashlib
import logging
from collections import Counter
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

        if mode == "contain":
            canvas = self._contain_with_border_color(img)
        else:
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

    def _contain_with_border_color(self, img: Image.Image) -> Image.Image:
        """Resize to fit viewport without cropping, fill margins with the
        dominant border color detected from the image edges."""
        bg = self._detect_border_color(img)
        logger.info(f"Detected border color: {bg}")

        # Resize to fit within viewport, preserving aspect ratio
        contained = ImageOps.contain(
            img,
            (self.viewport_width, self.viewport_height),
            Image.Resampling.LANCZOS,
        )

        # Create canvas with detected background color and center the image
        canvas = Image.new("RGB", (self.viewport_width, self.viewport_height), bg)
        x = (self.viewport_width - contained.width) // 2
        y = (self.viewport_height - contained.height) // 2
        canvas.paste(contained, (x, y))
        return canvas

    @staticmethod
    def _detect_border_color(img: Image.Image) -> tuple[int, int, int]:
        """Sample pixels along all four edges, find the dominant color bucket,
        then average the actual pixels in that bucket for precision."""
        rgb = img.convert("RGB")
        w, h = rgb.size
        pixels = []

        # Sample edges — a few rows/cols deep to avoid single-pixel artifacts
        depth = min(3, w // 10, h // 10)
        for d in range(depth):
            for x in range(0, w, 2):
                pixels.append(rgb.getpixel((x, d)))            # top rows
                pixels.append(rgb.getpixel((x, h - 1 - d)))    # bottom rows
            for y in range(0, h, 2):
                pixels.append(rgb.getpixel((d, y)))             # left cols
                pixels.append(rgb.getpixel((w - 1 - d, y)))     # right cols

        # Quantize into buckets of 16 to group similar shades
        def bucket(c):
            return ((c + 8) // 16) * 16

        bucketed = {}
        for r, g, b in pixels:
            key = (bucket(r), bucket(g), bucket(b))
            bucketed.setdefault(key, []).append((r, g, b))

        # Find the largest bucket
        dominant_key = max(bucketed, key=lambda k: len(bucketed[k]))
        members = bucketed[dominant_key]

        # Average the actual pixel values in the winning bucket
        avg_r = round(sum(p[0] for p in members) / len(members))
        avg_g = round(sum(p[1] for p in members) / len(members))
        avg_b = round(sum(p[2] for p in members) / len(members))

        # Snap near-white to pure white (avoids visible off-white margins)
        if avg_r >= 245 and avg_g >= 245 and avg_b >= 245:
            return (255, 255, 255)

        return (avg_r, avg_g, avg_b)

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
