"""Ported from src/router/EngineSelector.ts."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

from ..engines.claude.claude_engine import ClaudeEngine, GenerationEvent, GenerationParams
from ..policy.load_policy import load_policy
from ..policy.schema import PolicyConfig
from ..session.session_manager import SYSTEM_PROMPT, SessionManager
from ..session.user_profile import UserProfileStore
from ..tools.device_actions import DeviceActions
from ..tools.agent_tools import AgentToolRegistry
from ..utils.logging import logger
from .intent_interpreter import IntentInterpreter
from .router import Router


class EngineSelector:
    def __init__(
        self,
        claude_engine: Optional[ClaudeEngine] = None,
        policy: Optional[PolicyConfig] = None,
        session_manager: Optional[SessionManager] = None,
    ) -> None:
        self.policy = policy or load_policy()
        self.claude_engine = claude_engine or ClaudeEngine()
        self.router = Router()
        self.device_actions = DeviceActions()
        self.session_manager = session_manager
        workspace_root = Path(os.environ.get("JARVIS_WORKSPACE_ROOT", Path.cwd())).resolve()
        self.profile_store = UserProfileStore(workspace_root / ".jarvis_state")
        self.intent_interpreter = IntentInterpreter()
        self.agent_tools = AgentToolRegistry()

    def _compose_system_prompt(self, prompt: str) -> str:
        profile = self.profile_store.get()
        intent = self.intent_interpreter.interpret(prompt).to_dict()

        profile_context = (
            "\n\nUser Profile Context:\n"
            f"- Name: {profile.get('name', '') or '(unknown)'}\n"
            f"- Preferred tone: {profile.get('preferred_tone', 'direct')}\n"
            f"- Goals: {profile.get('goals', [])}\n"
            f"- Constraints: {profile.get('constraints', [])}\n"
            f"- Coding style notes: {profile.get('coding_style_notes', [])}\n"
        )
        intent_context = (
            "\nInterpreted Intent (best-effort; use as guidance, not strict truth):\n"
            f"- Goal: {intent.get('goal')}\n"
            f"- Domain: {intent.get('domain')}\n"
            f"- Likely tools: {intent.get('likely_tools')}\n"
            f"- Constraints: {intent.get('constraints')}\n"
            f"- Success criteria: {intent.get('success_criteria')}\n"
            f"- Confidence: {intent.get('confidence')}\n"
        )
        tool_policy = (
            "\nTooling Policy:\n"
            "- When user asks to create/scaffold a new project, call create_desktop_project by default.\n"
            "- Default project location is the projects root configured by JARVIS_PROJECTS_ROOT.\n"
            "- Only use workspace file-edit tools for changes inside this JARVIS repository unless user asks otherwise.\n"
        )
        return SYSTEM_PROMPT + profile_context + intent_context + tool_policy

    def _build_messages(self, session_id: str, prompt: str) -> list[dict[str, str]]:
        """Full conversation history for this session, mapped to Claude's
        message shape. Falls back to a single-turn message when no
        SessionManager was wired in (e.g. direct engine use in tests)."""
        if not self.session_manager:
            return [{"role": "user", "content": prompt}]

        history = self.session_manager.get_messages(session_id)
        return [{"role": m.role, "content": m.content} for m in history if m.role in ("user", "assistant")]

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
            temperature=params.temperature if params.temperature is not None else model_config.temperature,
            stop=params.stop,
        )
        messages = self._build_messages(session_id, prompt)
        system_prompt = self._compose_system_prompt(prompt)

        try:
            logger.debug(f"Using Claude engine (tier: {tier}, model: {model_config.id})")
            async for event in self.claude_engine.generate_stream_with_tools(
                session_id=session_id,
                messages=messages,
                params=final_params,
                model=model_config.id,
                system=system_prompt,
                tools=self.agent_tools.tool_schemas(),
                tool_runner=self.agent_tools.invoke,
            ):
                yield event
        except Exception as error:  # noqa: BLE001
            logger.error(f"Generation failed on {tier} tier ({model_config.id}):", error)
            if self.policy.policy.fallback_enabled and tier != "primary":
                logger.warn("Falling back to primary model")
                fallback_config = self.policy.models.primary
                fallback_params = GenerationParams(
                    max_tokens=final_params.max_tokens, temperature=final_params.temperature, stop=final_params.stop,
                )
                async for event in self.claude_engine.generate_stream_with_tools(
                    session_id=session_id,
                    messages=messages,
                    params=fallback_params,
                    model=fallback_config.id,
                    system=system_prompt,
                    tools=self.agent_tools.tool_schemas(),
                    tool_runner=self.agent_tools.invoke,
                ):
                    yield event
            else:
                raise

    async def get_health(self) -> dict[str, Any]:
        return {
            "claude": self.claude_engine.get_health(),
            "routing": {"policy_mode": self.policy.policy.mode, "fallback_enabled": self.policy.policy.fallback_enabled},
        }

    async def cleanup(self) -> None:
        await self.claude_engine.cleanup()

    async def generate_with_fallback(self, prompt: str, session_id: str) -> dict[str, Any]:
        route_result = self.router.classify(prompt)
        if route_result.route_class == "direct_command":
            return {"type": "direct_command", "device_command": route_result.device_command}
        return {"type": "llm", "stream": self.generate_stream(session_id, prompt)}
