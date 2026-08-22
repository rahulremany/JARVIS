"""Ported from src/asr/KwsPorcupine.ts.

Unlike the TypeScript original (which only stubbed the Porcupine binding),
this wraps the real `pvporcupine` library -- the same one already proven
working in wake_system_integrated.py.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from ..utils.logging import logger


@dataclass
class KwsConfig:
    access_key: str
    keywords: list[str]
    sensitivities: list[float]
    sample_rate: int = 16000


@dataclass
class KwsResult:
    detected: bool
    keyword: str
    index: int
    timestamp: float


class KwsPorcupine:
    def __init__(self, config: KwsConfig) -> None:
        self.config = config
        self._porcupine: Any = None

    def initialize(self) -> None:
        import pvporcupine

        self._porcupine = pvporcupine.create(
            access_key=self.config.access_key,
            keywords=self.config.keywords,
            sensitivities=self.config.sensitivities,
        )
        logger.info("Porcupine wake word detection initialized", {
            "keywords": self.config.keywords,
            "frameLength": self._porcupine.frame_length,
            "sampleRate": self._porcupine.sample_rate,
        })

    def process_frame(self, audio_frame: np.ndarray) -> KwsResult:
        """audio_frame: int16 PCM samples, length == self.get_frame_length()."""
        if self._porcupine is None:
            raise RuntimeError("Porcupine not initialized")

        keyword_index = self._porcupine.process(audio_frame)
        if keyword_index >= 0:
            keyword = self.config.keywords[keyword_index]
            logger.debug(f"Wake word detected: {keyword} (index: {keyword_index})")
            return KwsResult(True, keyword, keyword_index, time.time() * 1000)

        return KwsResult(False, "", -1, time.time() * 1000)

    def get_frame_length(self) -> int:
        return self._porcupine.frame_length if self._porcupine else 512

    def get_sample_rate(self) -> int:
        return self._porcupine.sample_rate if self._porcupine else 16000

    def cleanup(self) -> None:
        if self._porcupine:
            self._porcupine.delete()
            self._porcupine = None
            logger.info("Porcupine cleaned up")

    @staticmethod
    def validate_access_key(access_key: str) -> bool:
        import re
        return len(access_key) > 20 and re.match(r"^[A-Za-z0-9+/=]+$", access_key) is not None

    @staticmethod
    def get_builtin_keywords() -> list[str]:
        return ["jarvis", "hey jarvis", "computer", "alexa", "hey siri", "ok google", "bumblebee", "grasshopper", "hey barista"]
