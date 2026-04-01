"""Base image provider abstraction."""
import base64
import logging
import mimetypes
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from .prompts import build_classical_prompt, get_arrest_prompt

logger = logging.getLogger(__name__)


class ImageGenerationError(Exception):
    """Custom exception for image generation errors."""
    pass


class ImageProvider(ABC):
    """Abstract base class for image generation providers."""

    provider_name: str = "base"

    @property
    def is_available(self) -> bool:
        """Whether this provider is configured and ready."""
        return True

    @abstractmethod
    def generate(
        self,
        input_image_path: str,
        output_path: str,
        prompt: str,
        output_size: str = "1024x1536",
        **provider_options: Any,
    ) -> str:
        """Generate an image from input image + prompt. Returns output path."""
        ...

    def adapt_prompt(self, prompt: str) -> str:
        """Override to modify prompts for provider-specific formatting."""
        return prompt

    def _encode_image(self, image_path: str) -> tuple[str, str]:
        """Encode image to base64 and detect MIME type."""
        try:
            raw_bytes = Path(image_path).read_bytes()
            mime_type = mimetypes.guess_type(image_path)[0] or "image/jpeg"
            return base64.b64encode(raw_bytes).decode("utf-8"), mime_type
        except Exception as e:
            raise ImageGenerationError(f"Failed to encode image {image_path}: {e}") from e

    # --- Convenience methods (art generators call these) ---

    def generate_arrest_image(
        self,
        input_image_path: str,
        output_path: str,
        custom_prompt: str | None = None,
        output_size: str = "1024x1536",
    ) -> str:
        """Generate an arrest photo from input image."""
        prompt = custom_prompt if custom_prompt else get_arrest_prompt()
        return self.generate(input_image_path, output_path, prompt, output_size)

    def generate_classical_juxtaposition(
        self,
        input_image_path: str,
        output_path: str,
        prompt: str,
        output_size: str = "1024x1536",
    ) -> str:
        """Generate a classical art juxtaposition from input image."""
        full_prompt = build_classical_prompt(prompt)
        return self.generate(input_image_path, output_path, full_prompt, output_size)
