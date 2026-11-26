"""The OpenNeato integration."""

from __future__ import annotations

import shutil

from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import OpenNeatoClient, OpenNeatoError
from .const import DOMAIN
from .coordinator import OpenNeatoConfigEntry, OpenNeatoCoordinator

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.IMAGE,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.UPDATE,
    Platform.VACUUM,
]


async def async_setup_entry(hass: HomeAssistant, entry: OpenNeatoConfigEntry) -> bool:
    """Set up OpenNeato from a config entry."""
    client = OpenNeatoClient(entry.data[CONF_HOST], async_get_clientsession(hass))
    try:
        info = await client.async_get_info()
    except OpenNeatoError as err:
        raise ConfigEntryNotReady(f"Cannot reach OpenNeato at {client.host}: {err}") from err

    coordinator = OpenNeatoCoordinator(hass, entry, client, info)
    await coordinator.async_load_maps()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: OpenNeatoConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: OpenNeatoConfigEntry) -> None:
    """Delete the archived maps when the robot is removed."""
    if entry.unique_id:
        await hass.async_add_executor_job(
            shutil.rmtree, hass.config.path(DOMAIN, entry.unique_id), True
        )
