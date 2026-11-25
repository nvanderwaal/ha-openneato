"""Binary sensors for OpenNeato."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import OpenNeatoData
from .coordinator import OpenNeatoConfigEntry, OpenNeatoCoordinator
from .entity import OpenNeatoEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class OpenNeatoBinaryDescription(BinarySensorEntityDescription):
    value_fn: Callable[[OpenNeatoData], bool]


BINARY_SENSORS: tuple[OpenNeatoBinaryDescription, ...] = (
    OpenNeatoBinaryDescription(
        key="charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=lambda d: bool(d.charger.get("chargingActive")),
    ),
    OpenNeatoBinaryDescription(
        key="docked",
        translation_key="docked",
        device_class=BinarySensorDeviceClass.PLUG,
        value_fn=lambda d: bool(d.charger.get("extPwrPresent")),
    ),
    OpenNeatoBinaryDescription(
        key="problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda d: bool(d.error.get("hasError")),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OpenNeatoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(OpenNeatoBinarySensor(coordinator, d) for d in BINARY_SENSORS)


class OpenNeatoBinarySensor(OpenNeatoEntity, BinarySensorEntity):
    entity_description: OpenNeatoBinaryDescription

    def __init__(
        self, coordinator: OpenNeatoCoordinator, description: OpenNeatoBinaryDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        return self.entity_description.value_fn(self.coordinator.data)
