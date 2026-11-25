"""Base entity for OpenNeato."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import OpenNeatoCoordinator


class OpenNeatoEntity(CoordinatorEntity[OpenNeatoCoordinator]):
    """Common device info and naming."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: OpenNeatoCoordinator, key: str) -> None:
        super().__init__(coordinator)
        info = coordinator.info
        self._attr_unique_id = f"{info.unique_id}_{key}"
        connections = set()
        if len(info.unique_id) == 12 and all(c in "0123456789abcdef" for c in info.unique_id):
            mac = ":".join(info.unique_id[i : i + 2] for i in range(0, 12, 2))
            connections.add((CONNECTION_NETWORK_MAC, mac))
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, info.unique_id)},
            connections=connections,
            name=info.hostname,
            manufacturer=MANUFACTURER,
            model=info.model,
            serial_number=info.serial,
            sw_version=f"OpenNeato {info.firmware}",
            hw_version=info.robot_software,
            configuration_url=coordinator.client.base_url,
        )
