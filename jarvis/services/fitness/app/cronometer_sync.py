"""Pulls daily nutrition totals from Cronometer — manual trigger only.

No launch sync, no hourly loop: Cronometer rate-limits its export endpoints
(~10/day observed empirically — a real 429 was hit during testing), and this
app's automatic Garmin-style refresh-on-every-reload pattern blew through
that budget in a single sitting. So this only ever runs when the user
explicitly clicks sync, and a persisted daily counter (survives app restarts,
since this is launched on demand) stops them from doing that more than the
budget allows.

Each sync spends 2 exports (`daily_summary` + `get_food_log`), which is why
the default budget is conservative relative to Cronometer's raw cap.

Data shape: one row per day with calories/protein/carbs/fat plus every
micronutrient Cronometer tracks, stored in nutrition_logs.micronutrients.
Cronometer's per-meal export (`servings`) has no macro data — just food
name/amount/time — so per-meal macros aren't reconstructable from the API;
`food_items` carries the raw food list for display, sourced separately from
`get_food_log`.

Unofficial client (same category as python-garminconnect): logs in as you and
speaks the same GWT-RPC protocol the Cronometer web app uses internally, so
it can break when Cronometer changes their frontend. Gold-tier account
required for the export functions used here.
"""
import logging
import os
import threading
from datetime import date, datetime, timedelta

from . import models
from .database import SessionLocal

logger = logging.getLogger("volt.cronometer")

LOOKBACK_DAYS = int(os.environ.get("CRONOMETER_LOOKBACK_DAYS", "7"))
DAILY_SYNC_BUDGET = int(os.environ.get("CRONOMETER_DAILY_SYNC_LIMIT", "5"))

_state = {"status": "idle", "detail": None, "checked_at": None}
_lock = threading.Lock()


def snapshot() -> dict:
    with _lock:
        return dict(_state)


def _set(**kwargs) -> None:
    with _lock:
        _state.update(kwargs)


def is_configured() -> bool:
    return bool(os.environ.get("CRONOMETER_EMAIL") and os.environ.get("CRONOMETER_PASSWORD"))


def _budget_row(db) -> models.CronometerSyncBudget:
    today = date.today()
    row = db.get(models.CronometerSyncBudget, today)
    if row is None:
        row = models.CronometerSyncBudget(date=today, count=0)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def budget_status() -> dict:
    """Read-only: how many manual syncs are left today, without spending one."""
    db = SessionLocal()
    try:
        row = _budget_row(db)
        return {"limit": DAILY_SYNC_BUDGET, "used": row.count, "remaining": max(0, DAILY_SYNC_BUDGET - row.count)}
    finally:
        db.close()


def _spend_one(db) -> int:
    """Increments today's counter and returns the remaining budget. Spent right
    after login succeeds, before the export calls — a partially-failed sync
    still used real quota against Cronometer's own limiter."""
    row = _budget_row(db)
    row.count += 1
    db.commit()
    return max(0, DAILY_SYNC_BUDGET - row.count)


# Cronometer's CSV export mislabels micrograms as "Âµg" (a UTF-8/Latin-1
# mismatch on their end, not ours) — cosmetic, but ugly to store verbatim.
def _clean_key(key: str) -> str:
    return key.replace("Âµg", "µg").strip()


_MAIN_FIELDS = {"Date", "Energy (kcal)", "Protein (g)", "Carbs (g)", "Fat (g)", "Completed"}


def _to_float(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _row_to_fields(row: dict) -> tuple[dict, dict]:
    """Splits one daily_summary row into (macros, micronutrients).
    Zero-value micronutrients are dropped rather than stored as noise —
    Cronometer reports 0.00 for anything not logged, not necessarily a true
    zero, so keeping only nonzero readings avoids implying precision we don't
    have."""
    micros = {}
    for raw_key, raw_value in row.items():
        key = _clean_key(raw_key)
        if key in _MAIN_FIELDS:
            continue
        val = _to_float(raw_value)
        if val:
            micros[key] = val
    return {
        "calories": _to_float(row.get("Energy (kcal)")) or 0.0,
        "protein": _to_float(row.get("Protein (g)")) or 0.0,
        "carbs": _to_float(row.get("Carbs (g)")) or 0.0,
        "fat": _to_float(row.get("Fat (g)")) or 0.0,
    }, micros


def _food_items_for_day(rows: list[dict]) -> list[dict]:
    """The servings export has no macros, but it does have what the daily
    summary doesn't: what was actually eaten. Used only for display — the
    macro totals still come from daily_summary."""
    items = []
    for row in rows:
        name = row.get("Food Name")
        if not name:
            continue
        items.append({"name": name, "amount": row.get("Amount") or "", "time": row.get("Time") or "", "group": row.get("Group") or ""})
    return items


def _upsert_day(db, day: date, macros: dict, micros: dict, food_items: list[dict]) -> None:
    """One row per day — but a day's total can grow as more food gets logged
    in Cronometer during the day, so this overwrites rather than appends."""
    existing = (
        db.query(models.NutritionLog)
        .filter(models.NutritionLog.source == "cronometer", models.NutritionLog.datetime == datetime.combine(day, datetime.min.time()))
        .first()
    )
    if existing is None:
        existing = models.NutritionLog(
            datetime=datetime.combine(day, datetime.min.time()),
            source="cronometer",
            food_name=f"Cronometer — {day.isoformat()}",
        )
        db.add(existing)

    existing.calories = macros["calories"]
    existing.protein = macros["protein"]
    existing.carbs = macros["carbs"]
    existing.fat = macros["fat"]
    existing.micronutrients = micros or None
    existing.food_items = food_items or None


def sync_once(days: int = LOOKBACK_DAYS) -> dict:
    if not is_configured():
        _set(status="disabled", detail="CRONOMETER_EMAIL / CRONOMETER_PASSWORD not set")
        return snapshot()

    db = SessionLocal()
    try:
        budget = budget_status()
        if budget["remaining"] <= 0:
            _set(status="error", detail=f"daily sync limit reached ({budget['limit']}/day) — try again tomorrow")
            return snapshot()
    finally:
        db.close()

    from cronometer_mcp.client import CronometerClient

    _set(status="checking", detail=f"pulling last {days} days from Cronometer")
    db = SessionLocal()
    updated = 0
    try:
        client = CronometerClient(os.environ["CRONOMETER_EMAIL"], os.environ["CRONOMETER_PASSWORD"])
        client.authenticate()
        remaining = _spend_one(db)

        # +1 day hedge: this machine's local date and Cronometer's own
        # day-boundary (which may run on account-timezone or UTC) can
        # disagree near midnight in either direction, so a food entry can land
        # on what we'd call "tomorrow." Asking one day ahead costs nothing
        # extra when there's no such entry, and fixes it silently when there is.
        end = date.today() + timedelta(days=1)
        start = end - timedelta(days=days)
        summary = client.get_daily_summary(start, end)
        servings = client.get_food_log(start, end)

        items_by_day: dict[str, list[dict]] = {}
        for row in servings:
            items_by_day.setdefault(row.get("Day", ""), []).append(row)

        for row in summary:
            day_str = row.get("Date")
            if not day_str:
                continue
            day = date.fromisoformat(day_str)
            macros, micros = _row_to_fields(row)
            if macros["calories"] == 0 and not micros:
                continue  # a day with nothing logged — don't write an empty row
            food_items = _food_items_for_day(items_by_day.get(day_str, []))
            _upsert_day(db, day, macros, micros, food_items)
            updated += 1

        db.commit()
        _set(
            status="ok",
            detail=(f"updated {updated} day(s) — {remaining} sync(s) left today" if updated
                    else f"no data in range — {remaining} sync(s) left today"),
            checked_at=datetime.now().isoformat(),
        )
    except Exception as e:
        logger.exception("Cronometer sync failed")
        _set(status="error", detail=f"{type(e).__name__}: {e}")
    finally:
        db.close()

    if updated:
        from . import refresh

        refresh.bump_data_version()

    return snapshot()


def start(days: int = LOOKBACK_DAYS) -> bool:
    """Manual trigger only — nothing calls this automatically."""
    with _lock:
        if _state["status"] == "checking":
            return False
    threading.Thread(target=sync_once, args=(days,), daemon=True).start()
    return True
