"""Environment loading, ported from src/utils/env.ts."""
from __future__ import annotations

import os
from dataclasses import dataclass

from .logging import logger


@dataclass
class EnvConfig:
    mode: str
    use_ollama: bool
    vllm_base_url: str
    log_level: str
    ollama_keep_alive: str
    port: int
    eleven_api_key: str
    porcupine_access_key: str
    jarvis_voice_id: str
    openai_api_key: str


def load_env() -> EnvConfig:
    port_raw = os.environ.get("PORT", "3000")
    try:
        port = int(port_raw)
        if not (1 <= port <= 65535):
            raise ValueError
    except ValueError:
        logger.warn(f"Invalid PORT value: {port_raw}, using default 3000")
        port = 3000

    config = EnvConfig(
        mode=os.environ.get("MODE", "dev"),
        use_ollama=os.environ.get("USE_OLLAMA") == "true",
        vllm_base_url=os.environ.get("VLLM_BASE_URL", ""),
        log_level=os.environ.get("LOG_LEVEL", "info"),
        ollama_keep_alive=os.environ.get("OLLAMA_KEEP_ALIVE", "5m"),
        port=port,
        eleven_api_key=os.environ.get("ELEVEN_API_KEY", ""),
        porcupine_access_key=os.environ.get("PORCUPINE_ACCESS_KEY", ""),
        jarvis_voice_id=os.environ.get("JARVIS_VOICE_ID", "LE42bqYwZicKpZRastCO"),
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
    )

    for label, value in (
        ("ELEVEN_API_KEY", config.eleven_api_key),
        ("PORCUPINE_ACCESS_KEY", config.porcupine_access_key),
        ("OPENAI_API_KEY", config.openai_api_key),
    ):
        if value:
            logger.info(f"✅ {label} loaded: {value[:10]}...")
        else:
            logger.warn(f"❌ {label} not found in environment")

    return config
