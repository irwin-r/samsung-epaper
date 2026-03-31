"""Abstract base class for content sources."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


class ContentSource(ABC):
    source_type: str

    @abstractmethod
    async def fetch(self, config: dict, data_dir: Path) -> tuple[Path, dict]:
        """Fetch content and return (raw_image_path, metadata).

        The returned Path is a file in data_dir that the caller will
        move into asset storage after processing.

        metadata dict should contain optional keys:
            title, source_id, metadata_json
        """
        ...

    @abstractmethod
    async def validate_config(self, config: dict) -> bool:
        """Validate source-specific configuration."""
        ...
