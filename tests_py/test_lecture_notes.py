"""Tests for jarvis/tools/lecture_notes.py -- the batched (not incremental)
transcript -> study notes generation. Mocked Claude calls only, no API cost."""
from __future__ import annotations

import pytest

from jarvis.tools.lecture_notes import build_lecture_notes, _chunk_transcript


class _FakeEngine:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def generate_stream(self, session_id, messages, params, model, system=None):
        prompt = messages[0]["content"]
        self.calls.append(prompt)
        from jarvis.engines.claude.claude_engine import GenerationEvent
        yield GenerationEvent(type="token", text=f"[notes for: {prompt[:20]}...]", timestamp=0)


@pytest.mark.asyncio
async def test_short_transcript_uses_single_call():
    engine = _FakeEngine()
    notes = await build_lecture_notes(engine, "Today we covered photosynthesis and cellular respiration.")

    assert len(engine.calls) == 1
    assert "notes for" in notes


@pytest.mark.asyncio
async def test_empty_transcript_short_circuits_without_calling_claude():
    engine = _FakeEngine()
    notes = await build_lecture_notes(engine, "   ")

    assert engine.calls == []
    assert "No speech" in notes


@pytest.mark.asyncio
async def test_title_is_prefixed_as_heading():
    engine = _FakeEngine()
    notes = await build_lecture_notes(engine, "Some lecture content here.", title="CS 301 Lecture 4")

    assert notes.startswith("# CS 301 Lecture 4\n\n")


def test_chunk_transcript_splits_long_text():
    long_transcript = "word " * 20000  # ~100k chars, well over the chunk threshold
    chunks = _chunk_transcript(long_transcript, chunk_chars=60_000)

    assert len(chunks) > 1
    # No content lost across the split.
    assert sum(len(c.split(" ")) for c in chunks) == len(long_transcript.split(" "))


@pytest.mark.asyncio
async def test_long_transcript_chunks_then_combines(monkeypatch):
    import jarvis.tools.lecture_notes as ln

    # _chunk_transcript's chunk_chars default is bound at function-definition
    # time, so monkeypatching the _CHUNK_CHARS module constant afterward
    # wouldn't affect it -- patch the chunking function itself instead to
    # force the multi-chunk path build_lecture_notes takes for it.
    monkeypatch.setattr(ln, "_chunk_transcript", lambda transcript: ["part one.", "part two.", "part three."])
    engine = _FakeEngine()

    notes = await build_lecture_notes(engine, "irrelevant, chunking is mocked")

    # One call per chunk-summary, plus one final combine call.
    assert len(engine.calls) == 4
    assert "notes for" in notes
