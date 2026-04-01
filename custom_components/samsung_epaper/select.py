"""Select entities for Samsung ePaper integration."""

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import SamsungEpaperEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    _LOGGER.warning("samsung_epaper select setup: creating 2 entities (preset + favourite)")
    _LOGGER.warning("samsung_epaper favourites count: %d", len(coordinator.favourites))
    entities = [
        SamsungEpaperPresetSelect(coordinator, entry),
        SamsungEpaperFavouriteSelect(coordinator, entry),
    ]
    _LOGGER.warning("samsung_epaper adding %d select entities", len(entities))
    async_add_entities(entities)


class SamsungEpaperPresetSelect(SamsungEpaperEntity, SelectEntity):
    _attr_name = "Active Preset"
    _attr_icon = "mdi:palette"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_preset"

    @property
    def options(self) -> list[str]:
        return [p["name"] for p in self.coordinator.presets]

    @property
    def current_option(self) -> str | None:
        if not self.coordinator.data:
            return None
        active_id = self.coordinator.data.get("active_preset_id")
        for p in self.coordinator.presets:
            if p["id"] == active_id:
                return p["name"]
        return None

    async def async_select_option(self, option: str) -> None:
        for p in self.coordinator.presets:
            if p["name"] == option:
                await self.coordinator.client.async_activate_preset(p["id"])
                await self.coordinator.async_request_refresh()
                return


class SamsungEpaperFavouriteSelect(SamsungEpaperEntity, SelectEntity):
    _attr_name = "Display Favourite"
    _attr_icon = "mdi:heart"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_favourite"
        self._current = None

    def _fav_name(self, f: dict, idx: int) -> str:
        """Build a unique display name for a favourite."""
        name = f.get("name") or f.get("asset_title") or f"Image {idx + 1}"
        return name

    def _fav_options(self) -> list[tuple[str, str]]:
        """Return list of (display_name, fav_id) ensuring unique names."""
        seen = {}
        result = []
        for i, f in enumerate(self.coordinator.favourites):
            name = self._fav_name(f, i)
            if name in seen:
                seen[name] += 1
                name = f"{name} ({seen[name]})"
            else:
                seen[name] = 1
            result.append((name, f["id"]))
        return result

    @property
    def options(self) -> list[str]:
        opts = [name for name, _ in self._fav_options()]
        return opts if opts else ["(No favourites)"]

    @property
    def current_option(self) -> str | None:
        return self._current

    async def async_select_option(self, option: str) -> None:
        for name, fav_id in self._fav_options():
            if name == option:
                await self.coordinator.client.async_display_favourite(fav_id)
                self._current = option
                self.async_write_ha_state()
                await self.coordinator.async_request_refresh()
                return
