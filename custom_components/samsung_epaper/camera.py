"""Camera entity for Samsung ePaper integration — display preview."""

import logging

from homeassistant.components.camera import Camera

_LOGGER = logging.getLogger(__name__)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import SamsungEpaperEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    async_add_entities([SamsungEpaperPreviewCamera(coordinator, entry)])


class SamsungEpaperPreviewCamera(SamsungEpaperEntity, Camera):
    _attr_name = "Display Preview"
    _attr_is_streaming = False

    def __init__(self, coordinator, entry):
        SamsungEpaperEntity.__init__(self, coordinator, entry)
        Camera.__init__(self)
        self._attr_unique_id = f"{entry.entry_id}_preview"

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        if not self.coordinator.data:
            return None
        asset_id = self.coordinator.data.get("current_asset_id")
        if not asset_id:
            return None
        try:
            return await self.coordinator.client.async_get_thumbnail(asset_id)
        except Exception:
            _LOGGER.debug("Failed to fetch thumbnail for %s", asset_id, exc_info=True)
            return None
