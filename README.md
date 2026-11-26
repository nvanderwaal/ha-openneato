# OpenNeato for Home Assistant

A local Home Assistant integration for Neato Botvac robots running the
[OpenNeato](https://github.com/renjfk/OpenNeato) firmware. No cloud, no account:
Home Assistant talks directly to the robot's HTTP API on your network.

> Not affiliated with Neato Robotics or the OpenNeato project.

## Features

- **Vacuum entity**: start, pause, stop, return to dock, spot clean, with live state
  (cleaning / paused / returning / docked / idle / error)
- **Sensors**: battery, message (error/warning text), robot state; diagnostic sensors
  for battery voltage, Wi-Fi signal and uptime (disabled by default)
- **Last clean** (from `/api/history`): start and end time, duration, area, distance,
  battery used, errors during the clean
- **Cleaning map**: an image entity that draws the route of a clean (coloured from start to
  end) with the covered area, dock and end point, plus a select entity to browse earlier
  cleans. Tracks are archived in Home Assistant, so they outlive the robot's own history.
- **Binary sensors**: charging, docked, problem
- **Buttons**: clear errors, restart robot
- UI setup (config flow) and re-configure if the robot's IP changes
- English and Dutch translations

## Requirements

- A Neato robot with OpenNeato installed and connected to your Wi-Fi
- Home Assistant 2025.1 or newer
- A fixed IP address (DHCP reservation) for the robot is recommended

## Installation

### HACS (recommended)

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/nvanderwaal/ha-openneato`, category **Integration**.
2. Install **OpenNeato** and restart Home Assistant.

### Manual

Copy `custom_components/openneato` into your Home Assistant `config/custom_components/` folder and restart.

## Setup

**Settings → Devices & services → Add integration → OpenNeato**, then enter the robot's IP address.

## Tested with

| Robot | OpenNeato | Home Assistant |
|---|---|---|
| Botvac D4 Connected | 0.14 | 2026.11 |

Reports for other models are welcome. Please open an issue.

## How it works

The integration polls `/api/state`, `/api/charger`, `/api/error` and `/api/system` every
15 seconds and sends commands with `POST /api/clean?action=house|spot|pause|stop|dock`.
The cleaning history (`/api/history`) is read at start-up, right after a clean finishes,
and otherwise every 20 minutes as a safety net. Corrupt history entries, which some firmware versions
occasionally write, are skipped instead of breaking the whole list.

Each finished clean's track (`/api/history/<session>`) is downloaded once, a few per
update so the ESP32 isn't flooded, and stored in `<config>/openneato/<robot id>/` (newest
100 kept, included in Home Assistant backups, deleted when the robot is removed). The map
is rendered as SVG in Home Assistant, so the robot does no extra work.
The positions come from wheel odometry, which drifts during a clean: room shapes are
recognisable, but the map is not a precise floor plan.

### Map card example

```yaml
type: vertical-stack
cards:
  - type: picture-entity
    entity: image.jeffrey_map
    show_name: false
    show_state: false
  - type: tile
    entity: select.jeffrey_map_clean
    features:
      - type: select-options
```

## License

MIT
