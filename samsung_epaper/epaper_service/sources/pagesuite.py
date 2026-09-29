"""Newspaper front page from a PageSuite digital edition (Nine mastheads).

SMH, The Age and AFR publish their replica editions through PageSuite.
Each application has a ``published.json`` listing editions newest first;
each edition's ``edition.json`` links a high-res JPEG of every page. The
new edition lands around 15:00 UTC, i.e. 1-2am in Sydney, hours before
aggregators like frontpages.com pick it up.

Config:
    published_url   URL of the application's published.json
    name            masthead name used in the asset title
    require_today   raise StaleContentError unless the newest edition is
                    dated today in LOCAL_TIMEZONE (default True)
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

import aiohttp
from PIL import Image

from .base import ContentSource, StaleContentError, local_today, local_tz

logger = logging.getLogger(__name__)

# Nine's application feeds, found via the reader at edition.smh.com.au
PUBLICATIONS = {
    "smh": {
        "name": "The Sydney Morning Herald",
        "published_url": "https://d3eqybf73tu9r7.cloudfront.net/845a5db1-4b49-4e57-b053-afaf380e4f92/25250be9-a077-41bb-9088-76d5ca0e3f5c/published.json",
    },
    "the_age": {
        "name": "The Age",
        "published_url": "https://published.pagesuite.com/845a5db1-4b49-4e57-b053-afaf380e4f92/ed0b935a-fb91-4a54-959f-eaabdbc37830/published.json",
    },
    "afr": {
        "name": "The Australian Financial Review",
        "published_url": "https://d1hhd735agnr9c.cloudfront.net/845a5db1-4b49-4e57-b053-afaf380e4f92/b5c50dbf-4261-4bd9-a816-2530a82436c9/published.json",
    },
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
    )
}

# The page JPEG is ~3400x4700. The processor fits it to the 1440x2560
# viewport anyway, so shrink it here to keep memory down in the 256 MB LXC.
MAX_HEIGHT = 2560


class PageSuiteSource(ContentSource):
    source_type = "pagesuite"

    async def fetch(self, config: dict, data_dir: Path) -> tuple[Path, dict]:
        published_url = config["published_url"]
        name = config.get("name", "Front Page")
        timeout = aiohttp.ClientTimeout(total=60)

        async with aiohttp.ClientSession(timeout=timeout, headers=HEADERS) as session:
            logger.info(f"Fetching edition list from {published_url}")
            published = await self._get_json(session, published_url)
            edition = self._latest_edition(published)

            edition_day = (
                datetime.fromisoformat(edition["editionDate"].replace("Z", "+00:00"))
                .astimezone(local_tz())
                .date()
            )
            if config.get("require_today", True) and edition_day != local_today():
                raise StaleContentError(
                    f"{name}: newest edition is {edition_day} "
                    f"({edition.get('name')}), today is {local_today()}"
                )

            detail = await self._get_json(session, edition["editionLink"])
            page = detail["pages"][0]
            image_url = page.get("highRes") or page["screenshoturlOriginalFull"]

            logger.info(f"Downloading {edition.get('name')} page 1: {image_url}")
            async with session.get(image_url) as response:
                if response.status != 200:
                    raise Exception(f"Failed to download image: HTTP {response.status}")
                image_data = await response.read()

        raw_path = data_dir / f"pagesuite_{edition['editionGUID']}.jpg"
        output_path = data_dir / f"frontpage_{datetime.now():%Y%m%d_%H%M%S}.png"
        await asyncio.to_thread(raw_path.write_bytes, image_data)
        await asyncio.to_thread(self._shrink, raw_path, output_path)
        raw_path.unlink(missing_ok=True)
        logger.info(f"Downloaded: {output_path} ({len(image_data):,} bytes original)")

        return output_path, {
            "title": f"{name} — {edition_day:%d/%m/%Y}",
            "source_id": published_url,
            "metadata_json": json.dumps(
                {
                    "edition_guid": edition["editionGUID"],
                    "edition_name": edition.get("name"),
                    "edition_date": edition["editionDate"],
                }
            ),
        }

    async def validate_config(self, config: dict) -> bool:
        return bool(config.get("published_url"))

    @staticmethod
    async def _get_json(session: aiohttp.ClientSession, url: str):
        async with session.get(url) as response:
            if response.status != 200:
                raise Exception(f"Failed to fetch {url}: HTTP {response.status}")
            return await response.json(content_type=None)

    @staticmethod
    def _latest_edition(published: list) -> dict:
        editions = [
            e
            for day in published
            for e in day.get("editions", [])
            if e.get("isLive", True) and not e.get("isSupplement")
        ]
        if not editions:
            raise Exception("PageSuite edition list is empty")
        return max(editions, key=lambda e: e["editionDate"])

    @staticmethod
    def _shrink(src: Path, dest: Path) -> None:
        with Image.open(src) as img:
            img.draft("RGB", (img.width * MAX_HEIGHT // img.height, MAX_HEIGHT))
            img = img.convert("RGB")
            if img.height > MAX_HEIGHT:
                img = img.resize(
                    (img.width * MAX_HEIGHT // img.height, MAX_HEIGHT),
                    Image.Resampling.LANCZOS,
                )
            img.save(dest, format="PNG")
