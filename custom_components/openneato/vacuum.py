"""Vacuum entity for OpenNeato."""

from __future__ import annotations

from typing import Any

from homeassistant.components.vacuum import (
    StateVacuumEntity,
    VacuumActivity,
    VacuumEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import OpenNeatoConfigEntry, OpenNeatoCoordinator
from .entity import OpenNeatoEntity

PARALLEL_UPDATES = 1


def activity_from_data(ui_state: str, docked: bool, has_error: bool) -> VacuumActivity:
    """Map OpenNeato uiState (e.g. UIMGR_STATE_HOUSECLEANINGRUNNING) to an activity."""
    if has_error:
        return VacuumActivity.ERROR
    if "DOCKING" in ui_state:
        return VacuumActivity.RETURNING
    if "CLEANINGRUNNING" in ui_state:
        return VacuumActivity.CLEANING
    if "CLEANINGPAUSED" in ui_state or "CLEANINGSUSPENDED" in ui_state:
        return VacuumActivity.PAUSED
    if docked:
        return VacuumActivity.DOCKED
    return VacuumActivity.IDLE


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OpenNeatoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([OpenNeatoVacuum(entry.runtime_data)])


class OpenNeatoVacuum(OpenNeatoEntity, StateVacuumEntity):
    """The robot itself."""

    _attr_name = None  # use the device name
    _attr_supported_features = (
        VacuumEntityFeature.START
        | VacuumEntityFeature.PAUSE
        | VacuumEntityFeature.STOP
        | VacuumEntityFeature.RETURN_HOME
        | VacuumEntityFeature.CLEAN_SPOT
        | VacuumEntityFeature.STATE
    )

    def __init__(self, coordinator: OpenNeatoCoordinator) -> None:
        super().__init__(coordinator, "vacuum")

    @property
    def activity(self) -> VacuumActivity:
        data = self.coordinator.data
        return activity_from_data(
            data.ui_state,
            bool(data.charger.get("extPwrPresent")),
            bool(data.error.get("hasError")) and data.error.get("kind") != "warning",
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        return {"ui_state": data.ui_state, "robot_state": data.robot_state}

    async def async_start(self) -> None:
        await self.coordinator.async_command(self.coordinator.client.clean("house"))

    async def async_pause(self) -> None:
        await self.coordinator.async_command(self.coordinator.client.clean("pause"))

    async def async_stop(self, **kwargs: Any) -> None:
        await self.coordinator.async_command(self.coordinator.client.clean("stop"))

    async def async_return_to_base(self, **kwargs: Any) -> None:
        await self.coordinator.async_command(self.coordinator.client.clean("dock"))

    async def async_clean_spot(self, **kwargs: Any) -> None:
        await self.coordinator.async_command(self.coordinator.client.clean("spot"))
