"""Canvas LMS adapter, Phase 2.

Canvas's REST API takes a personal access token (generated in Canvas ->
Account -> Settings -> "New Access Token") -- no OAuth dance needed, unlike
Google. Put CANVAS_BASE_URL and CANVAS_ACCESS_TOKEN in .env.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from ..utils.logging import logger


class CanvasAdapter:
    def __init__(self, base_url: Optional[str] = None, access_token: Optional[str] = None) -> None:
        self.base_url = (base_url or os.environ.get("CANVAS_BASE_URL", "")).rstrip("/")
        self.access_token = access_token or os.environ.get("CANVAS_ACCESS_TOKEN", "")

    async def _get(self, path: str, params: Optional[dict[str, Any]] = None) -> Any:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                f"{self.base_url}{path}",
                headers={"Authorization": f"Bearer {self.access_token}"},
                params=params,
            )
        if response.status_code != 200:
            raise RuntimeError(f"Canvas API error: {response.status_code} {response.text}")
        return response.json()

    async def list_courses(self) -> dict[str, Any]:
        data = await self._get("/api/v1/courses", params={"enrollment_state": "active", "per_page": 50})

        courses = [
            {"id": c.get("id"), "name": c.get("name", "Untitled course"), "course_code": c.get("course_code", "")}
            for c in data
        ]
        return {"count": len(courses), "courses": courses}

    async def list_upcoming_assignments(self, days_ahead: int = 14, per_course_limit: int = 25) -> dict[str, Any]:
        """Pulls active-course assignments due within the window, sized for
        workload estimation (jarvis.tools.life_os.estimate_canvas_workload)."""
        courses = await self._get("/api/v1/courses", params={"enrollment_state": "active", "per_page": 50})

        now = datetime.now(timezone.utc)
        cutoff = now.timestamp() + days_ahead * 86400

        assignments: list[dict[str, Any]] = []
        for course in courses:
            course_id = course.get("id")
            if course_id is None:
                continue
            items = await self._get(
                f"/api/v1/courses/{course_id}/assignments",
                params={"per_page": per_course_limit, "order_by": "due_at"},
            )

            for item in items:
                due_at = item.get("due_at")
                if not due_at:
                    continue
                try:
                    due_dt = datetime.fromisoformat(due_at.replace("Z", "+00:00"))
                except ValueError:
                    continue
                if due_dt.timestamp() < now.timestamp() or due_dt.timestamp() > cutoff:
                    continue

                assignments.append({
                    "course": course.get("name", "Untitled course"),
                    "title": item.get("name", "Untitled assignment"),
                    "due_date": due_at,
                    "points": item.get("points_possible", 0) or 0,
                    "complexity": _infer_complexity(item.get("points_possible", 0) or 0),
                    "html_url": item.get("html_url", ""),
                })

        assignments.sort(key=lambda a: a["due_date"])
        return {"count": len(assignments), "assignments": assignments}

    async def list_grades(self) -> dict[str, Any]:
        """Current grade per active course, sized for daily-briefing "what to
        focus on" prioritization (jarvis.services.daily_briefing) -- a course
        with a low grade and an assignment due soon should outrank a course
        that's already in good shape."""
        courses = await self._get(
            "/api/v1/courses",
            params={"enrollment_state": "active", "per_page": 50, "include[]": "total_scores"},
        )

        grades: list[dict[str, Any]] = []
        for course in courses:
            enrollments = course.get("enrollments") or []
            student_enrollment = next((e for e in enrollments if e.get("type") == "student"), None)
            if student_enrollment is None:
                continue
            grades.append({
                "course_id": course.get("id"),
                "course": course.get("name", "Untitled course"),
                "current_score": student_enrollment.get("computed_current_score"),
                "current_grade": student_enrollment.get("computed_current_grade"),
            })

        return {"count": len(grades), "grades": grades}


def _infer_complexity(points: float) -> str:
    if points >= 75:
        return "hard"
    if points <= 15:
        return "easy"
    return "normal"
