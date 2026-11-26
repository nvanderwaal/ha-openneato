"""Data update coordinator for OpenNeato."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    OpenNeatoClient,
    OpenNeatoData,
    OpenNeatoError,
    OpenNeatoInfo,
    finished_sessions,
    last_clean,
)
from .maps import MapStore, StoredMap
from .const import (
    DOMAIN,
    HISTORY_INTERVAL,
    HISTORY_RETRY,
    MAP_DOWNLOADS_PER_UPDATE,
    REFRESH_AFTER_COMMAND,
    SCAN_INTERVAL,
)

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
        self.maps = MapStore(Path(hass.config.path(DOMAIN, info.unique_id)))
        self.map_index: dict[int, dict] = {}
        # Start time of the map picked in the select entity; None follows the newest.
        self.selected_map: int | None = None
        self._bad_sessions: set[str] = set()

    async def async_load_maps(self) -> None:
        self.map_index = dict(await self.hass.async_add_executor_job(self.maps.load_index))

    @property
    def shown_map(self) -> int | None:
        if self.selected_map in self.map_index:
            return self.selected_map
        return max(self.map_index, default=None)

    async def async_get_map(self, start: int) -> StoredMap | None:
        return await self.hass.async_add_executor_job(self.maps.load, start)

    def select_map(self, start: int | None) -> None:
        self.selected_map = start
        self.async_update_listeners()

    async def _async_sync_maps(self, items: list[dict]) -> bool:
        """Download finished sessions that are not archived yet. Returns True if more remain."""
        missing = [
            i for i in finished_sessions(items)
            if int(i["session"]["time"]) not in self.map_index and i.get("name")
            and i["name"] not in self._bad_sessions
        ]
        newest_before = max(self.map_index, default=None)
        for item in missing[:MAP_DOWNLOADS_PER_UPDATE]:
            session = await self.client.async_get_session(item["name"])
            if session.summary is None:
                session.summary = item.get("summary")
            if not session.session:
                session.session = item["session"]
            start = await self.hass.async_add_executor_job(self.maps.save, session)
            if start is None:
                self._bad_sessions.add(item["name"])
                continue
            self.map_index = dict(await self.hass.async_add_executor_job(self.maps.load_index))
        # A new clean arrived: jump back to showing the newest map.
        if max(self.map_index, default=None) != newest_before:
            self.selected_map = None
        return len(missing) > MAP_DOWNLOADS_PER_UPDATE

    async def _async_update_data(self) -> OpenNeatoData:
        try:
            data = await self.client.async_get_data()
        except OpenNeatoError as err:
            raise UpdateFailed(str(err)) from err

        # History is heavier and only changes when a clean ends: fetch it at start-up,
        # right after a clean finishes, and otherwise every HISTORY_INTERVAL (20 min).
        cleaning = "CLEANING" in data.ui_state or "DOCKING" in data.ui_state
        just_finished = self._was_cleaning and not cleaning
        self._was_cleaning = cleaning
        if just_finished or time.monotonic() - self._history_fetched > HISTORY_INTERVAL:
            try:
                items = await self.client.async_get_history()
                self._last_clean = last_clean(items)
                self._history_fetched = time.monotonic()
                more = await self._async_sync_maps(items)
                # Robot not cleaning but a session still marked recording: it is
                # still writing the summary. Also retry when tracks remain to download.
                writing = not cleaning and any(i.get("recording") for i in items)
                if more or writing:
                    self._history_fetched = time.monotonic() - HISTORY_INTERVAL + HISTORY_RETRY
            except OpenNeatoError as err:
                # Non-critical: keep the previous value and retry in about a minute.
                self._history_fetched = time.monotonic() - HISTORY_INTERVAL + HISTORY_RETRY
                _LOGGER.debug("Could not fetch history: %s", err)
        data.last_clean = self._last_clean
        return data

    async def async_command(self, coro) -> None:
        """Run a command, then refresh shortly after."""
        await coro
        await asyncio.sleep(REFRESH_AFTER_COMMAND)
        await self.async_request_refresh()
