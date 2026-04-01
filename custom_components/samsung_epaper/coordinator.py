"""DataUpdateCoordinator for Samsung ePaper integration."""

import logging
from datetime import timedelta

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class SamsungEpaperApiClient:
    """Client for the Samsung ePaper addon API."""

    def __init__(self, session: aiohttp.ClientSession, base_url: str, auth_token: str = ""):
        self.session = session
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token

    async def async_get_status(self) -> dict:
        async with self.session.get(f"{self.base_url}/api/status") as resp:
            resp.raise_for_status()
            return await resp.json()

    async def async_trigger_update(self, preset_id: str | None = None) -> dict:
        payload = {}
        if preset_id:
            payload["preset_id"] = preset_id
        async with self.session.post(
            f"{self.base_url}/api/update", json=payload
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def async_display_asset(self, asset_id: str) -> dict:
        async with self.session.post(
            f"{self.base_url}/api/display", json={"asset_id": asset_id}
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def async_get_presets(self) -> list[dict]:
        async with self.session.get(f"{self.base_url}/api/presets") as resp:
            resp.raise_for_status()
            return await resp.json()

    async def async_activate_preset(self, preset_id: str) -> dict:
        async with self.session.post(
            f"{self.base_url}/api/presets/{preset_id}/activate"
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def async_get_assets(self, limit: int = 50) -> list[dict]:
        async with self.session.get(
            f"{self.base_url}/api/assets", params={"limit": limit}
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def async_get_thumbnail(self, asset_id: str) -> bytes:
        async with self.session.get(
            f"{self.base_url}/api/assets/{asset_id}/thumbnail"
        ) as resp:
            resp.raise_for_status()
            return await resp.read()

    async def async_get_favourites(self) -> list[dict]:
        async with self.session.get(f"{self.base_url}/api/favourites") as resp:
            resp.raise_for_status()
            return await resp.json()

    async def async_display_favourite(self, favourite_id: str) -> dict:
        async with self.session.post(
            f"{self.base_url}/api/favourites/{favourite_id}/display"
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def async_display_url(self, url: str, title: str = "URL Image") -> dict:
        async with self.session.post(
            f"{self.base_url}/api/display_url",
            params={"url": url, "title": title},
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def async_get_schedules(self) -> list[dict]:
        async with self.session.get(f"{self.base_url}/api/schedules") as resp:
            resp.raise_for_status()
            return await resp.json()

    async def async_create_schedule(
        self, name: str, preset_id: str, cron_expression: str
    ) -> dict:
        async with self.session.post(
            f"{self.base_url}/api/schedules",
            json={
                "name": name,
                "preset_id": preset_id,
                "cron_expression": cron_expression,
            },
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def async_update_schedule(
        self, schedule_id: str, **kwargs
    ) -> dict:
        async with self.session.put(
            f"{self.base_url}/api/schedules/{schedule_id}",
            json=kwargs,
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def async_delete_schedule(self, schedule_id: str) -> dict:
        async with self.session.delete(
            f"{self.base_url}/api/schedules/{schedule_id}"
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def async_generate_art(
        self,
        photo_bytes: bytes,
        art_type: str = "random",
        variant: str | None = None,
        filename: str = "photo.jpg",
    ) -> dict:
        """Submit an art generation job with a photo."""
        data = aiohttp.FormData()
        data.add_field("photo", photo_bytes, filename=filename, content_type="image/jpeg")
        data.add_field("art_type", art_type)
        if variant:
            data.add_field("variant", variant)
        headers = {}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        async with self.session.post(
            f"{self.base_url}/api/generate/art", data=data, headers=headers
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def async_generate_frontpage(self, publication: str = "smh") -> dict:
        """Fetch a newspaper front page by publication key."""
        data = aiohttp.FormData()
        data.add_field("publication", publication)
        headers = {}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        async with self.session.post(
            f"{self.base_url}/api/generate/frontpage", data=data, headers=headers
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def async_get_generation_types(self) -> dict:
        """Get available art types and publications."""
        async with self.session.get(
            f"{self.base_url}/api/generate/types"
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def async_get_job_status(self, job_id: str) -> dict:
        """Poll generation job status."""
        async with self.session.get(
            f"{self.base_url}/api/generate/jobs/{job_id}"
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def async_health_check(self) -> bool:
        try:
            async with self.session.get(
                f"{self.base_url}/api/health",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                return resp.status == 200
        except Exception:
            return False


class SamsungEpaperCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, client: SamsungEpaperApiClient):
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.client = client
        self.presets: list[dict] = []
        self.schedules: list[dict] = []
        self.favourites: list[dict] = []

    async def _async_update_data(self) -> dict:
        try:
            status = await self.client.async_get_status()
            self.presets = await self.client.async_get_presets()
            self.schedules = await self.client.async_get_schedules()
            self.favourites = await self.client.async_get_favourites()
            return status
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Error communicating with addon: {err}") from err
