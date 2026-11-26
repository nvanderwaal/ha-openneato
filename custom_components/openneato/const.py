"""Constants for OpenNeato."""

from datetime import timedelta

DOMAIN = "openneato"
MANUFACTURER = "Neato Robotics (OpenNeato firmware)"
SCAN_INTERVAL = timedelta(seconds=15)
# Faster polling right after a command, so the UI reflects the change quickly.
REFRESH_AFTER_COMMAND = 3
# Cleaning history only changes when a clean ends. It is fetched right after each clean
# and otherwise this often (seconds), as a safety net.
HISTORY_INTERVAL = 20 * 60
# Retry delay when the history is incomplete (robot still writing, more maps to fetch).
HISTORY_RETRY = 60
# At most this many session tracks are downloaded per update, to spare the ESP32.
MAP_DOWNLOADS_PER_UPDATE = 3
