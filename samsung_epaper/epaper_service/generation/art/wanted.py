"""
Wanted poster generator.
"""
import logging
import random
from typing import Any, Optional

from ..ai.factory import create_image_generator
from ..ai.prompts import EPAPER_SUFFIX, IDENTITY_ANCHOR
from .base import ArtGenerationError, ArtGenerator, ArtGeneratorConfig

logger = logging.getLogger(__name__)


# Old West wanted poster styles
WANTED_STYLES = [
    {
        "name": "Classic Outlaw",
        "prompt": (
            f"{IDENTITY_ANCHOR} Create an authentic Old West wanted poster. Aged yellowed "
            "parchment with torn edges, coffee stains, and foxing. Large bold WANTED header "
            "in woodblock serif typeface across the top. Sepia-toned daguerreotype-style "
            "portrait in an oval vignette frame at center. Period styling — dusty wide-brimmed "
            "hat, bandana loosely around neck. Below the portrait: DEAD OR ALIVE in bold type, "
            "$10,000 REWARD in large numerals, and a paragraph of frontier-era criminal charges "
            "in smaller serif text. Pin holes visible in all four corners as if tacked to a "
            f"wooden post. Weathered, sun-faded, historically convincing. {EPAPER_SUFFIX}"
        ),
    },
    {
        "name": "Train Robber",
        "prompt": (
            f"{IDENTITY_ANCHOR} Create an Old West wanted poster nailed to rough wooden planks. "
            "Creased sun-bleached parchment with visible nail heads at top corners. WANTED FOR "
            "TRAIN ROBBERY in bold woodcut type across the top. Hand-drawn pencil sketch "
            "portrait in frontier style — wide-brimmed hat and long duster coat, crosshatched "
            "shading. $25,000 GOLD REWARD in ornate Victorian typography below the portrait. "
            "A sheriff's star stamp pressed into the bottom corner. Aged paper texture with "
            f"water stains and creases from folding. Period-authentic typography. {EPAPER_SUFFIX}"
        ),
    },
    {
        "name": "Cattle Rustler",
        "prompt": (
            f"{IDENTITY_ANCHOR} Create a rustic hand-made Old West wanted poster. Aged paper "
            "with bullet holes punched through and scorch marks along one edge. WANTED — CATTLE "
            "RUSTLER in rough hand-painted letters, uneven and slightly dripping. Charcoal "
            "sketch portrait with exaggerated Wild West styling — oversized cowboy hat, squinting "
            "eyes, dust on the face. REWARD: $5,000 AND A FREE HORSE in bold mismatched "
            "lettering below. The whole poster feels hand-made and frontier-rough, as if created "
            f"by a rancher rather than a printer. Weathered and authentic. {EPAPER_SUFFIX}"
        ),
    },
]


class WantedPosterGenerator(ArtGenerator):
    """Generates Old West wanted poster art from portrait photos."""

    ART_TYPE_NAME = "Wanted Poster"
    ART_TYPE_DESCRIPTION = "Creates authentic Old West wanted posters with aged parchment, bold typography, and frontier styling"

    def __init__(self, config: Optional[ArtGeneratorConfig] = None):
        """Initialize the wanted poster generator."""
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
        Generate a wanted poster from input images.

        Args:
            input_images: List of paths to input images (uses first image)
            output_path: Path where the generated art should be saved
            variant_name: Specific wanted style to use (random if None)
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
                (v for v in WANTED_STYLES if v["name"] == variant_name), None
            )
            if not variant:
                raise ArtGenerationError(f"Variant '{variant_name}' not found")
        else:
            variant = random.choice(WANTED_STYLES)

        logger.info(f"Generating {variant['name']} wanted poster...")

        try:
            return self.ai_generator.generate_arrest_image(
                source, output_path, variant["prompt"]
            )
        except Exception as e:
            raise ArtGenerationError(f"Failed to generate wanted poster: {e}")

    def get_variants(self) -> list[dict[str, Any]]:
        """Return available wanted poster variants."""
        return [
            {
                "variant": style["name"],
                "display_name": f"Wanted: {style['name']}",
                "params": {"variant_name": style["name"]}
            }
            for style in WANTED_STYLES
        ]
