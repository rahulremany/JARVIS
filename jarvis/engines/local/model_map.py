"""Ported from src/engines/local/modelMap.ts."""
from __future__ import annotations

import os
import platform
from dataclasses import dataclass
from typing import Literal

from ...utils.logging import logger


@dataclass
class ModelMetadata:
    id: str
    path: str
    size_gb: float
    min_ram_gb: int
    recommended_ram_gb: int
    parameters: str
    quantization: str
    capabilities: list[str]
    speed: Literal["fast", "medium", "slow"]
    quality: Literal["good", "better", "best"]


MODEL_CATALOG: list[ModelMetadata] = [
    ModelMetadata(
        id="qwen2.5:3b-instruct-q4_K_M",
        path="models/qwen2.5-3b-instruct-q4_k_m.gguf",
        size_gb=2.0, min_ram_gb=4, recommended_ram_gb=6,
        parameters="3B", quantization="Q4_K_M",
        capabilities=["chat", "instruct", "reasoning", "code"],
        speed="fast", quality="good",
    ),
    ModelMetadata(
        id="llama3.1:8b-instruct-q4_K_M",
        path="models/llama-3.1-8b-instruct-q4_k_m.gguf",
        size_gb=4.6, min_ram_gb=6, recommended_ram_gb=8,
        parameters="8B", quantization="Q4_K_M",
        capabilities=["chat", "instruct", "reasoning", "code", "analysis"],
        speed="medium", quality="better",
    ),
    ModelMetadata(
        id="phi3:mini",
        path="models/phi3-mini-4k-instruct-q4_0.gguf",
        size_gb=2.1, min_ram_gb=4, recommended_ram_gb=6,
        parameters="3.8B", quantization="Q4_0",
        capabilities=["chat", "instruct", "code"],
        speed="fast", quality="good",
    ),
    ModelMetadata(
        id="mixtral:8x7b-instruct-q4_K_M",
        path="models/mixtral-8x7b-instruct-q4_k_m.gguf",
        size_gb=26.4, min_ram_gb=32, recommended_ram_gb=64,
        parameters="46.7B", quantization="Q4_K_M",
        capabilities=["chat", "instruct", "reasoning", "code", "analysis", "multilingual"],
        speed="slow", quality="best",
    ),
]

MODEL_MAP: dict[str, str] = {m.id: m.path for m in MODEL_CATALOG}


def get_system_ram_gb() -> int:
    try:
        import psutil  # optional; fall back below if unavailable
        return round(psutil.virtual_memory().total / (1024 ** 3))
    except ImportError:
        # Best-effort fallback without a hard psutil dependency.
        pages = os.sysconf("SC_PHYS_PAGES") if hasattr(os, "sysconf") else 0
        page_size = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 0
        return round((pages * page_size) / (1024 ** 3)) if pages and page_size else 16


def detect_best_model() -> ModelMetadata:
    system_ram = get_system_ram_gb()
    available = [m for m in MODEL_CATALOG if os.path.exists(m.path)]

    if not available:
        raise RuntimeError("No GGUF models found on system")

    logger.info(f"[JARVIS] 🔍 System RAM: {system_ram}GB")
    logger.info(f"[JARVIS] 📋 Available models: {', '.join(m.id for m in available)}")

    compatible = [m for m in available if m.min_ram_gb <= system_ram]
    if not compatible:
        logger.warn("[JARVIS] ⚠️  No models meet minimum RAM requirement. Using smallest available.")
        return sorted(available, key=lambda m: m.min_ram_gb)[0]

    optimal = [m for m in compatible if m.recommended_ram_gb <= system_ram]
    selected = max(optimal, key=lambda m: m.size_gb) if optimal else max(compatible, key=lambda m: m.size_gb)

    logger.info(f"[JARVIS] 🎯 Selected optimal model: {selected.id}")
    return selected


def resolve_model_path(model_id: str) -> str:
    for m in MODEL_CATALOG:
        if m.id == model_id:
            return os.path.abspath(m.path)
    raise ValueError(f"Unknown model ID: {model_id}. Available: {', '.join(MODEL_MAP)}")


def get_model_metadata(model_id: str) -> ModelMetadata:
    for m in MODEL_CATALOG:
        if m.id == model_id:
            return m
    raise ValueError(f"Unknown model ID: {model_id}")


def is_apple_silicon() -> bool:
    return platform.system() == "Darwin" and platform.processor() == "arm"
