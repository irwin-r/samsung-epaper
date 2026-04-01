"""
Tabloid art generator implementation.
"""
import logging
import uuid
from pathlib import Path
from typing import Any, Optional

from ..ai.factory import ImageGenerationError, create_image_generator
from ..ai.text_generator import TextGenerationError, create_text_generator
from .config import get_config
from .content import format_current_date, get_content_manager
from .compositor import create_tabloid_compositor
from .base import ArtGenerationError, ArtGenerator, ArtGeneratorConfig

logger = logging.getLogger(__name__)


class TabloidArtGenerator(ArtGenerator):
    """Generates tabloid-style arrest photo art."""

    ART_TYPE_NAME = "tabloid"
    ART_TYPE_DESCRIPTION = "Creates humorous tabloid front pages featuring AI-generated arrest photos and stories"

    def __init__(self, config: Optional[ArtGeneratorConfig] = None):
        """Initialize the tabloid art generator."""
        super().__init__(config)

        self.app_config = get_config()
        self.content_manager = get_content_manager()
        self.generator = create_tabloid_compositor()

        # Try to initialize AI generators (optional)
        try:
            self.ai_generator = create_image_generator()
            self.text_generator = create_text_generator()
            self.ai_available = True
        except Exception as e:
            logger.warning(f"AI generation not available: {e}")
            self.ai_generator = None
            self.text_generator = None
            self.ai_available = False
    
    @property
    def name(self) -> str:
        """Return the name of this art generator."""
        return "Tabloid Arrest Photo"
    
    @property
    def description(self) -> str:
        """Return a description of what this art generator creates."""
        return "Creates humorous tabloid front pages featuring AI-generated arrest photos and stories"
    
    def get_required_resources(self) -> dict[str, Any]:
        """Get the resources required by this generator."""
        return {
            "templates": "Tabloid template images",
            "fonts": "Various fonts for text rendering",
            "openai_api": "OpenAI API key for AI generation (optional but recommended)"
        }
    
    def generate(
        self, 
        input_images: list[str], 
        output_path: str,
        template_name: Optional[str] = None,
        use_ai: bool = True,
        **kwargs
    ) -> str:
        """
        Generate tabloid art from input images.
        
        Args:
            input_images: List of paths to input images (uses first image)
            output_path: Path where the generated art should be saved
            template_name: Specific template to use (random if None)
            use_ai: Whether to use AI for image and text generation
            **kwargs: Additional parameters
            
        Returns:
            Path to the generated artwork
        """
        if not input_images:
            raise ArtGenerationError("No input images provided")
        
        if not self.validate_inputs(input_images):
            raise ArtGenerationError("One or more input images not found")
        
        # Use first image as the capture
        captured_photo = input_images[0]
        
        # Select template
        if template_name:
            template = self.app_config.get_template(template_name)
            if not template:
                raise ArtGenerationError(f"Template '{template_name}' not found")
        else:
            template = self.app_config.get_random_template()
            if not template:
                raise ArtGenerationError("No tabloid templates available")
        
        logger.info(f"Using template: {template.name}")
        
        # Generate content
        if use_ai and self.ai_available:
            arrest_photo, story = self._generate_ai_content(captured_photo, template)
        else:
            # Use the original photo and random story
            arrest_photo = captured_photo
            story = self.content_manager.get_random_story()
        
        # Generate tabloid
        current_date = format_current_date()

        try:
            final_tabloid = self.generator.generate_tabloid(
                template=template,
                arrest_image_path=arrest_photo,
                headline=story.headline,
                story_text=story.body if hasattr(story, 'body') else story.story,
                date_text=current_date,
                output_path=output_path
            )
            
            logger.info(f"Successfully generated tabloid: {final_tabloid}")
            return final_tabloid

        except Exception as e:
            raise ArtGenerationError(f"Failed to generate tabloid: {e}")
    
    def _generate_ai_content(self, captured_photo: str, template):
        """Generate AI content (arrest photo and story)."""
        # Generate story
        try:
            word_count = self.generator.calculate_optimal_word_count(template)
            story = self.text_generator.generate_arrest_story(word_count)
            logger.info(f"Generated story with {len(story.body.split())} words")
        except TextGenerationError as e:
            logger.error(f"Error generating story: {e}")
            story = self.content_manager.get_random_story()
        
        # Generate arrest photo
        try:
            # Create temporary output path for arrest photo
            arrest_photo_path = Path(captured_photo).parent / f"arrest_photo_{uuid.uuid4().hex[:8]}.png"
            
            image_prompt = getattr(story, 'image_prompt', None)
            if image_prompt:
                # Validate prompt
                problematic_words = ['priest', 'religious', 'church', 'divine', 'god', 'jesus', 'holy']
                if any(word.lower() in image_prompt.lower() for word in problematic_words) or len(image_prompt) > 1000:
                    image_prompt = None
            
            arrest_photo = self.ai_generator.generate_arrest_image(
                captured_photo, 
                str(arrest_photo_path),
                image_prompt
            )
            
            return arrest_photo, story
            
        except ImageGenerationError as e:
            logger.error(f"Error generating arrest photo: {e}")
            # Fall back to using original photo
            return captured_photo, story