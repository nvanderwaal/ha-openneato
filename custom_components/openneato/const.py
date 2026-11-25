"""Constants for OpenNeato."""

from datetime import timedelta

DOMAIN = "openneato"
MANUFACTURER = "Neato Robotics (OpenNeato firmware)"
SCAN_INTERVAL = timedelta(seconds=15)
# Faster polling right after a command, so the UI reflects the change quickly.
REFRESH_AFTER_COMMAND = 3
# Cleaning history is refreshed after each clean and otherwise this often (seconds).
HISTORY_INTERVAL = 15 * 60
