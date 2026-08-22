"""Ported from src/session/SessionManager.ts."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

from ..utils.logging import logger

Role = Literal["system", "user", "assistant"]

SYSTEM_PROMPT = (
    "You are JARVIS, a personal AI assistant. You are helpful, concise, and professional.\n"
    "Never reference Tony Stark, Iron Man, Marvel characters, or fictional scenarios. "
    "You assist real users with real tasks.\n"
    "Keep responses brief and focused. Remember user preferences and names when told."
)


@dataclass
class Message:
    role: Role
    content: str
    timestamp: float


@dataclass
class SessionContext:
    id: str
    messages: list[Message] = field(default_factory=list)
    created_at: float = field(default_factory=lambda: time.time() * 1000)
    last_accessed_at: float = field(default_factory=lambda: time.time() * 1000)


class SessionManager:
    MAX_SESSIONS = 100
    SESSION_TIMEOUT_MS = 30 * 60 * 1000

    def __init__(self) -> None:
        self._sessions: dict[str, SessionContext] = {}

    def get_or_create(self, session_id: str) -> SessionContext:
        session = self._sessions.get(session_id)
        if session is None:
            session = SessionContext(id=session_id, messages=[Message("system", SYSTEM_PROMPT, time.time() * 1000)])
            self._sessions[session_id] = session
            logger.debug(f"Created new session: {session_id}")
            self._cleanup()
        else:
            session.last_accessed_at = time.time() * 1000
        return session

    def append_user(self, session_id: str, content: str) -> SessionContext:
        session = self.get_or_create(session_id)
        session.messages.append(Message("user", content, time.time() * 1000))
        return session

    def append_assistant(self, session_id: str, content: str) -> SessionContext:
        session = self.get_or_create(session_id)
        session.messages.append(Message("assistant", content, time.time() * 1000))
        return session

    def get_messages(self, session_id: str) -> list[Message]:
        return self.get_or_create(session_id).messages

    def reset(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
        logger.debug(f"Reset session: {session_id}")

    def _cleanup(self) -> None:
        if len(self._sessions) <= self.MAX_SESSIONS:
            return

        now = time.time() * 1000
        to_delete = [sid for sid, s in self._sessions.items() if now - s.last_accessed_at > self.SESSION_TIMEOUT_MS]

        remaining = len(self._sessions) - len(to_delete)
        if remaining > self.MAX_SESSIONS:
            oldest = sorted(self._sessions.items(), key=lambda kv: kv[1].last_accessed_at)
            excess = remaining - self.MAX_SESSIONS
            to_delete.extend(sid for sid, _ in oldest[:excess])

        for sid in to_delete:
            self._sessions.pop(sid, None)
            logger.debug(f"Cleaned up session: {sid}")

    def get_sessions(self) -> list[str]:
        return list(self._sessions.keys())

    def get_session_count(self) -> int:
        return len(self._sessions)


# Global context/chat storage for llama.cpp sessions (KV-cache reuse),
# mirroring the module-level `llamaSessions` map in SessionManager.ts.
_llama_sessions: dict[str, Any] = {}


def get_llama_session(session_id: str, create: Any) -> Any:
    if session_id in _llama_sessions:
        return _llama_sessions[session_id]

    logger.debug(f"Creating new llama session: {session_id}")
    session = create()
    _llama_sessions[session_id] = session

    if len(_llama_sessions) > 50:
        oldest_key = next(iter(_llama_sessions))
        del _llama_sessions[oldest_key]
        logger.debug(f"Cleaned up old llama session: {oldest_key}")

    return session
