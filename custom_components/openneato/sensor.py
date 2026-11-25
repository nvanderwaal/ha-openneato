"""Sensors for OpenNeato."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfElectricPotential,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import OpenNeatoData
from .coordinator import OpenNeatoConfigEntry, OpenNeatoCoordinator
from .entity import OpenNeatoEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class OpenNeatoSensorDescription(SensorEntityDescription):
    value_fn: Callable[[OpenNeatoData], Any]


def _message(d: OpenNeatoData) -> str | None:
    if not d.error.get("hasError"):
        return None
    return d.error.get("displayMessage") or d.error.get("errorMessage") or str(d.error.get("errorCode"))


SENSORS: tuple[OpenNeatoSensorDescription, ...] = (
    OpenNeatoSensorDescription(
        key="battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.charger.get("fuelPercent"),
    ),
    OpenNeatoSensorDescription(
        key="battery_voltage",
        translation_key="battery_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.charger.get("vBattV"),
    ),
    OpenNeatoSensorDescription(
        key="message",
        translation_key="message",
        value_fn=_message,
    ),
    OpenNeatoSensorDescription(
        key="robot_state",
        translation_key="robot_state",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.ui_state.removeprefix("UIMGR_STATE_").lower() or None,
    ),
    OpenNeatoSensorDescription(
        key="wifi_signal",
        translation_key="wifi_signal",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.system.get("rssi"),
    ),
    OpenNeatoSensorDescription(
        key="uptime",
        translation_key="uptime",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MILLISECONDS,
        suggested_unit_of_measurement=UnitOfTime.DAYS,
        suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.system.get("uptime"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OpenNeatoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(OpenNeatoSensor(coordinator, desc) for desc in SENSORS)


class OpenNeatoSensor(OpenNeatoEntity, SensorEntity):
    entity_description: OpenNeatoSensorDescription

    def __init__(
        self, coordinator: OpenNeatoCoordinator, description: OpenNeatoSensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data)
