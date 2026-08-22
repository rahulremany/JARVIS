"""Ported from src/tools/DeviceActions.ts."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

from ..utils.logging import logger

DeviceType = Literal["lights", "thermostat", "music", "security", "general"]


@dataclass
class DeviceCommand:
    type: DeviceType
    action: str
    parameters: Optional[dict[str, Any]] = field(default=None)


class DeviceActions:
    async def execute_command(self, command: DeviceCommand) -> str:
        logger.info("Executing device command:", command)

        handlers = {
            "lights": self._handle_lights,
            "thermostat": self._handle_thermostat,
            "music": self._handle_music,
            "security": self._handle_security,
        }
        handler = handlers.get(command.type, self._handle_general)
        return handler(command)

    def _handle_lights(self, command: DeviceCommand) -> str:
        action, params = command.action.lower(), command.parameters or {}
        room = f" in {params['room']}" if params.get("room") else ""

        if action in ("turn_on", "on"):
            return f"Turning on lights{room}"
        if action in ("turn_off", "off"):
            return f"Turning off lights{room}"
        if action == "dim":
            return f"Dimming lights to {params.get('level', 50)}%{room}"
        if action == "brighten":
            return f"Brightening lights{room}"
        return f"Unknown light command: {command.action}"

    def _handle_thermostat(self, command: DeviceCommand) -> str:
        action, params = command.action.lower(), command.parameters or {}

        if action == "set_temperature":
            return f"Setting temperature to {params.get('temperature', 72)}°F"
        if action == "raise_temperature":
            return "Raising temperature by 2 degrees"
        if action == "lower_temperature":
            return "Lowering temperature by 2 degrees"
        if action == "set_mode":
            return f"Setting thermostat mode to {params.get('mode', 'auto')}"
        return f"Unknown thermostat command: {command.action}"

    def _handle_music(self, command: DeviceCommand) -> str:
        action, params = command.action.lower(), command.parameters or {}

        return {
            "play": f"Playing {params.get('song', 'music')}",
            "pause": "Pausing music",
            "stop": "Stopping music",
            "volume_up": "Turning volume up",
            "volume_down": "Turning volume down",
            "next": "Skipping to next track",
            "previous": "Going to previous track",
        }.get(action, f"Unknown music command: {command.action}")

    def _handle_security(self, command: DeviceCommand) -> str:
        action = command.action.lower()
        return {
            "arm": "Arming security system",
            "disarm": "Disarming security system",
            "lock_doors": "Locking all doors",
            "unlock_doors": "Unlocking doors",
            "check_status": "Security system is armed and all sensors are normal",
        }.get(action, f"Unknown security command: {command.action}")

    def _handle_general(self, command: DeviceCommand) -> str:
        suffix = f" with parameters: {command.parameters}" if command.parameters else ""
        return f"Executing {command.action}{suffix}"

    def parse_command(self, text: str) -> Optional[DeviceCommand]:
        lower = text.lower()

        if "light" in lower or "lamp" in lower:
            if "turn on" in lower or "switch on" in lower:
                return DeviceCommand("lights", "turn_on")
            if "turn off" in lower or "switch off" in lower:
                return DeviceCommand("lights", "turn_off")
            if "dim" in lower:
                return DeviceCommand("lights", "dim")
            if "brighten" in lower or "bright" in lower:
                return DeviceCommand("lights", "brighten")

        if any(w in lower for w in ("temperature", "thermostat", "heat", "cool")):
            if "set" in lower and re.search(r"\d+", lower):
                temp = re.search(r"\d+", lower)
                return DeviceCommand("thermostat", "set_temperature", {"temperature": int(temp.group())})
            if any(w in lower for w in ("raise", "up", "warmer")):
                return DeviceCommand("thermostat", "raise_temperature")
            if any(w in lower for w in ("lower", "down", "cooler")):
                return DeviceCommand("thermostat", "lower_temperature")

        if any(w in lower for w in ("music", "song", "play", "spotify")):
            if "play" in lower:
                return DeviceCommand("music", "play")
            if "pause" in lower:
                return DeviceCommand("music", "pause")
            if "stop" in lower:
                return DeviceCommand("music", "stop")
            if "volume up" in lower or "louder" in lower:
                return DeviceCommand("music", "volume_up")
            if "volume down" in lower or "quieter" in lower:
                return DeviceCommand("music", "volume_down")

        if any(w in lower for w in ("lock", "unlock", "security", "alarm")):
            if "lock" in lower:
                return DeviceCommand("security", "lock_doors")
            if "unlock" in lower:
                return DeviceCommand("security", "unlock_doors")
            if "arm" in lower:
                return DeviceCommand("security", "arm")
            if "disarm" in lower:
                return DeviceCommand("security", "disarm")

        return None

    async def execute_direct_command(self, text: str) -> dict[str, Any]:
        command = self.parse_command(text)
        if not command:
            return {"success": False, "message": "Command not recognized", "action": "unknown", "device": "unknown"}

        message = await self.execute_command(command)
        return {"success": True, "message": message, "action": command.action, "device": command.type}
