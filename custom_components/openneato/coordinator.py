"""Data update coordinator for OpenNeato."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import OpenNeatoClient, OpenNeatoData, OpenNeatoError, OpenNeatoInfo
from .const import DOMAIN, REFRESH_AFTER_COMMAND, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

type OpenNeatoConfigEntry = ConfigEntry[OpenNeatoCoordinator]


class OpenNeatoCoordinator(DataUpdateCoordinator[OpenNeatoData]):
    """Polls one robot."""

    config_entry: OpenNeatoConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: OpenNeatoConfigEntry,
        client: OpenNeatoClient,
        info: OpenNeatoInfo,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {info.hostname}",
            update_interval=SCAN_INTERVAL,
        )
        self.client = client
        self.info = info

    async def _async_update_data(self) -> OpenNeatoData:
        try:
            return await self.client.async_get_data()
        except OpenNeatoError as err:
            raise UpdateFailed(str(err)) from err

    async def async_command(self, coro) -> None:
        """Run a command, then refresh shortly after."""
        await coro
        await asyncio.sleep(REFRESH_AFTER_COMMAND)
        await self.async_request_refresh()
