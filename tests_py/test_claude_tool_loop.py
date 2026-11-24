from __future__ import annotations

import pytest

from jarvis.engines.claude.claude_engine import ClaudeEngine, GenerationParams


class _Block:
    def __init__(self, block_type: str, **kwargs):
        self.type = block_type
        for key, value in kwargs.items():
            setattr(self, key, value)


class _Response:
    def __init__(self, content):
        self.content = content


class _MessagesAPI:
    def __init__(self):
        self.calls = 0

    async def create(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return _Response([
                _Block("tool_use", id="toolu_1", name="profile_get", input={}),
            ])
        return _Response([
            _Block("text", text="Done, profile retrieved."),
        ])


class _Client:
    def __init__(self):
        self.messages = _MessagesAPI()


@pytest.mark.asyncio
async def test_generate_stream_with_tools_executes_tool_and_returns_text():
    engine = ClaudeEngine.__new__(ClaudeEngine)
    engine._client = _Client()
    engine._last_model = None

    tool_calls = []

    async def runner(name, payload):
        tool_calls.append((name, payload))
        return {"name": "Ada"}

    params = GenerationParams(max_tokens=64, temperature=0.2)
    messages = [{"role": "user", "content": "who am i?"}]

    chunks = []
    async for event in engine.generate_stream_with_tools(
        session_id="s1",
        messages=messages,
        params=params,
        model="claude-sonnet-5",
        system="You are JARVIS",
        tools=[{"name": "profile_get", "description": "get profile", "input_schema": {"type": "object", "properties": {}}}],
        tool_runner=runner,
    ):
        if event.type == "token" and event.text:
            chunks.append(event.text)

    text = "".join(chunks)
    assert "Done, profile retrieved." in text
    assert tool_calls == [("profile_get", {})]
