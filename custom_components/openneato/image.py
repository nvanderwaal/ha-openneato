"""Map of a cleaning run for OpenNeato."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import OpenNeatoConfigEntry, OpenNeatoCoordinator
from .entity import OpenNeatoEntity
from .maps import render_svg

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OpenNeatoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([OpenNeatoMap(entry.runtime_data)])


class OpenNeatoMap(OpenNeatoEntity, ImageEntity):
    """Route and covered area of the selected (by default the newest) clean."""

    _attr_translation_key = "map"
    _attr_content_type = "image/svg+xml"

    def __init__(self, coordinator: OpenNeatoCoordinator) -> None:
        OpenNeatoEntity.__init__(self, coordinator, "map")
        ImageEntity.__init__(self, coordinator.hass)
        self._shown: int | None = None
        self._svg: bytes | None = None
        self._set_shown()

    @property
    def available(self) -> bool:
        # The archive is local, so the map stays viewable while the robot sleeps.
        return self.coordinator.shown_map is not None

    def _set_shown(self) -> None:
        shown = self.coordinator.shown_map
        if shown != self._shown or self._attr_image_last_updated is None:
            self._shown = shown
            self._svg = None
            self._attr_image_last_updated = datetime.now(UTC)

    @property
    def entity_picture(self) -> str | None:
        # Same proxy URL for every map otherwise, so browsers would show a cached one.
        url = super().entity_picture
        return f"{url}&v={self._shown}" if url and self._shown else url

    @callback
    def _handle_coordinator_update(self) -> None:
        self._set_shown()
        super()._handle_coordinator_update()

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self._shown is None:
            return None
        s = self.coordinator.map_index.get(self._shown) or {}
        used = None
        if s.get("batteryStart") is not None and s.get("batteryEnd") is not None:
            used = s["batteryStart"] - s["batteryEnd"]
        return {
            "start": datetime.fromtimestamp(self._shown, UTC).isoformat(),
            "mode": s.get("mode"),
            "duration_min": round(s["duration"] / 60) if s.get("duration") else None,
            "area_m2": s.get("areaCovered"),
            "distance_m": s.get("distanceTraveled"),
            "battery_used": used,
            "errors": s.get("errorsDuringClean"),
            "stored_maps": len(self.coordinator.map_index),
        }

    async def async_image(self) -> bytes | None:
        if self._shown is None:
            return None
        if self._svg is None:
            stored = await self.coordinator.async_get_map(self._shown)
            self._svg = render_svg(stored.points if stored else []).encode()
        return self._svg
