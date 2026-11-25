"""Config flow for OpenNeato."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    OpenNeatoClient,
    OpenNeatoConnectionError,
    OpenNeatoInfo,
    OpenNeatoNotSupportedError,
)
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema({vol.Required(CONF_HOST): str})


class OpenNeatoConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for OpenNeato."""

    VERSION = 1

    async def _async_probe(self, host: str) -> tuple[OpenNeatoInfo | None, str | None]:
        client = OpenNeatoClient(host, async_get_clientsession(self.hass))
        try:
            return await client.async_get_info(), None
        except OpenNeatoNotSupportedError:
            return None, "not_openneato"
        except OpenNeatoConnectionError:
            return None, "cannot_connect"
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Unexpected error probing %s", host)
            return None, "unknown"

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            info, error = await self._async_probe(host)
            if info:
                await self.async_set_unique_id(info.unique_id)
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                return self.async_create_entry(
                    title=info.hostname, data={CONF_HOST: host}
                )
            errors["base"] = error or "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(STEP_USER_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the IP address/hostname of an existing robot."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            info, error = await self._async_probe(host)
            if info:
                await self.async_set_unique_id(info.unique_id)
                self._abort_if_unique_id_mismatch(reason="wrong_robot")
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_HOST: host}
                )
            errors["base"] = error or "unknown"

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_SCHEMA, user_input or entry.data
            ),
            errors=errors,
        )
