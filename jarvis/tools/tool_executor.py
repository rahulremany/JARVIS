"""Ported from src/tools/ToolExecutor.ts -- tier-2/tier-4 action layer:
direct macOS automation, plus vision-grounded fallback (screenshot + vision
model) for anything with no clean programmatic hook."""
from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from ..utils.logging import logger


@dataclass
class ToolCall:
    action: str
    params: dict[str, Any] = field(default_factory=dict)
    confidence: Optional[float] = None


@dataclass
class ToolResult:
    success: bool
    output: str
    action: str
    error: Optional[str] = None


async def _run(cmd: str) -> tuple[str, str]:
    proc = await asyncio.create_subprocess_shell(
        cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0 and not stdout:
        raise RuntimeError(stderr.decode().strip() or f"Command failed: {cmd}")
    return stdout.decode(), stderr.decode()


class ToolExecutor:
    SAFE_COMMANDS = {
        "ls", "pwd", "date", "whoami", "uptime", "df", "free",
        "ps", "top", "which", "echo", "cat", "head", "tail",
    }

    def parse_tool_call(self, text: str) -> Optional[ToolCall]:
        try:
            match = re.search(r'\{[^}]*"action"[^}]*\}', text)
            if match:
                data = json.loads(match.group())
                return ToolCall(action=data["action"], params=data.get("params", {}))
            return None
        except Exception as error:  # noqa: BLE001
            logger.error("Failed to parse tool call:", error)
            return None

    async def execute(self, call: ToolCall) -> ToolResult:
        handlers = {
            "get_time": self._get_current_time,
            "open_app": lambda: self._open_app(call.params["name"]),
            "type_text": lambda: self._type_text(call.params["text"]),
            "press_keys": lambda: self._press_keys(call.params["keys"]),
            "read_screen": self._read_screen,
            "run_shell": lambda: self._run_shell_command(call.params["command"]),
            "web_search": lambda: self._web_search(call.params["query"]),
            "web_search_and_open": lambda: self._web_search_and_open(call.params["query"]),
            "open_and_type": lambda: self._open_and_type(call.params["app"], call.params["text"]),
            "click_element": lambda: self._click_element(call.params["target"]),
            "type_in_field": lambda: self._type_in_field(call.params["text"], call.params["field"]),
            "scroll": lambda: self._scroll(call.params["direction"]),
        }

        handler = handlers.get(call.action)
        if not handler:
            return ToolResult(False, f"Unknown action: {call.action}", call.action, "Action not supported")

        try:
            result = handler()
            return await result if asyncio.iscoroutine(result) else result
        except Exception as error:  # noqa: BLE001
            logger.error(f"Tool execution error for {call.action}:", error)
            return ToolResult(False, f"Failed to execute {call.action}", call.action, str(error))

    def _get_current_time(self) -> ToolResult:
        now = time.strftime("%I:%M %p %Z, %A %B %d, %Y")
        return ToolResult(True, f"Current time: {now}", "get_time")

    async def _open_app(self, app_name: str) -> ToolResult:
        sanitized = re.sub(r"[^a-zA-Z0-9\s\-_]", "", app_name).strip()
        if not sanitized:
            return ToolResult(False, "Invalid app name provided", "open_app", "Empty or invalid app name")

        common = {
            "browser": "Safari", "chrome": "Google Chrome", "firefox": "Firefox",
            "safari": "Safari", "terminal": "Terminal", "finder": "Finder",
            "vscode": "Visual Studio Code", "code": "Visual Studio Code",
            "cursor": "Cursor", "notes": "Notes", "calculator": "Calculator", "mail": "Mail",
        }
        blocked = {"orion"}
        if sanitized.lower() in blocked:
            return ToolResult(
                False, f"{sanitized} blocks programmatic opening for security reasons. Please open it manually.",
                "open_app", "App blocks automation",
            )

        target = common.get(sanitized.lower(), sanitized)
        try:
            await _run(f'open -a "{target}"')
            return ToolResult(True, f"Opened {target}", "open_app")
        except Exception as error:  # noqa: BLE001
            return ToolResult(False, f"Failed to open {app_name}", "open_app", str(error))

    async def _type_text(self, text: str) -> ToolResult:
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        script = f'tell application "System Events" to keystroke "{escaped}"'
        try:
            await _run(f"osascript -e '{script}'")
            return ToolResult(True, f'Typed: "{text}"', "type_text")
        except Exception as error:  # noqa: BLE001
            return ToolResult(False, "Failed to type text", "type_text", str(error))

    async def _press_keys(self, keys: list[str]) -> ToolResult:
        mapping = {
            "cmd": "command", "ctrl": "control", "alt": "option",
            "enter": "return", "return": "return", "esc": "escape",
            "space": "space", "tab": "tab",
        }
        try:
            if len(keys) == 1:
                key = mapping.get(keys[0].lower(), keys[0])
                script = f'tell application "System Events" to keystroke "{key}"'
            else:
                mapped = [mapping.get(k.lower(), k) for k in keys]
                key_string = " down, ".join(mapped) + " down"
                script = f'tell application "System Events" to key down {{{key_string}}}'
            await _run(f"osascript -e '{script}'")
            return ToolResult(True, f"Pressed keys: {' + '.join(keys)}", "press_keys")
        except Exception as error:  # noqa: BLE001
            return ToolResult(False, "Failed to press keys", "press_keys", str(error))

    async def _read_screen(self) -> ToolResult:
        try:
            active_app, _ = await _run(
                'osascript -e \'tell application "System Events" to get name of first application process whose frontmost is true\''
            )
        except Exception:  # noqa: BLE001
            active_app = "unknown"

        try:
            window_title, _ = await _run(
                'osascript -e \'tell application "System Events" to get name of front window of first application process whose frontmost is true\''
            )
        except Exception:  # noqa: BLE001
            window_title = "No window title available"

        screenshot_path = f"/tmp/jarvis_screenshot_{int(time.time() * 1000)}.png"
        vision_description = ""

        try:
            await _run(f'screencapture -x "{screenshot_path}"')
            vision_description = await self._describe_screenshot(
                screenshot_path,
                "Analyze this screenshot and describe:\n"
                "1. What app is shown and what's visible on screen\n"
                "2. Any text content that's readable\n"
                "3. Clickable elements (buttons, links, text fields) and their approximate locations\n"
                "4. What actions the user might want to take\n\n"
                "Be specific about UI elements and their positions. Focus on actionable information.",
            )
        except Exception as error:  # noqa: BLE001
            logger.error("Screenshot failed:", error)
            vision_description = "Screenshot capture failed - please check screen recording permissions"
        finally:
            if os.path.exists(screenshot_path):
                os.remove(screenshot_path)

        output = "\n".join([f"Active app: {active_app.strip()}", f"Window: {window_title.strip()}", "", vision_description])
        return ToolResult(True, output, "read_screen")

    async def _describe_screenshot(self, path: str, prompt: str) -> str:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return "OpenAI API key not configured - set OPENAI_API_KEY environment variable to enable AI vision"

        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={
                        "model": "gpt-4o",
                        "messages": [{
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "high"}},
                            ],
                        }],
                        "max_tokens": 500,
                    },
                )
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"]
            raise RuntimeError(f"OpenAI API error: {response.status_code}")
        except Exception as error:  # noqa: BLE001
            logger.error("OpenAI Vision API failed:", error)
            return "AI Vision analysis failed - please check your OpenAI API key and connection"

    async def _run_shell_command(self, command: str) -> ToolResult:
        base_command = command.strip().split(" ")[0]
        if base_command not in self.SAFE_COMMANDS:
            return ToolResult(False, f"Command '{base_command}' is not in the safe commands list", "run_shell", "Command not allowed")
        try:
            stdout, stderr = await _run(command)
            return ToolResult(True, stdout or stderr or "Command executed successfully", "run_shell")
        except Exception as error:  # noqa: BLE001
            return ToolResult(False, f"Shell command failed: {command}", "run_shell", str(error))

    async def _web_search(self, query: str) -> ToolResult:
        url = f"https://www.google.com/search?q={query}"
        try:
            await _run(f'open "{url}"')
            return ToolResult(True, f"Opened web search for: {query}", "web_search")
        except Exception as error:  # noqa: BLE001
            return ToolResult(False, "Failed to perform web search", "web_search", str(error))

    async def _web_search_and_open(self, query: str) -> ToolResult:
        opened = await self._open_app("Safari")
        if not opened.success:
            return opened
        await asyncio.sleep(2)
        await self._press_keys(["cmd", "l"])
        await asyncio.sleep(0.5)
        url = f"https://www.google.com/search?q={query}"
        await self._type_text(url)
        await asyncio.sleep(0.5)
        await self._press_keys(["return"])
        return ToolResult(True, f'Opened Safari and searched for: "{query}"', "web_search_and_open")

    async def _open_and_type(self, app_name: str, text: str) -> ToolResult:
        opened = await self._open_app(app_name)
        if not opened.success:
            return opened
        await asyncio.sleep(2)
        typed = await self._type_text(text)
        return ToolResult(typed.success, f'{opened.output} and typed: "{text}"', "open_and_type")

    async def _click_element(self, target: str) -> ToolResult:
        screenshot_path = f"/tmp/jarvis_click_{int(time.time() * 1000)}.png"
        try:
            await _run(f'screencapture -x "{screenshot_path}"')
            api_key = os.environ.get("OPENAI_API_KEY")
            if api_key:
                with open(screenshot_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                async with httpx.AsyncClient(timeout=30) as client:
                    response = await client.post(
                        "https://api.openai.com/v1/chat/completions",
                        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                        json={
                            "model": "gpt-4o",
                            "messages": [{
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": f'Find the "{target}" element on this screen. Respond with ONLY the coordinates in this exact format: {{"x": 123, "y": 456}}. If you can\'t find it, respond with {{"error": "not found"}}.'},
                                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "high"}},
                                ],
                            }],
                            "max_tokens": 100,
                        },
                    )
                if response.status_code == 200:
                    content = response.json()["choices"][0]["message"]["content"]
                    try:
                        coords = json.loads(content)
                        if "error" not in coords:
                            await _run(f'osascript -e \'tell application "System Events" to click at {{{coords["x"]}, {coords["y"]}}}\'')
                            return ToolResult(True, f'Clicked on "{target}" at coordinates ({coords["x"]}, {coords["y"]})', "click_element")
                    except (json.JSONDecodeError, KeyError):
                        pass
            return await self._click_element_accessibility(target)
        except Exception as error:  # noqa: BLE001
            return ToolResult(False, f'Failed to click on "{target}"', "click_element", str(error))
        finally:
            if os.path.exists(screenshot_path):
                os.remove(screenshot_path)

    async def _click_element_accessibility(self, target: str) -> ToolResult:
        try:
            active_app, _ = await _run(
                'osascript -e \'tell application "System Events" to get name of first application process whose frontmost is true\''
            )
            script = f'''
                tell application "System Events"
                    tell process "{active_app.strip()}"
                        try
                            click button "{target}"
                            return "success"
                        on error
                            try
                                click (first button whose title contains "{target}")
                                return "success"
                            on error
                                return "not found"
                            end try
                        end try
                    end tell
                end tell
            '''
            stdout, _ = await _run(f"osascript -e '{script}'")
            if "success" in stdout:
                return ToolResult(True, f'Clicked on "{target}"', "click_element")
            return ToolResult(False, f'Could not find button "{target}"', "click_element", "Button not found")
        except Exception as error:  # noqa: BLE001
            return ToolResult(False, f'Failed to click "{target}"', "click_element", str(error))

    async def _type_in_field(self, text: str, field_name: str) -> ToolResult:
        clicked = await self._click_element(field_name)
        if not clicked.success:
            return ToolResult(False, f'Could not find field "{field_name}" to type in', "type_in_field", "Field not found")
        await asyncio.sleep(0.5)
        typed = await self._type_text(text)
        return ToolResult(typed.success, f'Typed "{text}" in field "{field_name}"', "type_in_field")

    async def _scroll(self, direction: str) -> ToolResult:
        amount = "-10" if direction == "up" else "10"
        script = f'tell application "System Events" to scroll (first window of first process whose frontmost is true) by {amount}'
        try:
            await _run(f"osascript -e '{script}'")
            return ToolResult(True, f"Scrolled {direction}", "scroll")
        except Exception as error:  # noqa: BLE001
            return ToolResult(False, f"Failed to scroll {direction}", "scroll", str(error))

    def needs_confirmation(self, call: ToolCall) -> bool:
        return call.action in {"run_shell", "delete_file", "modify_system"}
