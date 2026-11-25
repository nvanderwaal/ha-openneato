"""Data update coordinator for OpenNeato."""

from __future__ import annotations

import asyncio
import logging
import time

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import OpenNeatoClient, OpenNeatoData, OpenNeatoError, OpenNeatoInfo
from .const import DOMAIN, HISTORY_INTERVAL, REFRESH_AFTER_COMMAND, SCAN_INTERVAL

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
        self._last_clean: dict | None = None
        self._history_fetched = 0.0
        self._was_cleaning = False

    async def _async_update_data(self) -> OpenNeatoData:
        try:
            data = await self.client.async_get_data()
        except OpenNeatoError as err:
            raise UpdateFailed(str(err)) from err

        # History is heavier and only changes when a clean ends: fetch it at start-up,
        # right after a clean finishes, and otherwise every HISTORY_INTERVAL.
        cleaning = "CLEANING" in data.ui_state or "DOCKING" in data.ui_state
        just_finished = self._was_cleaning and not cleaning
        self._was_cleaning = cleaning
        if just_finished or time.monotonic() - self._history_fetched > HISTORY_INTERVAL:
            try:
                self._last_clean = await self.client.async_get_last_clean()
                self._history_fetched = time.monotonic()
            except OpenNeatoError as err:
                # Non-critical: keep the previous value and retry in about a minute.
                self._history_fetched = time.monotonic() - HISTORY_INTERVAL + 60
                _LOGGER.debug("Could not fetch history: %s", err)
        data.last_clean = self._last_clean
        return data

    async def async_command(self, coro) -> None:
        """Run a command, then refresh shortly after."""
        await coro
        await asyncio.sleep(REFRESH_AFTER_COMMAND)
        await self.async_request_refresh()
