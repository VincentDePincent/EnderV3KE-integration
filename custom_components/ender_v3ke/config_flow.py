"""Config flow for the Ender V3KE integration."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_ENABLE_MQTT,
    CONF_EXPOSED_IMAGE_PATH,
    CONF_LOCAL_IMAGE_PATH,
    CONF_MAX_IMAGE_BYTES,
    CONF_MQTT_TOPIC,
    CONF_PUBLISH_INTERVAL,
    CONF_SNAPSHOT_URL,
    CONF_WS_URL,
    DEFAULT_EXPOSED_IMAGE_PATH,
    DEFAULT_LOCAL_IMAGE_PATH,
    DEFAULT_MAX_IMAGE_BYTES,
    DEFAULT_MQTT_TOPIC,
    DEFAULT_PUBLISH_INTERVAL,
    DEFAULT_SNAPSHOT_URL,
    DEFAULT_WS_URL,
    DOMAIN,
)


class EnderV3KEConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Ender V3KE."""

    VERSION = 1

    async def async_step_user(self, user_input=None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            return self._create_entry(user_input)

        data_schema = vol.Schema(
            {
                vol.Required(CONF_WS_URL, default=DEFAULT_WS_URL): str,
                vol.Required(CONF_MQTT_TOPIC, default=DEFAULT_MQTT_TOPIC): str,
                vol.Optional(CONF_ENABLE_MQTT, default=True): bool,
                vol.Optional(
                    CONF_SNAPSHOT_URL, default=DEFAULT_SNAPSHOT_URL
                ): str,
                vol.Optional(
                    CONF_LOCAL_IMAGE_PATH, default=DEFAULT_LOCAL_IMAGE_PATH
                ): str,
                vol.Optional(
                    CONF_EXPOSED_IMAGE_PATH, default=DEFAULT_EXPOSED_IMAGE_PATH
                ): str,
                vol.Optional(
                    CONF_PUBLISH_INTERVAL, default=DEFAULT_PUBLISH_INTERVAL
                ): vol.Coerce(float),
                vol.Optional(
                    CONF_MAX_IMAGE_BYTES, default=DEFAULT_MAX_IMAGE_BYTES
                ): vol.Coerce(int),
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

    def _create_entry(self, data: dict) -> FlowResult:
        title = data.get(CONF_WS_URL, "Ender V3KE")
        return self.async_create_entry(title=title, data=data)

    async def async_step_import(self, user_input: dict | None = None) -> FlowResult:
        return await self.async_step_user(user_input)
