"""Phase 2 adapter tests -- these mock the HTTP layer (httpx.MockTransport)
to exercise the real request/response handling paths, since the adapters
now assume valid credentials are always present (no more "not configured"
branches -- real keys get dropped into .env directly)."""
from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from jarvis.tools.canvas_adapter import CanvasAdapter
from jarvis.tools.google_adapter import GoogleAdapter, GoogleCredentials


_RealAsyncClient = httpx.AsyncClient


def _client_factory(handler):
    def _make_client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(handler)
        return _RealAsyncClient(*args, **kwargs)

    return _make_client


# ---------------- Google (Calendar + Gmail) ----------------

@pytest.mark.asyncio
async def test_google_adapter_list_events(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "tok123", "expires_in": 3600})
        if "/calendars/primary/events" in request.url.path:
            return httpx.Response(200, json={"items": [
                {"id": "evt1", "summary": "Standup", "start": {"dateTime": "2026-09-01T09:00:00Z"},
                 "end": {"dateTime": "2026-09-01T09:15:00Z"}, "htmlLink": "https://cal/evt1"},
            ]})
        return httpx.Response(404)

    monkeypatch.setattr(httpx, "AsyncClient", _client_factory(handler))

    adapter = GoogleAdapter(GoogleCredentials("id", "secret", "refresh"))
    result = await adapter.list_events()

    assert result["count"] == 1
    assert result["events"][0]["summary"] == "Standup"


@pytest.mark.asyncio
async def test_google_adapter_create_event(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "tok123", "expires_in": 3600})
        if request.method == "POST" and "/events" in request.url.path:
            body = json.loads(request.content)
            return httpx.Response(200, json={"id": "evt-new", "htmlLink": "https://cal/evt-new", "summary": body["summary"]})
        return httpx.Response(404)

    monkeypatch.setattr(httpx, "AsyncClient", _client_factory(handler))

    adapter = GoogleAdapter(GoogleCredentials("id", "secret", "refresh"))
    result = await adapter.create_event("Design review", "2026-09-01T10:00:00Z", "2026-09-01T11:00:00Z")

    assert result["id"] == "evt-new"
    assert result["summary"] == "Design review"


@pytest.mark.asyncio
async def test_google_adapter_scan_inbox(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "tok123", "expires_in": 3600})
        if request.url.path.endswith("/users/me/messages") and request.method == "GET":
            return httpx.Response(200, json={"messages": [{"id": "m1"}]})
        if request.url.path.endswith("/users/me/messages/m1"):
            return httpx.Response(200, json={
                "snippet": "Assignment due soon",
                "payload": {"headers": [
                    {"name": "Subject", "value": "Assignment reminder"},
                    {"name": "From", "value": "prof@school.edu"},
                    {"name": "Date", "value": "Mon, 1 Sep 2026 08:00:00 -0400"},
                ]},
            })
        return httpx.Response(404)

    monkeypatch.setattr(httpx, "AsyncClient", _client_factory(handler))

    adapter = GoogleAdapter(GoogleCredentials("id", "secret", "refresh"))
    result = await adapter.scan_inbox()

    assert result["count"] == 1
    assert result["messages"][0]["subject"] == "Assignment reminder"


@pytest.mark.asyncio
async def test_google_adapter_update_event(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "tok123", "expires_in": 3600})
        if request.method == "PATCH" and request.url.path.endswith("/events/evt1"):
            body = json.loads(request.content)
            assert body == {"summary": "Renamed"}
            return httpx.Response(200, json={"id": "evt1", "htmlLink": "https://cal/evt1", "summary": "Renamed"})
        return httpx.Response(404)

    monkeypatch.setattr(httpx, "AsyncClient", _client_factory(handler))

    adapter = GoogleAdapter(GoogleCredentials("id", "secret", "refresh"))
    result = await adapter.update_event("evt1", summary="Renamed")

    assert result["summary"] == "Renamed"


@pytest.mark.asyncio
async def test_google_adapter_delete_event(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "tok123", "expires_in": 3600})
        if request.method == "DELETE" and request.url.path.endswith("/events/evt1"):
            return httpx.Response(204)
        return httpx.Response(404)

    monkeypatch.setattr(httpx, "AsyncClient", _client_factory(handler))

    adapter = GoogleAdapter(GoogleCredentials("id", "secret", "refresh"))
    result = await adapter.delete_event("evt1")

    assert result == {"id": "evt1", "deleted": True}


@pytest.mark.asyncio
async def test_google_adapter_create_event_with_recurrence(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "tok123", "expires_in": 3600})
        if request.method == "POST" and "/events" in request.url.path:
            body = json.loads(request.content)
            assert body["recurrence"] == ["RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR"]
            return httpx.Response(200, json={"id": "evt-rec", "htmlLink": "https://cal/evt-rec", "summary": body["summary"]})
        return httpx.Response(404)

    monkeypatch.setattr(httpx, "AsyncClient", _client_factory(handler))

    adapter = GoogleAdapter(GoogleCredentials("id", "secret", "refresh"))
    result = await adapter.create_event(
        "Lecture", "2026-09-01T10:00:00Z", "2026-09-01T11:00:00Z",
        recurrence=["RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR"],
    )

    assert result["id"] == "evt-rec"


# ---------------- Canvas ----------------

@pytest.mark.asyncio
async def test_canvas_list_courses(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/courses":
            return httpx.Response(200, json=[{"id": 1, "name": "Intro to Robotics", "course_code": "ROBO101"}])
        return httpx.Response(404)

    monkeypatch.setattr(httpx, "AsyncClient", _client_factory(handler))

    adapter = CanvasAdapter(base_url="https://canvas.example.edu", access_token="tok")
    result = await adapter.list_courses()

    assert result["count"] == 1
    assert result["courses"][0]["name"] == "Intro to Robotics"


@pytest.mark.asyncio
async def test_canvas_list_upcoming_assignments(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/courses":
            return httpx.Response(200, json=[{"id": 1, "name": "Intro to Robotics"}])
        if request.url.path == "/api/v1/courses/1/assignments":
            return httpx.Response(200, json=[{
                "name": "Final Project", "due_at": "2026-09-05T23:59:00Z",
                "points_possible": 100, "html_url": "https://canvas/assign/1",
            }])
        return httpx.Response(404)

    monkeypatch.setattr(httpx, "AsyncClient", _client_factory(handler))

    adapter = CanvasAdapter(base_url="https://canvas.example.edu", access_token="tok")
    result = await adapter.list_upcoming_assignments(days_ahead=30)

    assert result["count"] == 1
    assert result["assignments"][0]["complexity"] == "hard"


@pytest.mark.asyncio
async def test_canvas_list_grades(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/courses":
            return httpx.Response(200, json=[{
                "id": 1, "name": "Intro to Robotics",
                "enrollments": [{"type": "student", "computed_current_score": 87.5, "computed_current_grade": "B+"}],
            }])
        return httpx.Response(404)

    monkeypatch.setattr(httpx, "AsyncClient", _client_factory(handler))

    adapter = CanvasAdapter(base_url="https://canvas.example.edu", access_token="tok")
    result = await adapter.list_grades()

    assert result["count"] == 1
    assert result["grades"][0]["current_score"] == 87.5
