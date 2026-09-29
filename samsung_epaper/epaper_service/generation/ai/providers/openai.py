"""OpenAI image generation provider."""
import base64
import logging
import os
from pathlib import Path
from typing import Any

from ..base import ImageGenerationError, ImageProvider

logger = logging.getLogger(__name__)


class OpenAIProvider(ImageProvider):
    """Generates images by editing the input photo with OpenAI's Images API."""

    provider_name = "openai"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        try:
            import openai
        except ImportError as e:
            raise ImportError("openai package required: pip install openai") from e

        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ImageGenerationError(
                "OpenAI API key not found. Set OPENAI_API_KEY environment variable."
            )

        self.model = model or os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2.5-flare")
        self.quality = os.getenv("OPENAI_IMAGE_QUALITY", "high")
        self.client = openai.OpenAI(api_key=self.api_key, max_retries=3, timeout=300)

    def generate(
        self,
        input_image_path: str,
        output_path: str,
        prompt: str,
        output_size: str = "1024x1536",
        **provider_options: Any,
    ) -> str:
        logger.info(f"[OpenAI] Generating image from {input_image_path} with {self.model}")

        try:
            prompt = self.adapt_prompt(prompt)

            with open(input_image_path, "rb") as image_file:
                response = self.client.images.edit(
                    model=self.model,
                    image=image_file,
                    prompt=prompt,
                    size=output_size,
                    quality=self.quality,
                    # Parody styles (arrest, wanted) trip the default filter
                    extra_body={"moderation": "low"},
                )

            if not response.data or not response.data[0].b64_json:
                raise ImageGenerationError("No image data in OpenAI response")

            Path(output_path).write_bytes(base64.b64decode(response.data[0].b64_json))

            logger.info(f"[OpenAI] Successfully generated: {output_path}")
            return output_path

        except ImageGenerationError:
            raise
        except Exception as e:
            raise ImageGenerationError(f"OpenAI failed: {e}") from e
