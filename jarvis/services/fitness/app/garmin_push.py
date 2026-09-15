"""Uploads a workout to Garmin Connect's saved-workout library.

Deliberately upload-only: no scheduling, no push-to-device. The workout lands
in "My Workouts" exactly like one built in the Garmin Connect editor, syncs to
the watch, and you pick it from the workout list when you feel like doing it —
rather than the app putting a session on your calendar for you.

Garmin identifies each movement by a (category, exerciseName) pair from a
fixed vocabulary, not by free text, so exercise names are resolved against the
catalog the garminconnect library ships (1527 exercises / 47 categories).
Anything unresolvable is reported back to the caller rather than silently
uploaded as something else.
"""
import re
from dataclasses import dataclass

from garminconnect import Garmin
from garminconnect import exercises as catalog
from garminconnect.workout import StrengthWorkout, WorkoutSegment, create_strength_set

LB_PER_KG = 2.20462
DEFAULT_REST_SECONDS = 90

# Spelling differences between what our sync writes (from Garmin's own activity
# feed, title-cased) and what the workout catalog calls the same movement.
ALIASES = {
    "flye": "fly",
    "flyes": "flys",
}


def _normalize(name: str) -> str:
    """Case- and punctuation-insensitive key, with spelling aliases applied.
    'Ez Bar Pullover' and 'EZ Bar Pullover' must land on the same entry."""
    words = [ALIASES.get(w, w) for w in re.findall(r"[a-z0-9]+", name.lower())]
    return "".join(words)


_BY_NORM: dict[str, dict] = {}
for _entry in catalog.EXERCISES:
    _BY_NORM.setdefault(_normalize(_entry["name"]), _entry)


@dataclass
class ResolvedExercise:
    requested: str
    category: str
    exercise_name: str
    matched_name: str


def resolve_exercise(name: str) -> ResolvedExercise | None:
    """Maps a free-text exercise name onto Garmin's catalog. Tries exact
    display name, then a normalized match, then a unique substring match."""
    entry = catalog.resolve(name) or _BY_NORM.get(_normalize(name))

    if entry is None:
        hits = catalog.find(name)
        if len(hits) == 1:
            entry = hits[0]

    if entry is None:
        return None

    return ResolvedExercise(
        requested=name,
        category=entry["category"],
        exercise_name=entry["exercise"],
        matched_name=entry["name"],
    )


def build_strength_workout(name: str, exercises: list[dict]) -> tuple[StrengthWorkout, list[ResolvedExercise], list[str]]:
    """Builds a multi-exercise strength workout.

    Each item in `exercises` is {exercise, sets, reps, weight_lb?, rest_seconds?}.
    Returns the workout alongside what resolved and what didn't, so the caller
    can tell the user which movements Garmin wouldn't accept.
    """
    steps = []
    resolved: list[ResolvedExercise] = []
    unresolved: list[str] = []
    step_order = 1

    for item in exercises:
        match = resolve_exercise(item["exercise"])
        if match is None:
            unresolved.append(item["exercise"])
            continue

        weight_lb = item.get("weight_lb")
        steps.append(
            create_strength_set(
                category=match.category,
                step_order=step_order,
                sets=max(1, int(item.get("sets", 1))),
                reps=max(1, int(item.get("reps", 8))),
                rest_seconds=item.get("rest_seconds") or DEFAULT_REST_SECONDS,
                exercise_name=match.exercise_name,
                weight_kg=(weight_lb / LB_PER_KG) if weight_lb else None,
            )
        )
        resolved.append(match)
        step_order += 3  # repeat group + inner exercise step + rest step

    if not steps:
        raise ValueError(
            "None of the exercises could be matched to Garmin's catalog: "
            + ", ".join(unresolved)
        )

    workout = StrengthWorkout(
        workoutName=name,
        estimatedDurationInSecs=0,
        workoutSegments=[
            WorkoutSegment(
                segmentOrder=1,
                sportType={"sportTypeId": 5, "sportTypeKey": "strength_training"},
                workoutSteps=steps,
            )
        ],
    )
    return workout, resolved, unresolved


def upload_workout(client: Garmin, name: str, exercises: list[dict], send_to_device: bool = True) -> dict:
    """Saves the workout to the Garmin Connect workout library and queues it for
    the watch.

    The queue step matters: uploading alone only puts the workout in the cloud
    library, which the phone app can browse directly but the watch cannot. A
    watch-initiated sync only pulls files sitting in its device-message queue,
    so without this the workout is visible in Garmin Connect and absent from
    the watch. This is the API behind "Send to Device" — it queues a FIT file,
    it does not schedule anything on the calendar.
    """
    workout, resolved, unresolved = build_strength_workout(name, exercises)
    uploaded = client.upload_strength_workout(workout)
    workout_id = uploaded.get("workoutId")

    device = None
    device_error = None
    if send_to_device and workout_id:
        try:
            last_used = client.get_device_last_used()
            device = last_used.get("lastUsedDeviceName") or str(last_used.get("userDeviceId"))
            client.push_workout_to_device(workout_id, last_used["userDeviceId"])
        except Exception as e:
            # The workout is safely in the library either way — report the
            # queue failure rather than failing the whole save.
            device_error = f"{type(e).__name__}: {e}"

    return {
        "workout_id": workout_id,
        "workout_name": name,
        "uploaded": [
            {"requested": r.requested, "matched": r.matched_name} for r in resolved
        ],
        "skipped": unresolved,
        "sent_to_device": device if device_error is None else None,
        "device_error": device_error,
    }
