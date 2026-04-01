"""
Marble museum bust generator.
"""
import logging
from typing import Any, Optional

from ..ai.factory import create_image_generator
from ..ai.prompts import EPAPER_SUFFIX, IDENTITY_ANCHOR
from .base import ArtGenerationError, ArtGenerator, ArtGeneratorConfig

logger = logging.getLogger(__name__)


class MarbleBustGenerator(ArtGenerator):
    """Generates marble museum bust art from portrait photos."""

    ART_TYPE_NAME = "Marble Museum Bust"
    ART_TYPE_DESCRIPTION = "Transforms portraits into finely carved white marble museum busts with dramatic gallery lighting"

    def __init__(self, config: Optional[ArtGeneratorConfig] = None):
        """Initialize the marble bust generator."""
        super().__init__(config)

        # Try to initialize AI generator
        try:
            self.ai_generator = create_image_generator()
            self.ai_available = True
        except Exception as e:
            logger.warning(f"AI generation not available: {e}")
            self.ai_generator = None
            self.ai_available = False

    @property
    def name(self) -> str:
        """Return the name of this art generator."""
        return self.ART_TYPE_NAME

    @property
    def description(self) -> str:
        """Return a description of what this art generator creates."""
        return self.ART_TYPE_DESCRIPTION

    def get_required_resources(self) -> dict[str, Any]:
        """Get the resources required by this generator."""
        return {
            "openai_api": "OpenAI API key for AI generation (required)"
        }

    def generate(
        self,
        input_images: list[str],
        output_path: str,
        **kwargs
    ) -> str:
        """
        Generate a marble bust from input images.

        Args:
            input_images: List of paths to input images (uses first image)
            output_path: Path where the generated art should be saved
            **kwargs: Additional parameters

        Returns:
            Path to the generated artwork
        """
        if not self.ai_available:
            raise ArtGenerationError("AI not available")

        if not input_images:
            raise ArtGenerationError("No input images provided")

        if not self.validate_inputs(input_images):
            raise ArtGenerationError("One or more input images not found")

        source = input_images[0]

        prompt = (
            f"{IDENTITY_ANCHOR} Transform this person into a finely carved white marble "
            "museum bust, photographed like a gallery masterpiece. Realistic stone texture "
            "with subtle chisel marks and precise sculptural form while keeping the actual "
            "likeness of the person. Chest-up on a simple classical pedestal against a dark "
            "museum background. Dramatic side lighting creating strong shadows and crisp "
            "highlights across the marble surface. Noble, timeless, and slightly humorous "
            "because obviously this modern person has been immortalized as a classical "
            f"sculpture. {EPAPER_SUFFIX}"
        )

        logger.info("Generating marble museum bust...")

        try:
            return self.ai_generator.generate_arrest_image(
                source, output_path, prompt
            )
        except Exception as e:
            raise ArtGenerationError(f"Failed to generate marble bust: {e}")

    def get_variants(self) -> list[dict[str, Any]]:
        """Return available variants."""
        return [{"variant": "default", "display_name": "Marble Museum Bust", "params": {}}]
