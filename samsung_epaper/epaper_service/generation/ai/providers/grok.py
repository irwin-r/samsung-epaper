"""xAI Grok Imagine image generation provider."""
import base64
import logging
import os
from pathlib import Path
from typing import Any

from ..base import ImageGenerationError, ImageProvider

logger = logging.getLogger(__name__)

_EDITS_URL = "https://api.x.ai/v1/images/edits"
_ASPECT_RATIOS = ["1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9"]


def _aspect_ratio_for(output_size: str) -> str:
    """Pick the supported aspect ratio closest to a WxH size string."""
    width, height = (int(n) for n in output_size.lower().split("x"))
    target = width / height
    return min(_ASPECT_RATIOS, key=lambda r: abs(int(r.split(":")[0]) / int(r.split(":")[1]) - target))


class GrokProvider(ImageProvider):
    """Edits the input photo with xAI's /v1/images/edits endpoint."""

    provider_name = "grok"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        try:
            import httpx
        except ImportError as e:
            raise ImportError("httpx package required: pip install httpx") from e

        self.api_key = api_key or os.getenv("XAI_API_KEY")
        if not self.api_key:
            raise ImageGenerationError(
                "xAI API key not found. Set XAI_API_KEY environment variable."
            )

        self.model = model or os.getenv("GROK_IMAGE_MODEL", "grok-imagine-image-2.0")
        self.quality = os.getenv("GROK_IMAGE_QUALITY", "medium")
        self.client = httpx.Client(
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=300,
            transport=httpx.HTTPTransport(retries=3),
        )

    def generate(
        self,
        input_image_path: str,
        output_path: str,
        prompt: str,
        output_size: str = "1024x1536",
        **provider_options: Any,
    ) -> str:
        logger.info(f"[Grok] Generating image from {input_image_path} with {self.model}")

        try:
            image_b64, mime_type = self._encode_image(input_image_path)
            prompt = self.adapt_prompt(prompt)

            response = self.client.post(_EDITS_URL, json={
                "model": self.model,
                "prompt": prompt,
                "image": {"url": f"data:{mime_type};base64,{image_b64}", "type": "image_url"},
                "aspect_ratio": _aspect_ratio_for(output_size),
                "resolution": "2k",
                "quality": self.quality,
                "response_format": "b64_json",
            })
            if response.status_code != 200:
                raise ImageGenerationError(
                    f"Grok failed: HTTP {response.status_code}: {response.text[:500]}"
                )

            data = response.json().get("data") or []
            if not data or not data[0].get("b64_json"):
                raise ImageGenerationError("No image data in Grok response")

            Path(output_path).write_bytes(base64.b64decode(data[0]["b64_json"]))
            logger.info(f"[Grok] Successfully generated: {output_path}")
            return output_path

        except ImageGenerationError:
            raise
        except Exception as e:
            raise ImageGenerationError(f"Grok failed: {e}") from e
