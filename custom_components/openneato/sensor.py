"""Sensors for OpenNeato."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfArea,
    UnitOfLength,
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


def _last(key: str) -> Callable[[OpenNeatoData], Any]:
    return lambda d: (d.last_clean or {}).get(key)


def _last_time(key: str) -> Callable[[OpenNeatoData], datetime | None]:
    def fn(d: OpenNeatoData) -> datetime | None:
        ts = (d.last_clean or {}).get(key)
        return datetime.fromtimestamp(ts, UTC) if ts else None
    return fn


def _battery_used(d: OpenNeatoData) -> int | None:
    lc = d.last_clean or {}
    if lc.get("batteryStart") is None or lc.get("batteryEnd") is None:
        return None
    return lc["batteryStart"] - lc["batteryEnd"]


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
        key="last_clean_start",
        translation_key="last_clean_start",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_last_time("start"),
    ),
    OpenNeatoSensorDescription(
        key="last_clean_end",
        translation_key="last_clean_end",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_last_time("time"),
    ),
    OpenNeatoSensorDescription(
        key="last_clean_duration",
        translation_key="last_clean_duration",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.MINUTES,
        suggested_display_precision=0,
        value_fn=_last("duration"),
    ),
    OpenNeatoSensorDescription(
        key="last_clean_area",
        translation_key="last_clean_area",
        device_class=SensorDeviceClass.AREA,
        native_unit_of_measurement=UnitOfArea.SQUARE_METERS,
        suggested_display_precision=1,
        value_fn=_last("areaCovered"),
    ),
    OpenNeatoSensorDescription(
        key="last_clean_distance",
        translation_key="last_clean_distance",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.METERS,
        suggested_display_precision=0,
        value_fn=_last("distanceTraveled"),
    ),
    OpenNeatoSensorDescription(
        key="last_clean_battery_used",
        translation_key="last_clean_battery_used",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=_battery_used,
    ),
    OpenNeatoSensorDescription(
        key="last_clean_errors",
        translation_key="last_clean_errors",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_last("errorsDuringClean"),
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
