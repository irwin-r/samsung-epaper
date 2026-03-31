"""Sensor entities for Samsung ePaper integration."""

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import SamsungEpaperEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    async_add_entities(
        [
            SamsungEpaperStatusSensor(coordinator, entry),
            SamsungEpaperBatterySensor(coordinator, entry),
            SamsungEpaperContentSensor(coordinator, entry),
        ]
    )


class SamsungEpaperStatusSensor(SamsungEpaperEntity, SensorEntity):
    _attr_name = "Status"
    _attr_icon = "mdi:monitor"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_status"

    @property
    def native_value(self) -> str:
        if not self.coordinator.data:
            return "unknown"
        if self.coordinator.data.get("is_updating"):
            return "updating"
        return self.coordinator.data.get("last_update_status", "unknown")

    @property
    def extra_state_attributes(self):
        if not self.coordinator.data:
            return {}
        return {
            "last_update": self.coordinator.data.get("last_update"),
            "is_updating": self.coordinator.data.get("is_updating", False),
        }


class SamsungEpaperBatterySensor(SamsungEpaperEntity, SensorEntity):
    _attr_name = "Battery"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_battery"

    @property
    def native_value(self) -> int | None:
        if not self.coordinator.data:
            return None
        display = self.coordinator.data.get("display", {})
        return display.get("battery_percent")

    @property
    def extra_state_attributes(self):
        if not self.coordinator.data:
            return {}
        display = self.coordinator.data.get("display", {})
        return {"charging_state": display.get("charging_state")}


class SamsungEpaperContentSensor(SamsungEpaperEntity, SensorEntity):
    _attr_name = "Current Content"
    _attr_icon = "mdi:image"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_content"

    @property
    def native_value(self) -> str | None:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("active_preset_name")

    @property
    def extra_state_attributes(self):
        return {
            "asset_id": self.coordinator.data.get("current_asset_id"),
            "preset_id": self.coordinator.data.get("active_preset_id"),
        }
