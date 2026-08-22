"""Ported from src/conversation/ConversationHandler.ts."""
from __future__ import annotations

import asyncio
import os
import re
import time
from dataclasses import dataclass
from typing import Optional

import httpx

from ..engines.local.local_llama_engine import GenerationParams, LocalLlamaEngine
from ..tools.tool_executor import ToolCall, ToolExecutor, ToolResult
from ..utils.logging import logger


async def _run(cmd: str) -> None:
    proc = await asyncio.create_subprocess_shell(cmd)
    await proc.wait()


@dataclass
class ConversationConfig:
    eleven_labs_api_key: Optional[str] = None
    eleven_labs_voice_id: Optional[str] = None
    enable_tts: bool = True
    enable_tools: bool = True


class ConversationHandler:
    def __init__(self, config: Optional[ConversationConfig] = None) -> None:
        self.config = config or ConversationConfig()
        self.config.eleven_labs_api_key = self.config.eleven_labs_api_key or os.environ.get("ELEVEN_API_KEY")
        self.config.eleven_labs_voice_id = self.config.eleven_labs_voice_id or os.environ.get("JARVIS_VOICE_ID", "LE42bqYwZicKpZRastCO")
        self.tool_executor = ToolExecutor()
        self._is_speaking = False

        if self.config.enable_tts and not self.config.eleven_labs_api_key:
            logger.warn("TTS enabled but ELEVEN_API_KEY not set - will use macOS say command as fallback")

    async def handle_text_input(self, text: str, llm_engine: LocalLlamaEngine, session_id: str = "default") -> str:
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
                return final_response

            prompt = (
                "You are JARVIS, a helpful AI assistant. You are concise and professional.\n"
                "Never reference Tony Stark, Iron Man, or Marvel. Keep responses brief and natural.\n\n"
                f"User: {text}\nJARVIS:"
            )

            response = ""
            async for event in llm_engine.generate_stream(session_id, prompt, GenerationParams(max_tokens=150, temperature=0.7)):
                if event.type == "token" and event.text:
                    response += event.text

            response = response.strip()
            await self.process_and_speak(response, session_id)
            return response
        except Exception as error:  # noqa: BLE001
            logger.error("Conversation error:", error)
            error_message = "I apologize, I encountered an error."
            await self.process_and_speak(error_message, session_id)
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
            match = re.search(r"open\s+(\w+)", text, re.IGNORECASE)
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
            match = re.search(r"open\s+(\w+)\s+and\s+type\s+(.+)", text, re.IGNORECASE)
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
        self, original_query: str, tool_result: ToolResult, engine: LocalLlamaEngine, session_id: str
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
            async for event in engine.generate_stream(session_id + "_tool", prompt, GenerationParams(max_tokens=50, temperature=0.7)):
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

        if self.config.eleven_labs_api_key:
            await self._speak_with_eleven_labs(spoken_text)
        else:
            await self._speak_with_macos(spoken_text)

    def _clean_for_speech(self, text: str) -> str:
        text = re.sub(r"<\|.*?\|>", "", text)
        text = text.replace("|im_end|", "").replace("|im_start|", "").replace("assistant", "")
        text = re.sub(r"[*_~`]", "", text)
        text = re.sub(r"```[\s\S]*?```", "code block", text)
        text = re.sub(r"https?://\S+", "link", text)
        return re.sub(r"\s+", " ", text).strip()

    async def _speak_with_eleven_labs(self, text: str) -> None:
        if self._is_speaking:
            logger.warn("Already speaking, skipping...")
            return

        self._is_speaking = True
        try:
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.config.eleven_labs_voice_id}"
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    url,
                    headers={"Accept": "audio/mpeg", "Content-Type": "application/json", "xi-api-key": self.config.eleven_labs_api_key},
                    json={
                        "text": text, "model_id": "eleven_monolingual_v1",
                        "voice_settings": {"stability": 0.6, "similarity_boost": 1.0, "style": 0.0, "use_speaker_boost": True},
                    },
                )
            if response.status_code != 200:
                raise RuntimeError(f"ElevenLabs API error: {response.status_code}")

            temp_file = f"/tmp/jarvis_{int(time.time() * 1000)}.mp3"
            with open(temp_file, "wb") as f:
                f.write(response.content)

            await _run(f'afplay -v 2 "{temp_file}"')
            os.remove(temp_file)
            logger.info("TTS playback complete")
        except Exception as error:  # noqa: BLE001
            logger.error("ElevenLabs TTS error:", error)
            logger.error("TTS failed - check your ELEVEN_API_KEY")
        finally:
            self._is_speaking = False

    async def _speak_with_macos(self, text: str) -> None:
        if self._is_speaking:
            return
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
