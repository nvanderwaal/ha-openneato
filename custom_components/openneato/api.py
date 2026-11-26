"""Minimal async client for the OpenNeato local HTTP API."""

from __future__ import annotations

import asyncio
import json
import re
from urllib.parse import quote
from dataclasses import dataclass
from typing import Any

import aiohttp

REQUEST_TIMEOUT = 10
# The ESP32 web server occasionally sends a garbled or duplicated response.
# One quick retry hides that from the user.
RETRY_DELAY = 0.5
FIRMWARE_UPLOAD_TIMEOUT = 180


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
    last_clean: dict[str, Any] | None = None

    @property
    def ui_state(self) -> str:
        return str(self.state.get("uiState") or "")

    @property
    def robot_state(self) -> str:
        return str(self.state.get("robotState") or "")


@dataclass(slots=True)
class CleanSession:
    """One recorded clean: header, summary and the odometry track."""

    session: dict[str, Any]
    summary: dict[str, Any] | None
    points: list[tuple[float, float]]


def finished_sessions(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Finished sessions from /api/history, newest first."""
    done = [
        i for i in items
        if not i.get("recording") and isinstance(i.get("summary"), dict)
        and isinstance(i.get("session"), dict) and i["session"].get("time")
    ]
    return sorted(done, key=lambda i: i["session"]["time"], reverse=True)


def last_clean(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Summary of the newest finished session, with its start time."""
    done = finished_sessions(items)
    if not done:
        return None
    summary = dict(done[0]["summary"])
    summary["start"] = done[0]["session"]["time"]
    return summary


def parse_session(text: str) -> CleanSession:
    """Parse a session file. Lines that do not decode (truncated writes) are skipped."""
    session: dict[str, Any] = {}
    summary: dict[str, Any] | None = None
    points: list[tuple[float, float]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if not isinstance(obj, dict):
            continue
        kind = obj.get("type")
        if kind == "session":
            session = obj
        elif kind == "summary":
            summary = obj
        elif kind is None and "x" in obj and "y" in obj:
            try:
                points.append((float(obj["x"]), float(obj["y"])))
            except (TypeError, ValueError):
                continue
    return CleanSession(session=session, summary=summary, points=points)


def parse_history(text: str) -> list[dict[str, Any]]:
    """Parse /api/history, tolerating corrupt entries.

    Some firmware versions occasionally write a truncated session summary, which
    makes the whole response invalid JSON. Fall back to decoding entry by entry
    and skip the ones that are broken.
    """
    try:
        data = json.loads(text)
        return [i for i in data if isinstance(i, dict)] if isinstance(data, list) else []
    except ValueError:
        pass
    decoder = json.JSONDecoder()
    items: list[dict[str, Any]] = []
    for match in re.finditer(r'\{"name":', text):
        try:
            obj, _ = decoder.raw_decode(text, match.start())
        except ValueError:
            continue
        if isinstance(obj, dict) and "name" in obj:
            items.append(obj)
    return items


class OpenNeatoClient:
    """Talks to one OpenNeato robot."""

    def __init__(self, host: str, session: aiohttp.ClientSession) -> None:
        self.host = host.strip().removeprefix("http://").rstrip("/")
        self._session = session

    @property
    def base_url(self) -> str:
        return f"http://{self.host}"

    async def _request(self, method: str, path: str) -> Any:
        try:
            return await self._request_once(method, path)
        except OpenNeatoConnectionError:
            if method != "GET":
                raise
            await asyncio.sleep(RETRY_DELAY)
            return await self._request_once(method, path)

    async def _request_once(self, method: str, path: str) -> Any:
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

    async def _get_text(self, path: str) -> str:
        try:
            return await self._get_text_once(path)
        except OpenNeatoConnectionError:
            await asyncio.sleep(RETRY_DELAY)
            return await self._get_text_once(path)

    async def _get_text_once(self, path: str) -> str:
        url = f"{self.base_url}{path}"
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT * 2):
                async with self._session.get(url) as resp:
                    resp.raise_for_status()
                    return await resp.text()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise OpenNeatoConnectionError(f"GET {url} failed: {err}") from err

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

    async def async_get_data(self, system: dict[str, Any] | None = None) -> OpenNeatoData:
        """Poll the robot. Pass a cached /api/system result to skip that request."""
        # Sequential on purpose: the ESP32 copes badly with parallel connections.
        state = await self.get("/api/state")
        charger = await self.get("/api/charger")
        error = await self.get("/api/error")
        if system is None:
            system = await self.get("/api/system")
        return OpenNeatoData(state=state, charger=charger, error=error, system=system)

    async def async_get_history(self) -> list[dict[str, Any]]:
        """Return the session list from /api/history (unsorted)."""
        return parse_history(await self._get_text("/api/history"))

    async def async_get_session(self, name: str) -> CleanSession:
        """Download one recorded session (JSON lines) by file name."""
        return parse_session(await self._get_text(f"/api/history/{quote(name)}"))

    async def async_upload_firmware(self, firmware: bytes, md5: str, filename: str) -> None:
        """OTA: upload a firmware image. The robot verifies the MD5 and reboots."""
        form = aiohttp.FormData()
        form.add_field("file", firmware, filename=filename, content_type="application/octet-stream")
        url = f"{self.base_url}/api/firmware/update?hash={md5}"
        try:
            async with asyncio.timeout(FIRMWARE_UPLOAD_TIMEOUT):
                async with self._session.post(url, data=form) as resp:
                    if resp.status != 200:
                        raise OpenNeatoError(
                            f"Firmware update rejected ({resp.status}): {(await resp.text())[:200]}"
                        )
        except OpenNeatoError:
            raise
        except (aiohttp.ClientError, TimeoutError) as err:
            raise OpenNeatoConnectionError(f"Firmware upload failed: {err}") from err

    async def clean(self, action: str) -> None:
        """action: house, spot, pause, stop, dock."""
        await self.post(f"/api/clean?action={action}")

    async def clear_errors(self) -> None:
        await self.post("/api/clear-errors")

    async def restart(self) -> None:
        await self.post("/api/power?action=restart")
