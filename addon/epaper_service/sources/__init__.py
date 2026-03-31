"""Content source registry."""

from .base import ContentSource
from .frontpages import FrontpagesSource

SOURCE_REGISTRY: dict[str, type[ContentSource]] = {
    "frontpages": FrontpagesSource,
}


def get_source(source_type: str) -> ContentSource:
    cls = SOURCE_REGISTRY.get(source_type)
    if not cls:
        raise ValueError(f"Unknown source type: {source_type}")
    return cls()
