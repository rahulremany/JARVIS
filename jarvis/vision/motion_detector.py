"""Ported from src/vision/MotionDetector.ts.

Tier-1 reflex layer. Deliberately not an LLM, not even the fast-utility
model -- this is plain pixel-diffing so "is anything happening" resolves in
well under a millisecond and never touches the model mesh at all. Its only
job is to gate whether ObjectDetector (and, beyond that, the mesh) gets
invoked for a given frame.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass
class BoundingBox:
    x: int
    y: int
    width: int
    height: int


@dataclass
class MotionResult:
    changed: bool
    changed_pixel_ratio: float
    bounding_box: Optional[BoundingBox]


@dataclass
class FrameBuffer:
    data: np.ndarray  # grayscale, shape (height, width), dtype uint8
    width: int
    height: int


class MotionDetector:
    def __init__(self, pixel_diff_threshold: int = 25, trigger_ratio: float = 0.01) -> None:
        # per-pixel intensity delta to count as "changed"
        self.pixel_diff_threshold = pixel_diff_threshold
        # fraction of frame that must change to fire
        self.trigger_ratio = trigger_ratio
        self._previous_frame: Optional[FrameBuffer] = None

    def process(self, frame: FrameBuffer) -> MotionResult:
        """Feed the next grayscale frame; returns whether it differs enough
        from the last one to matter."""
        if (
            self._previous_frame is None
            or self._previous_frame.width != frame.width
            or self._previous_frame.height != frame.height
        ):
            self._previous_frame = frame
            return MotionResult(changed=False, changed_pixel_ratio=0.0, bounding_box=None)

        diff = np.abs(frame.data.astype(np.int16) - self._previous_frame.data.astype(np.int16))
        changed_mask = diff > self.pixel_diff_threshold

        self._previous_frame = frame
        changed_pixel_ratio = float(np.count_nonzero(changed_mask)) / (frame.width * frame.height)
        changed = changed_pixel_ratio > self.trigger_ratio

        bounding_box = None
        if changed:
            ys, xs = np.nonzero(changed_mask)
            bounding_box = BoundingBox(
                x=int(xs.min()), y=int(ys.min()),
                width=int(xs.max() - xs.min()), height=int(ys.max() - ys.min()),
            )

        return MotionResult(changed=changed, changed_pixel_ratio=changed_pixel_ratio, bounding_box=bounding_box)

    def reset(self) -> None:
        self._previous_frame = None
