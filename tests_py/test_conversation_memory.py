"""Regression test for the session-memory bug: handle_text_input used to
build a fresh single-message [{"role": "user", "content": text}] on every
call, so JARVIS had no memory of anything said earlier in the same session.
It now reads/writes jarvis.session.session_manager.SessionManager."""
from __future__ import annotations

from typing import Any

import pytest

from jarvis.conversation.conversation_handler import ConversationConfig, ConversationHandler
from jarvis.engines.claude.claude_engine import GenerationEvent
from jarvis.session.session_manager import SessionManager


class _FakeEngine:
    """Records the messages it was called with and returns a canned reply --
    no real API calls, no narration/tool rounds needed for this test."""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.seen_messages: list[list[dict[str, Any]]] = []

    async def generate_stream_with_tools(self, session_id, messages, params, model, system, tools, tool_runner):
        self.seen_messages.append(list(messages))
        yield GenerationEvent(type="first", ms=0, timestamp=0)
        for word in self.reply.split(" "):
            yield GenerationEvent(type="token", text=word + " ", timestamp=0)
        yield GenerationEvent(type="done", timestamp=0)


@pytest.mark.asyncio
async def test_handle_text_input_remembers_prior_turns():
    session_manager = SessionManager()
    handler = ConversationHandler(config=ConversationConfig(enable_tts=False), session_manager=session_manager)

    engine = _FakeEngine("Nice to meet you, Rahul.")
    await handler.handle_text_input("my name is Rahul", engine, session_id="s1")

    engine2 = _FakeEngine("Your name is Rahul.")
    await handler.handle_text_input("what did I just tell you my name was", engine2, session_id="s1")

    # The second call's request must include the first turn's user+assistant
    # messages, not just the new question on its own -- that's the whole bug.
    second_call_messages = engine2.seen_messages[0]
    contents = [m["content"] for m in second_call_messages]
    assert any("my name is Rahul" in c for c in contents)
    assert any("Nice to meet you, Rahul" in c for c in contents)
    assert contents[-1] == "what did I just tell you my name was"


@pytest.mark.asyncio
async def test_handle_text_input_appends_both_turns_to_session():
    session_manager = SessionManager()
    handler = ConversationHandler(config=ConversationConfig(enable_tts=False), session_manager=session_manager)

    engine = _FakeEngine("The capital of France is Paris.")
    response = await handler.handle_text_input("what is the capital of france", engine, session_id="s2")

    history = session_manager.get_messages("s2")
    roles_and_content = [(m.role, m.content) for m in history if m.role != "system"]
    assert ("user", "what is the capital of france") in roles_and_content
    assert ("assistant", response.strip()) in roles_and_content
