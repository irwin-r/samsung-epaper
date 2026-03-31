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

    def __init__(self, session: aiohttp.ClientSession, base_url: str):
        self.session = session
        self.base_url = base_url.rstrip("/")

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

    async def _async_update_data(self) -> dict:
        try:
            status = await self.client.async_get_status()
            self.presets = await self.client.async_get_presets()
            return status
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Error communicating with addon: {err}") from err
