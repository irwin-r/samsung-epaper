"""Config flow for Samsung ePaper integration."""

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_ADDON_URL, CONF_DISPLAY_NAME, DOMAIN


class SamsungEpaperConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            url = user_input[CONF_ADDON_URL].rstrip("/")

            # Prevent duplicate entries for the same addon URL
            await self.async_set_unique_id(url)
            self._abort_if_unique_id_configured()

            try:
                session = async_get_clientsession(self.hass)
                async with session.get(
                    f"{url}/api/health",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status == 200:
                        user_input[CONF_ADDON_URL] = url
                        return self.async_create_entry(
                            title=user_input[CONF_DISPLAY_NAME],
                            data=user_input,
                        )
                    errors["base"] = "cannot_connect"
            except (aiohttp.ClientError, TimeoutError):
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDON_URL): str,
                    vol.Required(
                        CONF_DISPLAY_NAME, default="Samsung ePaper"
                    ): str,
                }
            ),
            errors=errors,
        )
