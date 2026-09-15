"""Google Calendar + Gmail adapter, Phase 2.

Uses OAuth2 refresh-token flow against Google's REST APIs directly over
httpx -- no google-api-python-client dependency needed.

Setup:
1. Create an OAuth 2.0 Client ID (Desktop app) in Google Cloud Console with
   the Calendar and Gmail readonly/modify scopes enabled.
2. Run any standard OAuth "installed app" flow once to get a refresh token
   (e.g. google-auth-oauthlib's InstalledAppFlow, run manually/out-of-band).
3. Put GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN in .env.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from ..utils.logging import logger

TOKEN_URL = "https://oauth2.googleapis.com/token"
CALENDAR_API = "https://www.googleapis.com/calendar/v3"
GMAIL_API = "https://gmail.googleapis.com/gmail/v1"


@dataclass
class GoogleCredentials:
    client_id: str
    client_secret: str
    refresh_token: str

    @staticmethod
    def from_env() -> "GoogleCredentials":
        return GoogleCredentials(
            client_id=os.environ.get("GOOGLE_CLIENT_ID", ""),
            client_secret=os.environ.get("GOOGLE_CLIENT_SECRET", ""),
            refresh_token=os.environ.get("GOOGLE_REFRESH_TOKEN", ""),
        )


class GoogleAdapter:
    """Shared OAuth token handling for Calendar + Gmail."""

    def __init__(self, credentials: Optional[GoogleCredentials] = None) -> None:
        self.credentials = credentials or GoogleCredentials.from_env()
        self._access_token: Optional[str] = None
        self._access_token_expiry: float = 0.0

    async def _get_access_token(self) -> str:
        if self._access_token and time.time() < self._access_token_expiry - 30:
            return self._access_token

        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(TOKEN_URL, data={
                "client_id": self.credentials.client_id,
                "client_secret": self.credentials.client_secret,
                "refresh_token": self.credentials.refresh_token,
                "grant_type": "refresh_token",
            })

        if response.status_code != 200:
            raise RuntimeError(f"Google token refresh failed: {response.status_code} {response.text}")

        payload = response.json()
        self._access_token = payload["access_token"]
        self._access_token_expiry = time.time() + payload.get("expires_in", 3600)
        return self._access_token

    async def _authed_get(self, url: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        token = await self._get_access_token()
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(url, headers={"Authorization": f"Bearer {token}"}, params=params)
        if response.status_code != 200:
            raise RuntimeError(f"Google API error: {response.status_code} {response.text}")
        return response.json()

    async def _authed_post(self, url: str, json_body: dict[str, Any]) -> dict[str, Any]:
        token = await self._get_access_token()
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(url, headers={"Authorization": f"Bearer {token}"}, json=json_body)
        if response.status_code not in (200, 201):
            raise RuntimeError(f"Google API error: {response.status_code} {response.text}")
        return response.json()

    async def _authed_patch(self, url: str, json_body: dict[str, Any]) -> dict[str, Any]:
        token = await self._get_access_token()
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.patch(url, headers={"Authorization": f"Bearer {token}"}, json=json_body)
        if response.status_code not in (200, 201):
            raise RuntimeError(f"Google API error: {response.status_code} {response.text}")
        return response.json()

    async def _authed_delete(self, url: str) -> None:
        token = await self._get_access_token()
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.delete(url, headers={"Authorization": f"Bearer {token}"})
        # Google returns 204 on success and 410 if it's already gone -- both mean
        # "the event isn't there anymore", which is what the caller wants.
        if response.status_code not in (200, 204, 410):
            raise RuntimeError(f"Google API error: {response.status_code} {response.text}")

    # ---------------- Calendar ----------------

    async def list_events(self, calendar_id: str = "primary", max_results: int = 20, time_min: str = "") -> dict[str, Any]:
        params: dict[str, Any] = {
            "maxResults": max(1, min(max_results, 100)),
            "singleEvents": "true",
            "orderBy": "startTime",
        }
        params["timeMin"] = time_min or _utc_now_rfc3339()

        data = await self._authed_get(f"{CALENDAR_API}/calendars/{calendar_id}/events", params=params)

        events = []
        for item in data.get("items", []):
            start = item.get("start", {}).get("dateTime") or item.get("start", {}).get("date")
            end = item.get("end", {}).get("dateTime") or item.get("end", {}).get("date")
            events.append({
                "id": item.get("id"),
                "summary": item.get("summary", "(no title)"),
                "start": start,
                "end": end,
                "location": item.get("location", ""),
                "html_link": item.get("htmlLink", ""),
            })

        return {"count": len(events), "events": events}

    async def create_event(
        self,
        summary: str,
        start_iso: str,
        end_iso: str,
        calendar_id: str = "primary",
        description: str = "",
        location: str = "",
        recurrence: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        body = {
            "summary": summary,
            "description": description,
            "location": location,
            "start": {"dateTime": start_iso},
            "end": {"dateTime": end_iso},
        }
        if recurrence:
            # RRULE strings per RFC5545, e.g. "RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR"
            body["recurrence"] = recurrence

        data = await self._authed_post(f"{CALENDAR_API}/calendars/{calendar_id}/events", body)

        return {
            "id": data.get("id"),
            "html_link": data.get("htmlLink", ""),
            "summary": data.get("summary", summary),
        }

    async def update_event(
        self,
        event_id: str,
        calendar_id: str = "primary",
        summary: Optional[str] = None,
        start_iso: Optional[str] = None,
        end_iso: Optional[str] = None,
        description: Optional[str] = None,
        location: Optional[str] = None,
        recurrence: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Patches only the fields provided, leaving the rest of the event untouched."""
        body: dict[str, Any] = {}
        if summary is not None:
            body["summary"] = summary
        if start_iso is not None:
            body["start"] = {"dateTime": start_iso}
        if end_iso is not None:
            body["end"] = {"dateTime": end_iso}
        if description is not None:
            body["description"] = description
        if location is not None:
            body["location"] = location
        if recurrence is not None:
            body["recurrence"] = recurrence

        data = await self._authed_patch(f"{CALENDAR_API}/calendars/{calendar_id}/events/{event_id}", body)

        return {
            "id": data.get("id"),
            "html_link": data.get("htmlLink", ""),
            "summary": data.get("summary", ""),
        }

    async def delete_event(self, event_id: str, calendar_id: str = "primary") -> dict[str, Any]:
        await self._authed_delete(f"{CALENDAR_API}/calendars/{calendar_id}/events/{event_id}")
        return {"id": event_id, "deleted": True}

    # ---------------- Gmail ----------------

    async def scan_inbox(self, query: str = "is:unread", max_results: int = 10) -> dict[str, Any]:
        """Lists matching messages with subject/snippet/from -- read-only summary,
        never deletes/sends. Good for "check my email and organize" style requests."""
        listing = await self._authed_get(
            f"{GMAIL_API}/users/me/messages", params={"q": query, "maxResults": max(1, min(max_results, 50))}
        )

        message_ids = [m["id"] for m in listing.get("messages", [])]
        messages: list[dict[str, Any]] = []

        for message_id in message_ids:
            detail = await self._authed_get(
                f"{GMAIL_API}/users/me/messages/{message_id}",
                params={"format": "metadata", "metadataHeaders": ["Subject", "From", "Date"]},
            )

            headers = {h["name"]: h["value"] for h in detail.get("payload", {}).get("headers", [])}
            messages.append({
                "id": message_id,
                "subject": headers.get("Subject", "(no subject)"),
                "from": headers.get("From", ""),
                "date": headers.get("Date", ""),
                "snippet": detail.get("snippet", ""),
            })

        return {"count": len(messages), "messages": messages}


def _utc_now_rfc3339() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
