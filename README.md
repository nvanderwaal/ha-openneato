# OpenNeato for Home Assistant

A local Home Assistant integration for Neato Botvac robots running the
[OpenNeato](https://github.com/renjfk/OpenNeato) firmware. No cloud, no account:
Home Assistant talks directly to the robot's HTTP API on your network. The only outside
connection is an optional check for new firmware releases on GitHub.

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
- **Firmware updates**: an update entity that compares the robot with the latest stable
  OpenNeato release and installs it over the air from Home Assistant (Settings → Updates)
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

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=nvanderwaal&repository=ha-openneato&category=integration)

Click the button above, or add the repository by hand:

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/nvanderwaal/ha-openneato`, category **Integration**.
2. Install **OpenNeato** and restart Home Assistant.

### Manual

Copy `custom_components/openneato` into your Home Assistant `config/custom_components/` folder and restart.

## Setup

Go to **Settings → Devices & services → Add integration → OpenNeato**, then enter the robot's IP address.

## Tested with

| Robot | OpenNeato | Home Assistant |
|---|---|---|
| Botvac D4 Connected | 0.14, 0.15 | 2026.11 |

Reports for other models are welcome. Please open an issue.

## How it works

The integration polls `/api/state`, `/api/charger` and `/api/error` every 15 seconds while
the robot is cleaning, paused or returning to the dock, and every 60 seconds when it is
docked or idle. `/api/system` (Wi-Fi signal, uptime) is read every 5 minutes. Commands are
sent with `POST /api/clean?action=house|spot|pause|stop|dock`, followed by a refresh 3
seconds later, so the dashboard reacts right away.
Requests are sent one after another (the ESP32 copes badly with parallel connections) and
a failed read is retried once. The cleaning history (`/api/history`) is read at start-up,
right after a clean finishes, and otherwise every 20 minutes as a safety net. Corrupt
history entries, which some firmware versions occasionally write, are skipped instead of
breaking the whole list.

Each finished clean's track (`/api/history/<session>`) is downloaded once, a few per
update so the ESP32 isn't flooded, and stored in `<config>/openneato/<robot id>/` (newest
100 kept, included in Home Assistant backups, deleted when the robot is removed). The map
is rendered as SVG in Home Assistant, so the robot does no extra work.
The positions come from wheel odometry, which drifts during a clean: room shapes are
recognisable, but the map is not a precise floor plan.

### Firmware updates

Every 6 hours the integration asks the GitHub API for the latest stable OpenNeato release.
This is the only connection it makes outside your network; nothing about your robot is sent.
Installing downloads the generic firmware for the robot's chip (`openneato-<chip>-firmware.bin`),
checks it against the release's `checksums.txt` (SHA-256), uploads it to
`/api/firmware/update` with its MD5 and waits for the robot to come back with the new version.
Installation is refused while the robot is cleaning or returning to the dock, and
pre-releases are ignored. If your board needs a dedicated build (for example the Seeed
XIAO), update through the robot's own web UI instead.

If you don't want the GitHub check, disable the **Firmware** update entity.

## Dashboard examples

Replace `<robot>` with your robot's entity name (for example `jeffrey`).

### Map with a picker for earlier cleans

```yaml
type: vertical-stack
cards:
  - type: picture-entity
    entity: image.<robot>_map
    show_name: false
    show_state: false
  - type: tile
    entity: select.<robot>_map_clean
    features:
      - type: select-options
```

<img width="562" height="701" alt="image" src="https://github.com/user-attachments/assets/25527fe1-827c-4b30-a46e-003570085d88" />

### Latest clean in one card

The map image entity carries the stats of the clean it shows as attributes
(`start`, `duration_min`, `area_m2`, `distance_m`, `battery_used`, `errors`),
so a single Markdown card can show the map with its numbers:

```yaml
type: markdown
content: |
  {%- set a = states.image.<robot>_map.attributes -%}
  {%- if a.start -%}
  ### Last clean
  {{ as_local(as_datetime(a.start)).strftime('%a %d %b, %H:%M') }}

  <img src="{{ a.entity_picture }}" width="100%">

  <ha-icon icon="mdi:timer-outline"></ha-icon> {{ a.duration_min }} min &nbsp;
  <ha-icon icon="mdi:texture-box"></ha-icon> {{ a.area_m2 }} m² &nbsp;
  <ha-icon icon="mdi:map-marker-distance"></ha-icon> {{ a.distance_m | round(0) | int }} m &nbsp;
  <ha-icon icon="mdi:battery-arrow-down-outline"></ha-icon> {{ a.battery_used }}%
  {%- else -%}
  No map yet. It appears after the first clean.
  {%- endif -%}
```

## Removing

**Settings → Devices & services → OpenNeato → ⋮ → Delete.** The archived maps in
`<config>/openneato/<robot id>/` are deleted with it. Then remove the repository in HACS.

## License

MIT
