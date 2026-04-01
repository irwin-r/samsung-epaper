"""
Art generator factory and registry.
"""
import random

from typing import Optional

from .art_nouveau import ArtNouveauGenerator
from .base import ArtGenerator, ArtGeneratorConfig
from .classical import ClassicalArtGenerator
from .currency import CurrencyGenerator
from .film_noir import FilmNoirGenerator
from .magazine import MagazineCoverGenerator
from .marble_bust import MarbleBustGenerator
from .tabloid import TabloidArtGenerator
from .popart import PopArtGenerator
from .stained_glass import StainedGlassGenerator
from .tarot import TarotCardGenerator
from .wanted import WantedPosterGenerator

# Registry of available art generators
ART_GENERATORS: dict[str, type[ArtGenerator]] = {
    "tabloid": TabloidArtGenerator,
    "classical": ClassicalArtGenerator,
    "popart": PopArtGenerator,
    "magazine": MagazineCoverGenerator,
    "film_noir": FilmNoirGenerator,
    "tarot": TarotCardGenerator,
    "currency": CurrencyGenerator,
    "wanted": WantedPosterGenerator,
    "art_nouveau": ArtNouveauGenerator,
    "marble_bust": MarbleBustGenerator,
    "stained_glass": StainedGlassGenerator,
}


def get_available_art_types() -> list[str]:
    """Get list of available art generator types."""
    return list(ART_GENERATORS.keys())


def create_art_generator(
    art_type: str, 
    config: Optional[ArtGeneratorConfig] = None
) -> ArtGenerator:
    """
    Create an art generator of the specified type.
    
    Args:
        art_type: Type of art generator to create
        config: Configuration for the generator
        
    Returns:
        Art generator instance
        
    Raises:
        ValueError: If art_type is not recognized
    """
    if art_type not in ART_GENERATORS:
        raise ValueError(
            f"Unknown art type: {art_type}. "
            f"Available types: {', '.join(ART_GENERATORS.keys())}"
        )
    
    generator_class = ART_GENERATORS[art_type]
    return generator_class(config)


def create_random_art_generator(
    allowed_types: Optional[list[str]] = None,
    config: Optional[ArtGeneratorConfig] = None
) -> ArtGenerator:
    """
    Create a random art generator from available types.
    
    Args:
        allowed_types: List of allowed art types. If None, all types are allowed.
        config: Configuration for the generator
        
    Returns:
        Random art generator instance
    """
    if allowed_types:
        # Filter to only allowed types that exist
        valid_types = [t for t in allowed_types if t in ART_GENERATORS]
        if not valid_types:
            raise ValueError(f"No valid art types in {allowed_types}")
    else:
        valid_types = list(ART_GENERATORS.keys())
    
    selected_type = random.choice(valid_types)
    return create_art_generator(selected_type, config)


def get_art_generator_info(art_type: str) -> dict[str, str]:
    """
    Get information about a specific art generator without instantiating it.

    Args:
        art_type: Type of art generator

    Returns:
        Dictionary with name and description
    """
    if art_type not in ART_GENERATORS:
        raise ValueError(f"Unknown art type: {art_type}")

    cls = ART_GENERATORS[art_type]
    return {
        "type": art_type,
        "name": cls.ART_TYPE_NAME,
        "description": cls.ART_TYPE_DESCRIPTION
    }


def get_all_art_generators_info() -> list[dict[str, str]]:
    """Get information about all available art generators."""
    return [get_art_generator_info(art_type) for art_type in ART_GENERATORS]