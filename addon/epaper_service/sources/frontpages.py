"""Newspaper front page source — scrapes frontpages.com."""

import asyncio
import logging
from datetime import datetime
from pathlib import Path

import aiohttp
from bs4 import BeautifulSoup

from .base import ContentSource

logger = logging.getLogger(__name__)


class FrontpagesSource(ContentSource):
    source_type = "frontpages"

    async def fetch(self, config: dict, data_dir: Path) -> tuple[Path, dict]:
        url = config["url"]
        pattern = config["image_pattern"]
        timeout = aiohttp.ClientTimeout(total=30)

        logger.info(f"Fetching front page from {url}")

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as response:
                if response.status != 200:
                    raise Exception(f"Failed to fetch page: HTTP {response.status}")
                html = await response.text()

        soup = BeautifulSoup(html, "html.parser")
        image_url = self._find_image_url(soup, pattern)

        if not image_url:
            raise Exception("Could not find newspaper front page image URL on page")

        logger.info(f"Downloading front page image: {image_url}")

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(image_url) as response:
                if response.status != 200:
                    raise Exception(f"Failed to download image: HTTP {response.status}")
                image_data = await response.read()

        output_path = data_dir / f"frontpage_{datetime.now():%Y%m%d_%H%M%S}.png"
        await asyncio.to_thread(output_path.write_bytes, image_data)
        logger.info(f"Downloaded: {output_path} ({len(image_data):,} bytes)")

        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else "Newspaper Front Page"

        metadata = {
            "title": title,
            "source_id": url,
            "metadata_json": None,
        }
        return output_path, metadata

    async def validate_config(self, config: dict) -> bool:
        return bool(config.get("url") and config.get("image_pattern"))

    def _find_image_url(self, soup: BeautifulSoup, pattern: str) -> str | None:
        # Strategy 1: Find @2x srcset image matching pattern (best quality)
        for img in soup.find_all("img"):
            srcset = img.get("srcset", "")
            src = img.get("src", "")
            if pattern in srcset or pattern in src:
                if "@2x" in srcset:
                    url_part = srcset.split("@2x")[0] + "@2x.webp"
                    url_part = url_part.strip().split()[0]
                    if not url_part.startswith("http"):
                        url_part = f"https://www.frontpages.com{url_part}"
                    return url_part
                elif pattern in src:
                    if not src.startswith("http"):
                        src = f"https://www.frontpages.com{src}"
                    return src

        # Strategy 2: Find image in /t/ path matching pattern
        for img in soup.find_all("img"):
            src = img.get("src", "")
            if "/t/" in src and pattern in src:
                base = src.rsplit(".", 1)[0]
                ext = src.rsplit(".", 1)[1] if "." in src else "webp"
                twox_url = f"{base}@2x.{ext}"
                if not twox_url.startswith("http"):
                    twox_url = f"https://www.frontpages.com{twox_url}"
                return twox_url

        # Strategy 3: Extract from og:image meta tag
        og_image = soup.find("meta", property="og:image")
        if og_image and og_image.get("content"):
            og_url = og_image["content"]
            if "/g/" in og_url:
                og_url = og_url.replace("/g/", "/t/")
                if og_url.endswith(".webp.jpg"):
                    og_url = og_url[:-4]
                base = og_url.rsplit(".", 1)[0]
                ext = og_url.rsplit(".", 1)[1] if "." in og_url else "webp"
                og_url = f"{base}@2x.{ext}"
            return og_url

        # Strategy 4: Fallback — any image with /t/ path
        for img in soup.find_all("img"):
            src = img.get("src", "")
            if "/t/" in src and src.endswith(".webp"):
                if not src.startswith("http"):
                    src = f"https://www.frontpages.com{src}"
                return src

        return None
