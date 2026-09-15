"""Policy schema, ported from src/policy/schema.ts (Zod -> Pydantic)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ModelDef(BaseModel):
    """One Claude model bound to a difficulty tier."""

    id: str
    max_tokens: int
    temperature: float


class RoutingConfig(BaseModel):
    escalate_tags: list[str]
    hard_keywords: list[str]
    default_class: Literal["trivial", "normal", "hard"]


class ModelsConfig(BaseModel):
    router: ModelDef   # trivial / direct_command -> fastest, cheapest
    primary: ModelDef  # normal -> everyday conversation
    heavy: ModelDef     # hard -> deep reasoning, planning, coding


class PolicyMode(BaseModel):
    mode: Literal["dev", "prod"]
    fallback_enabled: bool
    log_routing_decisions: bool


class PolicyConfig(BaseModel):
    routing: RoutingConfig
    models: ModelsConfig
    policy: PolicyMode
