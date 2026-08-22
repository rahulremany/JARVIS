"""Ported from src/policy/loadPolicy.ts."""
from __future__ import annotations

import yaml

from ..utils.logging import logger
from .schema import PolicyConfig

DEFAULT_POLICY_PATH = "config/model-policy.yaml"


def load_policy(path: str = DEFAULT_POLICY_PATH) -> PolicyConfig:
    try:
        with open(path, "r", encoding="utf-8") as f:
            parsed = yaml.safe_load(f)
        validated = PolicyConfig.model_validate(parsed)
        logger.info("✅ Policy loaded from", path)
        return validated
    except Exception as error:  # noqa: BLE001 -- surfaced immediately below
        logger.error("Failed to load policy:", error)
        raise RuntimeError(f"Failed to load policy from {path}: {error}") from error
