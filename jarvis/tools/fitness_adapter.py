"""Adapter for the Volt fitness tracker (jarvis/services/fitness), a
separately-launched FastAPI service that owns Garmin recovery/workout sync
and Cronometer nutrition data in its own SQLite DB.

Volt is not started by JARVIS -- run `./fitness.sh` from the repo root first
(or set FITNESS_AUTOSTART, see start_jarvis.sh) so this adapter has something
to talk to. Base URL defaults to http://localhost:8000, matching fitness.sh.
"""
from __future__ import annotations

import os
from typing import Any, Optional

import httpx

from ..utils.logging import logger

DEFAULT_BASE_URL = "http://localhost:8000"


class FitnessAdapter:
    def __init__(self, base_url: Optional[str] = None) -> None:
        self.base_url = (base_url or os.environ.get("FITNESS_API_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")

    async def _get(self, path: str, params: Optional[dict[str, Any]] = None) -> Any:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(f"{self.base_url}{path}", params=params)
        except httpx.ConnectError as exc:
            raise RuntimeError(
                "Volt fitness service is not reachable -- run ./fitness.sh from the "
                "JARVIS repo root to start it."
            ) from exc
        if response.status_code != 200:
            raise RuntimeError(f"Volt API error: {response.status_code} {response.text}")
        return response.json()

    async def _post(self, path: str, json_body: dict[str, Any]) -> Any:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(f"{self.base_url}{path}", json=json_body)
        except httpx.ConnectError as exc:
            raise RuntimeError(
                "Volt fitness service is not reachable -- run ./fitness.sh from the "
                "JARVIS repo root to start it."
            ) from exc
        if response.status_code not in (200, 201):
            raise RuntimeError(f"Volt API error: {response.status_code} {response.text}")
        return response.json()

    # ---------------- Recovery ----------------

    async def latest_recovery(self) -> dict[str, Any]:
        """Most recent Garmin recovery snapshot: HRV, sleep score, resting HR, stress."""
        return await self._get("/garmin-recovery/latest")

    async def recovery_history(self, limit: int = 14) -> dict[str, Any]:
        entries = await self._get("/garmin-recovery", params={"limit": max(1, min(limit, 90))})
        return {"count": len(entries), "entries": entries}

    # ---------------- Workouts ----------------

    async def list_workouts(self, limit: int = 14) -> dict[str, Any]:
        """Recent logged strength-training sessions (exercise, sets, reps, weight)."""
        entries = await self._get("/workouts", params={"limit": max(1, min(limit, 90))})
        return {"count": len(entries), "workouts": entries}

    async def todays_workout(self) -> dict[str, Any]:
        """AI coach's workout recommendation for today, reasoned from recent training + recovery."""
        return await self._get("/coach/todays-workout")

    async def save_workout_to_garmin(self, name: str, exercises: list[dict[str, Any]]) -> dict[str, Any]:
        """Push a workout to the Garmin Connect workout library (selectable on the watch)."""
        return await self._post("/coach/save-workout", {"name": name, "exercises": exercises})

    # ---------------- Coach chat ----------------

    async def coach_chat(self, message: str) -> dict[str, Any]:
        """Ask Volt's built-in coach (has direct DB access to training history, recovery,
        and persistent memory of injuries/goals/equipment) a training question."""
        return await self._post("/coach/chat", {"messages": [{"role": "user", "content": message}]})

    # ---------------- Nutrition ----------------

    async def nutrition_logs(self, limit: int = 14) -> dict[str, Any]:
        entries = await self._get("/nutrition-logs", params={"limit": max(1, min(limit, 90))})
        return {"count": len(entries), "logs": entries}
