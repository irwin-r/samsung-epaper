"""
Font utilities for cross-platform font resolution.
"""
import logging
import os
import sys
from pathlib import Path

from PIL import ImageFont

logger = logging.getLogger(__name__)


class FontResolver:
    """Resolves font names to font files across different platforms."""
    
    def __init__(self):
        self.platform = sys.platform
        self._font_cache = {}
    
    def resolve_font(self, font_name: str, size: int) -> ImageFont.ImageFont:
        """
        Resolve a font name to a font object, trying common locations.
        
        Args:
            font_name: Font name like "Helvetica", "Times", "IBMPlexSerif-Bold", etc.
            size: Font size
        
        Returns:
            PIL ImageFont object
        """
        cache_key = f"{font_name}_{size}"
        if cache_key in self._font_cache:
            return self._font_cache[cache_key]
        
        font_paths = self._get_font_paths(font_name)
        
        # Try each path
        for font_path in font_paths:
            try:
                if Path(font_path).exists():
                    font = ImageFont.truetype(str(font_path), size)
                    self._font_cache[cache_key] = font
                    logger.debug(f"Loaded font {font_name} from {font_path}")
                    return font
            except Exception as e:
                logger.debug(f"Failed to load font from {font_path}: {e}")
                continue
        
        # Final fallback to default font
        logger.warning(f"Could not find font {font_name}, using default")
        try:
            font = ImageFont.load_default()
            self._font_cache[cache_key] = font
            return font
        except Exception:
            # Last resort - create a simple default font
            font = ImageFont.load_default()
            self._font_cache[cache_key] = font
            return font
    
    def _get_font_paths(self, font_name: str) -> list:
        """Get list of potential font paths for the given font name."""
        paths = []

        # Check FONT_DIR environment variable first
        font_dir = os.environ.get("FONT_DIR")
        if font_dir:
            font_dir_path = Path(font_dir)
            if font_dir_path.is_dir():
                name_variations = self._get_font_name_variations(font_name)
                for name in name_variations:
                    for ext in (".ttf", ".otf", ".ttc"):
                        paths.append(str(font_dir_path / f"{name}{ext}"))

        if self.platform == "darwin":  # macOS
            # Get common name variations
            name_variations = self._get_font_name_variations(font_name)
            
            for name in name_variations:
                paths.extend([
                    f"/System/Library/Fonts/{name}.ttc",
                    f"/System/Library/Fonts/{name}.ttf",
                    f"/System/Library/Fonts/{name}.otf",
                    f"/System/Library/Fonts/Supplemental/{name}.ttf",
                    f"/System/Library/Fonts/Supplemental/{name}.otf",
                    f"/Library/Fonts/{name}.ttf",
                    f"/Library/Fonts/{name}.otf",
                    f"/Users/{os.environ.get('USER', '')}/Library/Fonts/{name}.ttf",
                    f"/Users/{os.environ.get('USER', '')}/Library/Fonts/{name}.otf",
                ])
            
            # Add fallbacks
            paths.extend([
                "/System/Library/Fonts/Helvetica.ttc",
                "/System/Library/Fonts/Times.ttc",
            ])
        
        elif self.platform.startswith("linux"):  # Linux/Raspberry Pi
            paths.extend([
                f"/usr/share/fonts/truetype/dejavu/{font_name}.ttf",
                f"/usr/share/fonts/truetype/liberation/{font_name}.ttf",
                f"/usr/share/fonts/TTF/{font_name}.ttf",
                f"/usr/share/fonts/opentype/{font_name}.otf",
                f"/usr/local/share/fonts/{font_name}.ttf",
                f"/usr/local/share/fonts/{font_name}.otf",
                # Fallbacks
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            ])
        
        elif self.platform == "win32":  # Windows
            paths.extend([
                f"C:\\Windows\\Fonts\\{font_name}.ttf",
                f"C:\\Windows\\Fonts\\{font_name}.otf",
                # Fallbacks
                "C:\\Windows\\Fonts\\arial.ttf",
                "C:\\Windows\\Fonts\\times.ttf",
            ])
        
        return paths
    
    def _get_font_name_variations(self, font_name: str) -> list:
        """Get variations of font names to try."""
        variations = [font_name]
        
        # Handle Times New Roman PostScript names
        times_mappings = {
            'TimesNewRomanPS-BoldMT': [
                'TimesNewRomanPS BoldMT',
                'TimesNewRomanPS-BoldMT',
                'Times-Bold',
                'Times Bold',
            ],
            'TimesNewRomanPSMT': [
                'TimesNewRomanPSMT Regular',
                'TimesNewRomanPSMT',
                'Times-Roman',
                'Times',
                'Times Regular',
            ],
            'TimesNewRomanPS-ItalicMT': [
                'TimesNewRomanPS ItalicMT',
                'Times-Italic',
                'Times Italic',
            ],
            'TimesNewRomanPS-BoldItalicMT': [
                'TimesNewRomanPS BoldItalicMT',
                'Times-BoldItalic',
                'Times Bold Italic',
            ]
        }
        
        # Handle Helvetica variations
        helvetica_mappings = {
            'Helvetica-Bold': [
                'HelveticaBold',
                'Helvetica Bold',
                'Helvetica-Bold',
                'helvetica-bold',
                'HELVETICA-BOLD',
            ],
            'Helvetica': [
                'Helvetica Regular',
                'Helvetica',
                'helvetica',
                'HELVETICA',
            ]
        }
        
        # Handle Impact variations
        impact_mappings = {
            'Impact': [
                'Impact Regular',
                'Impact',
                'impact',
                'IMPACT',
            ]
        }
        
        if font_name in times_mappings:
            variations.extend(times_mappings[font_name])
        
        if font_name in helvetica_mappings:
            variations.extend(helvetica_mappings[font_name])
        
        if font_name in impact_mappings:
            variations.extend(impact_mappings[font_name])
        
        # General transformations
        variations.append(font_name.replace('-', ' '))  # Hyphen to space
        variations.append(font_name.replace(' ', '-'))  # Space to hyphen
        variations.append(font_name.replace(' ', ''))   # Remove spaces
        
        # Remove duplicates while preserving order
        seen = set()
        unique_variations = []
        for var in variations:
            if var not in seen:
                seen.add(var)
                unique_variations.append(var)
        
        return unique_variations


# Global font resolver instance
_font_resolver = None

def get_font_resolver() -> FontResolver:
    """Get the global font resolver instance."""
    global _font_resolver
    if _font_resolver is None:
        _font_resolver = FontResolver()
    return _font_resolver


def resolve_font(font_name: str, size: int) -> ImageFont.ImageFont:
    """Convenience function to resolve a font."""
    return get_font_resolver().resolve_font(font_name, size)