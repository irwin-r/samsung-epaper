"""xAI Grok image generation provider."""
import base64
import logging
import os
from pathlib import Path
from typing import Any

from ..base import ImageGenerationError, ImageProvider

logger = logging.getLogger(__name__)


class GrokProvider(ImageProvider):
    """Generates images using xAI's Grok API (OpenAI-compatible SDK)."""

    provider_name = "grok"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        try:
            import openai
        except ImportError as e:
            raise ImportError("openai package required: pip install openai") from e

        self.api_key = api_key or os.getenv("XAI_API_KEY")
        if not self.api_key:
            raise ImageGenerationError(
                "xAI API key not found. Set XAI_API_KEY environment variable."
            )

        self.model = model or os.getenv("GROK_IMAGE_MODEL", "grok-imagine-image")
        self.client = openai.OpenAI(
            api_key=self.api_key,
            base_url="https://api.x.ai/v1",
            max_retries=3,
        )

    def generate(
        self,
        input_image_path: str,
        output_path: str,
        prompt: str,
        output_size: str = "1024x1536",
        **provider_options: Any,
    ) -> str:
        logger.info(f"[Grok] Generating image from {input_image_path}")

        try:
            image_b64, mime_type = self._encode_image(input_image_path)
            prompt = self.adapt_prompt(prompt)

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{image_b64}"},
                        },
                    ],
                }],
            )

            # Extract image from response
            for choice in response.choices:
                message = choice.message
                if hasattr(message, "content") and message.content:
                    # Grok returns base64 image in content
                    for block in (message.content if isinstance(message.content, list) else [message.content]):
                        if isinstance(block, str):
                            continue
                        if hasattr(block, "type") and block.type == "image_url":
                            image_data = block.image_url.url.split(",", 1)[1]
                            Path(output_path).write_bytes(base64.b64decode(image_data))
                            logger.info(f"[Grok] Successfully generated: {output_path}")
                            return output_path

            raise ImageGenerationError("No image found in Grok response")

        except ImageGenerationError:
            raise
        except Exception as e:
            raise ImageGenerationError(f"Grok failed: {e}") from e
