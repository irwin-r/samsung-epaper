"""Abstract base class for content sources."""

import os
from abc import ABC, abstractmethod
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo


class StaleContentError(Exception):
    """The source hasn't published today's edition yet."""


def local_tz() -> ZoneInfo:
    """Timezone that "today" and schedule cron expressions are read in.

    The service host runs on UTC, but editions and schedules follow the
    reader's local day.
    """
    return ZoneInfo(os.environ.get("LOCAL_TIMEZONE", "Australia/Sydney"))


def local_today() -> date:
    return datetime.now(local_tz()).date()


class ContentSource(ABC):
    source_type: str

    @abstractmethod
    async def fetch(self, config: dict, data_dir: Path) -> tuple[Path, dict]:
        """Fetch content and return (raw_image_path, metadata).

        The returned Path is a file in data_dir that the caller will
        move into asset storage after processing.

        metadata dict should contain optional keys:
            title, source_id, metadata_json

        Raise StaleContentError when config asks for today's edition
        (``require_today``) and the source only has an older one.
        """
        ...

    @abstractmethod
    async def validate_config(self, config: dict) -> bool:
        """Validate source-specific configuration."""
        ...
