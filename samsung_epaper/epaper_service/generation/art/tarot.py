"""
Tarot card illustration generator.
"""
import logging
import random
from typing import Any, Optional

from ..ai.factory import create_image_generator
from ..ai.prompts import EPAPER_SUFFIX, IDENTITY_ANCHOR
from .base import ArtGenerationError, ArtGenerator, ArtGeneratorConfig

logger = logging.getLogger(__name__)


# Major Arcana tarot card variants
TAROT_CARDS = [
    {
        "name": "The Magician",
        "numeral": "I",
        "prompt": (
            f"{IDENTITY_ANCHOR} Transform this person into The Magician tarot card (I). "
            "Standing behind a table bearing a cup, pentacle, sword, and wand — the four "
            "suits of the tarot. One hand raises a wand skyward while the other points "
            "to the earth, channeling power between realms. An infinity symbol (lemniscate) "
            "floats above the head. Lush roses and white lilies form a border around the "
            "scene. Art Nouveau style with flowing organic lines and rich decorative detail. "
            f"Classic tarot card composition with ornate border. {EPAPER_SUFFIX}"
        ),
    },
    {
        "name": "The Emperor",
        "numeral": "IV",
        "prompt": (
            f"{IDENTITY_ANCHOR} Transform this person into The Emperor tarot card (IV). "
            "Seated upon a grand stone throne carved with ram heads on the armrests, "
            "symbolizing Aries. Wearing imposing armor beneath a rich red robe. One hand "
            "grips an ankh scepter, the other holds a golden orb. Behind the throne, "
            "barren rocky mountains rise under a fiery orange sky. Rider-Waite tarot style "
            "with bold flat colors and clear symbolic imagery. Classic tarot card "
            f"composition with ornate border. {EPAPER_SUFFIX}"
        ),
    },
    {
        "name": "The Star",
        "numeral": "XVII",
        "prompt": (
            f"{IDENTITY_ANCHOR} Transform this person into The Star tarot card (XVII). "
            "Kneeling serenely beside a calm reflective pool, pouring water from two "
            "vessels — one onto the land, one into the pool. Above, a large radiant "
            "eight-pointed star dominates the sky, surrounded by seven smaller stars. "
            "A lush green landscape with trees and birds in the background. Atmosphere "
            "of hope, renewal, and tranquility. Classic tarot card illustration style "
            f"with ornate border and Roman numeral XVII. {EPAPER_SUFFIX}"
        ),
    },
    {
        "name": "The Fool",
        "numeral": "0",
        "prompt": (
            f"{IDENTITY_ANCHOR} Transform this person into The Fool tarot card (0). "
            "Walking carefree toward the edge of a cliff with a joyful, innocent "
            "expression. Carrying a small bundle tied to a stick over one shoulder. "
            "A small white dog leaps playfully at the heels. A bright sun shines in "
            "a clear sky, snow-capped mountains in the distance. Holding a single white "
            "rose in one hand. Colorful patterned clothing. Classic tarot card "
            f"illustration style with ornate border and numeral 0. {EPAPER_SUFFIX}"
        ),
    },
    {
        "name": "Wheel of Fortune",
        "numeral": "X",
        "prompt": (
            f"{IDENTITY_ANCHOR} Transform this person into the central face of the "
            "Wheel of Fortune tarot card (X). The face appears at the hub of a great "
            "turning wheel inscribed with alchemical symbols and Hebrew letters. A sphinx "
            "bearing a sword sits atop the wheel. A serpent descends along one side while "
            "Anubis rises on the other. Winged figures of a bull, lion, eagle, and angel "
            "occupy the four corners. Medieval manuscript illumination style with gold "
            f"leaf and rich jewel tones. Ornate tarot card border. {EPAPER_SUFFIX}"
        ),
    },
]


class TarotCardGenerator(ArtGenerator):
    """Generates tarot card illustrations placing subjects into Major Arcana compositions."""

    ART_TYPE_NAME = "Tarot Card"
    ART_TYPE_DESCRIPTION = "Creates Major Arcana tarot card illustrations with rich symbolic imagery and classic tarot art styles"

    def __init__(self, config: Optional[ArtGeneratorConfig] = None):
        """Initialize the tarot card generator."""
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
        Generate tarot card illustration from input images.

        Args:
            input_images: List of paths to input images (uses first image)
            output_path: Path where the generated art should be saved
            variant_name: Specific tarot card variant (random if None)
            **kwargs: Additional parameters

        Returns:
            Path to the generated artwork
        """
        if not self.ai_available:
            raise ArtGenerationError("AI not available. Tarot card generation requires AI.")

        if not input_images:
            raise ArtGenerationError("No input images provided")

        if not self.validate_inputs(input_images):
            raise ArtGenerationError("One or more input images not found")

        # Use first image as the source
        source_photo = input_images[0]

        # Select variant
        if variant_name:
            variant = next((v for v in TAROT_CARDS if v["name"] == variant_name), None)
            if not variant:
                raise ArtGenerationError(f"Variant '{variant_name}' not found")
        else:
            variant = random.choice(TAROT_CARDS)

        logger.info(f"Generating tarot card: {variant['name']} ({variant['numeral']}) from: {source_photo}")

        try:
            result_path = self.ai_generator.generate_arrest_image(
                source_photo,
                output_path,
                variant["prompt"]
            )
            logger.info(f"Successfully generated tarot card: {result_path}")
            return result_path
        except Exception as e:
            raise ArtGenerationError(f"Failed to generate tarot card: {e}")

    def get_variants(self) -> list[dict[str, Any]]:
        """Return available tarot card variants."""
        return [
            {
                "variant": card["name"],
                "display_name": f"Tarot: {card['name']} ({card['numeral']})",
                "params": {"variant_name": card["name"]}
            }
            for card in TAROT_CARDS
        ]
