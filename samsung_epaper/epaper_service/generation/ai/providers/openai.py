"""OpenAI image generation provider."""
import base64
import logging
import os
from pathlib import Path
from typing import Any

from ..base import ImageGenerationError, ImageProvider

logger = logging.getLogger(__name__)


class OpenAIProvider(ImageProvider):
    """Generates images using OpenAI's Responses API with image_generation tool."""

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

        self.model = model or os.getenv("OPENAI_IMAGE_MODEL", "gpt-4.1")
        self.client = openai.OpenAI(api_key=self.api_key, max_retries=3)

    def generate(
        self,
        input_image_path: str,
        output_path: str,
        prompt: str,
        output_size: str = "1024x1536",
        **provider_options: Any,
    ) -> str:
        logger.info(f"[OpenAI] Generating image from {input_image_path}")

        try:
            image_b64, mime_type = self._encode_image(input_image_path)
            prompt = self.adapt_prompt(prompt)

            fidelity = provider_options.get("fidelity", "high")

            response = self.client.responses.create(
                model=self.model,
                input=[{
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {"type": "input_image", "image_url": f"data:{mime_type};base64,{image_b64}"},
                    ],
                }],
                tools=[{
                    "type": "image_generation",
                    "input_fidelity": fidelity,
                    "size": output_size,
                }],
            )

            image_data = self._extract_image_from_response(response)
            Path(output_path).write_bytes(base64.b64decode(image_data))

            logger.info(f"[OpenAI] Successfully generated: {output_path}")
            return output_path

        except Exception as e:
            raise ImageGenerationError(f"OpenAI failed: {e}") from e

    def _extract_image_from_response(self, response) -> str:
        """Extract base64 image data from OpenAI response."""
        image_data: list[str] = []

        if hasattr(response, "output"):
            for output in response.output:
                if getattr(output, "type", None) == "image_generation_call":
                    image_data.append(output.result)

        if hasattr(response, "outputs"):
            for output in response.outputs:
                if getattr(output, "type", None) == "image_generation_call":
                    image_data.append(output.result)

        if not image_data:
            logger.error(f"No image data found. Response: {response}")
            raise ImageGenerationError("No image generation output found in response")

        return image_data[0]
