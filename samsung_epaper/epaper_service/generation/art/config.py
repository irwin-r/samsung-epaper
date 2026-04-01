"""
Configuration management for the tabloid generator.
"""
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Dict


@dataclass
class FontConfig:
    """Font configuration data class."""
    name: str
    size: int
    color: tuple
    background: Optional[tuple] = None
    alignment: str = "left"  # "left", "center", "right"
    format_type: str = "single_line"  # "single_line", "multi_line"
    line_spacing: int = 2  # Additional spacing between lines (for multi_line format)
    text_transform: Optional[str] = None  # "uppercase", "lowercase", or None


@dataclass
class BoundingBox:
    """Bounding box data class."""
    x: int
    y: int
    width: int
    height: int
    
    @classmethod
    def from_tuple(cls, bbox_tuple: tuple) -> 'BoundingBox':
        """Create BoundingBox from (x, y, width, height) tuple."""
        return cls(*bbox_tuple)
    


@dataclass
class TemplateConfig:
    """Template configuration data class."""
    name: str
    image_path: str
    arrest_photo_bbox: BoundingBox
    headline_bbox: BoundingBox
    date_bbox: BoundingBox
    body_bbox: BoundingBox
    headline_font: FontConfig
    date_font: FontConfig
    body_font: FontConfig


@dataclass
class SamsungDisplaySettings:
    """Samsung EM32DX display settings."""
    enabled: bool = False
    host: str = ""
    pin: str = "0000"
    mac_address: Optional[str] = None
    auto_publish: bool = False
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SamsungDisplaySettings':
        """Create settings from dictionary."""
        return cls(
            enabled=data.get('enabled', False),
            host=data.get('host', ''),
            pin=data.get('pin') or os.getenv('SAMSUNG_DISPLAY_PIN', '0000'),
            mac_address=data.get('mac_address'),
            auto_publish=data.get('auto_publish', False)
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert settings to dictionary."""
        return {
            'enabled': self.enabled,
            'host': self.host,
            'pin': self.pin,
            'mac_address': self.mac_address,
            'auto_publish': self.auto_publish
        }


class Config:
    """Main configuration class."""
    
    def __init__(self, config_dir: str = "config"):
        self.config_dir = Path(config_dir)
        self.assets_dir = Path("assets")
        self.output_dir = Path("output")
        self._templates: dict[str, TemplateConfig] = {}
        self.samsung_display: SamsungDisplaySettings = SamsungDisplaySettings()
        self._load_config()
    
    def _load_config(self):
        """Load configuration from files."""
        # Ensure directories exist
        self.config_dir.mkdir(exist_ok=True)
        self.assets_dir.mkdir(exist_ok=True)
        self.output_dir.mkdir(exist_ok=True)
        
        # Load templates
        templates_file = self.config_dir / "templates.json"
        if templates_file.exists():
            with open(templates_file) as f:
                templates_data = json.load(f)
                self._load_templates_from_dict(templates_data)
        else:
            self._create_default_templates_config()
        
        # Load Samsung display settings
        display_file = self.config_dir / "samsung_display.json"
        if display_file.exists():
            with open(display_file) as f:
                display_data = json.load(f)
                self.samsung_display = SamsungDisplaySettings.from_dict(display_data)
        else:
            self._create_default_display_config()
    
    @staticmethod
    def _parse_font_config(font_data: dict) -> FontConfig:
        """Parse a font configuration dict into a FontConfig."""
        data = font_data.copy()
        data["color"] = tuple(data["color"])
        if data.get("background"):
            data["background"] = tuple(data["background"])
        data.setdefault("alignment", "left")
        data.setdefault("format_type", "single_line")
        data.setdefault("line_spacing", 2)
        return FontConfig(**data)

    def _load_templates_from_dict(self, templates_data: dict[str, Any]):
        """Load templates from dictionary data."""
        for name, template_data in templates_data.items():
            # Parse bounding boxes
            arrest_bbox = BoundingBox.from_tuple(template_data["arrest_photo_bbox"])
            headline_bbox = BoundingBox.from_tuple(template_data["headline_bbox"])
            date_bbox = BoundingBox.from_tuple(template_data["date_bbox"])
            body_bbox = BoundingBox.from_tuple(template_data["body_bbox"])
            
            # Parse fonts (convert color lists to tuples)
            fonts = template_data["fonts"]
            headline_font = self._parse_font_config(fonts["headline"])
            date_font = self._parse_font_config(fonts["date"])
            body_font = self._parse_font_config(fonts["body"])
            
            # Create template config
            template = TemplateConfig(
                name=name,
                image_path=template_data["image_path"],
                arrest_photo_bbox=arrest_bbox,
                headline_bbox=headline_bbox,
                date_bbox=date_bbox,
                body_bbox=body_bbox,
                headline_font=headline_font,
                date_font=date_font,
                body_font=body_font
            )
            
            self._templates[name] = template
    
    def _create_default_templates_config(self):
        """Create default templates configuration."""
        default_config = {
            "sydney_morning_herald": {
                "image_path": "assets/templates/sydney_morning_herald.jpg",
                "arrest_photo_bbox": [190, 425, 440, 440],
                "headline_bbox": [40, 280, 592, 140],
                "date_bbox": [40, 105, 88, 12],
                "body_bbox": [40, 450, 140, 415],
                "fonts": {
                    "headline": {
                        "name": "IBMPlexSerif-Bold",
                        "size": 40,
                        "color": [0, 0, 0],
                        "background": [255, 255, 255, 255]
                    },
                    "date": {
                        "name": "Helvetica",
                        "size": 8,
                        "color": [0, 0, 0],
                        "background": [255, 255, 255, 255]
                    },
                    "body": {
                        "name": "IBMPlexSerif-Regular",
                        "size": 9,
                        "color": [0, 0, 0],
                        "background": [255, 255, 255, 255]
                    }
                }
            }
        }
        
        # Save default config
        templates_file = self.config_dir / "templates.json"
        with open(templates_file, 'w') as f:
            json.dump(default_config, f, indent=2)
        
        # Load the default config
        self._load_templates_from_dict(default_config)
    
    def _create_default_display_config(self):
        """Create default Samsung display configuration."""
        default_config = {
            "enabled": False,
            "host": "",
            "pin": "0000",
            "mac_address": None,
            "auto_publish": False
        }
        
        # Save default config
        display_file = self.config_dir / "samsung_display.json"
        with open(display_file, 'w') as f:
            json.dump(default_config, f, indent=2)
        
        # Load the default config
        self.samsung_display = SamsungDisplaySettings.from_dict(default_config)
    
    def save_samsung_display_settings(self):
        """Save Samsung display settings to file."""
        display_file = self.config_dir / "samsung_display.json"
        with open(display_file, 'w') as f:
            json.dump(self.samsung_display.to_dict(), f, indent=2)
    
    def get_template(self, name: str) -> Optional[TemplateConfig]:
        """Get template configuration by name."""
        return self._templates.get(name)
    
    def get_available_templates(self) -> list:
        """Get list of available template names."""
        # Only return templates whose image files exist
        available = []
        for name, template in self._templates.items():
            image_path = Path(template.image_path)
            if image_path.exists():
                available.append(name)
        return available
    
    def get_random_template(self) -> Optional[TemplateConfig]:
        """Get a random available template."""
        import random
        available = self.get_available_templates()
        if not available:
            return None
        return self._templates[random.choice(available)]


# Global config instance
import os
import threading

_config = None
_config_lock = threading.Lock()

def get_config() -> Config:
    """Get the global configuration instance."""
    global _config
    with _config_lock:
        if _config is None:
            _config = Config()
        return _config