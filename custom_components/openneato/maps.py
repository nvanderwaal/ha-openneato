"""Archive of cleaning tracks and the SVG renderer for the map image.

Tracks are kept in the Home Assistant config directory
(``<config>/openneato/<robot id>/<start>.json``), so they survive the robot
pruning its own history and are included in Home Assistant backups.
"""

from __future__ import annotations

import json
import logging
import math
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .api import CleanSession

_LOGGER = logging.getLogger(__name__)

MAX_MAPS = 100
# Points closer together than this (metres) are merged; keeps files small.
MIN_STEP = 0.02
# Approximate cleaning width of a Botvac brush, in metres.
BRUSH_WIDTH = 0.28
MARGIN = 0.6
PIXELS_PER_METRE = 80
MIN_SIZE_M = 3.0

ROUTE_COLORS = ("#64D2FF", "#0A84FF", "#5E5CE6", "#BF5AF2")


@dataclass(slots=True)
class StoredMap:
    """One archived clean."""

    start: int
    summary: dict[str, Any]
    points: list[tuple[float, float]]


def simplify(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Drop points that barely moved since the previous kept point."""
    out: list[tuple[float, float]] = []
    for x, y in points:
        if out and math.hypot(x - out[-1][0], y - out[-1][1]) < MIN_STEP:
            continue
        out.append((round(x, 3), round(y, 3)))
    if points and out and out[-1] != (round(points[-1][0], 3), round(points[-1][1], 3)):
        out.append((round(points[-1][0], 3), round(points[-1][1], 3)))
    return out


class MapStore:
    """Blocking file store; call the methods from an executor."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self._index: dict[int, dict[str, Any]] | None = None

    def _path(self, start: int) -> Path:
        return self.directory / f"{start}.json"

    def load_index(self) -> dict[int, dict[str, Any]]:
        """Start time -> summary of every stored map."""
        if self._index is None:
            index: dict[int, dict[str, Any]] = {}
            if self.directory.is_dir():
                for file in self.directory.glob("*.json"):
                    try:
                        data = json.loads(file.read_text())
                        index[int(data["start"])] = data.get("summary") or {}
                    except (OSError, ValueError, KeyError, TypeError) as err:
                        _LOGGER.warning("Skipping unreadable map %s: %s", file, err)
            self._index = index
        return self._index

    def save(self, session: CleanSession) -> int | None:
        start = session.session.get("time")
        points = simplify(session.points)
        if not start or len(points) < 2:
            return None
        start = int(start)
        summary = session.summary or {}
        self.directory.mkdir(parents=True, exist_ok=True)
        tmp = self._path(start).with_suffix(".tmp")
        tmp.write_text(json.dumps(
            {"start": start, "session": session.session, "summary": summary, "points": points},
            separators=(",", ":"),
        ))
        tmp.replace(self._path(start))
        index = self.load_index()
        index[start] = summary
        for old in sorted(index)[:-MAX_MAPS]:
            self._path(old).unlink(missing_ok=True)
            index.pop(old, None)
        return start

    def load(self, start: int) -> StoredMap | None:
        try:
            data = json.loads(self._path(start).read_text())
        except (OSError, ValueError):
            return None
        return StoredMap(
            start=start,
            summary=data.get("summary") or {},
            points=[(float(x), float(y)) for x, y in data.get("points") or []],
        )

    def remove_all(self) -> None:
        shutil.rmtree(self.directory, ignore_errors=True)
        self._index = {}


def render_svg(points: list[tuple[float, float]]) -> str:
    """Draw the track: covered area, route coloured by time, start and end markers.

    Robot coordinates are metres with y pointing up; SVG y points down, so y is negated.
    The background is transparent so the card's own colour shows through.
    """
    if len(points) < 2:
        return _empty_svg()
    pts = [(x, -y) for x, y in points]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
    # Keep small maps from being blown up to giant strokes.
    w = max(max_x - min_x, MIN_SIZE_M)
    h = max(max_y - min_y, MIN_SIZE_M)
    cx, cy = (min_x + max_x) / 2, (min_y + max_y) / 2
    vx, vy = cx - w / 2 - MARGIN, cy - h / 2 - MARGIN
    vw, vh = w + 2 * MARGIN, h + 2 * MARGIN

    def path(seq: list[tuple[float, float]]) -> str:
        return "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in seq)

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vx:.2f} {vy:.2f} {vw:.2f} {vh:.2f}" '
        f'width="{round(vw * PIXELS_PER_METRE)}" height="{round(vh * PIXELS_PER_METRE)}">',
        '<g stroke="#8E8E93" stroke-opacity="0.18" stroke-width="0.01">',
    ]
    # 1 m grid
    for gx in range(math.floor(vx), math.ceil(vx + vw) + 1):
        out.append(f'<line x1="{gx}" y1="{vy:.2f}" x2="{gx}" y2="{vy + vh:.2f}"/>')
    for gy in range(math.floor(vy), math.ceil(vy + vh) + 1):
        out.append(f'<line x1="{vx:.2f}" y1="{gy}" x2="{vx + vw:.2f}" y2="{gy}"/>')
    out.append("</g>")

    # Covered area: one wide translucent stroke, so overlaps don't get darker.
    out.append(
        f'<path d="{path(pts)}" fill="none" stroke="#0A84FF" stroke-opacity="0.22" '
        f'stroke-width="{BRUSH_WIDTH}" stroke-linecap="round" stroke-linejoin="round"/>'
    )
    # Route, split in chunks that shift colour from start to end.
    chunks = len(ROUTE_COLORS)
    size = math.ceil(len(pts) / chunks)
    for i, color in enumerate(ROUTE_COLORS):
        seg = pts[max(i * size - 1, 0) : (i + 1) * size]
        if len(seg) >= 2:
            out.append(
                f'<path d="{path(seg)}" fill="none" stroke="{color}" stroke-width="0.035" '
                'stroke-linecap="round" stroke-linejoin="round"/>'
            )

    sx, sy = pts[0]
    ex, ey = pts[-1]
    out.append(f'<circle cx="{ex:.2f}" cy="{ey:.2f}" r="0.11" fill="#FF9F0A" stroke="#fff" stroke-width="0.03"/>')
    out.append(f'<circle cx="{sx:.2f}" cy="{sy:.2f}" r="0.13" fill="#30D158" stroke="#fff" stroke-width="0.03"/>')

    # 1 m scale bar, bottom left
    bx, by = vx + 0.25, vy + vh - 0.25
    out.append(
        f'<g stroke="#8E8E93" stroke-width="0.03" stroke-linecap="round">'
        f'<line x1="{bx:.2f}" y1="{by:.2f}" x2="{bx + 1:.2f}" y2="{by:.2f}"/>'
        f'<line x1="{bx:.2f}" y1="{by - 0.06:.2f}" x2="{bx:.2f}" y2="{by + 0.06:.2f}"/>'
        f'<line x1="{bx + 1:.2f}" y1="{by - 0.06:.2f}" x2="{bx + 1:.2f}" y2="{by + 0.06:.2f}"/></g>'
        f'<text x="{bx + 0.5:.2f}" y="{by - 0.1:.2f}" font-size="0.2" text-anchor="middle" '
        'fill="#8E8E93" font-family="-apple-system,Segoe UI,Roboto,sans-serif">1 m</text>'
    )
    out.append("</svg>")
    return "".join(out)


def _empty_svg() -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 4 3" width="320" height="240">'
        '<circle cx="2" cy="1.5" r="0.15" fill="#8E8E93" fill-opacity="0.4"/></svg>'
    )
