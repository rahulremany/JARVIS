"""Ported from src/asr/AsrWhisper.ts.

Unlike the TypeScript original (which only mocked transcription), this
wraps the real `openai-whisper` package -- the same one already proven
working in wake_system_integrated.py.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from ..utils.logging import logger

_SUPPORTED_LANGUAGES = [
    "en", "es", "fr", "de", "it", "pt", "ru", "ja", "ko", "zh",
    "ar", "hi", "tr", "pl", "nl", "sv", "da", "no", "fi",
]

_MODEL_RECOMMENDATIONS = {
    "tiny": "Fastest, least accurate (~40MB)",
    "base": "Good balance of speed and accuracy (~150MB)",
    "small": "Better accuracy, slower (~500MB)",
    "medium": "High accuracy, much slower (~1.5GB)",
    "large": "Best accuracy, very slow (~3GB)",
}


@dataclass
class AsrConfig:
    model_size: str = "base"
    language: str = "en"
    temperature: float = 0.0
    initial_prompt: str = "Hello, I am JARVIS. How may I help you?"


@dataclass
class AsrResult:
    text: str
    confidence: float
    language: str
    duration: float
    timestamp: float


class AsrWhisper:
    def __init__(self, config: Optional[AsrConfig] = None) -> None:
        self.config = config or AsrConfig()
        self._model: Any = None

    def initialize(self) -> None:
        import whisper

        logger.info("Initializing Whisper ASR...", {"modelSize": self.config.model_size, "language": self.config.language})
        self._model = whisper.load_model(self.config.model_size)
        logger.info("Whisper ASR initialized successfully")

    def transcribe(self, audio_data: np.ndarray, sample_rate: int = 16000) -> AsrResult:
        if self._model is None:
            raise RuntimeError("Whisper not initialized")

        start = time.perf_counter()
        logger.debug(f"Transcribing audio: {len(audio_data)} samples at {sample_rate}Hz")

        if len(audio_data) == 0:
            raise ValueError("Empty audio data")

        audio_level = self._audio_level(audio_data)
        if audio_level < 0.001:
            logger.debug("Audio appears to be mostly silence")
            return AsrResult("", 0.0, self.config.language, (time.perf_counter() - start) * 1000, time.time() * 1000)

        import whisper

        audio_f32 = audio_data.astype(np.float32)
        peak = np.max(np.abs(audio_f32))
        if peak > 0:
            audio_f32 = audio_f32 / peak
        audio_f32 = whisper.pad_or_trim(audio_f32)

        result = self._model.transcribe(
            audio_f32,
            language=self.config.language,
            fp16=False,
            no_speech_threshold=0.3,
            condition_on_previous_text=False,
            initial_prompt=self.config.initial_prompt,
        )

        duration = (time.perf_counter() - start) * 1000
        text = result["text"].strip()
        logger.debug(f'Transcription completed in {duration:.1f}ms: "{text}"')

        return AsrResult(text, 0.8, result.get("language", self.config.language), duration, time.time() * 1000)

    def _audio_level(self, audio_data: np.ndarray) -> float:
        return float(np.mean(np.abs(audio_data)))

    def convert_to_float32(self, audio_data: np.ndarray) -> np.ndarray:
        return audio_data.astype(np.float32) / 32768.0

    def preprocess_audio(self, audio_data: np.ndarray) -> np.ndarray:
        max_value = float(np.max(np.abs(audio_data))) if len(audio_data) else 0.0
        if max_value > 0:
            return audio_data * (0.95 / max_value)
        return audio_data

    def cleanup(self) -> None:
        self._model = None
        logger.info("Whisper ASR cleaned up")

    @staticmethod
    def get_supported_languages() -> list[str]:
        return list(_SUPPORTED_LANGUAGES)

    @staticmethod
    def get_model_recommendations() -> dict[str, str]:
        return dict(_MODEL_RECOMMENDATIONS)
