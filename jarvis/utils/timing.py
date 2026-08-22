"""Timing helpers, ported from src/utils/timing.ts."""
from __future__ import annotations

import asyncio
import time
from typing import Awaitable, TypeVar

T = TypeVar("T")


class Stopwatch:
    def __init__(self) -> None:
        self._start = 0.0
        self._end = 0.0

    def start(self) -> None:
        self._start = time.perf_counter() * 1000

    def stop(self) -> float:
        self._end = time.perf_counter() * 1000
        return self.elapsed()

    def elapsed(self) -> float:
        if self._end == 0:
            return time.perf_counter() * 1000 - self._start
        return self._end - self._start

    def reset(self) -> None:
        self._start = 0.0
        self._end = 0.0


def calculate_percentiles(values: list[float], percentiles: list[int]) -> dict[str, float]:
    if not values:
        return {f"p{p}": 0.0 for p in percentiles}

    sorted_values = sorted(values)
    result: dict[str, float] = {}

    for p in percentiles:
        index = (p / 100) * (len(sorted_values) - 1)
        lower, upper = int(index // 1), -(-int(index) // 1)
        lower = int(index)
        upper = min(lower + 1, len(sorted_values) - 1)
        weight = index - lower

        if lower == upper:
            result[f"p{p}"] = sorted_values[lower]
        else:
            result[f"p{p}"] = sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight

    return result


async def with_timeout(coro: Awaitable[T], ms: float) -> T:
    try:
        return await asyncio.wait_for(coro, timeout=ms / 1000)
    except asyncio.TimeoutError as exc:
        raise TimeoutError(f"Timeout after {ms}ms") from exc
