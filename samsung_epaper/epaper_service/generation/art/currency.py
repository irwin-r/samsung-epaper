"""
Currency portrait engraving generator.
"""
import logging
import random
from typing import Any, Optional

from ..ai.factory import create_image_generator
from ..ai.prompts import EPAPER_SUFFIX, IDENTITY_ANCHOR
from .base import ArtGenerationError, ArtGenerator, ArtGeneratorConfig

logger = logging.getLogger(__name__)


# Currency engraving style variants
CURRENCY_STYLES = [
    {
        "name": "US Dollar Style",
        "prompt": (
            f"{IDENTITY_ANCHOR} Transform this person into a portrait engraved on a US "
            "dollar bill. Fine intaglio engraving technique with thousands of precise "
            "parallel lines of varying weight to create tone and depth. Three-quarter "
            "pose with a dignified, statesmanlike expression. Ornate geometric lathe-work "
            "borders with intricate rosettes and guilloche patterns. Delicate filigree "
            "scrollwork surrounding the oval portrait frame. Monochromatic green-black "
            "ink on cream paper. Precise crosshatching for shadows. The unmistakable look "
            f"of US currency engraving, hyper-detailed linework. {EPAPER_SUFFIX}"
        ),
    },
    {
        "name": "Victorian Banknote",
        "prompt": (
            f"{IDENTITY_ANCHOR} Transform this person into a portrait on a Victorian-era "
            "British banknote. Classical steel-engraving technique with meticulous "
            "crosshatching building up rich tonal gradations. Ornate border featuring "
            "Britannia, heraldic lions, and royal crowns in elaborate decorative frames. "
            "Mix of Gothic and Roman typography for denomination and bank name. Portrait "
            "in formal three-quarter pose within an oval cartouche. Sepia and dark brown "
            "ink on aged cream paper with subtle foxing. 19th-century printing aesthetic "
            f"with extraordinary fine detail and engraver craftsmanship. {EPAPER_SUFFIX}"
        ),
    },
    {
        "name": "Fantasy Treasury",
        "prompt": (
            f"{IDENTITY_ANCHOR} Transform this person into a portrait on a fantasy "
            "kingdom treasury note. Regal engraving style with the subject wearing a "
            "crown or ornate circlet. Mythical creatures — dragons and griffins — woven "
            "into the elaborate border design alongside castle towers and heraldic shields. "
            "Magical runes and arcane symbols integrated into the lathe-work patterns. "
            "The denomination '1000 GOLD CROWNS' rendered in ornate blackletter Gothic "
            "script. Printed on aged parchment with a weathered, antiqued appearance. "
            "Fine intaglio line engraving with crosshatching, combining real currency "
            f"craftsmanship with high-fantasy world-building. {EPAPER_SUFFIX}"
        ),
    },
]


class CurrencyGenerator(ArtGenerator):
    """Generates currency-style portrait engravings with fine intaglio linework."""

    ART_TYPE_NAME = "Currency Portrait"
    ART_TYPE_DESCRIPTION = "Creates currency-style portrait engravings with fine intaglio linework, ornate borders, and banknote aesthetics"

    def __init__(self, config: Optional[ArtGeneratorConfig] = None):
        """Initialize the currency generator."""
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
        Generate currency portrait engraving from input images.

        Args:
            input_images: List of paths to input images (uses first image)
            output_path: Path where the generated art should be saved
            variant_name: Specific currency style variant (random if None)
            **kwargs: Additional parameters

        Returns:
            Path to the generated artwork
        """
        if not self.ai_available:
            raise ArtGenerationError("AI not available. Currency generation requires AI.")

        if not input_images:
            raise ArtGenerationError("No input images provided")

        if not self.validate_inputs(input_images):
            raise ArtGenerationError("One or more input images not found")

        # Use first image as the source
        source_photo = input_images[0]

        # Select variant
        if variant_name:
            variant = next((v for v in CURRENCY_STYLES if v["name"] == variant_name), None)
            if not variant:
                raise ArtGenerationError(f"Variant '{variant_name}' not found")
        else:
            variant = random.choice(CURRENCY_STYLES)

        logger.info(f"Generating currency portrait: {variant['name']} from: {source_photo}")

        try:
            result_path = self.ai_generator.generate_arrest_image(
                source_photo,
                output_path,
                variant["prompt"]
            )
            logger.info(f"Successfully generated currency portrait: {result_path}")
            return result_path
        except Exception as e:
            raise ArtGenerationError(f"Failed to generate currency portrait: {e}")

    def get_variants(self) -> list[dict[str, Any]]:
        """Return available currency style variants."""
        return [
            {
                "variant": style["name"],
                "display_name": f"Currency: {style['name']}",
                "params": {"variant_name": style["name"]}
            }
            for style in CURRENCY_STYLES
        ]
