"""Ported from src/router/EngineSelector.ts."""
from __future__ import annotations

from typing import Any, AsyncGenerator, Optional

from ..engines.heavy.vllm_engine import VllmEngine
from ..engines.local.local_llama_engine import GenerationEvent, GenerationParams, LocalLlamaEngine
from ..engines.mesh.ollama_engine import FacetModelMap, OllamaEngine
from ..policy.load_policy import load_policy
from ..policy.schema import PolicyConfig
from ..tools.device_actions import DeviceActions
from ..utils.logging import logger
from .router import Facet, Router


class EngineSelector:
    def __init__(
        self,
        local_engine: Optional[LocalLlamaEngine] = None,
        heavy_engine: Optional[VllmEngine] = None,
        policy: Optional[PolicyConfig] = None,
    ) -> None:
        self.policy = policy or load_policy()
        self.local_engine = local_engine or LocalLlamaEngine()
        self.heavy_engine = heavy_engine
        self.router = Router()
        self.device_actions = DeviceActions()

        if not self.heavy_engine and self.policy.endpoints.vllm_base_url:
            self.heavy_engine = VllmEngine(self.policy.endpoints.vllm_base_url)

        # Mesh engine only comes up if the policy actually declares facets --
        # keeps this a no-op for anyone still running the plain
        # trivial/normal/hard policy shape.
        self.mesh_engine: Optional[OllamaEngine] = None
        if self.policy.facets:
            self.mesh_engine = OllamaEngine(facet_models=FacetModelMap(
                planner=self.policy.facets.planner.model,
                coder=self.policy.facets.coder.model,
                fast=self.policy.facets.fast.model,
            ))

    async def generate_facet_stream(
        self, prompt: str, params: Optional[GenerationParams] = None
    ) -> AsyncGenerator[GenerationEvent, None]:
        """Task-routed mesh entry point: classify by facet (what kind of
        work this is), not by difficulty, and dispatch straight to the
        specialist model."""
        if not self.mesh_engine or not self.policy.facets:
            raise RuntimeError("Model mesh not configured -- add a `facets` block to model-policy.yaml")

        params = params or GenerationParams()
        facet: Facet = self.router.classify_facet(prompt)
        facet_config = getattr(self.policy.facets, facet)

        if self.policy.policy.log_routing_decisions:
            logger.info("Facet route decision:", {"input": prompt[:100], "facet": facet, "model": facet_config.model})

        final_params = GenerationParams(
            max_tokens=params.max_tokens or facet_config.max_tokens,
            ctx=params.ctx or facet_config.ctx,
            temperature=params.temperature if params.temperature is not None else facet_config.temperature,
            stop=params.stop,
        )

        async for event in self.mesh_engine.generate_stream(facet, prompt, final_params):
            yield event

    async def generate_stream(
        self, session_id: str, prompt: str, params: Optional[GenerationParams] = None
    ) -> AsyncGenerator[GenerationEvent, None]:
        params = params or GenerationParams()
        route_result = self.router.classify(prompt)

        if self.policy.policy.log_routing_decisions:
            logger.info("Route decision:", {
                "input": prompt[:100], "route": route_result,
                "tier": self.router.get_engine_tier(route_result.route_class),
            })

        if route_result.route_class == "direct_command" and route_result.device_command:
            try:
                result = await self.device_actions.execute_command(route_result.device_command)
                yield GenerationEvent(type="first", timestamp=0, ms=50)
                yield GenerationEvent(type="token", text=result, timestamp=0)
                yield GenerationEvent(type="done", timestamp=0)
                return
            except Exception as error:  # noqa: BLE001
                logger.error("Device command failed:", error)
                # fall through to LLM generation

        tier = self.router.get_engine_tier(route_result.route_class)
        model_config = getattr(self.policy.models, tier)

        final_params = GenerationParams(
            max_tokens=params.max_tokens or model_config.max_tokens,
            ctx=params.ctx or model_config.ctx,
            temperature=params.temperature if params.temperature is not None else model_config.temperature,
            stop=params.stop,
        )

        try:
            if tier == "heavy" and self.heavy_engine:
                logger.debug("Using heavy engine (vLLM)")
                model_id = (model_config.candidates_cpu or ["mixtral:8x7b-instruct-q4_K_M"])[0]
                async for event in self.heavy_engine.generate_stream(prompt, final_params, model_id):
                    yield event
            else:
                logger.debug(f"Using local engine (tier: {tier})")
                async for event in self.local_engine.generate_stream(session_id, prompt, final_params):
                    yield event
        except Exception as error:  # noqa: BLE001
            logger.error(f"Generation failed on {tier} tier:", error)
            if self.policy.policy.fallback_enabled and tier != "primary":
                logger.warn("Falling back to local engine")
                async for event in self.local_engine.generate_stream(session_id, prompt, final_params):
                    yield event
            else:
                raise

    async def get_health(self) -> dict[str, Any]:
        return {
            "local": self.local_engine.get_health(),
            "heavy": self.heavy_engine.get_health() if self.heavy_engine else {"ok": False, "reason": "not_configured"},
            "mesh": {"ok": self.mesh_engine is not None, "loaded": await self.mesh_engine.list_loaded() if self.mesh_engine else []},
            "routing": {"policy_mode": self.policy.policy.mode, "fallback_enabled": self.policy.policy.fallback_enabled},
        }

    async def cleanup(self) -> None:
        await self.local_engine.cleanup()

    async def generate_with_fallback(self, prompt: str, session_id: str) -> dict[str, Any]:
        route_result = self.router.classify(prompt)
        if route_result.route_class == "direct_command":
            return {"type": "direct_command", "device_command": route_result.device_command}
        return {"type": "llm", "stream": self.generate_stream(session_id, prompt)}
