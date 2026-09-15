"""Tests for the daily-briefing composition service (jarvis/tools/daily_briefing.py)
against fake Canvas/Google/Reminders adapters -- this is glue logic (dedup
bookkeeping, focus scoring, summary text), not HTTP/AppleScript handling,
so it doesn't need the mock-transport machinery test_phase2_adapters.py uses."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from jarvis.tools.daily_briefing import DailyBriefingService
from jarvis.tools.life_os import LifeOSService


class _FakeCanvas:
    def __init__(self, assignments: list[dict[str, Any]], grades: list[dict[str, Any]]) -> None:
        self._assignments = assignments
        self._grades = grades

    async def list_upcoming_assignments(self, days_ahead: int = 7) -> dict[str, Any]:
        return {"count": len(self._assignments), "assignments": [dict(a) for a in self._assignments]}

    async def list_grades(self) -> dict[str, Any]:
        return {"count": len(self._grades), "grades": self._grades}


class _FakeGoogle:
    def __init__(self) -> None:
        self.created_events: list[dict[str, Any]] = []

    async def create_event(self, summary: str, start_iso: str, end_iso: str, **kwargs: Any) -> dict[str, Any]:
        event = {"id": f"evt-{len(self.created_events)}", "summary": summary}
        self.created_events.append(event)
        return event


class _FakeReminders:
    def __init__(self) -> None:
        self.created_reminders: list[dict[str, Any]] = []

    async def add_reminder(self, title: str, due_date_iso: str = "", notes: str = "", list_name: str = "") -> dict[str, Any]:
        reminder = {"id": f"rem-{len(self.created_reminders)}", "title": title}
        self.created_reminders.append(reminder)
        return reminder


def _assignments() -> list[dict[str, Any]]:
    return [
        {"course": "Robotics", "title": "Lab 3", "due_date": "2026-09-10T23:59:00Z", "points": 100, "complexity": "hard", "html_url": ""},
        {"course": "History", "title": "Reading response", "due_date": "2026-09-11T23:59:00Z", "points": 10, "complexity": "easy", "html_url": ""},
    ]


def _grades() -> list[dict[str, Any]]:
    return [
        {"course_id": 1, "course": "Robotics", "current_score": 72.0, "current_grade": "C-"},
        {"course_id": 2, "course": "History", "current_score": 95.0, "current_grade": "A"},
    ]


@pytest.mark.asyncio
async def test_daily_briefing_syncs_and_prioritizes_by_focus(tmp_path: Path):
    canvas = _FakeCanvas(_assignments(), _grades())
    google = _FakeGoogle()
    reminders = _FakeReminders()
    life_os = LifeOSService(state_dir=tmp_path / ".state")

    service = DailyBriefingService(canvas=canvas, google=google, reminders=reminders, life_os=life_os)
    result = await service.run(days_ahead=7)

    assert result["newly_synced_count"] == 2
    assert len(google.created_events) == 2
    assert len(reminders.created_reminders) == 2
    # Robotics: low grade (72) + high points (100) should outrank History's easy/low-priority item.
    assert result["assignments"][0]["course"] == "Robotics"
    assert "Robotics" in result["summary_text"] or "History" in result["summary_text"]


@pytest.mark.asyncio
async def test_daily_briefing_skips_already_synced_assignments(tmp_path: Path):
    canvas = _FakeCanvas(_assignments(), _grades())
    google = _FakeGoogle()
    reminders = _FakeReminders()
    life_os = LifeOSService(state_dir=tmp_path / ".state")

    service = DailyBriefingService(canvas=canvas, google=google, reminders=reminders, life_os=life_os)
    await service.run(days_ahead=7)

    # Second run against the same assignments shouldn't re-create events/reminders.
    result = await service.run(days_ahead=7)

    assert result["newly_synced_count"] == 0
    assert len(google.created_events) == 2
    assert len(reminders.created_reminders) == 2
