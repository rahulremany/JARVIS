"""Tests for the reflex-tier vision modules (new in the Python rewrite --
these are genuinely runnable since MotionDetector has no external
dependency, unlike the model-backed engines)."""
import numpy as np
import pytest

from jarvis.vision.motion_detector import FrameBuffer, MotionDetector
from jarvis.vision.object_detector import ObjectDetector, StubObjectDetector
from jarvis.vision.reflex_loop import ReflexLoop


def _frame(fill: int, width: int = 8, height: int = 8) -> FrameBuffer:
    return FrameBuffer(data=np.full((height, width), fill, dtype=np.uint8), width=width, height=height)


def test_motion_detector_first_frame_never_triggers():
    detector = MotionDetector()
    result = detector.process(_frame(0))
    assert result.changed is False


def test_motion_detector_detects_significant_change():
    detector = MotionDetector(pixel_diff_threshold=10, trigger_ratio=0.1)
    detector.process(_frame(0))
    result = detector.process(_frame(255))
    assert result.changed is True
    assert result.changed_pixel_ratio == pytest.approx(1.0)
    assert result.bounding_box is not None


def test_motion_detector_ignores_tiny_change():
    detector = MotionDetector(pixel_diff_threshold=10, trigger_ratio=0.5)
    detector.process(_frame(100))
    result = detector.process(_frame(105))  # below threshold
    assert result.changed is False


@pytest.mark.asyncio
async def test_stub_object_detector_returns_nothing():
    detector = ObjectDetector(StubObjectDetector())
    detections = await detector.detect(np.zeros((8, 8), dtype=np.uint8))
    assert detections == []


@pytest.mark.asyncio
async def test_reflex_loop_does_not_escalate_without_motion():
    loop = ReflexLoop()
    event = await loop.process_frame(_frame(0))
    assert event.escalate is False
    assert event.detections == []
