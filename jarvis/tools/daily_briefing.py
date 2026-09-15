"""Daily assignment ingest, Phase 2.

Composes the adapters that already exist (Canvas, Google Calendar,
Reminders, LifeOSService's workload estimator) into one "what do I need to
do today" pass: pulls upcoming assignments + current grades, estimates
workload, pushes new due dates onto the calendar and classes onto
Reminders (deduped against previously-synced assignments so re-running
this doesn't spam duplicates), and returns both the structured payload and
a short spoken-friendly summary text.

Meant to be called once a day (see scripts/daily_briefing.sh) but is just
as safe to call on demand -- it's idempotent aside from the actual
create-event/create-reminder calls, which are skipped for anything already
synced.
"""
from __future__ import annotations

from typing import Any

from .canvas_adapter import CanvasAdapter
from .google_adapter import GoogleAdapter
from .life_os import LifeOSService
from .reminders_adapter import RemindersAdapter
from ..utils.logging import logger


def _assignment_key(assignment: dict[str, Any]) -> str:
    return f"{assignment.get('course', '')}::{assignment.get('title', '')}::{assignment.get('due_date', '')}"


def _focus_score(assignment: dict[str, Any], grade_by_course: dict[str, float]) -> float:
    """Higher score = more urgent to focus on: soon-due + high-point-value +
    a course you're currently doing worse in should all push a task up."""
    points = float(assignment.get("points", 0) or 0)
    course_score = grade_by_course.get(assignment.get("course", ""))
    grade_penalty = (100 - course_score) / 20 if course_score is not None else 1.0
    return round((points / 20.0) + grade_penalty, 2)


class DailyBriefingService:
    def __init__(
        self,
        canvas: CanvasAdapter,
        google: GoogleAdapter,
        reminders: RemindersAdapter,
        life_os: LifeOSService,
    ) -> None:
        self.canvas = canvas
        self.google = google
        self.reminders = reminders
        self.life_os = life_os

    async def run(
        self,
        days_ahead: int = 7,
        sync_calendar: bool = True,
        sync_reminders: bool = True,
        max_hours_per_day: float = 8.0,
    ) -> dict[str, Any]:
        assignments_result = await self.canvas.list_upcoming_assignments(days_ahead=days_ahead)
        assignments = assignments_result.get("assignments", [])

        try:
            grades_result = await self.canvas.list_grades()
            grade_by_course = {
                g["course"]: g["current_score"]
                for g in grades_result.get("grades", [])
                if g.get("current_score") is not None
            }
        except Exception as error:  # noqa: BLE001
            logger.warn("Daily briefing: grade fetch failed, continuing without it:", error)
            grade_by_course = {}

        workload = self.life_os.estimate_canvas_workload(assignments)

        for assignment in assignments:
            assignment["focus_score"] = _focus_score(assignment, grade_by_course)
        assignments.sort(key=lambda a: a["focus_score"], reverse=True)

        already_synced = self.life_os.get_synced_canvas_ids()
        newly_synced: list[str] = []
        calendar_created: list[dict[str, Any]] = []
        reminders_created: list[dict[str, Any]] = []

        for assignment in assignments:
            key = _assignment_key(assignment)
            if key in already_synced:
                continue

            due_date = assignment.get("due_date", "")
            if sync_calendar and due_date:
                try:
                    event = await self.google.create_event(
                        summary=f"Due: {assignment['title']} ({assignment['course']})",
                        start_iso=due_date,
                        end_iso=due_date,
                        description=assignment.get("html_url", ""),
                    )
                    calendar_created.append(event)
                except Exception as error:  # noqa: BLE001
                    logger.error(f"Daily briefing: failed to create calendar event for {key}:", error)

            if sync_reminders:
                try:
                    reminder = await self.reminders.add_reminder(
                        title=f"{assignment['course']}: {assignment['title']}",
                        due_date_iso=due_date,
                        notes=assignment.get("html_url", ""),
                        list_name="Classes",
                    )
                    reminders_created.append(reminder)
                except Exception as error:  # noqa: BLE001
                    logger.error(f"Daily briefing: failed to create reminder for {key}:", error)

            newly_synced.append(key)

        if newly_synced:
            self.life_os.mark_canvas_synced(newly_synced)

        daily_plan = self.life_os.daily_plan(max_hours=max_hours_per_day)

        summary_text = self._build_summary(assignments, workload, grade_by_course)

        return {
            "assignments": assignments,
            "grades": grade_by_course,
            "workload": workload,
            "daily_plan": daily_plan,
            "calendar_events_created": calendar_created,
            "reminders_created": reminders_created,
            "newly_synced_count": len(newly_synced),
            "summary_text": summary_text,
        }

    def _build_summary(
        self,
        assignments: list[dict[str, Any]],
        workload: dict[str, Any],
        grade_by_course: dict[str, float],
    ) -> str:
        if not assignments:
            return "No Canvas assignments due in the coming days. You're clear."

        lines = [f"You have {len(assignments)} assignment(s) coming up, ~{workload['total_estimated_hours']} hours of estimated work."]

        top = assignments[:3]
        for assignment in top:
            lines.append(f"- {assignment['title']} ({assignment['course']}), due {assignment['due_date']}")

        struggling = [course for course, score in grade_by_course.items() if score < 80]
        if struggling:
            lines.append(f"Grades are lowest in: {', '.join(struggling)} -- worth prioritizing that work.")

        return "\n".join(lines)
