import json
import os
import re
from datetime import date, datetime, timedelta

import anthropic
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import coach_memory, garmin_sync, models, schemas
from ..database import get_db

router = APIRouter(prefix="/coach", tags=["coach"])

RECOMMENDATION_SYSTEM_PROMPT = """You are a strength coach recommending a specific, actionable \
workout for today. You'll be given the lifter's logged workouts from the last \
14 days (exercise names, sets with weight/reps/rpe) and their most recent \
Garmin recovery metrics (HRV, sleep score, resting heart rate, stress score).

Prioritize the recovery signals: if recovery looks poor (low HRV or sleep \
relative to what's typical, elevated resting HR or stress), recommend a \
lighter session or a deload rather than pushing hard. If recovery looks good \
and a lift has been trending up, recommend progressive overload with a \
specific target weight based on the most recent working sets for that \
exercise. If there isn't enough history for an exercise, give a sensible \
starting point instead of leaving fields blank. If there's no workout \
history at all, recommend a reasonable general full-body strength session.

Be specific and cite the actual numbers you're reacting to in your reasoning."""

CHAT_SYSTEM_PROMPT = """You are a knowledgeable, direct strength coach chatting \
with the user inside their personal training app. You have access to their \
recent logged workouts (from manual entry and their Garmin watch) and their \
latest Garmin recovery metrics, included below — each workout has an "id" \
you must use when editing it.

Answer questions about programming, exercise technique, how to approach a \
specific lift today, progression, deloads, and recovery. Be conversational \
but substantive, and cite the user's actual logged numbers when relevant \
instead of speaking generically. Keep answers reasonably concise unless the \
user asks for depth.

Format replies in markdown so they're easy to scan on a phone: use **bold** \
for exercise names and key numbers, `##` subheadings to separate sections, \
and bulleted or numbered lists when walking through multiple exercises or \
steps. Prefer short paragraphs over one dense block of text. Don't wrap the \
whole reply in a code block.

You can also act directly using tools:
- create_workout_entry: when the user wants to add a new exercise/sets to a day's log.
- update_workout_entry: when the user wants to change the sets on an existing logged exercise (use its id from the context above).
- remember: call this tool — actually call it, saying "noted" in your reply is not the same thing and the fact will be lost — whenever the user tells you something durable about themselves that isn't in the logged data — an injury or nagging joint, their goal and timeline, equipment or gym constraints, schedule, food preferences or restrictions, a coaching approach they said works or doesn't. Save the fact itself, not the small talk around it. Don't record sets/reps/macros/recovery numbers — those are already in the database and re-logging them here wastes context. Call it once per distinct fact, before you write your reply. Don't announce every save; just weave it into your reply naturally.

- forget: when something you remembered is now wrong or outdated (an injury that healed, a goal that changed, a gym they left). Forget the stale fact, then remember the new one — don't leave both sitting there contradicting each other.

- save_workout_to_garmin: when the user asks to send a workout to their Garmin watch or save it to Garmin. It saves to their Garmin Connect workout library (like one built in the Garmin editor) so they can pick it from the watch — it does NOT schedule it on a date. Exercise names are matched against Garmin's catalog, so report back clearly which movements were saved and name any that were skipped.

Only call a tool when the user has actually asked for that action, not speculatively. After a tool call, confirm in plain language what you did with the real numbers used."""

TOOLS = [
    {
        "name": "create_workout_entry",
        "description": "Create a new logged exercise entry for a given date (defaults to today).",
        "input_schema": {
            "type": "object",
            "properties": {
                "exercise": {"type": "string"},
                "date": {"type": "string", "description": "YYYY-MM-DD, defaults to today if omitted"},
                "sets": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "weight": {"type": "number"},
                            "reps": {"type": "integer"},
                            "rpe": {"type": "number"},
                        },
                        "required": ["weight", "reps"],
                    },
                },
            },
            "required": ["exercise", "sets"],
            "additionalProperties": False,
        },
    },
    {
        "name": "update_workout_entry",
        "description": "Replace the sets on an existing logged workout entry, identified by its id.",
        "input_schema": {
            "type": "object",
            "properties": {
                "workout_id": {"type": "integer"},
                "sets": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "weight": {"type": "number"},
                            "reps": {"type": "integer"},
                            "rpe": {"type": "number"},
                        },
                        "required": ["weight", "reps"],
                    },
                },
            },
            "required": ["workout_id", "sets"],
            "additionalProperties": False,
        },
    },
    {
        "name": "save_workout_to_garmin",
        "description": (
            "Save a multi-exercise strength workout to the user's Garmin Connect "
            "workout library so it syncs to the watch and can be selected from the "
            "workout list. Does not schedule it on any date."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Workout name as it will appear in Garmin"},
                "exercises": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "exercise": {"type": "string"},
                            "sets": {"type": "integer"},
                            "reps": {"type": "integer"},
                            "weight_lb": {"type": "number"},
                        },
                        "required": ["exercise", "sets", "reps"],
                    },
                },
            },
            "required": ["name", "exercises"],
            "additionalProperties": False,
        },
    },
    {
        "name": "forget",
        "description": "Remove a remembered fact that is now outdated or wrong. Pass distinctive words from the fact to drop.",
        "input_schema": {
            "type": "object",
            "properties": {"match": {"type": "string", "description": "Distinctive text from the fact to remove, e.g. 'left shoulder clicks'."}},
            "required": ["match"],
            "additionalProperties": False,
        },
    },
    {
        "name": "remember",
        "description": (
            "Save a durable fact about the user for future sessions (injury, goal, "
            "equipment, schedule, preference). Not for workout numbers, "
            "which are already stored in the database."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "fact": {"type": "string", "description": "One self-contained sentence, written to be useful months from now."},
            },
            "required": ["fact"],
            "additionalProperties": False,
        },
    },
]


def _build_context(db: Session) -> str:
    since = date.today() - timedelta(days=14)
    recent_workouts = (
        db.query(models.Workout)
        .filter(models.Workout.date >= since)
        .order_by(models.Workout.date.desc())
        .all()
    )
    recovery = db.query(models.GarminRecovery).order_by(models.GarminRecovery.date.desc()).first()

    history_payload = [
        {"id": w.id, "date": w.date.isoformat(), "exercise": w.exercise, "sets": w.sets}
        for w in recent_workouts
    ]
    recovery_payload = (
        {
            "date": recovery.date.isoformat(),
            "hrv": recovery.hrv,
            "sleep_score": recovery.sleep_score,
            "resting_hr": recovery.resting_hr,
            "stress_score": recovery.stress_score,
        }
        if recovery
        else None
    )

    memory = coach_memory.as_prompt_context()
    return (
        (f"{memory}\n\n---\n\n" if memory else "")
        + f"Last 14 days of logged workouts:\n{json.dumps(history_payload, indent=2)}\n\n"
        + f"Latest recovery data:\n{json.dumps(recovery_payload, indent=2)}"
    )


def _get_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY is not set in the backend environment")
    return anthropic.Anthropic(api_key=api_key)


def _execute_tool(name: str, tool_input: dict, db: Session) -> dict:
    if name == "create_workout_entry":
        entry_date = date.fromisoformat(tool_input["date"]) if tool_input.get("date") else date.today()
        entry = models.Workout(
            date=entry_date,
            source="manual",
            exercise=tool_input["exercise"],
            sets=tool_input["sets"],
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return {"ok": True, "id": entry.id}

    if name == "update_workout_entry":
        entry = db.get(models.Workout, tool_input["workout_id"])
        if not entry:
            return {"ok": False, "error": f"No workout with id {tool_input['workout_id']}"}
        entry.sets = tool_input["sets"]
        db.commit()
        return {"ok": True, "id": entry.id}

    if name == "forget":
        return {"ok": True, "result": coach_memory.forget(tool_input["match"])}

    if name == "remember":
        return {"ok": True, "result": coach_memory.remember(tool_input["fact"])}

    if name == "save_workout_to_garmin":
        try:
            return {"ok": True, **_save_to_garmin(tool_input["name"], tool_input["exercises"], db=db)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    return {"ok": False, "error": f"Unknown tool {name}"}


@router.get("/todays-workout", response_model=schemas.WorkoutRecommendation)
def todays_workout(db: Session = Depends(get_db)):
    client = _get_client()
    user_content = f"{_build_context(db)}\n\nRecommend today's workout."

    try:
        response = client.messages.parse(
            model="claude-sonnet-5",
            # Generous ceiling: a truncated response yields invalid JSON that
            # parse() rejects, which previously surfaced as an intermittent
            # 500 whenever the recommendation ran long. max_tokens is a cap,
            # not a target, so a high value costs nothing on short answers.
            max_tokens=16000,
            system=RECOMMENDATION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
            output_format=schemas.WorkoutRecommendation,
        )
    except anthropic.APIStatusError as e:
        raise HTTPException(status_code=502, detail=f"Claude API error: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise HTTPException(status_code=502, detail=f"Could not reach Claude API: {e}") from e

    if response.stop_reason == "max_tokens":
        raise HTTPException(status_code=502, detail="Recommendation was cut off before it finished — try again.")

    return response.parsed_output


@router.post("/chat", response_model=schemas.ChatResponse)
def chat(req: schemas.ChatRequest, db: Session = Depends(get_db)):
    client = _get_client()
    system = f"{CHAT_SYSTEM_PROMPT}\n\n{_build_context(db)}"
    messages = [{"role": m.role, "content": m.content} for m in req.messages]

    try:
        for _ in range(5):  # guard against runaway tool loops
            response = client.messages.create(
                model="claude-sonnet-5",
                max_tokens=16000,
                system=system,
                messages=messages,
                tools=TOOLS,
            )

            if response.stop_reason != "tool_use":
                reply = next((b.text for b in response.content if b.type == "text"), "")
                last_user = next((m.content for m in reversed(req.messages) if m.role == "user"), "")
                coach_memory.log_exchange(last_user, reply)
                return schemas.ChatResponse(reply=reply)

            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = _execute_tool(block.name, block.input, db)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result),
                    })
            messages.append({"role": "user", "content": tool_results})

        return schemas.ChatResponse(reply="Sorry, that took too many steps — try rephrasing.")
    except anthropic.APIStatusError as e:
        raise HTTPException(status_code=502, detail=f"Claude API error: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise HTTPException(status_code=502, detail=f"Could not reach Claude API: {e}") from e


def _reps_to_int(reps) -> int:
    """The coach writes reps as a range ('8-10'); Garmin wants one number, so
    take the low end — the conservative target to hit for every set."""
    if isinstance(reps, int):
        return reps
    match = re.search(r"\d+", str(reps))
    return int(match.group()) if match else 8


def _save_to_garmin(name: str, exercises: list[dict], db: Session | None = None, auto: bool = False) -> dict:
    from .. import garmin_push

    try:
        client = garmin_sync.login(interactive=False)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not log in to Garmin: {e}") from e

    payload = [
        {
            "exercise": e["exercise"],
            "sets": e.get("sets") or 3,
            "reps": _reps_to_int(e.get("reps")),
            "weight_lb": e.get("weight_lb") if "weight_lb" in e else e.get("target_weight"),
            "rest_seconds": e.get("rest_seconds"),
        }
        for e in exercises
    ]

    try:
        result = garmin_push.upload_workout(client, name, payload)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Garmin rejected the workout: {e}") from e

    if db is not None:
        _record_saved_workout(db, result, auto=auto)
    return result


def _record_saved_workout(db: Session, result: dict, auto: bool) -> None:
    """Upserts today's row so a later manual save overwrites the auto-saved one
    rather than adding a second record for the same day."""
    today = date.today()
    row = db.get(models.GarminSavedWorkout, today)
    if row is None:
        row = models.GarminSavedWorkout(date=today)
        db.add(row)
    row.workout_id = result.get("workout_id")
    row.workout_name = result["workout_name"]
    row.exercises = result["uploaded"]
    row.skipped = result["skipped"]
    row.auto = 1 if auto else 0
    row.created_at = datetime.now()
    db.commit()


@router.post("/save-workout", response_model=schemas.SaveWorkoutResponse)
def save_workout(req: schemas.SaveWorkoutRequest, db: Session = Depends(get_db)):
    """Saves a workout to the Garmin Connect library — no scheduling, no
    calendar entry. It shows up on the watch under saved workouts."""
    name = req.name or f"Volt — {date.today().isoformat()}"
    return _save_to_garmin(name, [e.model_dump() for e in req.exercises], db=db)


@router.get("/memory", response_model=list[schemas.MemoryFact])
def get_memory():
    """The durable facts the coach is carrying between sessions."""
    return coach_memory.list_facts()


@router.delete("/memory/{index}")
def delete_memory(index: int):
    if not coach_memory.delete_fact(index):
        raise HTTPException(status_code=404, detail="No fact at that index")
    return {"ok": True}


@router.post("/memory/compact")
def compact_memory():
    return {"result": coach_memory.compact()}


@router.get("/saved-workout/today", response_model=schemas.SavedWorkoutRecord)
def saved_workout_today(db: Session = Depends(get_db)):
    """What (if anything) has already been pushed to Garmin for today — lets the
    UI say "already saved" instead of inviting a duplicate."""
    row = db.get(models.GarminSavedWorkout, date.today())
    if row is None:
        raise HTTPException(status_code=404, detail="Nothing saved to Garmin for today yet")
    return row
