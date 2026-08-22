"""Ported from src/vision/ReflexLoop.ts.

Ties the two reflex-tier pieces together and defines the one escalation
path out of it: motion gates detection, detection gates whether the mesh
(tier 3) ever gets called at all. Nothing in this file makes a model call
unless _something_worth_reasoning_about() says so -- that's what keeps the
reflex tier free of network/LLM latency.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from ..utils.logging import logger
from .motion_detector import FrameBuffer, MotionDetector
from .object_detector import Detection, ObjectDetector


@dataclass
class ReflexEvent:
    motion_ratio: float
    detections: list[Detection]
    escalate: bool


class ReflexLoop:
    def __init__(self, on_escalate: Optional[Callable[[ReflexEvent], None]] = None) -> None:
        self.motion = MotionDetector()
        self.objects = ObjectDetector()
        self.on_escalate = on_escalate

    async def process_frame(self, frame: FrameBuffer) -> ReflexEvent:
        motion_result = self.motion.process(frame)

        if not motion_result.changed:
            return ReflexEvent(motion_ratio=motion_result.changed_pixel_ratio, detections=[], escalate=False)

        detections = await self.objects.detect(frame.data)
        escalate = self._something_worth_reasoning_about(detections)

        event = ReflexEvent(motion_ratio=motion_result.changed_pixel_ratio, detections=detections, escalate=escalate)

        if escalate:
            logger.debug("Reflex loop escalating to mesh:", {
                "motionRatio": event.motion_ratio,
                "labels": [d.label for d in detections],
            })
            if self.on_escalate:
                self.on_escalate(event)

        return event

    def _something_worth_reasoning_about(self, detections: list[Detection]) -> bool:
        """Placeholder policy: escalate whenever the object detector finds
        anything above a confidence bar. Real workshop rules (e.g. "only
        escalate for hands near tool_bit") replace this once ObjectDetector
        has a real backend behind it."""
        return any(d.confidence > 0.5 for d in detections)
