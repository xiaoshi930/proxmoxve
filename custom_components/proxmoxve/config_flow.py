from __future__ import annotations
import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv
from homeassistant.const import (
    CONF_NAME,
    CONF_HOST,
    CONF_PORT,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_VERIFY_SSL,
    CONF_SCAN_INTERVAL
)

CONF_SSH_PORT = "ssh_port"

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class PVEFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""
        errors = {}

        if user_input is not None:
            await self.async_set_unique_id(
                f"{DOMAIN}-{user_input[CONF_HOST]}-{user_input[CONF_PORT]}"
            )
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                    {
                        vol.Required(CONF_NAME, default="PVE"): str,
                        vol.Required(CONF_HOST, default="localhost"): str,
                        vol.Required(CONF_PORT, default=8006): vol.Coerce(int),
                        vol.Optional(CONF_SSH_PORT, default=22): vol.Coerce(int),
                        vol.Required(CONF_USERNAME, default="root@pam"): str,
                        vol.Required(CONF_PASSWORD): str,
                        vol.Required(CONF_VERIFY_SSL, default=False): bool,
                    }
            ),
            errors=errors,
        )


    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry
        self.config = dict(config_entry.data)

    async def async_step_init(self, user_input=None):

        if user_input is not None:
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data=user_input
            )
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                    {
                        vol.Required(CONF_VERIFY_SSL, default=self.config.get(CONF_VERIFY_SSL, False)): bool,
                    }
            ),
        )
