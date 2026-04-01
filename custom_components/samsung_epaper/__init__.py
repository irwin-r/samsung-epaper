"""Samsung ePaper Display integration for Home Assistant."""

import logging

import voluptuous as vol

from homeassistant.components.camera import async_get_image
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_ADDON_URL,
    DOMAIN,
    PLATFORMS,
    SERVICE_CREATE_SCHEDULE,
    SERVICE_DELETE_SCHEDULE,
    SERVICE_DISPLAY_ASSET,
    SERVICE_DISPLAY_PRESET,
    SERVICE_DISPLAY_FAVOURITE,
    SERVICE_DISPLAY_URL,
    SERVICE_GENERATE_ART,
    SERVICE_GENERATE_FRONTPAGE,
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
SERVICE_DISPLAY_FAVOURITE_SCHEMA = vol.Schema(
    {vol.Required("favourite_name"): str}
)
SERVICE_DISPLAY_URL_SCHEMA = vol.Schema(
    {
        vol.Required("url"): str,
        vol.Optional("title", default="URL Image"): str,
    }
)
SERVICE_CREATE_SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Required("name"): str,
        vol.Required("preset_id"): str,
        vol.Required("cron_expression"): str,
    }
)
SERVICE_DELETE_SCHEDULE_SCHEMA = vol.Schema(
    {vol.Required("schedule_id"): str}
)
SERVICE_GENERATE_ART_SCHEMA = vol.Schema(
    {
        vol.Optional("camera_entity_id"): str,
        vol.Optional("image_url"): str,
        vol.Optional("art_type", default="random"): str,
        vol.Optional("variant"): str,
    }
)
SERVICE_GENERATE_FRONTPAGE_SCHEMA = vol.Schema(
    {vol.Optional("publication", default="smh"): str}
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    client = SamsungEpaperApiClient(
        session, entry.data[CONF_ADDON_URL],
        auth_token=entry.data.get("auth_token", ""),
    )

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
            for service in (
                SERVICE_DISPLAY_PRESET, SERVICE_DISPLAY_ASSET,
                SERVICE_DISPLAY_URL, SERVICE_REFRESH,
                SERVICE_CREATE_SCHEDULE, SERVICE_DELETE_SCHEDULE,
                SERVICE_GENERATE_ART, SERVICE_GENERATE_FRONTPAGE,
            ):
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

    async def handle_display_favourite(call: ServiceCall) -> None:
        favourite_name = call.data["favourite_name"]
        for entry_data in hass.data.get(DOMAIN, {}).values():
            client = entry_data["client"]
            coordinator = entry_data["coordinator"]
            # Find favourite by name
            for f in coordinator.favourites:
                if (f.get("name") or "") == favourite_name:
                    await client.async_display_favourite(f["id"])
                    await coordinator.async_request_refresh()
                    return
            _LOGGER.warning("Favourite '%s' not found", favourite_name)

    async def handle_refresh(call: ServiceCall) -> None:
        for entry_data in hass.data.get(DOMAIN, {}).values():
            client = entry_data["client"]
            coordinator = entry_data["coordinator"]
            await client.async_trigger_update()
            await coordinator.async_request_refresh()

    async def handle_create_schedule(call: ServiceCall) -> None:
        name = call.data["name"]
        preset_id = call.data["preset_id"]
        cron_expression = call.data["cron_expression"]
        for entry_data in hass.data.get(DOMAIN, {}).values():
            client = entry_data["client"]
            coordinator = entry_data["coordinator"]
            await client.async_create_schedule(name, preset_id, cron_expression)
            await coordinator.async_request_refresh()

    async def handle_delete_schedule(call: ServiceCall) -> None:
        schedule_id = call.data["schedule_id"]
        for entry_data in hass.data.get(DOMAIN, {}).values():
            client = entry_data["client"]
            coordinator = entry_data["coordinator"]
            await client.async_delete_schedule(schedule_id)
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
    hass.services.async_register(
        DOMAIN, SERVICE_DISPLAY_FAVOURITE, handle_display_favourite,
        schema=SERVICE_DISPLAY_FAVOURITE_SCHEMA,
    )
    hass.services.async_register(DOMAIN, SERVICE_REFRESH, handle_refresh)
    hass.services.async_register(
        DOMAIN, SERVICE_CREATE_SCHEDULE, handle_create_schedule,
        schema=SERVICE_CREATE_SCHEDULE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_DELETE_SCHEDULE, handle_delete_schedule,
        schema=SERVICE_DELETE_SCHEDULE_SCHEMA,
    )

    async def handle_generate_art(call: ServiceCall) -> None:
        camera_entity_id = call.data.get("camera_entity_id")
        image_url = call.data.get("image_url")
        art_type = call.data.get("art_type", "random")
        variant = call.data.get("variant")

        if not camera_entity_id and not image_url:
            _LOGGER.error("generate_art requires camera_entity_id or image_url")
            return

        photo_bytes = None
        if camera_entity_id:
            try:
                image = await async_get_image(hass, camera_entity_id)
                photo_bytes = image.content
            except Exception:
                _LOGGER.exception("Failed to get image from camera %s", camera_entity_id)
                return
        elif image_url:
            try:
                session = async_get_clientsession(hass)
                async with session.get(image_url) as resp:
                    if resp.status == 200:
                        photo_bytes = await resp.read()
            except Exception:
                _LOGGER.exception("Failed to fetch image from URL %s", image_url)
                return

        if not photo_bytes:
            _LOGGER.error("Failed to obtain photo for art generation")
            return

        for entry_data in hass.data.get(DOMAIN, {}).values():
            client = entry_data["client"]
            coordinator = entry_data["coordinator"]
            await client.async_generate_art(
                photo_bytes, art_type=art_type, variant=variant,
            )
            await coordinator.async_request_refresh()

    async def handle_generate_frontpage(call: ServiceCall) -> None:
        publication = call.data.get("publication", "smh")
        for entry_data in hass.data.get(DOMAIN, {}).values():
            client = entry_data["client"]
            coordinator = entry_data["coordinator"]
            await client.async_generate_frontpage(publication)
            await coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN, SERVICE_GENERATE_ART, handle_generate_art,
        schema=SERVICE_GENERATE_ART_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_GENERATE_FRONTPAGE, handle_generate_frontpage,
        schema=SERVICE_GENERATE_FRONTPAGE_SCHEMA,
    )
