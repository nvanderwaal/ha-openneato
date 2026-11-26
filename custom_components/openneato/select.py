"""Pick which archived clean the map shows."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import OpenNeatoConfigEntry, OpenNeatoCoordinator
from .entity import OpenNeatoEntity

PARALLEL_UPDATES = 0
MAX_OPTIONS = 50


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OpenNeatoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([OpenNeatoMapSelect(entry.runtime_data)])


def _label(start: int, summary: dict) -> str:
    when = dt_util.as_local(dt_util.utc_from_timestamp(start)).strftime("%Y-%m-%d %H:%M")
    area = summary.get("areaCovered")
    return f"{when} · {area:g} m²" if isinstance(area, (int, float)) else when


class OpenNeatoMapSelect(OpenNeatoEntity, SelectEntity):
    """Newest first; picking an entry changes the map image."""

    _attr_translation_key = "map_session"

    def __init__(self, coordinator: OpenNeatoCoordinator) -> None:
        super().__init__(coordinator, "map_session")

    @property
    def available(self) -> bool:
        return bool(self.coordinator.map_index)

    def _labels(self) -> dict[str, int]:
        index = self.coordinator.map_index
        newest = sorted(index, reverse=True)[:MAX_OPTIONS]
        return {_label(start, index[start]): start for start in newest}

    @property
    def options(self) -> list[str]:
        return list(self._labels())

    @property
    def current_option(self) -> str | None:
        shown = self.coordinator.shown_map
        for label, start in self._labels().items():
            if start == shown:
                return label
        return None

    async def async_select_option(self, option: str) -> None:
        start = self._labels().get(option)
        newest = max(self.coordinator.map_index, default=None)
        # Picking the newest means "follow new cleans" again.
        self.coordinator.select_map(None if start == newest else start)
