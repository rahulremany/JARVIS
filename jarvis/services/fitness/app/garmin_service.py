"""Runs the Garmin sync in the background and records its progress.

The app is launched on demand (see fitness.sh), so every launch kicks off a
sync immediately — this module is what lets the UI show that it's happening
and refetch the moment fresh data lands, instead of silently rendering
whatever was in the DB from the last session.

State is deliberately in-process: it describes *this* run of the app. The
durable record of what has been synced is the data itself (garmin_recovery /
workouts rows).
"""
import logging
import os
import threading
from datetime import datetime, timezone

from . import garmin_sync
from .database import SessionLocal

logger = logging.getLogger("volt.sync")

# status:
#   idle     — nothing has run yet this session
#   running  — a sync is in flight
#   ok       — last run finished, data is fresh
#   error    — last run failed (detail says why)
#   mfa      — Garmin wants an MFA code; needs a manual CLI run to re-auth
#   disabled — no GARMIN_EMAIL/GARMIN_PASSWORD configured
_state: dict = {
    "status": "idle",
    "detail": None,
    "started_at": None,
    "finished_at": None,
    # Bumped on every successful sync. The frontend watches this and refetches
    # when it changes, which is what makes "open the app and see latest" work.
    "data_version": 0,
    # Auto-saved workout: none | saving | saved | skipped | failed
    "workout_status": "none",
    "workout_detail": None,
}
_lock = threading.Lock()


def snapshot() -> dict:
    with _lock:
        return dict(_state)


def _set(**kwargs) -> None:
    with _lock:
        _state.update(kwargs)


def auto_save_enabled() -> bool:
    return os.environ.get("GARMIN_AUTO_SAVE_WORKOUT", "1").lower() not in ("0", "false", "no")


def _auto_save_todays_workout() -> None:
    """Asks Claude for today's session and uploads it to the Garmin workout
    library, so it's already on the watch by the time you look. Idempotent per
    day: if something was already saved for today (auto or by hand), skip.

    Runs only after a successful sync, so the recommendation sees today's
    recovery numbers rather than yesterday's.
    """
    from datetime import date

    from . import models
    from .routers import workout_coach

    db = SessionLocal()
    try:
        if db.get(models.GarminSavedWorkout, date.today()) is not None:
            _set(workout_status="skipped", workout_detail="already saved for today")
            return

        _set(workout_status="saving", workout_detail="asking Claude for today's session")
        rec = workout_coach.todays_workout(db=db)
        result = workout_coach._save_to_garmin(
            f"Volt — {rec.summary}"[:80],
            [e.model_dump() for e in rec.exercises],
            db=db,
            auto=True,
        )
        detail = f"{result['workout_name']} ({len(result['uploaded'])} exercises)"
        if result["skipped"]:
            detail += f" — skipped {', '.join(result['skipped'])}"
        _set(workout_status="saved", workout_detail=detail)
        logger.info("Auto-saved workout to Garmin: %s", detail)
    except Exception as e:
        logger.exception("Auto-save of today's workout failed")
        _set(workout_status="failed", workout_detail=f"{type(e).__name__}: {e}")
    finally:
        db.close()


def is_configured() -> bool:
    return bool(os.environ.get("GARMIN_EMAIL") and os.environ.get("GARMIN_PASSWORD"))


def _run(days: int, auto_save: bool) -> None:
    try:
        client = garmin_sync.login(interactive=False)
        garmin_sync.run_sync(client, days=days)
    except garmin_sync.MfaRequiredError as e:
        logger.warning("Garmin sync needs MFA: %s", e)
        _set(status="mfa", detail=str(e), finished_at=_now())
        return
    except Exception as e:
        logger.exception("Garmin sync failed")
        _set(status="error", detail=f"{type(e).__name__}: {e}", finished_at=_now())
        return

    from . import refresh

    with _lock:
        _state.update(status="ok", detail=f"synced {days} days", finished_at=_now())
    _state["data_version"] = refresh.bump_data_version()
    logger.info("Garmin sync completed (%s days)", days)

    if auto_save:
        _auto_save_todays_workout()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def start(days: int = 7, auto_save: bool | None = None) -> bool:
    """Kicks off a sync in a background thread. Returns False if one is already
    running (callers treat that as "fine, it's already happening")."""
    auto_save = auto_save_enabled() if auto_save is None else auto_save

    if not is_configured():
        _set(status="disabled", detail="GARMIN_EMAIL/GARMIN_PASSWORD not set in backend/.env")
        return False

    with _lock:
        if _state["status"] == "running":
            return False
        _state.update(status="running", detail=f"pulling last {days} days", started_at=_now(), finished_at=None)

    threading.Thread(target=_run, args=(days, auto_save), daemon=True).start()
    return True
