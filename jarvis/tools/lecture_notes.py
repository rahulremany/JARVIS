"""Lecture/meeting transcription mode, Phase 3.

Turns a raw Whisper transcript of a class or meeting into organized study
notes with a single batched Claude call -- deliberately NOT a running
"update the notes every few minutes" loop. Streaming updates would mean
re-sending the growing transcript-so-far context on every single call over
an hour-plus recording; one call at the end pays for the transcript's
tokens exactly once. See jarvis/conversation/conversation_handler.py's
prompt-caching notes for the same reasoning applied elsewhere.
"""
from __future__ import annotations

from typing import Optional

from ..engines.claude.claude_engine import ClaudeEngine, GenerationParams

# Comfortably under any current Claude context window even with the prompt
# and output budget included, but big enough that a normal 60-90 minute
# lecture transcript (usually 8-15k words / ~50-80k characters) needs at
# most a couple of chunks, not dozens.
_CHUNK_CHARS = 60_000

NOTES_SYSTEM_PROMPT = (
    "You are JARVIS, reformatting a raw speech-to-text lecture/meeting transcript into clean, "
    "organized study notes. The transcript will contain transcription errors, filler words, and "
    "run-on sentences -- clean those up. Produce markdown with:\n"
    "- A one-paragraph summary of what was covered\n"
    "- Organized sections with headers matching the actual topic structure of the talk (infer this "
    "from content and pacing, not just chronological order)\n"
    "- Key terms/definitions called out clearly\n"
    "- Any examples, formulas, or dates mentioned, preserved accurately\n"
    "- A short list of likely exam/review-worthy points at the end\n"
    "Do not invent content that wasn't said. If a section is garbled or inaudible-sounding, note that "
    "briefly rather than guessing."
)

_CHUNK_SUMMARY_PROMPT = (
    "This is one part of a longer lecture transcript (part {index} of {total}). Summarize the key "
    "points, terms, and examples from this part in dense markdown notes -- this will be combined with "
    "the other parts afterward, so don't add an overall introduction/conclusion, just the substance."
)

_COMBINE_PROMPT = (
    "Below are notes from consecutive parts of the same lecture, taken separately. Combine them into "
    "one coherent, well-organized set of study notes -- merge duplicate points, order by topic rather "
    "than by part, and follow the same structure (summary, sections, key terms, review points)."
)


def _chunk_transcript(transcript: str, chunk_chars: int = _CHUNK_CHARS) -> list[str]:
    words = transcript.split(" ")
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for word in words:
        current.append(word)
        current_len += len(word) + 1
        if current_len >= chunk_chars:
            chunks.append(" ".join(current))
            current = []
            current_len = 0
    if current:
        chunks.append(" ".join(current))
    return chunks or [transcript]


async def _generate(engine: ClaudeEngine, system: str, prompt: str, max_tokens: int) -> str:
    params = GenerationParams(max_tokens=max_tokens)
    messages = [{"role": "user", "content": prompt}]
    text = ""
    async for event in engine.generate_stream("lecture-notes", messages, params, "claude-sonnet-5", system=system):
        if event.type == "token" and event.text:
            text += event.text
    return text.strip()


async def build_lecture_notes(engine: ClaudeEngine, transcript: str, title: Optional[str] = None) -> str:
    """Batched (not streaming/incremental) transcript -> study notes. One
    Claude call for a normal-length lecture; chunk-then-combine only kicks
    in for unusually long transcripts."""
    transcript = transcript.strip()
    if not transcript:
        return "No speech was detected in this recording."

    heading = f"# {title}\n\n" if title else ""

    chunks = _chunk_transcript(transcript)
    if len(chunks) == 1:
        notes = await _generate(engine, NOTES_SYSTEM_PROMPT, transcript, max_tokens=4096)
        return heading + notes

    chunk_summaries = [
        await _generate(
            engine, NOTES_SYSTEM_PROMPT,
            _CHUNK_SUMMARY_PROMPT.format(index=i + 1, total=len(chunks)) + "\n\n" + chunk,
            max_tokens=2048,
        )
        for i, chunk in enumerate(chunks)
    ]
    combined_prompt = _COMBINE_PROMPT + "\n\n" + "\n\n---\n\n".join(chunk_summaries)
    notes = await _generate(engine, NOTES_SYSTEM_PROMPT, combined_prompt, max_tokens=4096)
    return heading + notes
