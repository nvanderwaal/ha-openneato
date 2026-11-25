"""Minimal async client for the OpenNeato local HTTP API."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import aiohttp

REQUEST_TIMEOUT = 10


class OpenNeatoError(Exception):
    """Base error for OpenNeato."""


class OpenNeatoConnectionError(OpenNeatoError):
    """The robot could not be reached."""


class OpenNeatoNotSupportedError(OpenNeatoError):
    """The host answered, but it is not an OpenNeato robot."""


@dataclass(slots=True)
class OpenNeatoInfo:
    """Static device information."""

    unique_id: str
    hostname: str
    model: str
    firmware: str
    robot_software: str | None
    serial: str | None


@dataclass(slots=True)
class OpenNeatoData:
    """Polled robot state."""

    state: dict[str, Any]
    charger: dict[str, Any]
    error: dict[str, Any]
    system: dict[str, Any]

    @property
    def ui_state(self) -> str:
        return str(self.state.get("uiState") or "")

    @property
    def robot_state(self) -> str:
        return str(self.state.get("robotState") or "")


class OpenNeatoClient:
    """Talks to one OpenNeato robot."""

    def __init__(self, host: str, session: aiohttp.ClientSession) -> None:
        self.host = host.strip().removeprefix("http://").rstrip("/")
        self._session = session

    @property
    def base_url(self) -> str:
        return f"http://{self.host}"

    async def _request(self, method: str, path: str) -> Any:
        url = f"{self.base_url}{path}"
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                async with self._session.request(method, url) as resp:
                    if resp.status == 404:
                        raise OpenNeatoNotSupportedError(f"{path} not found")
                    resp.raise_for_status()
                    if method == "GET":
                        return await resp.json(content_type=None)
                    return None
        except OpenNeatoError:
            raise
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise OpenNeatoConnectionError(f"{method} {url} failed: {err}") from err

    async def get(self, path: str) -> dict[str, Any]:
        data = await self._request("GET", path)
        if not isinstance(data, dict):
            raise OpenNeatoNotSupportedError(f"Unexpected response from {path}")
        return data

    async def post(self, path: str) -> None:
        await self._request("POST", path)

    async def async_get_info(self) -> OpenNeatoInfo:
        """Identify the robot. Raises OpenNeatoNotSupportedError if it is not OpenNeato."""
        fw = await self.get("/api/firmware/version")
        if fw.get("name") != "OpenNeato":
            raise OpenNeatoNotSupportedError("Firmware is not OpenNeato")
        try:
            robot = await self.get("/api/version")
        except OpenNeatoError:
            robot = {}
        serial = robot.get("serialNumber")
        # Neato serials look like "GPC36518,f045da652b30,P"; the middle part is the robot MAC.
        parts = [p for p in str(serial or "").split(",") if p]
        unique = parts[1] if len(parts) > 1 else (parts[0] if parts else fw.get("hostname", self.host))
        return OpenNeatoInfo(
            unique_id=str(unique).lower(),
            hostname=str(fw.get("hostname") or self.host),
            model=str(fw.get("model") or robot.get("modelName") or "Neato"),
            firmware=str(fw.get("version") or ""),
            robot_software=robot.get("softwareVersion"),
            serial=parts[0] if parts else None,
        )

    async def async_get_data(self) -> OpenNeatoData:
        state, charger, error, system = await asyncio.gather(
            self.get("/api/state"),
            self.get("/api/charger"),
            self.get("/api/error"),
            self.get("/api/system"),
        )
        return OpenNeatoData(state=state, charger=charger, error=error, system=system)

    async def clean(self, action: str) -> None:
        """action: house, spot, pause, stop, dock."""
        await self.post(f"/api/clean?action={action}")

    async def clear_errors(self) -> None:
        await self.post("/api/clear-errors")

    async def restart(self) -> None:
        await self.post("/api/power?action=restart")
