"""Apple Reminders adapter, Phase 2.

Drives the local Reminders.app via AppleScript/osascript -- same automation
pattern jarvis/tools/tool_executor.py already uses for screen/keyboard
control. No OAuth, no API key: this is local-machine automation, so it just
needs Reminders access granted to Terminal/JARVIS in System Settings ->
Privacy & Security -> Reminders the first time it runs.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

from ..utils.logging import logger

DEFAULT_LIST = "JARVIS"


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


async def _run_osascript(script: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        "osascript", "-e", script,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(stderr.decode().strip() or "osascript failed")
    return stdout.decode().strip()


class RemindersAdapter:
    def __init__(self, default_list: str = DEFAULT_LIST) -> None:
        self.default_list = default_list

    async def _ensure_list(self, list_name: str) -> None:
        script = f'''
            tell application "Reminders"
                if not (exists list "{_escape(list_name)}") then
                    make new list with properties {{name:"{_escape(list_name)}"}}
                end if
            end tell
        '''
        await _run_osascript(script)

    async def add_reminder(
        self,
        title: str,
        due_date_iso: str = "",
        notes: str = "",
        list_name: str = "",
    ) -> dict[str, Any]:
        target_list = list_name.strip() or self.default_list
        await self._ensure_list(target_list)

        props = [f'name:"{_escape(title)}"']
        if notes:
            props.append(f'body:"{_escape(notes)}"')
        if due_date_iso:
            props.append(f'due date:(my _isoToDate("{_escape(due_date_iso)}"))')

        script = f'''
            on _isoToDate(isoString)
                set {{year:y, month:m, day:d}} to my _parseIso(isoString)
                set targetDate to current date
                set year of targetDate to y
                set month of targetDate to m
                set day of targetDate to d
                set time of targetDate to 0
                return targetDate
            end _isoToDate

            on _parseIso(isoString)
                set y to (text 1 thru 4 of isoString) as integer
                set m to (text 6 thru 7 of isoString) as integer
                set d to (text 9 thru 10 of isoString) as integer
                return {{year:y, month:m, day:d}}
            end _parseIso

            tell application "Reminders"
                tell list "{_escape(target_list)}"
                    set newReminder to make new reminder with properties {{{", ".join(props)}}}
                    return id of newReminder
                end tell
            end tell
        '''
        try:
            reminder_id = await _run_osascript(script)
        except RuntimeError as error:  # noqa: BLE001
            logger.error("Failed to create reminder:", error)
            raise

        return {"id": reminder_id, "title": title, "list": target_list, "due_date": due_date_iso}

    async def list_reminders(self, list_name: str = "", include_completed: bool = False) -> dict[str, Any]:
        target_list = list_name.strip() or self.default_list
        completed_filter = "" if include_completed else "whose completed is false"
        script = f'''
            tell application "Reminders"
                if not (exists list "{_escape(target_list)}") then
                    return "[]"
                end if
                set output to "["
                set isFirst to true
                repeat with r in (reminders of list "{_escape(target_list)}" {completed_filter})
                    if not isFirst then set output to output & ","
                    set isFirst to false
                    set dueText to ""
                    try
                        set dueText to (due date of r) as string
                    end try
                    set output to output & "{{\\"id\\":\\"" & (id of r) & "\\",\\"title\\":\\"" & (my _jsonEscape(name of r)) & "\\",\\"due_date\\":\\"" & dueText & "\\",\\"completed\\":" & (completed of r) & "}}"
                end repeat
                set output to output & "]"
                return output
            end tell

            on _jsonEscape(t)
                set AppleScript's text item delimiters to "\\""
                set parts to text items of t
                set AppleScript's text item delimiters to "\\\\\\""
                set t to parts as string
                set AppleScript's text item delimiters to ""
                return t
            end _jsonEscape
        '''
        raw = await _run_osascript(script)
        try:
            items = json.loads(raw) if raw else []
        except json.JSONDecodeError:
            items = []
        return {"list": target_list, "count": len(items), "reminders": items}

    async def complete_reminder(self, reminder_id: str, list_name: str = "") -> dict[str, Any]:
        target_list = list_name.strip() or self.default_list
        script = f'''
            tell application "Reminders"
                tell list "{_escape(target_list)}"
                    set r to (first reminder whose id is "{_escape(reminder_id)}")
                    set completed of r to true
                end tell
            end tell
        '''
        await _run_osascript(script)
        return {"id": reminder_id, "completed": True}
