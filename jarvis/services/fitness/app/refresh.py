"""One place that means "go get everything current".

Both the backend launch and a frontend reload call this, so opening or
refreshing the app always re-checks Garmin rather than showing whatever
happened to be in the database from last time.

`data_version` is the signal the UI watches: any source that writes new rows
bumps it, and the frontend refetches when it changes.
"""
import threading
import time

from . import garmin_service

# A reload-triggered refresh is cheap but not free (real Garmin API calls),
# and reloads can come in bursts while you're using the app. Two minutes is
# short enough that "reload to update" always feels true, long enough that
# hammering ⌘R doesn't hammer Garmin.
MIN_INTERVAL_SECONDS = 120
RELOAD_SYNC_DAYS = 2

_data_version = 0
_last_started = 0.0
_lock = threading.Lock()


def bump_data_version() -> int:
    """Called by any source that wrote new data."""
    global _data_version
    with _lock:
        _data_version += 1
        return _data_version


def data_version() -> int:
    with _lock:
        return _data_version


def refresh_all(days: int = RELOAD_SYNC_DAYS, force: bool = False) -> dict:
    """Kicks off a Garmin sync. Returns immediately — it runs in a background
    thread and reports through `status()`."""
    global _last_started
    now = time.monotonic()

    with _lock:
        too_soon = not force and (now - _last_started) < MIN_INTERVAL_SECONDS
        if not too_soon:
            _last_started = now

    if too_soon:
        return {"started": False, "reason": "refreshed moments ago", **status()}

    garmin_service.start(days=days, auto_save=False)
    return {"started": True, **status()}


def status() -> dict:
    garmin = garmin_service.snapshot()
    return {
        "data_version": data_version(),
        "busy": garmin["status"] == "running",
        "garmin": garmin,
    }
