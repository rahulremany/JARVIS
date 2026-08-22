"""Policy schema, ported from src/policy/schema.ts (Zod -> Pydantic)."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel


class ModelDef(BaseModel):
    candidates: Optional[list[str]] = None
    candidates_cpu: Optional[list[str]] = None
    max_tokens: Optional[int] = None
    ctx: Optional[int] = None
    temperature: Optional[float] = None
    timeout_ms: Optional[int] = None


class FacetDef(BaseModel):
    """One specialist model in the task-routed local mesh."""

    model: str
    engine: Literal["ollama", "llama_cpp", "vllm"]
    always_loaded: bool = False
    max_tokens: int
    ctx: int
    temperature: float


class RoutingConfig(BaseModel):
    escalate_tags: list[str]
    hard_keywords: list[str]
    default_class: Literal["trivial", "normal", "hard"]


class ModelsConfig(BaseModel):
    router: ModelDef
    primary: ModelDef
    heavy: ModelDef


class FacetsConfig(BaseModel):
    planner: FacetDef
    coder: FacetDef
    fast: FacetDef


class AutotuneConfig(BaseModel):
    first_token_threshold_ms: int
    total_threshold_ms: int
    success_rate_threshold: float


class PolicyMode(BaseModel):
    mode: Literal["dev", "prod"]
    fallback_enabled: bool
    log_routing_decisions: bool


class EndpointsConfig(BaseModel):
    vllm_base_url: str


class PolicyConfig(BaseModel):
    routing: RoutingConfig
    models: ModelsConfig
    # Task-routed mesh: which specialist model handles which kind of work,
    # independent of the trivial/normal/hard difficulty axis above.
    facets: Optional[FacetsConfig] = None
    autotune: AutotuneConfig
    policy: PolicyMode
    endpoints: EndpointsConfig
