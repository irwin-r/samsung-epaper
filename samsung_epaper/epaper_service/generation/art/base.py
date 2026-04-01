"""
Base art generator abstract class.
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional


class ArtGeneratorConfig:
    """Configuration for art generators."""
    
    def __init__(self, output_dimensions: tuple[int, int] = (1024, 1792), **kwargs):
        """
        Initialize art generator configuration.
        
        Args:
            output_dimensions: Output image dimensions (width, height)
            **kwargs: Additional generator-specific configuration
        """
        self.output_width, self.output_height = output_dimensions
        self.extra_config = kwargs


class ArtGenerator(ABC):
    """Abstract base class for art generators."""

    ART_TYPE_NAME: str = ""
    ART_TYPE_DESCRIPTION: str = ""

    def __init__(self, config: Optional[ArtGeneratorConfig] = None):
        """
        Initialize the art generator.

        Args:
            config: Configuration for the art generator
        """
        self.config = config or ArtGeneratorConfig()

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the name of this art generator."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Return a description of what this art generator creates."""
        pass

    def get_variants(self) -> list[dict[str, Any]]:
        """Return available variants/options for this generator.

        Each variant is a dict with:
            - variant: str identifier
            - display_name: str for display
            - params: dict of kwargs to pass to generate()
        """
        return [{"variant": "default", "display_name": self.name, "params": {}}]
    
    @abstractmethod
    def generate(
        self, 
        input_images: list[str], 
        output_path: str,
        **kwargs
    ) -> str:
        """
        Generate art from input images.
        
        Args:
            input_images: List of paths to input images
            output_path: Path where the generated art should be saved
            **kwargs: Additional generator-specific parameters
            
        Returns:
            Path to the generated artwork
            
        Raises:
            ArtGenerationError: If generation fails
        """
        pass
    
    @abstractmethod
    def get_required_resources(self) -> dict[str, Any]:
        """
        Get the resources required by this generator.
        
        Returns:
            Dictionary describing required resources (e.g., templates, models, etc.)
        """
        pass
    
    def validate_inputs(self, input_images: list[str]) -> bool:
        """
        Validate that input images exist and are accessible.
        
        Args:
            input_images: List of image paths to validate
            
        Returns:
            True if all inputs are valid, False otherwise
        """
        for image_path in input_images:
            if not Path(image_path).exists():
                return False
        return True


class ArtGenerationError(Exception):
    """Custom exception for art generation errors."""
    pass