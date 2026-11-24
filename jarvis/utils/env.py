"""Environment loading, ported from src/utils/env.ts."""
from __future__ import annotations

import os
from dataclasses import dataclass

from .logging import logger


@dataclass
class EnvConfig:
    mode: str
    log_level: str
    port: int
    anthropic_api_key: str
    eleven_api_key: str
    jarvis_voice_id: str


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
        log_level=os.environ.get("LOG_LEVEL", "info"),
        port=port,
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        eleven_api_key=os.environ.get("ELEVEN_API_KEY", ""),
        jarvis_voice_id=os.environ.get("JARVIS_VOICE_ID", ""),
    )

    for label, value in (
        ("ANTHROPIC_API_KEY", config.anthropic_api_key),
        ("ELEVEN_API_KEY", config.eleven_api_key),
    ):
        if value:
            logger.info(f"✅ {label} loaded: {value[:10]}...")
        else:
            logger.warn(f"❌ {label} not found in environment")

    return config
