"""Ported from src/vision/ObjectDetector.ts.

Second half of the reflex tier: once MotionDetector says a region changed,
this answers "what is it" -- a dedicated detector, not an LLM call, so it
stays fast enough to run per-frame. Pluggable by design: swap the backend
for a real ONNX Runtime + YOLO session without touching call sites in
Router/EngineSelector. Ships with a stub backend so the interface and the
reflex -> escalate flow are runnable end-to-end before model weights and a
camera are wired up.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass
class Detection:
    label: str
    confidence: float
    box: tuple[int, int, int, int]  # x, y, width, height


class ObjectDetectorBackend(Protocol):
    async def detect(self, frame: np.ndarray) -> list[Detection]: ...


class StubObjectDetector:
    """Returns no detections, but exercises the real call shape so the rest
    of the reflex pipeline (motion -> detect -> escalate-to-mesh) is
    demonstrable without bundling model weights into the repo. Replace with
    a YOLOv8/v11 ONNX session for real per-frame object recognition."""

    async def detect(self, frame: np.ndarray) -> list[Detection]:
        return []


class ObjectDetector:
    def __init__(self, backend: ObjectDetectorBackend | None = None) -> None:
        self.backend: ObjectDetectorBackend = backend or StubObjectDetector()

    async def detect(self, frame: np.ndarray) -> list[Detection]:
        return await self.backend.detect(frame)

    def set_backend(self, backend: ObjectDetectorBackend) -> None:
        """Swap in a real backend (e.g. an ONNX Runtime YOLO session) at runtime."""
        self.backend = backend
