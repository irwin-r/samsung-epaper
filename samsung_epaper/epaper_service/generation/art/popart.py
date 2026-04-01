"""
Pop Art Quad (Warhol style) generator.
"""
import logging
import random
from typing import Any, Optional

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

from ..ai.factory import create_image_generator
from ..ai.prompts import EPAPER_SUFFIX, IDENTITY_ANCHOR
from .base import ArtGenerationError, ArtGenerator, ArtGeneratorConfig

logger = logging.getLogger(__name__)


# Warhol-style color combinations for duotone effects
WARHOL_COLOR_SCHEMES = [
    {"primary": "#00FFFF", "secondary": "#FF00FF", "name": "Cyan-Magenta"},  # cyan, magenta
    {"primary": "#FFFF00", "secondary": "#000000", "name": "Yellow-Black"},   # yellow, black
    {"primary": "#FF00FF", "secondary": "#00FFFF", "name": "Magenta-Cyan"},   # magenta, cyan
    {"primary": "#000000", "secondary": "#FFFF00", "name": "Black-Yellow"},   # black, yellow
    {"primary": "#00FFFF", "secondary": "#000000", "name": "Cyan-Black"},     # cyan, black
    {"primary": "#FF00FF", "secondary": "#FFFF00", "name": "Magenta-Yellow"}, # magenta, yellow
]


class PopArtGenerator(ArtGenerator):
    """Generates Warhol-style pop art quads with bold duotone colors and thick outlines."""

    ART_TYPE_NAME = "Pop Art Quad (Warhol)"
    ART_TYPE_DESCRIPTION = "Creates Warhol-style pop art grids of four with bold duotone colors, thick outlines, and silkscreen aesthetic"

    def __init__(self, config: Optional[ArtGeneratorConfig] = None):
        """Initialize the pop art generator."""
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
        return "Pop Art Quad (Warhol)"
    
    @property
    def description(self) -> str:
        """Return a description of what this art generator creates."""
        return "Creates Warhol-style pop art grids of four with bold duotone colors (cyan, magenta, yellow, black), thick outlines, and silkscreen aesthetic"
    
    def get_required_resources(self) -> dict[str, Any]:
        """Get the resources required by this generator."""
        return {
            "openai_api": "OpenAI API key for AI generation (optional - can work without)",
            "image_processing": "PIL/Pillow for local image manipulation"
        }
    
    def generate(
        self, 
        input_images: list[str], 
        output_path: str,
        use_ai: bool = True,
        color_scheme: Optional[str] = None,
        contrast_boost: float = 1.5,
        **kwargs
    ) -> str:
        """
        Generate Warhol-style pop art quad from input images.
        
        Args:
            input_images: List of paths to input images (uses first image)
            output_path: Path where the generated art should be saved
            use_ai: Whether to use AI enhancement (True) or pure image processing (False)
            color_scheme: Specific color scheme name (random if None)
            contrast_boost: How much to boost contrast (1.0 = no change, 2.0 = double)
            **kwargs: Additional parameters
            
        Returns:
            Path to the generated artwork
        """
        if not input_images:
            raise ArtGenerationError("No input images provided")
        
        if not self.validate_inputs(input_images):
            raise ArtGenerationError("One or more input images not found")
        
        # Use first image as the source
        source_photo = input_images[0]
        
        logger.info(f"Generating Warhol-style pop art from: {source_photo}")
        
        try:
            if use_ai and self.ai_available:
                return self._generate_with_ai(source_photo, output_path, color_scheme, **kwargs)
            else:
                return self._generate_with_image_processing(source_photo, output_path, color_scheme, contrast_boost)
                
        except Exception as e:
            raise ArtGenerationError(f"Failed to generate pop art: {e}")
    
    def _generate_with_ai(self, source_photo: str, output_path: str, color_scheme: Optional[str], **kwargs) -> str:
        """Generate pop art using AI assistance."""
        logger.info("Using AI generation for Warhol-style pop art")
        
        # Build Warhol-style prompt with identity preservation
        prompt = (
            f"{IDENTITY_ANCHOR} Create an Andy Warhol silk-screen pop art portrait. "
            "Four-panel grid (2x2), each panel showing the same head-and-shoulders crop "
            "with a different bold duotone color treatment. High contrast with only 3-4 "
            "flat color values per panel — no gradients. Thick black outlines around all "
            "forms. Simplified graphic shapes for hair and clothing. Each panel background "
            "is a different solid saturated color. 1960s Factory silkscreen aesthetic with "
            f"slight registration offset between color layers. {EPAPER_SUFFIX}"
        )
        
        # Try to use AI generation
        try:
            result_path = self.ai_generator.generate_arrest_image(
                source_photo,
                output_path,
                prompt
            )
            logger.info(f"Successfully generated pop art with AI: {result_path}")
            return result_path

        except Exception as e:
            logger.warning(f"AI generation failed: {e}. Falling back to image processing.")
            return self._generate_with_image_processing(source_photo, output_path, color_scheme, 1.5)
    
    def _generate_with_image_processing(self, source_photo: str, output_path: str, color_scheme: Optional[str], contrast_boost: float) -> str:
        """Generate pop art using pure image processing (no AI)."""
        logger.info("Generating pop art using image processing")
        
        # Load and prepare the source image
        with Image.open(source_photo) as img:
            # Convert to RGB if needed
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Resize to square for better composition
            size = min(img.size)
            img = img.resize((size, size), Image.Resampling.LANCZOS)
            
            # Create four variations with different color treatments
            variations = []
            
            for i, scheme in enumerate(WARHOL_COLOR_SCHEMES[:4]):
                variation = self._create_duotone_variation(img, scheme, contrast_boost)
                variation = self._add_thick_outline(variation)
                variations.append(variation)
            
            # Create 2x2 grid
            quad_image = self._create_quad_grid(variations)
            
            # Save the result
            quad_image.save(output_path, 'JPEG', quality=95)
            
            logger.info(f"Successfully generated pop art with image processing: {output_path}")
            return output_path
    
    def _create_duotone_variation(self, img: Image.Image, color_scheme: dict[str, str], contrast_boost: float) -> Image.Image:
        """Create a duotone variation of the image."""
        # Make a copy
        variation = img.copy()
        
        # Boost contrast
        enhancer = ImageEnhance.Contrast(variation)
        variation = enhancer.enhance(contrast_boost)
        
        # Convert to grayscale first
        gray = variation.convert('L')
        
        # Apply posterization for that silkscreen look
        gray = gray.point(lambda p: 0 if p < 128 else 255, mode='1')
        gray = gray.convert('L')
        
        # Create duotone effect
        primary_color = self._hex_to_rgb(color_scheme['primary'])
        secondary_color = self._hex_to_rgb(color_scheme['secondary'])
        
        # Vectorized duotone mapping using NumPy
        gray_array = np.array(gray)
        result = np.zeros((*gray_array.shape, 3), dtype=np.uint8)
        mask = gray_array > 128
        result[mask] = primary_color
        result[~mask] = secondary_color

        return Image.fromarray(result, 'RGB')
    
    def _add_thick_outline(self, img: Image.Image) -> Image.Image:
        """Add thick black outlines to the image."""
        # Create edge detection
        edges = img.convert('L').filter(ImageFilter.FIND_EDGES)
        edges = edges.point(lambda p: 0 if p > 50 else 255, mode='1')
        
        # Dilate edges to make them thicker
        for _ in range(3):  # Make outlines thicker
            edges = edges.filter(ImageFilter.MaxFilter(3))
        
        # Convert back to RGB
        edges_rgb = edges.convert('RGB')
        
        # Vectorized edge compositing using NumPy
        edges_array = np.array(edges_rgb)
        img_array = np.array(img)
        mask = edges_array[:, :, 0] < 128
        result_array = img_array.copy()
        result_array[mask] = [0, 0, 0]

        return Image.fromarray(result_array)
    
    def _create_quad_grid(self, variations: list[Image.Image]) -> Image.Image:
        """Create a 2x2 grid from four image variations."""
        if len(variations) != 4:
            raise ValueError("Need exactly 4 variations for quad grid")
        
        # Get dimensions
        img_width, img_height = variations[0].size
        
        # Create grid canvas
        grid_width = img_width * 2
        grid_height = img_height * 2
        grid = Image.new('RGB', (grid_width, grid_height), 'white')
        
        # Paste images in 2x2 grid
        positions = [
            (0, 0),                    # Top-left
            (img_width, 0),            # Top-right
            (0, img_height),           # Bottom-left
            (img_width, img_height)    # Bottom-right
        ]
        
        for i, (variation, pos) in enumerate(zip(variations, positions, strict=False)):
            grid.paste(variation, pos)
        
        return grid
    
    def _hex_to_rgb(self, hex_color: str) -> tuple[int, int, int]:
        """Convert hex color to RGB tuple."""
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    
    
    def get_variants(self) -> list[dict[str, Any]]:
        """Return available color scheme variants."""
        return [
            {
                "variant": scheme["name"],
                "display_name": f"Pop Art: {scheme['name']}",
                "params": {"color_scheme": scheme["name"]}
            }
            for scheme in WARHOL_COLOR_SCHEMES
        ]

    def list_available_color_schemes(self) -> list[dict[str, str]]:
        """Get list of available color schemes."""
        return [
            {"name": scheme["name"], "primary": scheme["primary"], "secondary": scheme["secondary"]}
            for scheme in WARHOL_COLOR_SCHEMES
        ]