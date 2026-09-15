"""Wake word detection via openWakeWord (github.com/dscripka/openWakeWord).

Swapped in for Porcupine: no access key, no per-device licensing, runs fully
local against ONNX models. Ships a pretrained "hey_jarvis" model out of the
box, which is what JARVIS uses as its wake phrase.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from ..utils.logging import logger

# openWakeWord's recommended chunk size: 80ms @ 16kHz.
FRAME_LENGTH = 1280
SAMPLE_RATE = 16000


@dataclass
class KwsConfig:
    wakeword_models: list[str]
    threshold: float = 0.5
    sample_rate: int = SAMPLE_RATE

    @staticmethod
    def from_env() -> "KwsConfig":
        models_raw = os.environ.get("WAKEWORD_MODELS", "hey_jarvis")
        models = [m.strip() for m in models_raw.split(",") if m.strip()]
        if not models:
            models = ["hey_jarvis"]

        threshold_raw = os.environ.get("WAKEWORD_THRESHOLD", "0.5")
        try:
            threshold = float(threshold_raw)
        except ValueError:
            threshold = 0.5
        threshold = max(0.0, min(1.0, threshold))

        return KwsConfig(wakeword_models=models, threshold=threshold, sample_rate=SAMPLE_RATE)


@dataclass
class KwsResult:
    detected: bool
    keyword: str
    score: float
    timestamp: float


class KwsOpenWakeWord:
    def __init__(self, config: KwsConfig) -> None:
        self.config = config
        self._model: Any = None

    def initialize(self) -> None:
        import openwakeword
        from openwakeword.model import Model

        openwakeword.utils.download_models(self.config.wakeword_models)
        self._model = Model(wakeword_models=self.config.wakeword_models)
        logger.info("openWakeWord wake word detection initialized", {
            "models": self.config.wakeword_models,
            "frameLength": FRAME_LENGTH,
            "sampleRate": self.config.sample_rate,
        })

    def process_frame(self, audio_frame: np.ndarray) -> KwsResult:
        """audio_frame: int16 PCM or normalized float32 samples, length == FRAME_LENGTH."""
        if self._model is None:
            raise RuntimeError("openWakeWord model not initialized")

        frame = audio_frame
        if frame.dtype != np.int16:
            frame = np.clip(frame, -1.0, 1.0)
            frame = (frame * 32768).astype(np.int16)

        predictions = self._model.predict(frame)
        if not predictions:
            return KwsResult(False, "", 0.0, time.time() * 1000)

        best_keyword, best_score = max(predictions.items(), key=lambda kv: kv[1])

        if best_score >= self.config.threshold:
            logger.debug(f"Wake word detected: {best_keyword} (score: {best_score:.3f})")
            return KwsResult(True, best_keyword, best_score, time.time() * 1000)

        return KwsResult(False, "", best_score, time.time() * 1000)

    def get_frame_length(self) -> int:
        return FRAME_LENGTH

    def get_sample_rate(self) -> int:
        return self.config.sample_rate

    def cleanup(self) -> None:
        self._model = None
        logger.info("openWakeWord cleaned up")

    @staticmethod
    def get_builtin_keywords() -> list[str]:
        # Pretrained models shipped by openWakeWord as of writing.
        return ["hey_jarvis", "alexa", "hey_mycroft", "timer", "weather"]
