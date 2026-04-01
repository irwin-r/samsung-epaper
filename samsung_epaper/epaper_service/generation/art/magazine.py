"""
Glossy Magazine Cover generator using pure AI generation.
"""
import logging
import random
from typing import Any, Optional

from ..ai.factory import create_image_generator
from ..ai.prompts import EPAPER_SUFFIX, IDENTITY_ANCHOR
from .base import ArtGenerationError, ArtGenerator, ArtGeneratorConfig

logger = logging.getLogger(__name__)


# Magazine style prompts for AI generation
MAGAZINE_STYLES = {
    "time": {
        "name": "TIME Magazine Style",
        "prompt_template": (
            f"{IDENTITY_ANCHOR} Create a TIME Magazine Person of the Year cover portrait. "
            "Tight crop on face and shoulders against a solid deep-red background. "
            "Dramatic Rembrandt lighting with one side brighter. Commanding, confident "
            "expression gazing directly into camera. Ultra-sharp focus, photojournalistic "
            f"style. {EPAPER_SUFFIX}"
        ),
    },
    "vogue": {
        "name": "Vogue Magazine Style",
        "prompt_template": (
            f"{IDENTITY_ANCHOR} Create a Vogue magazine cover portrait. High-fashion "
            "editorial presentation with dramatic pose — chin slightly lifted, eyes "
            "piercing. Soft butterfly lighting with clean catchlights. Minimalist studio "
            "backdrop in muted cream. Elegant, aspirational, luminous skin. Fashion "
            f"photography aesthetic. {EPAPER_SUFFIX}"
        ),
    },
    "newsweek": {
        "name": "Newsweek Magazine Style",
        "prompt_template": (
            f"{IDENTITY_ANCHOR} Create a Newsweek magazine cover portrait. Serious, "
            "contemplative expression with intense direct gaze. Clean background in deep "
            "blue or dark gradient. Precise editorial lighting emphasizing authority and "
            f"gravitas. Sharp photojournalistic quality. {EPAPER_SUFFIX}"
        ),
    },
    "people": {
        "name": "People Magazine Style",
        "prompt_template": (
            f"{IDENTITY_ANCHOR} Create a People magazine cover portrait. Warm, "
            "approachable expression with genuine smile. Bright even lighting, no harsh "
            "shadows. Casual but polished styling. Warm golden-hour tones suggesting an "
            f"active lifestyle. Celebrity candid warmth. {EPAPER_SUFFIX}"
        ),
    },
    "rolling_stone": {
        "name": "Rolling Stone Magazine Style",
        "prompt_template": (
            f"{IDENTITY_ANCHOR} Create a Rolling Stone magazine cover portrait. "
            "High-contrast moody lighting — deep shadows, single dramatic side light. "
            "Edgy rock-and-roll attitude: intensity, confidence. Background in deep black. "
            f"Gritty authentic music photography style. {EPAPER_SUFFIX}"
        ),
    },
    "forbes": {
        "name": "Forbes Magazine Style",
        "prompt_template": (
            f"{IDENTITY_ANCHOR} Create a Forbes magazine cover portrait. Power pose — "
            "arms crossed or leaning forward with authority. Sharp business attire. "
            "Background: abstract dark gradient suggesting wealth and ambition. Clean "
            f"corporate lighting. Polished executive portrait photography. {EPAPER_SUFFIX}"
        ),
    },
}

# Story type variations for headlines
STORY_TYPES = {
    "achievement": [
        "PERSON OF THE YEAR",
        "THE GAME CHANGER", 
        "MAKING HISTORY",
        "BREAKING BARRIERS",
        "THE POWER PLAYER"
    ],
    "fashion": [
        "STYLE ICON",
        "FASHION FORWARD",
        "THE NEW FACE OF BEAUTY", 
        "TRENDSETTER",
        "REDEFINING ELEGANCE"
    ],
    "business": [
        "THE BILLIONAIRE",
        "BUSINESS GENIUS",
        "THE INNOVATOR",
        "SUCCESS STORY",
        "EMPIRE BUILDER"
    ],
    "entertainment": [
        "SUPERSTAR",
        "THE SENSATION",
        "HOLLYWOOD'S HOTTEST",
        "RISING STAR",
        "ENTERTAINMENT ICON"
    ],
    "politics": [
        "THE LEADER",
        "POLITICAL POWERHOUSE", 
        "CHANGING AMERICA",
        "THE INFLUENCER",
        "FUTURE PRESIDENT"
    ]
}


class MagazineCoverGenerator(ArtGenerator):
    """Generates glossy magazine covers using pure AI generation."""

    ART_TYPE_NAME = "Glossy Magazine Cover"
    ART_TYPE_DESCRIPTION = "Creates professional magazine covers in styles like TIME, Vogue, GQ, National Geographic, and Forbes"

    def __init__(self, config: Optional[ArtGeneratorConfig] = None):
        """Initialize the magazine cover generator."""
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
        return "Glossy Magazine Cover"
    
    @property
    def description(self) -> str:
        """Return a description of what this art generator creates."""
        return "Creates professional magazine covers using AI in the style of TIME, Vogue, Newsweek, People, Rolling Stone, and Forbes"
    
    def get_required_resources(self) -> dict[str, Any]:
        """Get the resources required by this generator."""
        return {
            "openai_api": "OpenAI API key for AI generation (required)"
        }
    
    def generate(
        self, 
        input_images: list[str], 
        output_path: str,
        magazine_style: Optional[str] = None,
        story_type: Optional[str] = None,
        custom_prompt: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Generate magazine cover using pure AI generation.
        
        Args:
            input_images: List of paths to input images (uses first image)
            output_path: Path where the generated cover should be saved
            magazine_style: Magazine style (time, vogue, newsweek, people, rolling_stone, forbes)
            story_type: Story type for headline (achievement, fashion, business, entertainment, politics)
            custom_prompt: Custom prompt override
            **kwargs: Additional parameters
            
        Returns:
            Path to the generated magazine cover
        """
        if not self.ai_available:
            raise ArtGenerationError("OpenAI API not available. Magazine cover generation requires AI.")
        
        if not input_images:
            raise ArtGenerationError("No input images provided")
        
        if not self.validate_inputs(input_images):
            raise ArtGenerationError("One or more input images not found")
        
        # Use first image as the source
        source_photo = input_images[0]
        
        # Select magazine style
        if magazine_style and magazine_style in MAGAZINE_STYLES:
            style = MAGAZINE_STYLES[magazine_style]
        else:
            style = random.choice(list(MAGAZINE_STYLES.values()))
        
        logger.info(f"Generating {style['name']} magazine cover from: {source_photo}")
        
        try:
            if custom_prompt:
                prompt = custom_prompt
            else:
                # Build the prompt
                base_prompt = style['prompt_template']
                
                # Add story type variation if specified
                if story_type and story_type in STORY_TYPES:
                    headline_options = STORY_TYPES[story_type]
                    headline = random.choice(headline_options)
                    prompt = base_prompt.replace(
                        "PERSON OF THE YEAR", headline
                    ).replace(
                        "impactful title", f"'{headline}'"
                    ).replace(
                        "about this person being", f"about this person being '{headline}' or"
                    )
                else:
                    prompt = base_prompt
                
                # Add quality and technical specifications
                prompt += (
                    ", professional magazine photography, "
                    "high resolution, perfect lighting, "
                    "glossy magazine cover quality, "
                    "commercial photography style, "
                    "magazine cover layout with text and graphics"
                )
            
            logger.info(f"Using prompt: {prompt[:150]}...")
            
            # Generate the magazine cover
            result_path = self._generate_with_ai(source_photo, output_path, prompt)
            
            logger.info(f"Successfully generated magazine cover: {result_path}")
            return result_path
            
        except Exception as e:
            raise ArtGenerationError(f"Failed to generate magazine cover: {e}")
    
    def _generate_with_ai(self, source_photo: str, output_path: str, prompt: str) -> str:
        """Generate magazine cover using AI."""
        try:
            return self.ai_generator.generate_arrest_image(
                source_photo,
                output_path,
                prompt
            )
        except Exception as e:
            raise ArtGenerationError(f"AI generation failed: {e}")
    
    def get_variants(self) -> list[dict[str, Any]]:
        """Return available magazine style variants."""
        return [
            {
                "variant": key,
                "display_name": f"Magazine: {style['name']}",
                "params": {"magazine_style": key}
            }
            for key, style in MAGAZINE_STYLES.items()
        ]

    def list_available_styles(self) -> list[dict[str, str]]:
        """Get list of available magazine styles."""
        return [
            {"style": key, "name": style["name"]}
            for key, style in MAGAZINE_STYLES.items()
        ]
    
