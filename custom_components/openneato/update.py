"""Firmware update entity for OpenNeato (over-the-air, from GitHub releases)."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from typing import Any

import aiohttp

from homeassistant.components.update import UpdateEntity, UpdateEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import OpenNeatoError
from .const import DOMAIN, FIRMWARE_CHECK_INTERVAL, FIRMWARE_REPO
from .coordinator import OpenNeatoConfigEntry, OpenNeatoCoordinator
from .entity import OpenNeatoEntity

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1
SCAN_INTERVAL = FIRMWARE_CHECK_INTERVAL
GITHUB_API = f"https://api.github.com/repos/{FIRMWARE_REPO}/releases/latest"
REBOOT_TIMEOUT = 120


def firmware_asset(chip: str) -> str | None:
    """Release asset for a chip, e.g. "ESP32-C3" -> openneato-esp32-c3-firmware.bin.

    Uses the generic build for the chip. It reads the UART pins from the robot's
    settings, so it also runs on boards that have their own dedicated build.
    """
    slug = chip.strip().lower()
    if slug not in ("esp32", "esp32-c3", "esp32-s3"):
        return None
    return f"openneato-{slug}-firmware.bin"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OpenNeatoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([OpenNeatoFirmwareUpdate(entry.runtime_data)], update_before_add=True)


class OpenNeatoFirmwareUpdate(OpenNeatoEntity, UpdateEntity):
    """Compares the robot's firmware with the latest stable OpenNeato release."""

    _attr_translation_key = "firmware"
    _attr_title = "OpenNeato"
    _attr_supported_features = (
        UpdateEntityFeature.INSTALL | UpdateEntityFeature.RELEASE_NOTES
    )

    def __init__(self, coordinator: OpenNeatoCoordinator) -> None:
        super().__init__(coordinator, "firmware")
        self._attr_installed_version = coordinator.info.firmware or None
        self._chip = ""
        self._release: dict[str, Any] | None = None

    @property
    def should_poll(self) -> bool:
        # Release checks run on their own slow schedule, not on the 15 s robot poll.
        return True

    async def async_update(self) -> None:
        try:
            fw = await self.coordinator.client.get("/api/firmware/version")
            self._chip = str(fw.get("chip") or "")
            self._attr_installed_version = str(fw.get("version") or "") or None
        except OpenNeatoError:
            pass  # robot asleep or rebooting; keep the last known version
        session = async_get_clientsession(self.hass)
        try:
            async with asyncio.timeout(20):
                async with session.get(
                    GITHUB_API, headers={"Accept": "application/vnd.github+json"}
                ) as resp:
                    resp.raise_for_status()
                    release = await resp.json()
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            _LOGGER.debug("Could not check OpenNeato releases: %s", err)
            return
        if release.get("prerelease") or release.get("draft"):
            return
        self._release = release
        tag = str(release.get("tag_name") or "")
        self._attr_latest_version = tag.removeprefix("v") or None
        self._attr_release_url = release.get("html_url")
        self._attr_release_summary = (release.get("name") or tag)[:255]

    async def async_release_notes(self) -> str | None:
        return (self._release or {}).get("body")

    def _asset_url(self, name: str) -> str | None:
        for asset in (self._release or {}).get("assets") or []:
            if asset.get("name") == name:
                return asset.get("browser_download_url")
        return None

    async def async_install(self, version: str | None, backup: bool, **kwargs: Any) -> None:
        if version and version != self.latest_version:
            raise HomeAssistantError("Only the latest OpenNeato release can be installed")
        data = self.coordinator.data
        if data and ("CLEANING" in data.ui_state or "DOCKING" in data.ui_state):
            raise HomeAssistantError("The robot is cleaning; update once it is back on the dock")
        name = firmware_asset(self._chip)
        if not name:
            raise HomeAssistantError(f"No firmware build known for chip '{self._chip}'")
        bin_url, sums_url = self._asset_url(name), self._asset_url("checksums.txt")
        if not bin_url or not sums_url:
            raise HomeAssistantError(f"Release {self.latest_version} has no {name} or checksums.txt")

        session = async_get_clientsession(self.hass)
        try:
            async with asyncio.timeout(120):
                async with session.get(sums_url) as resp:
                    resp.raise_for_status()
                    sums = await resp.text()
                async with session.get(bin_url) as resp:
                    resp.raise_for_status()
                    firmware = await resp.read()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise HomeAssistantError(f"Download from GitHub failed: {err}") from err

        expected = next(
            (line.split()[0] for line in sums.splitlines()
             if len(line.split()) == 2 and line.split()[1] == name),
            None,
        )
        if not expected or hashlib.sha256(firmware).hexdigest() != expected.lower():
            raise HomeAssistantError("Downloaded firmware does not match the release checksum")
        md5 = hashlib.md5(firmware).hexdigest()  # noqa: S324 - required by the robot's OTA API

        self._attr_in_progress = True
        self.async_write_ha_state()
        try:
            _LOGGER.info("Uploading OpenNeato %s (%s) to %s", self.latest_version, name, self.coordinator.client.host)
            try:
                await self.coordinator.client.async_upload_firmware(firmware, md5, name)
            except OpenNeatoError as err:
                raise HomeAssistantError(str(err)) from err
            await self._async_wait_for_version(self.latest_version)
        finally:
            self._attr_in_progress = False
            self.async_write_ha_state()

    async def _async_wait_for_version(self, version: str | None) -> None:
        """The robot reboots after flashing; wait until it reports the new version."""
        deadline = time.monotonic() + REBOOT_TIMEOUT
        await asyncio.sleep(10)
        while time.monotonic() < deadline:
            try:
                fw = await self.coordinator.client.get("/api/firmware/version")
            except OpenNeatoError:
                await asyncio.sleep(5)
                continue
            installed = str(fw.get("version") or "")
            if installed == version:
                self._attr_installed_version = installed
                self.coordinator.info.firmware = installed
                registry = dr.async_get(self.hass)
                for device in dr.async_entries_for_config_entry(
                    registry, self.coordinator.config_entry.entry_id
                ):
                    if (DOMAIN, self.coordinator.info.unique_id) in device.identifiers:
                        registry.async_update_device(
                            device.id, sw_version=f"OpenNeato {installed}"
                        )
                await self.coordinator.async_request_refresh()
                return
            await asyncio.sleep(5)
        raise HomeAssistantError(
            f"Upload succeeded, but the robot did not report version {version} within "
            f"{REBOOT_TIMEOUT} s. Check the robot's web UI."
        )
