"""Base entity for Samsung ePaper integration."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DISPLAY_NAME, DOMAIN
from .coordinator import SamsungEpaperCoordinator


class SamsungEpaperEntity(CoordinatorEntity[SamsungEpaperCoordinator]):
    _attr_has_entity_name = True

    def __init__(
        self, coordinator: SamsungEpaperCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        display = coordinator.data.get("display", {})
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get(CONF_DISPLAY_NAME, "Samsung ePaper"),
            manufacturer="Samsung",
            model=display.get("model_name", "ePaper Display"),
            serial_number=display.get("serial_number"),
        )
