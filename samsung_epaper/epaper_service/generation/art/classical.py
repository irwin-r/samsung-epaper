"""
Classical art juxtaposition generator.
"""
import logging
import random
from typing import Any, Optional

from ..ai.factory import create_image_generator
from ..ai.prompts import EPAPER_SUFFIX, IDENTITY_ANCHOR
from .base import ArtGenerationError, ArtGenerator, ArtGeneratorConfig

logger = logging.getLogger(__name__)


# Famous classical artworks for juxtaposition
CLASSICAL_ARTWORKS = [
    {
        "name": "Mona Lisa",
        "artist": "Leonardo da Vinci",
        "prompt": (
            f"{IDENTITY_ANCHOR} Reimagine this person as the sitter in Leonardo da "
            "Vinci's Mona Lisa. Dark Renaissance dress with delicate embroidery, hands "
            "in the characteristic folded pose with natural hand anatomy. Iconic "
            "atmospheric sfumato landscape background with winding river and misty "
            "mountains. Oil painting texture with visible craquelure. Warm amber museum "
            f"lighting, three-quarter pose facing left, waist-up framing. {EPAPER_SUFFIX}"
        ),
    },
    {
        "name": "The Starry Night",
        "artist": "Vincent van Gogh",
        "prompt": (
            f"{IDENTITY_ANCHOR} Transform this person entirely into Van Gogh's "
            "post-impressionist style. Every element — skin, hair, clothing — rendered "
            "in thick impasto brushstrokes with visible paint texture. Swirling night sky "
            "of Starry Night behind them, deep cobalt blues and bright cadmium yellows. "
            "Cypress tree frames one side, village glows below. Period clothing rendered "
            f"in the same painted style. Waist-up, three-quarter view. {EPAPER_SUFFIX}"
        ),
    },
    {
        "name": "The Scream",
        "artist": "Edvard Munch",
        "prompt": (
            f"{IDENTITY_ANCHOR} Transform this person into Munch's The Scream. Subject "
            "stands on the bridge, hands raised to sides of face in exaggerated alarm, "
            "mouth open. Wavy distorted expressionist landscape behind: blood-orange and "
            "red sky bleeding into deep blue fjord. Sinuous lines throughout. Munch's "
            "unsettling palette with bold visible brushwork. Retain recognizable facial "
            f"features within the expressionist style. {EPAPER_SUFFIX}"
        ),
    },
    {
        "name": "Girl with a Pearl Earring",
        "artist": "Johannes Vermeer",
        "prompt": (
            f"{IDENTITY_ANCHOR} Recreate this person as Vermeer's Girl with a Pearl "
            "Earring. Over-the-shoulder pose turning toward the viewer, lips slightly "
            "parted. Deep black background. Blue and gold silk turban wrapped around the "
            "head. Single luminous oversized pearl earring catching the light. Soft "
            "directional lighting from upper left. Dutch Golden Age painting technique "
            f"with smooth glazing and luminous skin tones. {EPAPER_SUFFIX}"
        ),
    },
    {
        "name": "American Gothic",
        "artist": "Grant Wood",
        "prompt": (
            f"{IDENTITY_ANCHOR} Transform this person into the farmer figure of Grant "
            "Wood's American Gothic. Stern, tight-lipped expression. Round spectacles, "
            "dark jacket over collarless shirt. One hand grips a three-pronged pitchfork "
            "vertically. Behind: the iconic white Carpenter Gothic house with pointed "
            "arched window. Flat, precise regionalist painting style with smooth surfaces "
            f"and sharp edges. Strong midday light. {EPAPER_SUFFIX}"
        ),
    },
    {
        "name": "The Arnolfini Portrait",
        "artist": "Jan van Eyck",
        "prompt": (
            f"{IDENTITY_ANCHOR} Transform this person into van Eyck's Arnolfini Portrait "
            "style. Richly detailed interior: brass chandelier with single lit candle, "
            "convex mirror on back wall, Persian rug on wooden floor. Subject wears "
            "voluminous fur-trimmed robe with one hand raised in formal gesture. "
            "Hyper-detailed Northern Renaissance painting technique with luminous glazes. "
            f"Waist-up framing, formal dignified pose. {EPAPER_SUFFIX}"
        ),
    },
    {
        "name": "The Last Supper",
        "artist": "Leonardo da Vinci",
        "prompt": (
            f"{IDENTITY_ANCHOR} Place this person as the central figure in da Vinci's "
            "Last Supper composition. Seated at long table with calm serene expression, "
            "arms spread in welcoming gesture. Symmetrical Renaissance architecture "
            "recedes to vanishing point behind. Other figures react with dramatic gestures "
            "on both sides. Bread, wine, and plates on the table. Fresco painting style, "
            f"warm candlelight tones. {EPAPER_SUFFIX}"
        ),
    },
    {
        "name": "The Creation of Adam",
        "artist": "Michelangelo",
        "prompt": (
            f"{IDENTITY_ANCHOR} Place this person in Michelangelo's Creation of Adam "
            "composition as the Adam figure. Reclining on earthen ledge, one arm extended "
            "with finger nearly touching the divine hand reaching from the right. Sistine "
            "Chapel fresco style with muted earth tones and soft modeling. Heavenly drapery "
            f"and angelic figures in background cloud. Monumental Renaissance fresco. {EPAPER_SUFFIX}"
        ),
    },
]


class ClassicalArtGenerator(ArtGenerator):
    """Generates art by juxtaposing subjects onto famous classical artworks."""

    ART_TYPE_NAME = "Classical Art Juxtaposition"
    ART_TYPE_DESCRIPTION = "Places subjects from photos into famous classical artworks like the Mona Lisa, Starry Night, etc."

    def __init__(self, config: Optional[ArtGeneratorConfig] = None):
        """Initialize the classical art generator."""
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
        return "Classical Art Juxtaposition"
    
    @property
    def description(self) -> str:
        """Return a description of what this art generator creates."""
        return "Places subjects from photos into famous classical artworks like the Mona Lisa, Starry Night, etc."
    
    def get_required_resources(self) -> dict[str, Any]:
        """Get the resources required by this generator."""
        return {
            "openai_api": "OpenAI API key for AI generation (required)",
            "classical_references": "Built-in prompts for famous artworks"
        }
    
    def generate(
        self, 
        input_images: list[str], 
        output_path: str,
        artwork_name: Optional[str] = None,
        custom_prompt: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Generate classical art juxtaposition from input images.
        
        Args:
            input_images: List of paths to input images (uses first image)
            output_path: Path where the generated art should be saved
            artwork_name: Specific artwork to use (random if None)
            custom_prompt: Custom prompt override
            **kwargs: Additional parameters
            
        Returns:
            Path to the generated artwork
        """
        if not self.ai_available:
            raise ArtGenerationError("OpenAI API not available. Classical art generation requires AI.")
        
        if not input_images:
            raise ArtGenerationError("No input images provided")
        
        if not self.validate_inputs(input_images):
            raise ArtGenerationError("One or more input images not found")
        
        # Use first image as the source
        source_photo = input_images[0]
        
        # Select artwork
        if artwork_name:
            artwork = self._find_artwork_by_name(artwork_name)
            if not artwork:
                raise ArtGenerationError(f"Artwork '{artwork_name}' not found")
        else:
            artwork = random.choice(CLASSICAL_ARTWORKS)
        
        logger.info(f"Using artwork: {artwork['name']} by {artwork['artist']}")
        
        # Generate the juxtaposition
        try:
            prompt = custom_prompt if custom_prompt else artwork['prompt']
            logger.info(f"Generating with prompt: {prompt[:100]}...")
            
            # Generate the image
            result_path = self.ai_generator.generate_classical_juxtaposition(
                source_photo,
                output_path,
                prompt
            )

            logger.info(f"Successfully generated classical art: {result_path}")
            return result_path
            
        except Exception as e:
            raise ArtGenerationError(f"Failed to generate classical art: {e}")
    
    def _find_artwork_by_name(self, name: str) -> Optional[dict[str, str]]:
        """Find artwork by name (case insensitive)."""
        name_lower = name.lower()
        for artwork in CLASSICAL_ARTWORKS:
            if name_lower in artwork['name'].lower() or name_lower in artwork['artist'].lower():
                return artwork
        return None
    
    def get_variants(self) -> list[dict[str, Any]]:
        """Return available artwork variants."""
        return [
            {
                "variant": art["name"],
                "display_name": f"Classical: {art['name']} ({art['artist']})",
                "params": {"artwork_name": art["name"]}
            }
            for art in CLASSICAL_ARTWORKS
        ]

    def list_available_artworks(self) -> list[dict[str, str]]:
        """Get list of available classical artworks."""
        return [
            {"name": art["name"], "artist": art["artist"]}
            for art in CLASSICAL_ARTWORKS
        ]