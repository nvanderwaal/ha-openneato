"""Buttons for OpenNeato."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import OpenNeatoClient
from .coordinator import OpenNeatoConfigEntry, OpenNeatoCoordinator
from .entity import OpenNeatoEntity

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class OpenNeatoButtonDescription(ButtonEntityDescription):
    press_fn: Callable[[OpenNeatoClient], Awaitable[None]]


BUTTONS: tuple[OpenNeatoButtonDescription, ...] = (
    OpenNeatoButtonDescription(
        key="clear_errors",
        translation_key="clear_errors",
        press_fn=lambda c: c.clear_errors(),
    ),
    OpenNeatoButtonDescription(
        key="restart",
        device_class=ButtonDeviceClass.RESTART,
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda c: c.restart(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OpenNeatoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(OpenNeatoButton(coordinator, d) for d in BUTTONS)


class OpenNeatoButton(OpenNeatoEntity, ButtonEntity):
    entity_description: OpenNeatoButtonDescription

    def __init__(
        self, coordinator: OpenNeatoCoordinator, description: OpenNeatoButtonDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    async def async_press(self) -> None:
        await self.coordinator.async_command(
            self.entity_description.press_fn(self.coordinator.client)
        )
