"""Claude API engine -- replaces the local llama.cpp/Ollama/vLLM mesh.

One engine, three models. Instead of loading/evicting different quantized
weights locally, requests are routed by difficulty (see
`jarvis/router/router.py::Router.classify`) to whichever Claude model fits:
Haiku for trivial lookups, Sonnet for everyday conversation, Opus for
genuinely hard reasoning/planning/coding work.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Awaitable, Callable, Literal, Optional

from ...utils.logging import logger

GenerationEventType = Literal["first", "token", "narration", "done"]

# Prompt caching: the system prompt (profile + intent + tool policy) and the
# tool definitions are near-identical on every single request -- both in one
# session's back-and-forth and across sessions, since profile/tool schemas
# rarely change turn to turn. Marking them as ephemeral cache breakpoints
# means Anthropic reuses that server-side KV cache instead of reprocessing
# the same few thousand tokens (system + ~30 tool schemas) on every call,
# which is most of the fixed cost of every request. Cache writes cost a bit
# more than a normal read but hits are ~90% cheaper, so this pays for itself
# after the first request of a session. See:
# https://docs.claude.com/en/docs/build-with-claude/prompt-caching
_CACHE_CONTROL = {"type": "ephemeral"}


def _system_blocks(system: str) -> list[dict[str, Any]]:
    return [{"type": "text", "text": system, "cache_control": _CACHE_CONTROL}]


def _cached_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Tags the last tool definition with a cache breakpoint -- Anthropic
    caches everything up to and including a breakpoint, so one marker at the
    end of the (static, ordered) tools list covers the whole block."""
    if not tools:
        return tools
    marked = [dict(tool) for tool in tools]
    marked[-1] = {**marked[-1], "cache_control": _CACHE_CONTROL}
    return marked


_TOOL_NARRATION = {
    "open_app": "opening that for you",
    "web_search": "searching for that now",
    "open_and_type": "pulling that up",
    "read_screen": "taking a look at your screen",
    "click_element": "clicking that",
    "type_text": "typing that in",
    "press_keys": "on it",
    "switch_tab": "switching tabs",
    "scroll": "scrolling",
    "calendar_list_events": "checking your calendar",
    "calendar_create_event": "adding that to your calendar",
    "calendar_update_event": "updating that event",
    "calendar_delete_event": "removing that event",
    "canvas_list_upcoming_assignments": "checking Canvas for upcoming work",
    "canvas_list_grades": "pulling your grades",
    "reminders_add": "adding a reminder",
    "reminders_list": "checking your reminders",
    "reminders_complete": "marking that done",
    "daily_briefing_run": "putting your briefing together",
    "run_dev_command": "running that",
    "search_workspace": "searching the codebase",
    "write_workspace_file": "writing that file",
    "edit_workspace_file": "making that edit",
}


def _narrate_tool(tool_name: str) -> str:
    """Short, human in-progress line for a tool call the model didn't
    narrate itself -- keeps JARVIS from going silent while it works (see
    feedback_visible_progress memory: the user wants to see it happen live,
    not get a single report at the end)."""
    return _TOOL_NARRATION.get(tool_name, f"working on it ({tool_name.replace('_', ' ')})")


def _with_cache_breakpoint(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Marks the last message's final content block as a cache breakpoint so
    everything before it (the whole conversation-so-far prefix) can be
    served from cache on the next call -- the growing tool_use/tool_result
    history within one agentic tool loop, and the accumulating session
    history across turns, are exactly this repeated-prefix shape."""
    if not messages:
        return messages
    copied = list(messages)
    last = dict(copied[-1])
    content = last.get("content")
    blocks = [{"type": "text", "text": content}] if isinstance(content, str) else [dict(b) for b in content]
    if blocks:
        blocks[-1] = {**blocks[-1], "cache_control": _CACHE_CONTROL}
    last["content"] = blocks
    copied[-1] = last
    return copied


@dataclass
class GenerationEvent:
    type: GenerationEventType
    text: Optional[str] = None
    timestamp: float = 0.0
    ms: Optional[float] = None


@dataclass
class GenerationParams:
    max_tokens: Optional[int] = None
    ctx: Optional[int] = None  # unused for Claude (no fixed context window to reserve) but kept for interface parity
    temperature: Optional[float] = None
    stop: Optional[list[str]] = None


class ClaudeEngine:
    """Thin wrapper around the Anthropic Messages API, streaming."""

    def __init__(self, api_key: Optional[str] = None) -> None:
        import anthropic  # imported lazily so the package is optional until this engine is actually used

        self._anthropic = anthropic
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            logger.warn("ANTHROPIC_API_KEY not set -- Claude engine will fail on first request")
        self._client = anthropic.AsyncAnthropic(api_key=key) if key else anthropic.AsyncAnthropic()
        self._last_model: Optional[str] = None

    async def generate_stream(
        self,
        session_id: str,
        messages: list[dict[str, str]],
        params: GenerationParams,
        model: str,
        system: Optional[str] = None,
    ) -> AsyncGenerator[GenerationEvent, None]:
        t0 = time.perf_counter()
        first_ms: Optional[float] = None
        tokens_out = 0
        full_response = ""
        self._last_model = model
        prompt_chars = sum(len(m.get("content", "")) for m in messages)

        max_tokens = params.max_tokens or 1024
        # `temperature` is tracked on GenerationParams/logged for now but no
        # longer forwarded to the API -- the installed SDK's Messages.create
        # (anthropic>=1.0) dropped it as a request parameter entirely.
        temperature = params.temperature if params.temperature is not None else 0.7

        request_kwargs: dict[str, Any] = dict(
            model=model,
            max_tokens=max_tokens,
            messages=_with_cache_breakpoint(messages),
        )
        if params.stop:
            request_kwargs["stop_sequences"] = params.stop
        if system:
            request_kwargs["system"] = _system_blocks(system)

        try:
            async with self._client.messages.stream(**request_kwargs) as stream:
                async for text in stream.text_stream:
                    if not text:
                        continue
                    if first_ms is None:
                        first_ms = (time.perf_counter() - t0) * 1000
                        yield GenerationEvent(type="first", ms=first_ms, timestamp=time.time() * 1000)
                    tokens_out += 1
                    full_response += text
                    yield GenerationEvent(type="token", text=text, timestamp=time.time() * 1000)
        except Exception as error:  # noqa: BLE001
            logger.error(f"Claude generation failed (model={model}):", error)
            raise
        finally:
            total_ms = (time.perf_counter() - t0) * 1000
            logger.log_latency({
                "engine": "claude", "model_id": model,
                "params": {"max_tokens": max_tokens, "temperature": temperature, "stop": params.stop or []},
                "prompt_chars": prompt_chars, "session_id": session_id,
                "first_token_ms": first_ms or total_ms, "total_ms": total_ms,
                "tokens_out": tokens_out, "route": model,
            })
            yield GenerationEvent(type="done", timestamp=time.time() * 1000)

    async def generate_stream_with_tools(
        self,
        session_id: str,
        messages: list[dict[str, Any]],
        params: GenerationParams,
        model: str,
        system: Optional[str],
        tools: list[dict[str, Any]],
        tool_runner: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]],
        max_tool_rounds: int = 8,
    ) -> AsyncGenerator[GenerationEvent, None]:
        """Anthropic native tool-use loop.

        Runs iterative assistant -> tool_use -> tool_result rounds until the
        model returns a final text answer (or the round cap is reached).
        """
        t0 = time.perf_counter()
        first_ms: Optional[float] = None
        tokens_out = 0
        self._last_model = model

        max_tokens = params.max_tokens or 1024
        temperature = params.temperature if params.temperature is not None else 0.7

        convo: list[dict[str, Any]] = list(messages)
        final_text = ""
        # Tools and system are static for the whole loop -- compute the cached
        # forms once instead of re-tagging them every round.
        cached_tools = _cached_tools(tools)
        system_blocks = _system_blocks(system) if system else None

        def _mark_first() -> Optional[GenerationEvent]:
            nonlocal first_ms
            if first_ms is not None:
                return None
            first_ms = (time.perf_counter() - t0) * 1000
            return GenerationEvent(type="first", ms=first_ms, timestamp=time.time() * 1000)

        try:
            for round_index in range(max_tool_rounds):
                request_kwargs: dict[str, Any] = dict(
                    model=model,
                    max_tokens=max_tokens,
                    messages=_with_cache_breakpoint(convo),
                    tools=cached_tools,
                )
                if params.stop:
                    request_kwargs["stop_sequences"] = params.stop
                if system_blocks:
                    request_kwargs["system"] = system_blocks

                response = await self._client.messages.create(**request_kwargs)

                assistant_content: list[dict[str, Any]] = []
                tool_uses: list[dict[str, Any]] = []
                text_chunks: list[str] = []

                for block in response.content:
                    block_type = getattr(block, "type", "")
                    if block_type == "text":
                        text_value = getattr(block, "text", "") or ""
                        assistant_content.append({"type": "text", "text": text_value})
                        text_chunks.append(text_value)
                    elif block_type == "tool_use":
                        tool_block = {
                            "type": "tool_use",
                            "id": getattr(block, "id", ""),
                            "name": getattr(block, "name", ""),
                            "input": getattr(block, "input", {}) or {},
                        }
                        assistant_content.append(tool_block)
                        tool_uses.append(tool_block)

                convo.append({"role": "assistant", "content": assistant_content})

                if tool_uses:
                    # One brief acknowledgment on the FIRST round only, then
                    # go quiet while the actual work happens -- per-round
                    # narration ("checking file 1 of 12...") is exactly what
                    # script.md's persona rules out, and it was also racing
                    # against the final response's speech (both checked
                    # `if _is_speaking: return` and silently dropped audio).
                    # The tool calls themselves still execute for real and
                    # are still visible on screen; it's the play-by-play
                    # narration that's gone, not the actual work.
                    if round_index == 0:
                        event = _mark_first()
                        if event:
                            yield event

                        narration = " ".join(chunk.strip() for chunk in text_chunks if chunk.strip())
                        if not narration:
                            narration = ", ".join(_narrate_tool(t["name"]) for t in tool_uses)
                        if narration:
                            yield GenerationEvent(type="narration", text=narration.strip(), timestamp=time.time() * 1000)

                    tool_results: list[dict[str, Any]] = []
                    for tool_call in tool_uses:
                        try:
                            result = await tool_runner(tool_call["name"], tool_call["input"])
                        except Exception as error:  # noqa: BLE001
                            result = {"error": str(error), "success": False}

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_call["id"],
                            "content": json.dumps(result),
                        })

                    convo.append({"role": "user", "content": tool_results})
                    continue

                final_text = "".join(text_chunks).strip()
                break
            else:
                final_text = "I reached the tool-execution limit before finishing."

            event = _mark_first()
            if event:
                yield event

            if final_text:
                for chunk in final_text.split(" "):
                    piece = chunk + " "
                    tokens_out += 1
                    yield GenerationEvent(type="token", text=piece, timestamp=time.time() * 1000)

        except Exception as error:  # noqa: BLE001
            logger.error(f"Claude tool loop failed (model={model}):", error)
            raise
        finally:
            total_ms = (time.perf_counter() - t0) * 1000
            logger.log_latency({
                "engine": "claude",
                "model_id": model,
                "params": {"max_tokens": max_tokens, "temperature": temperature, "stop": params.stop or []},
                "prompt_chars": sum(len(str(m.get("content", ""))) for m in messages),
                "session_id": session_id,
                "first_token_ms": first_ms or total_ms,
                "total_ms": total_ms,
                "tokens_out": tokens_out,
                "route": model,
            })
            yield GenerationEvent(type="done", timestamp=time.time() * 1000)

    async def smoke_test(self, model: str) -> None:
        logger.info(f"Running startup smoke test against {model}...")
        params = GenerationParams(max_tokens=16, temperature=0.0)

        start = time.perf_counter()
        first_token_ms = 0.0
        response = ""
        tokens_out = 0

        messages = [{"role": "user", "content": "Reply with OK"}]
        async for event in self.generate_stream("smoke-test", messages, params, model):
            if event.type == "first":
                first_token_ms = event.ms or 0
            elif event.type == "token" and event.text:
                tokens_out += 1
                response += event.text
            elif event.type == "done":
                break

        total_ms = (time.perf_counter() - start) * 1000
        if tokens_out == 0:
            logger.warn(f"Smoke test produced no tokens (first={first_token_ms}ms total={total_ms}ms)")
        else:
            logger.info(f"✅ SMOKE OK first={first_token_ms}ms total={total_ms}ms engine=claude model={model}")

    def get_health(self) -> dict[str, Any]:
        return {
            "ok": bool(os.environ.get("ANTHROPIC_API_KEY")),
            "engine": "claude",
            "lastModel": self._last_model,
        }

    async def cleanup(self) -> None:
        await self._client.close()
