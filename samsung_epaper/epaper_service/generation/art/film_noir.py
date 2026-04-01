"""
Film noir cinematic scene generator.
"""
import logging
import random
from typing import Any, Optional

from ..ai.factory import create_image_generator
from ..ai.prompts import EPAPER_SUFFIX, IDENTITY_ANCHOR
from .base import ArtGenerationError, ArtGenerator, ArtGeneratorConfig

logger = logging.getLogger(__name__)


# Film noir scene variants
NOIR_SCENES = [
    {
        "name": "Private Eye",
        "prompt": (
            f"{IDENTITY_ANCHOR} Transform this person into a 1940s hard-boiled private "
            "detective in a film noir scene. Harsh chiaroscuro lighting with deep blacks "
            "and bright whites. Wearing a fedora tilted low and a rumpled trench coat. "
            "Venetian blind shadows casting diagonal stripes across the face. Rain-streaked "
            "window in the background. Pure black and white, extreme contrast, no midtones. "
            "Cigarette smoke curling upward. Gritty pulp detective atmosphere, classic "
            f"Hollywood noir cinematography. {EPAPER_SUFFIX}"
        ),
    },
    {
        "name": "Femme Fatale",
        "prompt": (
            f"{IDENTITY_ANCHOR} Transform this person into a mysterious femme fatale in "
            "a classic film noir scene. Half-turned, looking back over one shoulder with "
            "an enigmatic expression. Dramatic backlighting creating a luminous rim light "
            "around hair and silhouette. Elegant evening wear with satin sheen. Wisps of "
            "smoke or fog drifting through the frame. Pure black and white photography, "
            "deep shadows, sensuous lighting. 1940s Hollywood glamour meets danger. "
            f"Moody, atmospheric, seductive noir cinematography. {EPAPER_SUFFIX}"
        ),
    },
    {
        "name": "Crime Scene",
        "prompt": (
            f"{IDENTITY_ANCHOR} Transform this person into a figure at a rain-slicked "
            "alley crime scene in classic film noir style. A single bare bulb hanging "
            "overhead casts harsh downward light. A neon HOTEL sign glows in the background, "
            "reflecting off wet cobblestones. Wearing a fedora and dark overcoat, casting "
            "a long dramatic shadow on the rain-soaked street. Flash-bulb press photography "
            "aesthetic with blown-out highlights and crushed blacks. Pure black and white, "
            f"gritty 1940s crime thriller atmosphere. {EPAPER_SUFFIX}"
        ),
    },
]


class FilmNoirGenerator(ArtGenerator):
    """Generates film noir cinematic scenes with dramatic chiaroscuro lighting."""

    ART_TYPE_NAME = "Film Noir"
    ART_TYPE_DESCRIPTION = "Creates dramatic 1940s film noir scenes with harsh chiaroscuro lighting, deep shadows, and classic Hollywood noir atmosphere"

    def __init__(self, config: Optional[ArtGeneratorConfig] = None):
        """Initialize the film noir generator."""
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
        Generate film noir scene from input images.

        Args:
            input_images: List of paths to input images (uses first image)
            output_path: Path where the generated art should be saved
            variant_name: Specific noir scene variant (random if None)
            **kwargs: Additional parameters

        Returns:
            Path to the generated artwork
        """
        if not self.ai_available:
            raise ArtGenerationError("AI not available. Film noir generation requires AI.")

        if not input_images:
            raise ArtGenerationError("No input images provided")

        if not self.validate_inputs(input_images):
            raise ArtGenerationError("One or more input images not found")

        # Use first image as the source
        source_photo = input_images[0]

        # Select variant
        if variant_name:
            variant = next((v for v in NOIR_SCENES if v["name"] == variant_name), None)
            if not variant:
                raise ArtGenerationError(f"Variant '{variant_name}' not found")
        else:
            variant = random.choice(NOIR_SCENES)

        logger.info(f"Generating film noir scene: {variant['name']} from: {source_photo}")

        try:
            result_path = self.ai_generator.generate_arrest_image(
                source_photo,
                output_path,
                variant["prompt"]
            )
            logger.info(f"Successfully generated film noir scene: {result_path}")
            return result_path
        except Exception as e:
            raise ArtGenerationError(f"Failed to generate film noir scene: {e}")

    def get_variants(self) -> list[dict[str, Any]]:
        """Return available noir scene variants."""
        return [
            {
                "variant": scene["name"],
                "display_name": f"Film Noir: {scene['name']}",
                "params": {"variant_name": scene["name"]}
            }
            for scene in NOIR_SCENES
        ]
