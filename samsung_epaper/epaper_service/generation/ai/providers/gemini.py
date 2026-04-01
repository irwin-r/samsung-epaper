"""Google Gemini image generation provider."""
import base64
import logging
import os
from pathlib import Path
from typing import Any

from ..base import ImageGenerationError, ImageProvider

logger = logging.getLogger(__name__)


class GeminiProvider(ImageProvider):
    """Generates images using Google's Gemini API."""

    provider_name = "gemini"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ImageGenerationError(
                "Gemini API key not found. Set GEMINI_API_KEY environment variable."
            )

        self.model = model or os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
        self._client = None

    @property
    def client(self):
        if self._client is None:
            try:
                from google import genai
            except ImportError as e:
                raise ImportError("google-genai package required: pip install google-genai") from e

            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def adapt_prompt(self, prompt: str) -> str:
        return (
            f"{prompt}\n"
            "Use the supplied input image as the identity reference for the subject. "
            "Preserve their facial features accurately."
        )

    def generate(
        self,
        input_image_path: str,
        output_path: str,
        prompt: str,
        output_size: str = "1024x1536",
        **provider_options: Any,
    ) -> str:
        from google.genai import types

        logger.info(f"[Gemini] Generating image from {input_image_path}")

        try:
            prompt = self.adapt_prompt(prompt)

            # Read input image
            image_bytes = Path(input_image_path).read_bytes()
            import mimetypes as mt
            mime_type = mt.guess_type(input_image_path)[0] or "image/jpeg"

            response = self.client.models.generate_content(
                model=self.model,
                contents=[
                    types.Part.from_text(text=prompt),
                    types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                ],
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE", "TEXT"],
                ),
            )

            # Extract generated image from response
            for part in response.candidates[0].content.parts:
                if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                    Path(output_path).write_bytes(part.inline_data.data)
                    logger.info(f"[Gemini] Successfully generated: {output_path}")
                    return output_path

            raise ImageGenerationError("No image found in Gemini response")

        except ImageGenerationError:
            raise
        except Exception as e:
            raise ImageGenerationError(f"Gemini failed: {e}") from e
