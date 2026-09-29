"""Content source registry."""

from .base import ContentSource, StaleContentError
from .frontpages import FrontpagesSource
from .pagesuite import PageSuiteSource

SOURCE_REGISTRY: dict[str, type[ContentSource]] = {
    "frontpages": FrontpagesSource,
    "pagesuite": PageSuiteSource,
}


def get_source(source_type: str) -> ContentSource:
    cls = SOURCE_REGISTRY.get(source_type)
    if not cls:
        raise ValueError(f"Unknown source type: {source_type}")
    return cls()
