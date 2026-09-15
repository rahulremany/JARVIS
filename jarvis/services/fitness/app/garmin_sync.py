"""
Pulls recovery data (HRV, sleep score, resting HR, stress) into garmin_recovery,
and strength-training activity history (exercise names, reps, weight per set)
into workouts, from Garmin Connect via the unofficial python-garminconnect
library (see CLAUDE.md spec section 5.1 for why this is unofficial rather
than the sanctioned Garmin Health API).

Usage:
    python -m app.garmin_sync                 # sync the last 7 days
    python -m app.garmin_sync --days 30        # sync the last 30 days
    python -m app.garmin_sync --dry-run        # print raw API responses, write nothing

Requires GARMIN_EMAIL and GARMIN_PASSWORD in backend/.env.

Garmin's internal API response shape isn't officially documented and has
shifted across library versions, so field extraction below is defensive
(falls back across a few known key names). Run --dry-run first if a field
comes back empty to see the raw response and adjust the extractor.
"""
import argparse
import os
import sys
import time
from datetime import date, timedelta

from dotenv import load_dotenv
from garminconnect import Garmin

from . import models
from .database import SessionLocal

load_dotenv()

TOKEN_STORE = os.path.join(os.path.dirname(__file__), "..", ".garmin_tokens")


class MfaRequiredError(Exception):
    """Raised instead of blocking on input() when running non-interactively
    (e.g. the background auto-sync thread) and Garmin demands an MFA code."""


def login(interactive: bool = True) -> Garmin:
    email = os.environ.get("GARMIN_EMAIL")
    password = os.environ.get("GARMIN_PASSWORD")
    if not email or not password:
        if interactive:
            print("Set GARMIN_EMAIL and GARMIN_PASSWORD in backend/.env")
            sys.exit(1)
        raise RuntimeError("GARMIN_EMAIL/GARMIN_PASSWORD not set")

    client = Garmin(email, password)
    result1, result2 = client.login(tokenstore=TOKEN_STORE)

    if result1 == "needs_mfa":
        if not interactive:
            raise MfaRequiredError("Garmin requires an MFA code — run `python -m app.garmin_sync` manually once to re-authenticate")
        mfa_code = input("Garmin MFA code: ").strip()
        client.resume_login(result2, mfa_code)

    client.client.dump(TOKEN_STORE)

    return client


def extract_hrv(data: dict) -> float | None:
    summary = (data or {}).get("hrvSummary") or {}
    return summary.get("lastNightAvg") or summary.get("weeklyAvg")


def extract_sleep_score(data: dict) -> float | None:
    dto = (data or {}).get("dailySleepDTO") or {}
    scores = dto.get("sleepScores") or {}
    overall = scores.get("overall") or {}
    return overall.get("value") or dto.get("sleepScorePercentage")


def extract_resting_hr(stats: dict) -> float | None:
    return (stats or {}).get("restingHeartRate")


def extract_stress(data: dict) -> float | None:
    return (data or {}).get("avgStressLevel")


GRAMS_PER_LB = 453.59237


def sync_activities(client: Garmin, session, start_day: date, end_day: date, dry_run: bool) -> None:
    """Pulls strength_training activities and their per-set exercise/weight/rep
    detail. Contrary to the spec's assumption (Garmin's Training API not
    exposing set/rep detail), get_activity_exercise_sets() does return it —
    exercise name, reps, and weight (in grams) per set."""
    activities = client.get_activities_by_date(start_day.isoformat(), end_day.isoformat())
    strength_activities = [a for a in activities if (a.get("activityType") or {}).get("typeKey") == "strength_training"]

    for activity in strength_activities:
        activity_id = activity["activityId"]
        activity_date = date.fromisoformat(activity["startTimeLocal"][:10])
        exercise_sets = client.get_activity_exercise_sets(activity_id)

        if dry_run:
            print(f"--- activity {activity_id} ({activity.get('activityName')}, {activity_date}) ---")
            print(exercise_sets)
            continue

        # group ACTIVE sets by exercise name, in the order they occur
        grouped: dict[str, list[dict]] = {}
        for s in exercise_sets.get("exerciseSets", []):
            if s.get("setType") != "ACTIVE" or s.get("repetitionCount") is None:
                continue
            exercises = s.get("exercises") or []
            name = (exercises[0].get("name") or exercises[0].get("category") or "Unknown") if exercises else "Unknown"
            name = name.replace("_", " ").title()
            weight_lb = round((s.get("weight") or 0) / GRAMS_PER_LB, 1)
            grouped.setdefault(name, []).append({"reps": s["repetitionCount"], "weight": weight_lb})

        if not grouped:
            continue

        # idempotent re-sync: replace this date's garmin-sourced rows rather than duplicating
        session.query(models.Workout).filter(
            models.Workout.date == activity_date, models.Workout.source == "garmin"
        ).delete()

        for exercise_name, sets in grouped.items():
            session.add(models.Workout(date=activity_date, source="garmin", exercise=exercise_name, sets=sets))

        session.commit()
        print(f"synced activity {activity_date} '{activity.get('activityName')}': {list(grouped.keys())}")


def sync_day(client: Garmin, session, day: date, dry_run: bool) -> None:
    iso = day.isoformat()
    hrv_raw = client.get_hrv_data(iso)
    sleep_raw = client.get_sleep_data(iso)
    stats_raw = client.get_stats(iso)
    stress_raw = client.get_stress_data(iso)

    if dry_run:
        print(f"--- {iso} ---")
        print("hrv:", hrv_raw)
        print("sleep:", sleep_raw)
        print("stats:", stats_raw)
        print("stress:", stress_raw)
        return

    entry = session.get(models.GarminRecovery, day)
    if entry is None:
        entry = models.GarminRecovery(date=day)
        session.add(entry)

    entry.hrv = extract_hrv(hrv_raw)
    entry.sleep_score = extract_sleep_score(sleep_raw)
    entry.resting_hr = extract_resting_hr(stats_raw)
    entry.stress_score = extract_stress(stress_raw)
    session.commit()

    print(f"synced {iso}: hrv={entry.hrv} sleep={entry.sleep_score} rhr={entry.resting_hr} stress={entry.stress_score}")


def run_sync(client: Garmin, days: int = 7, dry_run: bool = False) -> None:
    """Runs a full recovery + activity sync using an already-logged-in client.
    Shared by the CLI entrypoint and the background auto-sync thread."""
    session = SessionLocal()
    today = date.today()
    try:
        for offset in range(days):
            day = today - timedelta(days=offset)
            sync_day(client, session, day, dry_run)
            time.sleep(1)  # basic courtesy rate-limit

        sync_activities(client, session, today - timedelta(days=days - 1), today, dry_run)
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7, help="How many days back to sync (default 7)")
    parser.add_argument("--dry-run", action="store_true", help="Print raw API responses instead of writing to the DB")
    args = parser.parse_args()

    client = login()
    run_sync(client, args.days, args.dry_run)


if __name__ == "__main__":
    main()
