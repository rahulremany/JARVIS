"""Structured logging + latency tracking, ported 1:1 from src/utils/logging.ts."""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

LogLevel = Literal["debug", "info", "warn", "error"]
_LEVELS: list[LogLevel] = ["debug", "info", "warn", "error"]


@dataclass
class LatencyLog:
    engine: str
    model_id: str
    params: dict[str, Any]
    prompt_chars: int
    session_id: str
    first_token_ms: float
    total_ms: float
    tokens_out: int
    route: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class Logger:
    def __init__(self) -> None:
        self.level: LogLevel = "debug"
        self.sample_rate: float = 1.0
        self._latency_logs: list[LatencyLog] = []

    def set_level(self, level: LogLevel) -> None:
        self.level = level

    def set_sample_rate(self, rate: float) -> None:
        self.sample_rate = rate

    def _should_log(self, level: LogLevel) -> bool:
        return _LEVELS.index(level) >= _LEVELS.index(self.level)

    def _fmt(self, level: LogLevel, message: str, *args: Any) -> str:
        prefix = f"[JARVIS] {level.upper()}"
        if args:
            formatted = " ".join(
                json.dumps(a, indent=2, default=str) if isinstance(a, (dict, list)) else str(a)
                for a in args
            )
            return f"{prefix} {message} {formatted}"
        return f"{prefix} {message}"

    def debug(self, message: str, *args: Any) -> None:
        if self._should_log("debug"):
            print(self._fmt("debug", message, *args))

    def info(self, message: str, *args: Any) -> None:
        if self._should_log("info"):
            print(self._fmt("info", message, *args))

    def warn(self, message: str, *args: Any) -> None:
        if self._should_log("warn"):
            print(self._fmt("warn", message, *args))

    def error(self, message: str, *args: Any) -> None:
        if self._should_log("error"):
            print(self._fmt("error", message, *args))

    def log_latency(self, log: dict[str, Any]) -> None:
        if random.random() > self.sample_rate:
            return
        entry = LatencyLog(**log)
        self._latency_logs.append(entry)
        if len(self._latency_logs) > 100:
            self._latency_logs = self._latency_logs[-100:]
        print("[JARVIS] \U0001f4ca LATENCY:", json.dumps(entry.__dict__))

    def get_latency_logs(self) -> list[dict[str, Any]]:
        return [log.__dict__ for log in self._latency_logs]

    def get_latency_stats(self) -> dict[str, Any]:
        if not self._latency_logs:
            return {"count": 0, "avg_first_token_ms": 0, "avg_total_ms": 0, "avg_tokens_out": 0}
        n = len(self._latency_logs)
        return {
            "count": n,
            "avg_first_token_ms": round(sum(l.first_token_ms for l in self._latency_logs) / n),
            "avg_total_ms": round(sum(l.total_ms for l in self._latency_logs) / n),
            "avg_tokens_out": round(sum(l.tokens_out for l in self._latency_logs) / n),
        }


logger = Logger()
