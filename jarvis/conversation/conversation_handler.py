"""Ported from src/conversation/ConversationHandler.ts."""
from __future__ import annotations

import asyncio
import hashlib
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

from ..engines.claude.claude_engine import ClaudeEngine, GenerationParams
from ..session.session_manager import SessionManager
from ..tools.agent_tools import AgentToolRegistry
from ..tools.tool_executor import ToolCall, ToolExecutor, ToolResult
from ..utils.logging import logger

# Default model for the direct text-chat path (/chat/test), which bypasses
# Router.classify -- everyday conversational quality without per-request
# difficulty routing.
DEFAULT_CHAT_MODEL = "claude-sonnet-5"

# Persona distilled from script.md (the project's reference interaction
# scripts) -- a collaborator with presence, not a chatbot: dry, competent,
# a little wry. Update script.md and this prompt together if the tone drifts.
CHAT_SYSTEM_PROMPT = (
    "You are JARVIS -- a dry, competent, quietly confident engineering collaborator, not a chatbot. "
    "Address the user as \"sir\". Never reference Tony Stark, Iron Man, or Marvel.\n\n"
    "You have tools to actually act on this computer and the user's accounts -- open apps, search "
    "the web live, switch/read browser tabs, read what's on screen, manage their Google Calendar, "
    "check Canvas assignments/grades, and manage Apple Reminders. Use them for real instead of "
    "describing what you'd do -- the actions themselves happen visibly on screen as you do them.\n\n"
    "How you operate:\n"
    "1. Go quiet while working. One brief acknowledgment before diving in (\"Yes sir, let me see and "
    "I'll get back to you\"), then do the work without narrating each step -- no \"checking file 1 of "
    "12...\". Report when there's something to report, not before.\n"
    "2. If a request is ambiguous, ask exactly one sharp clarifying question, not an interview.\n"
    "3. Lead every report with the headline result first, then the one or two things that actually "
    "matter. Exhaustive detail only if asked.\n"
    "4. Notice things worth flagging even unasked, but don't act on them without permission -- report "
    "it, then stop and wait.\n"
    "5. Before anything irreversible or that affects other people (force-push, deploy, delete), state "
    "the risk in one sentence and wait for the go-ahead.\n"
    "6. Own mistakes in one breath -- what broke, why, what you're doing about it. No over-apologizing, "
    "no defensiveness.\n"
    "7. If interrupted mid-task, confirm nothing was left broken and hand back a precise resume point "
    "when you return to it.\n"
    "8. Disagree when warranted, with a concrete reason and an alternative -- then defer once the user "
    "decides.\n"
    "9. Keep responses tight. Personality lives in word choice and timing, not extra text."
)


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


async def _run(cmd: str) -> None:
    proc = await asyncio.create_subprocess_shell(cmd)
    await proc.wait()


@dataclass
class ConversationConfig:
    eleven_labs_api_key: Optional[str] = None
    eleven_labs_voice_id: Optional[str] = None
    eleven_model_id: str = "eleven_flash_v2_5"
    enable_tts: bool = True
    enable_tools: bool = True
    tts_mode: str = "auto"  # auto | eleven | macos


class ConversationHandler:
    def __init__(self, config: Optional[ConversationConfig] = None, session_manager: Optional[SessionManager] = None) -> None:
        self.config = config or ConversationConfig()
        # Without this, every handle_text_input call built a single-message
        # `[{"role": "user", "content": text}]` conversation -- JARVIS had
        # zero memory of anything said earlier in the same session, even
        # seconds ago (e.g. "I changed that setting, try again" meant
        # nothing without the prior turn that explained what "that" was).
        self.session_manager = session_manager or SessionManager()
        self.config.eleven_labs_api_key = self.config.eleven_labs_api_key or os.environ.get("ELEVEN_API_KEY")
        self.config.eleven_labs_voice_id = self.config.eleven_labs_voice_id or os.environ.get("JARVIS_VOICE_ID", "LE42bqYwZicKpZRastCO")
        self.config.eleven_model_id = os.environ.get("ELEVEN_MODEL_ID", self.config.eleven_model_id)
        self.config.tts_mode = os.environ.get("JARVIS_TTS_MODE", self.config.tts_mode).strip().lower() or "auto"
        self.tool_executor = ToolExecutor()
        self.agent_tools = AgentToolRegistry()
        self._is_speaking = False
        # Narration and a final report can both want to speak in close
        # succession -- this serializes actual playback so the second one
        # queues instead of silently dropping (the old `if _is_speaking:
        # return` guard would just discard whichever call lost the race,
        # which is why TTS looked like it "wasn't working").
        self._speak_lock = asyncio.Lock()
        self._tts_cache_dir = Path(os.environ.get("JARVIS_TTS_CACHE_DIR", "/tmp/jarvis_tts_cache"))
        self._tts_cache_dir.mkdir(parents=True, exist_ok=True)

        if self.config.enable_tts and not self.config.eleven_labs_api_key:
            logger.warn("TTS enabled but ELEVEN_API_KEY not set - will use macOS say command as fallback")

    async def handle_text_input(self, text: str, llm_engine: ClaudeEngine, session_id: str = "default") -> str:
        # ConversationHandler owns session history end-to-end -- append the
        # user turn here (not in the caller) so every path below reads/writes
        # the same session_manager instance and nothing double-appends.
        self.session_manager.append_user(session_id, text)

        try:
            direct_tool = self._detect_direct_tool_call(text)

            if direct_tool:
                logger.info(f"Direct tool detected: {direct_tool.action}")

                if self.config.enable_tts:
                    feedback = self._get_tool_feedback_message(direct_tool)
                    if feedback:
                        asyncio.create_task(self.process_and_speak(feedback, "system"))

                tool_result = await self.tool_executor.execute(direct_tool)
                final_response = await self._generate_tool_result_response(text, tool_result, llm_engine, session_id)
                await self.process_and_speak(final_response, session_id)
                self.session_manager.append_assistant(session_id, final_response)
                return final_response

            response = ""
            params = GenerationParams(max_tokens=1024, temperature=0.7)
            history = self.session_manager.get_messages(session_id)
            messages = [{"role": m.role, "content": m.content} for m in history if m.role in ("user", "assistant")]
            async for event in llm_engine.generate_stream_with_tools(
                session_id, messages, params, DEFAULT_CHAT_MODEL, system=CHAT_SYSTEM_PROMPT,
                tools=self.agent_tools.tool_schemas(), tool_runner=self.agent_tools.invoke,
            ):
                if event.type == "narration" and event.text:
                    # Speak it live and let the tool call underneath keep
                    # running -- don't block on TTS finishing before the
                    # actual action starts (see feedback_visible_progress).
                    asyncio.create_task(self.process_and_speak(event.text, session_id))
                elif event.type == "token" and event.text:
                    response += event.text

            response = response.strip()
            await self.process_and_speak(response, session_id)
            self.session_manager.append_assistant(session_id, response)
            return response
        except Exception as error:  # noqa: BLE001
            logger.error("Conversation error:", error)
            error_message = "I apologize, I encountered an error."
            await self.process_and_speak(error_message, session_id)
            self.session_manager.append_assistant(session_id, error_message)
            return error_message

    def _detect_direct_tool_call(self, text: str) -> Optional[ToolCall]:
        lower = text.lower()

        if ("time" in lower or "clock" in lower) and ("what" in lower or "current" in lower):
            return ToolCall("get_time", {})

        if "screen" in lower and any(w in lower for w in ("what", "on", "see")):
            return ToolCall("read_screen", {})

        if any(w in lower for w in ("search", "google", "look up")):
            match = re.search(r"(?:search|google|look up)\s+(?:for\s+)?(.+)", text, re.IGNORECASE)
            if match:
                return ToolCall("web_search_and_open", {"query": match.group(1)})

        if "open" in lower and "search" not in lower:
            match = re.search(r"open\s+(?:the|a|an)?\s*(\w+)", text, re.IGNORECASE)
            if match:
                return ToolCall("open_app", {"name": match.group(1)})

        if "click" in lower:
            match = re.search(r"click\s+(?:on\s+)?(.+)", text, re.IGNORECASE)
            if match:
                return ToolCall("click_element", {"target": match.group(1)})

        if "type" in lower and ("in" in lower or "into" in lower):
            match = re.search(r"type\s+(.+?)\s+(?:in|into)\s+(.+)", text, re.IGNORECASE)
            if match:
                return ToolCall("type_in_field", {"text": match.group(1), "field": match.group(2)})

        if "type" in lower:
            match = re.search(r"type\s+(.+)", text, re.IGNORECASE)
            if match:
                return ToolCall("type_text", {"text": match.group(1)})

        if "scroll" in lower:
            direction = "down" if "down" in lower else "up" if "up" in lower else "down"
            return ToolCall("scroll", {"direction": direction})

        if "press" in lower:
            match = re.search(r"press\s+(.+)", text, re.IGNORECASE)
            if match:
                keys = re.split(r"\s+(?:and|plus|\+)\s+", match.group(1))
                return ToolCall("press_keys", {"keys": keys})

        if "open" in lower and "and" in lower and "type" in lower:
            match = re.search(r"open\s+(?:the|a|an)?\s*(\w+)\s+and\s+type\s+(.+)", text, re.IGNORECASE)
            if match:
                return ToolCall("open_and_type", {"app": match.group(1), "text": match.group(2)})

        return None

    def _get_tool_feedback_message(self, call: ToolCall) -> Optional[str]:
        messages = {
            "open_app": f"One moment sir, opening {call.params.get('name')}",
            "read_screen": "One moment sir, analyzing your screen",
            "web_search_and_open": "One moment sir, opening browser and searching",
            "click_element": f"One moment sir, clicking on {call.params.get('target')}",
            "type_in_field": f"One moment sir, typing in {call.params.get('field')}",
            "type_text": "One moment sir, typing text",
            "open_and_type": f"One moment sir, opening {call.params.get('app')} and typing text",
        }
        return messages.get(call.action)

    async def _generate_tool_result_response(
        self, original_query: str, tool_result: ToolResult, engine: ClaudeEngine, session_id: str
    ) -> str:
        if not tool_result.success:
            return f"I apologize, but I wasn't able to {tool_result.action.replace('_', ' ')}. {tool_result.error or 'Please try again.'}"

        if tool_result.action in ("get_time", "calculate"):
            return tool_result.output

        prompt = (
            f'The user asked: "{original_query}"\n'
            f"I executed the action and got this result: {tool_result.output}\n\n"
            "Respond naturally as JARVIS, confirming what was done. Keep it brief:"
        )

        try:
            response = ""
            params = GenerationParams(max_tokens=50, temperature=0.7)
            messages = [{"role": "user", "content": prompt}]
            async for event in engine.generate_stream(session_id + "_tool", messages, params, DEFAULT_CHAT_MODEL, system=CHAT_SYSTEM_PROMPT):
                if event.type == "token" and event.text:
                    response += event.text
            return response.strip()
        except Exception:  # noqa: BLE001
            return f"Done. {tool_result.output}"

    async def process_and_speak(self, response: str, session_id: str) -> None:
        if not self.config.enable_tts:
            logger.info(f'JARVIS says: "{response}"')
            return

        spoken_text = self._clean_for_speech(response)
        if not spoken_text:
            return

        use_eleven = self.config.tts_mode == "eleven" or (
            self.config.tts_mode == "auto" and bool(self.config.eleven_labs_api_key)
        )

        async with self._speak_lock:
            await self._notify_frontend_speaking(True)
            try:
                if use_eleven and self.config.eleven_labs_api_key:
                    await self._speak_with_eleven_labs(spoken_text)
                else:
                    await self._speak_with_macos(spoken_text)
            finally:
                await self._notify_frontend_speaking(False)

    async def _notify_frontend_speaking(self, active: bool) -> None:
        """Tells the Electron app's local wake-listener (see
        frontend/main.js's /speaking route) that real TTS playback is
        starting/stopping, so the particle field can react live -- this
        audio plays server-side (afplay/say), so the renderer has no other
        way to know. Fire-and-forget: the desktop app may not be running
        (e.g. /chat/test hit directly), and that's fine."""
        wake_port = os.environ.get("JARVIS_WAKE_PORT", "3131")
        try:
            async with httpx.AsyncClient(timeout=0.5) as client:
                await client.post(f"http://127.0.0.1:{wake_port}/speaking", json={"active": active})
        except httpx.HTTPError:
            pass

    def _clean_for_speech(self, text: str) -> str:
        text = re.sub(r"<\|.*?\|>", "", text)
        text = text.replace("|im_end|", "").replace("|im_start|", "").replace("assistant", "")
        text = re.sub(r"[*_~`]", "", text)
        text = re.sub(r"```[\s\S]*?```", "code block", text)
        text = re.sub(r"https?://\S+", "link", text)
        return re.sub(r"\s+", " ", text).strip()

    async def _synth_eleven_sentence(self, sentence: str) -> Optional[Path]:
        """Synthesizes one sentence to a cached mp3 file, or returns the
        cache hit. Split out of _speak_with_eleven_labs so sentences can be
        synthesized concurrently with the previous one's playback."""
        cache_key = hashlib.sha256(
            f"{self.config.eleven_labs_voice_id}|{self.config.eleven_model_id}|{sentence}".encode("utf-8")
        ).hexdigest()
        cache_file = self._tts_cache_dir / f"{cache_key}.mp3"
        if cache_file.exists():
            return cache_file

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.config.eleven_labs_voice_id}"
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(
                    url,
                    headers={
                        "Accept": "audio/mpeg",
                        "Content-Type": "application/json",
                        "xi-api-key": self.config.eleven_labs_api_key,
                    },
                    json={
                        "text": sentence,
                        "model_id": self.config.eleven_model_id,
                        "voice_settings": {
                            "stability": 0.6,
                            "similarity_boost": 1.0,
                            "style": 0.0,
                            "use_speaker_boost": True,
                        },
                    },
                )
            if response.status_code != 200:
                raise RuntimeError(f"ElevenLabs API error: {response.status_code}")
            cache_file.write_bytes(response.content)
            return cache_file
        except Exception as error:  # noqa: BLE001
            logger.error("ElevenLabs TTS error:", error)
            return None

    async def _speak_with_eleven_labs(self, text: str) -> None:
        self._is_speaking = True
        try:
            # Sentence-level pipelining: synthesize the next sentence while
            # the current one plays, instead of waiting for the entire
            # response to finish synthesizing before any audio starts. For
            # the multi-sentence reports script.md's persona calls for, this
            # is most of the difference between "snappy" and "slow and janky".
            sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()] or [text]

            next_task = asyncio.ensure_future(self._synth_eleven_sentence(sentences[0]))
            for i in range(len(sentences)):
                audio_file = await next_task
                if i + 1 < len(sentences):
                    next_task = asyncio.ensure_future(self._synth_eleven_sentence(sentences[i + 1]))
                if audio_file:
                    await _run(f'afplay -v 2 "{audio_file}"')
            logger.info("TTS playback complete")
        finally:
            self._is_speaking = False

    async def _speak_with_macos(self, text: str) -> None:
        self._is_speaking = True
        try:
            escaped = text.replace('"', '\\"')
            await _run(f'say -v Daniel "{escaped}"')
            logger.info("macOS TTS playback complete")
        except Exception as error:  # noqa: BLE001
            logger.error("macOS say command failed:", error)
        finally:
            self._is_speaking = False

    async def stop_speaking(self) -> None:
        if self._is_speaking:
            try:
                await _run("pkill -f afplay || true")
                await _run("pkill -f say || true")
                self._is_speaking = False
            except Exception as error:  # noqa: BLE001
                logger.error("Error stopping speech:", error)
