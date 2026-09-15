"""Regression tests for the TTS bugs found 2026-09-14:

1. process_and_speak used to guard with `if self._is_speaking: return`,
   silently DROPPING a speech request if another was already playing --
   e.g. the final report would just never get spoken if narration for the
   same turn was still mid-playback. Fixed with an asyncio.Lock that queues
   instead of dropping.
2. _speak_with_eleven_labs synthesized the entire response as one blocking
   HTTP call before any audio played -- slow for the multi-sentence reports
   script.md's persona produces. Fixed with sentence-level pipelining
   (synthesize sentence N+1 while sentence N plays).

Both are tested against _run (the subprocess `afplay`/`say` runner) and
ElevenLabs synthesis, mocked -- no real audio, no network, no API cost.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from jarvis.conversation import conversation_handler as ch_module
from jarvis.conversation.conversation_handler import ConversationConfig, ConversationHandler


@pytest.mark.asyncio
async def test_process_and_speak_queues_instead_of_dropping(monkeypatch, tmp_path):
    handler = ConversationHandler(config=ConversationConfig(enable_tts=True, tts_mode="macos"))
    handler._tts_cache_dir = tmp_path

    spoken: list[str] = []

    async def fake_run(cmd: str) -> None:
        spoken.append(cmd)
        await asyncio.sleep(0.05)  # simulate playback taking a moment

    async def fake_notify(active: bool) -> None:
        return None

    monkeypatch.setattr(ch_module, "_run", fake_run)
    monkeypatch.setattr(handler, "_notify_frontend_speaking", fake_notify)

    # Two speech requests fired back-to-back, like narration + the final
    # report -- both must actually play, none silently skipped.
    await asyncio.gather(
        handler.process_and_speak("First thing JARVIS says.", "s1"),
        handler.process_and_speak("Second thing JARVIS says.", "s1"),
    )

    assert len(spoken) == 2


@pytest.mark.asyncio
async def test_eleven_labs_pipelines_sentence_synthesis(monkeypatch, tmp_path):
    handler = ConversationHandler(
        config=ConversationConfig(enable_tts=True, tts_mode="eleven", eleven_labs_api_key="fake-key"),
    )
    handler._tts_cache_dir = tmp_path

    synth_calls: list[str] = []
    play_calls: list[str] = []

    async def fake_synth(sentence: str) -> Path:
        synth_calls.append(sentence)
        await asyncio.sleep(0.02)
        fake_file = tmp_path / f"{len(synth_calls)}.mp3"
        fake_file.write_bytes(b"fake-audio")
        return fake_file

    async def fake_run(cmd: str) -> None:
        play_calls.append(cmd)
        await asyncio.sleep(0.02)

    async def fake_notify(active: bool) -> None:
        return None

    monkeypatch.setattr(handler, "_synth_eleven_sentence", fake_synth)
    monkeypatch.setattr(ch_module, "_run", fake_run)
    monkeypatch.setattr(handler, "_notify_frontend_speaking", fake_notify)

    await handler.process_and_speak("First sentence. Second sentence. Third sentence.", "s1")

    assert len(synth_calls) == 3
    assert len(play_calls) == 3
    # Sentence punctuation preserved, filler stripped by _clean_for_speech.
    assert synth_calls[0].startswith("First sentence")
