"""
Art Nouveau poster generator.
"""
import logging
import random
from typing import Any, Optional

from ..ai.factory import create_image_generator
from ..ai.prompts import EPAPER_SUFFIX, IDENTITY_ANCHOR
from .base import ArtGenerationError, ArtGenerator, ArtGeneratorConfig

logger = logging.getLogger(__name__)


# Art Nouveau style variations
ART_NOUVEAU_STYLES = [
    {
        "name": "Mucha Seasons",
        "prompt": (
            f"{IDENTITY_ANCHOR} Create a portrait in the style of Alphonse Mucha's Seasons "
            "series. The subject in an ornamental pose, hair streaming outward in sinuous "
            "whiplash curves intertwined with flowers and trailing vines. A circular halo or "
            "nimbus radiates behind the head. Flat color areas with bold black outlines — "
            "muted gold, sage green, dusty rose, and cream. An ornate rectangular border "
            "filled with botanical motifs frames the composition. Lithographic print quality "
            "with visible halftone texture. Decorative Art Nouveau poster, turn-of-century "
            f"Parisian illustration. {EPAPER_SUFFIX}"
        ),
    },
    {
        "name": "Theatre Poster",
        "prompt": (
            f"{IDENTITY_ANCHOR} Create a Belle Époque theatre advertisement poster. The "
            "subject in a dramatic performer's pose wearing a flowing theatrical costume with "
            "sweeping fabric. An ornate typographic header in sinuous Art Nouveau lettering "
            "across the top. Peacock feathers, lilies, and stars frame the figure. Rich flat "
            "color with strong black contours defining every form. Gold accents highlight "
            "borders and decorative elements. Elaborate corner ornaments with organic flowing "
            "lines. The style blends Toulouse-Lautrec's bold graphic energy with Mucha's "
            f"decorative elegance. Vintage poster print quality. {EPAPER_SUFFIX}"
        ),
    },
    {
        "name": "Absinthe Advertisement",
        "prompt": (
            f"{IDENTITY_ANCHOR} Create a vintage Art Nouveau absinthe advertisement poster. "
            "The subject lounges elegantly, holding an ornate crystal absinthe glass with a "
            "slotted spoon balanced on top. A green fairy motif glows ethereally nearby. The "
            "border is filled with wormwood and fennel botanical illustrations in sinuous "
            "Art Nouveau line work. Deep emerald greens, rich golds, and solid blacks dominate "
            "the palette. Bold sinuous outlines define flat decorative color fields. "
            "Turn-of-century Parisian poster aesthetic — decadent, mysterious, seductive. "
            f"Lithographic print quality with period-authentic typography. {EPAPER_SUFFIX}"
        ),
    },
]


class ArtNouveauGenerator(ArtGenerator):
    """Generates Art Nouveau poster art from portrait photos."""

    ART_TYPE_NAME = "Art Nouveau Poster"
    ART_TYPE_DESCRIPTION = "Creates decorative Art Nouveau posters in the style of Mucha, Toulouse-Lautrec, and Belle Époque Parisian illustration"

    def __init__(self, config: Optional[ArtGeneratorConfig] = None):
        """Initialize the Art Nouveau generator."""
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
        Generate Art Nouveau poster art from input images.

        Args:
            input_images: List of paths to input images (uses first image)
            output_path: Path where the generated art should be saved
            variant_name: Specific Art Nouveau style to use (random if None)
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
                (v for v in ART_NOUVEAU_STYLES if v["name"] == variant_name), None
            )
            if not variant:
                raise ArtGenerationError(f"Variant '{variant_name}' not found")
        else:
            variant = random.choice(ART_NOUVEAU_STYLES)

        logger.info(f"Generating {variant['name']} Art Nouveau poster...")

        try:
            return self.ai_generator.generate_arrest_image(
                source, output_path, variant["prompt"]
            )
        except Exception as e:
            raise ArtGenerationError(f"Failed to generate Art Nouveau poster: {e}")

    def get_variants(self) -> list[dict[str, Any]]:
        """Return available Art Nouveau style variants."""
        return [
            {
                "variant": style["name"],
                "display_name": f"Art Nouveau: {style['name']}",
                "params": {"variant_name": style["name"]}
            }
            for style in ART_NOUVEAU_STYLES
        ]
