"""Select entities for Samsung ePaper integration."""

from homeassistant.components.select import SelectEntity
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
    async_add_entities([
        SamsungEpaperPresetSelect(coordinator, entry),
        SamsungEpaperFavouriteSelect(coordinator, entry),
    ])


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

    @property
    def options(self) -> list[str]:
        return [f.get("name") or "Untitled" for f in self.coordinator.favourites]

    @property
    def current_option(self) -> str | None:
        return self._current

    async def async_select_option(self, option: str) -> None:
        for f in self.coordinator.favourites:
            name = f.get("name") or "Untitled"
            if name == option:
                await self.coordinator.client.async_display_favourite(f["id"])
                self._current = option
                self.async_write_ha_state()
                await self.coordinator.async_request_refresh()
                return
