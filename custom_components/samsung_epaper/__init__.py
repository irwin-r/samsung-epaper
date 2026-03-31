"""Samsung ePaper Display integration for Home Assistant."""

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_ADDON_URL,
    DOMAIN,
    PLATFORMS,
    SERVICE_DISPLAY_ASSET,
    SERVICE_DISPLAY_PRESET,
    SERVICE_DISPLAY_URL,
    SERVICE_REFRESH,
)
from .coordinator import SamsungEpaperApiClient, SamsungEpaperCoordinator

_LOGGER = logging.getLogger(__name__)

SERVICE_DISPLAY_PRESET_SCHEMA = vol.Schema(
    {vol.Required("preset_name"): str}
)
SERVICE_DISPLAY_ASSET_SCHEMA = vol.Schema(
    {vol.Required("asset_id"): str}
)
SERVICE_DISPLAY_URL_SCHEMA = vol.Schema(
    {
        vol.Required("url"): str,
        vol.Optional("title", default="URL Image"): str,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    client = SamsungEpaperApiClient(session, entry.data[CONF_ADDON_URL])

    coordinator = SamsungEpaperCoordinator(hass, client)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _async_setup_services(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        if not hass.data[DOMAIN]:
            for service in (SERVICE_DISPLAY_PRESET, SERVICE_DISPLAY_ASSET, SERVICE_DISPLAY_URL, SERVICE_REFRESH):
                hass.services.async_remove(DOMAIN, service)
    return unload_ok


def _async_setup_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_REFRESH):
        return

    async def handle_display_preset(call: ServiceCall) -> None:
        preset_name = call.data["preset_name"]
        for entry_data in hass.data.get(DOMAIN, {}).values():
            client = entry_data["client"]
            coordinator = entry_data["coordinator"]
            for p in coordinator.presets:
                if p["name"] == preset_name:
                    await client.async_activate_preset(p["id"])
                    await client.async_trigger_update(preset_id=p["id"])
                    await coordinator.async_request_refresh()

    async def handle_display_asset(call: ServiceCall) -> None:
        asset_id = call.data["asset_id"]
        for entry_data in hass.data.get(DOMAIN, {}).values():
            client = entry_data["client"]
            coordinator = entry_data["coordinator"]
            await client.async_display_asset(asset_id)
            await coordinator.async_request_refresh()

    async def handle_display_url(call: ServiceCall) -> None:
        url = call.data["url"]
        title = call.data.get("title", "URL Image")
        for entry_data in hass.data.get(DOMAIN, {}).values():
            client = entry_data["client"]
            coordinator = entry_data["coordinator"]
            await client.async_display_url(url, title)
            await coordinator.async_request_refresh()

    async def handle_refresh(call: ServiceCall) -> None:
        for entry_data in hass.data.get(DOMAIN, {}).values():
            client = entry_data["client"]
            coordinator = entry_data["coordinator"]
            await client.async_trigger_update()
            await coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN, SERVICE_DISPLAY_PRESET, handle_display_preset,
        schema=SERVICE_DISPLAY_PRESET_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_DISPLAY_ASSET, handle_display_asset,
        schema=SERVICE_DISPLAY_ASSET_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_DISPLAY_URL, handle_display_url,
        schema=SERVICE_DISPLAY_URL_SCHEMA,
    )
    hass.services.async_register(DOMAIN, SERVICE_REFRESH, handle_refresh)
