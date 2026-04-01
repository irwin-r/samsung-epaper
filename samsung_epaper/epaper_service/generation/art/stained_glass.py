"""
Stained glass window generator.
"""
import logging
import random
from typing import Any, Optional

from ..ai.factory import create_image_generator
from ..ai.prompts import EPAPER_SUFFIX, IDENTITY_ANCHOR
from .base import ArtGenerationError, ArtGenerator, ArtGeneratorConfig

logger = logging.getLogger(__name__)


# Stained glass style variations
STAINED_GLASS_STYLES = [
    {
        "name": "Cathedral Saint",
        "prompt": (
            f"{IDENTITY_ANCHOR} Create a Gothic cathedral stained glass window portrait in "
            "a tall lancet shape. Follow medieval stained glass tradition with bold black lead "
            "lines (cames) separating each piece of colored glass. The face is painted on a "
            "single piece of 'glass' with fine grisaille detail — delicate painted lines for "
            "features. Flowing robes in deep ruby red, sapphire blue, and emerald green glass. "
            "A golden halo radiates behind the head. An ornate Gothic architectural frame with "
            "trefoil arch and pinnacles surrounds the figure. Backlit luminous quality as if "
            f"sunlight streams through from behind. {EPAPER_SUFFIX}"
        ),
    },
    {
        "name": "Rose Window",
        "prompt": (
            f"{IDENTITY_ANCHOR} Create a Gothic rose window design centered on the face. "
            "Circular mandala composition with the portrait at the center medallion, "
            "radiating petals of colored glass with small symbolic scenes filling each petal. "
            "Deep jewel tones — ruby, sapphire, emerald, amethyst. Thick black lead lines "
            "creating a bold graphic pattern throughout. Gothic tracery and quatrefoil motifs "
            "in the surrounding stonework. The entire rose window fits within a tall pointed "
            "arch frame. Luminous backlit quality with rich saturated color. Cathedral "
            f"grandeur and medieval craftsmanship. {EPAPER_SUFFIX}"
        ),
    },
    {
        "name": "Modern Stained Glass",
        "prompt": (
            f"{IDENTITY_ANCHOR} Create a modern Art Deco stained glass portrait. Geometric "
            "rather than Gothic — angular facets, sharp straight lines, Cubist influence. The "
            "face is fragmented across multiple geometric glass planes but remains clearly "
            "recognizable. Bold primary colors — red, blue, yellow — with black zinc came "
            "outlines defining each sharp-edged piece. Sunburst and chevron patterns radiate "
            "outward. Frank Lloyd Wright geometric glass aesthetic — clean, architectural, "
            "dramatic. Strong graphic impact with modern sensibility rather than medieval "
            f"tradition. {EPAPER_SUFFIX}"
        ),
    },
]


class StainedGlassGenerator(ArtGenerator):
    """Generates stained glass window art from portrait photos."""

    ART_TYPE_NAME = "Stained Glass Window"
    ART_TYPE_DESCRIPTION = "Creates stained glass window portraits in Gothic cathedral, rose window, and modern geometric styles"

    def __init__(self, config: Optional[ArtGeneratorConfig] = None):
        """Initialize the stained glass generator."""
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
        variant_name: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Generate stained glass window art from input images.

        Args:
            input_images: List of paths to input images (uses first image)
            output_path: Path where the generated art should be saved
            variant_name: Specific stained glass style to use (random if None)
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

        if variant_name:
            variant = next(
                (v for v in STAINED_GLASS_STYLES if v["name"] == variant_name), None
            )
            if not variant:
                raise ArtGenerationError(f"Variant '{variant_name}' not found")
        else:
            variant = random.choice(STAINED_GLASS_STYLES)

        logger.info(f"Generating {variant['name']} stained glass window...")

        try:
            return self.ai_generator.generate_arrest_image(
                source, output_path, variant["prompt"]
            )
        except Exception as e:
            raise ArtGenerationError(f"Failed to generate stained glass window: {e}")

    def get_variants(self) -> list[dict[str, Any]]:
        """Return available stained glass style variants."""
        return [
            {
                "variant": style["name"],
                "display_name": f"Stained Glass: {style['name']}",
                "params": {"variant_name": style["name"]}
            }
            for style in STAINED_GLASS_STYLES
        ]
