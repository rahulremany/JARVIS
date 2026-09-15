from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from ..session.user_profile import UserProfileStore
from ..tools.canvas_adapter import CanvasAdapter
from ..tools.daily_briefing import DailyBriefingService
from ..tools.google_adapter import GoogleAdapter
from ..tools.life_os import LifeOSService
from ..tools.reminders_adapter import RemindersAdapter
from ..tools.tool_executor import ToolCall, ToolExecutor
from .workspace import WORKSPACE_ROOT, safe_path


_SEARCH_SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", ".pytest_cache",
    "dist", "build", ".mypy_cache", ".ruff_cache", ".jarvis_state",
}


class AgentToolRegistry:
    """In-process tool registry for Claude native tool-calling.

    Mirrors key MCP capabilities but without the stdio server dependency,
    so the live JARVIS chat path can be agentic directly.
    """

    def __init__(self) -> None:
        self.workspace_root = WORKSPACE_ROOT
        self.executor = ToolExecutor()
        self.life_os = LifeOSService(state_dir=self.workspace_root / ".jarvis_state")
        self.profile_store = UserProfileStore(state_dir=self.workspace_root / ".jarvis_state")
        self.google = GoogleAdapter()
        self.canvas = CanvasAdapter()
        self.reminders = RemindersAdapter()
        self.daily_briefing = DailyBriefingService(
            canvas=self.canvas, google=self.google, reminders=self.reminders, life_os=self.life_os,
        )

        projects_root = os.environ.get("JARVIS_PROJECTS_ROOT", str(Path.home() / "Desktop"))
        self.projects_root = Path(projects_root).expanduser().resolve()
        self.projects_root.mkdir(parents=True, exist_ok=True)

    def tool_schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "list_workspace",
                "description": "List files/folders inside the workspace.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "default": "."},
                        "max_entries": {"type": "integer", "default": 200},
                    },
                },
            },
            {
                "name": "read_workspace_file",
                "description": "Read a file with line range controls.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "start_line": {"type": "integer", "default": 1},
                        "end_line": {"type": "integer", "default": 200},
                    },
                    "required": ["path"],
                },
            },
            {
                "name": "write_workspace_file",
                "description": "Create or overwrite a file in workspace.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                        "overwrite": {"type": "boolean", "default": True},
                    },
                    "required": ["path", "content"],
                },
            },
            {
                "name": "edit_workspace_file",
                "description": "Surgical literal find/replace in a file.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "old_string": {"type": "string"},
                        "new_string": {"type": "string"},
                        "expected_replacements": {"type": "integer", "default": 1},
                    },
                    "required": ["path", "old_string", "new_string"],
                },
            },
            {
                "name": "create_workspace_directory",
                "description": "Create a directory inside workspace.",
                "input_schema": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
            {
                "name": "delete_workspace_file",
                "description": "Delete a single file inside workspace.",
                "input_schema": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
            {
                "name": "run_dev_command",
                "description": "Run development command (git/python/pytest/npm...) with safety checks.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"},
                        "cwd": {"type": "string", "default": "."},
                        "timeout_s": {"type": "number", "default": 120.0},
                    },
                    "required": ["command"],
                },
            },
            {
                "name": "search_workspace",
                "description": "Search file contents across workspace.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string"},
                        "path": {"type": "string", "default": "."},
                        "file_glob": {"type": "string", "default": "*"},
                        "is_regex": {"type": "boolean", "default": False},
                        "case_sensitive": {"type": "boolean", "default": False},
                        "max_results": {"type": "integer", "default": 200},
                    },
                    "required": ["pattern"],
                },
            },
            {
                "name": "code_review_file",
                "description": "Collect structural review context for one file.",
                "input_schema": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
            {
                "name": "project_create",
                "description": "Create an R&D project workspace entry.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "objective": {"type": "string"},
                        "constraints": {"type": "array", "items": {"type": "string"}},
                        "budget": {"type": "number"},
                        "deadline": {"type": "string"},
                    },
                    "required": ["name", "objective"],
                },
            },
            {
                "name": "create_desktop_project",
                "description": "Scaffold a basic runnable project on Desktop by default.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "description": {"type": "string", "default": ""},
                        "template": {
                            "type": "string",
                            "default": "python-basic",
                            "enum": ["python-basic", "web-basic"],
                        },
                        "target_dir": {
                            "type": "string",
                            "description": "Optional subdirectory under Desktop root; defaults to Desktop/<slugified-name>",
                        },
                    },
                    "required": ["name"],
                },
            },
            {
                "name": "project_list",
                "description": "List R&D projects.",
                "input_schema": {
                    "type": "object",
                    "properties": {"status": {"type": "string"}},
                },
            },
            {
                "name": "project_add_note",
                "description": "Append note to project timeline.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "string"},
                        "text": {"type": "string"},
                    },
                    "required": ["project_id", "text"],
                },
            },
            {
                "name": "profile_get",
                "description": "Get persistent user profile context.",
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "profile_update",
                "description": "Update persistent user profile context.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "preferred_tone": {"type": "string"},
                        "coding_style_notes": {"type": "array", "items": {"type": "string"}},
                        "goals": {"type": "array", "items": {"type": "string"}},
                        "constraints": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
            # ---------------- Computer control -- actually drive the machine ----------------
            # These give the live agent loop the same on-screen capability
            # tool_executor.py already has, so it can open real links, switch
            # real tabs, and read the real screen instead of only describing
            # what it would do.
            {
                "name": "open_app",
                "description": "Open a named application (browser, editor, etc) on the local machine.",
                "input_schema": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                },
            },
            {
                "name": "web_search",
                "description": "Run a live web search for a query in Chrome -- use this whenever the user "
                "wants something looked up right now, not just described from memory. Manage tabs "
                "intuitively: pass new_tab=true for the first search of a new topic/conversation, and "
                "new_tab=false for a follow-up search that continues what you were just looking at (so tabs "
                "don't pile up) -- check the conversation so far to tell which one this is.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "new_tab": {
                            "type": "boolean",
                            "default": True,
                            "description": "true to open a new tab for this search, false to reuse the current tab",
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "open_and_type",
                "description": "Open an application and type text into it (e.g. open a browser and type a URL).",
                "input_schema": {
                    "type": "object",
                    "properties": {"app": {"type": "string"}, "text": {"type": "string"}},
                    "required": ["app", "text"],
                },
            },
            {
                "name": "read_screen",
                "description": "Read what's currently on screen (active app, window title, and a vision-model "
                "description of visible content). Use this whenever the user is stuck on something on their "
                "screen and asks for help without specifying what -- the answer is on the screen.",
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "click_element",
                "description": "Click a UI element on screen by describing it (e.g. 'the Submit button').",
                "input_schema": {
                    "type": "object",
                    "properties": {"target": {"type": "string"}},
                    "required": ["target"],
                },
            },
            {
                "name": "type_text",
                "description": "Type text at the current cursor/focus location.",
                "input_schema": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
            },
            {
                "name": "press_keys",
                "description": "Press a key combination (e.g. ['cmd', 'l'] for the address bar).",
                "input_schema": {
                    "type": "object",
                    "properties": {"keys": {"type": "array", "items": {"type": "string"}}},
                    "required": ["keys"],
                },
            },
            {
                "name": "switch_tab",
                "description": "Switch to the next or previous browser/app tab.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "direction": {"type": "string", "enum": ["next", "previous"], "default": "next"},
                    },
                },
            },
            {
                "name": "scroll",
                "description": "Scroll the frontmost window up or down.",
                "input_schema": {
                    "type": "object",
                    "properties": {"direction": {"type": "string", "enum": ["up", "down"]}},
                    "required": ["direction"],
                },
            },
            # ---------------- Calendar / Canvas / Reminders (daily assignment ingest) ----------------
            {
                "name": "calendar_list_events",
                "description": "List upcoming Google Calendar events.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "calendar_id": {"type": "string", "default": "primary"},
                        "max_results": {"type": "integer", "default": 20},
                        "time_min": {"type": "string", "description": "RFC3339, defaults to now"},
                    },
                },
            },
            {
                "name": "calendar_create_event",
                "description": "Create a Google Calendar event. start_iso/end_iso are RFC3339. Pass recurrence "
                "as RRULE strings (e.g. ['RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR']) for a recurring class/meeting.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "summary": {"type": "string"},
                        "start_iso": {"type": "string"},
                        "end_iso": {"type": "string"},
                        "calendar_id": {"type": "string", "default": "primary"},
                        "description": {"type": "string", "default": ""},
                        "location": {"type": "string", "default": ""},
                        "recurrence": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["summary", "start_iso", "end_iso"],
                },
            },
            {
                "name": "calendar_update_event",
                "description": "Update fields on an existing Google Calendar event -- only pass what changed.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "event_id": {"type": "string"},
                        "calendar_id": {"type": "string", "default": "primary"},
                        "summary": {"type": "string"},
                        "start_iso": {"type": "string"},
                        "end_iso": {"type": "string"},
                        "description": {"type": "string"},
                        "location": {"type": "string"},
                        "recurrence": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["event_id"],
                },
            },
            {
                "name": "calendar_delete_event",
                "description": "Delete a Google Calendar event.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "event_id": {"type": "string"},
                        "calendar_id": {"type": "string", "default": "primary"},
                    },
                    "required": ["event_id"],
                },
            },
            {
                "name": "canvas_list_upcoming_assignments",
                "description": "List upcoming Canvas assignments across active courses within a day window.",
                "input_schema": {
                    "type": "object",
                    "properties": {"days_ahead": {"type": "integer", "default": 14}},
                },
            },
            {
                "name": "canvas_list_grades",
                "description": "Current grade per active Canvas course.",
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "reminders_add",
                "description": "Add an item to Apple Reminders. Defaults to the 'JARVIS' list.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "due_date_iso": {"type": "string", "default": ""},
                        "notes": {"type": "string", "default": ""},
                        "list_name": {"type": "string", "default": ""},
                    },
                    "required": ["title"],
                },
            },
            {
                "name": "reminders_list",
                "description": "List items in an Apple Reminders list.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "list_name": {"type": "string", "default": ""},
                        "include_completed": {"type": "boolean", "default": False},
                    },
                },
            },
            {
                "name": "reminders_complete",
                "description": "Mark an Apple Reminders item complete.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "reminder_id": {"type": "string"},
                        "list_name": {"type": "string", "default": ""},
                    },
                    "required": ["reminder_id"],
                },
            },
            {
                "name": "daily_briefing_run",
                "description": "Run the full daily assignment ingest: pulls upcoming Canvas assignments + "
                "grades, estimates workload, syncs new due dates to Calendar and Reminders, returns a summary.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "days_ahead": {"type": "integer", "default": 7},
                        "max_hours_per_day": {"type": "number", "default": 8.0},
                    },
                },
            },
        ]

    async def invoke(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        handlers = {
            "list_workspace": self._list_workspace,
            "read_workspace_file": self._read_workspace_file,
            "write_workspace_file": self._write_workspace_file,
            "edit_workspace_file": self._edit_workspace_file,
            "create_workspace_directory": self._create_workspace_directory,
            "delete_workspace_file": self._delete_workspace_file,
            "run_dev_command": self._run_dev_command,
            "search_workspace": self._search_workspace,
            "code_review_file": self._code_review_file,
            "project_create": self._project_create,
            "create_desktop_project": self._create_desktop_project,
            "project_list": self._project_list,
            "project_add_note": self._project_add_note,
            "profile_get": self._profile_get,
            "profile_update": self._profile_update,
            "open_app": self._open_app,
            "web_search": self._web_search,
            "open_and_type": self._open_and_type,
            "read_screen": self._read_screen,
            "click_element": self._click_element,
            "type_text": self._type_text,
            "press_keys": self._press_keys,
            "switch_tab": self._switch_tab,
            "scroll": self._scroll,
            "calendar_list_events": self._calendar_list_events,
            "calendar_create_event": self._calendar_create_event,
            "calendar_update_event": self._calendar_update_event,
            "calendar_delete_event": self._calendar_delete_event,
            "canvas_list_upcoming_assignments": self._canvas_list_upcoming_assignments,
            "canvas_list_grades": self._canvas_list_grades,
            "reminders_add": self._reminders_add,
            "reminders_list": self._reminders_list,
            "reminders_complete": self._reminders_complete,
            "daily_briefing_run": self._daily_briefing_run,
        }
        handler = handlers.get(name)
        if not handler:
            raise ValueError(f"Unknown tool: {name}")
        return await handler(payload)

    async def _list_workspace(self, payload: dict[str, Any]) -> dict[str, Any]:
        path = str(payload.get("path", "."))
        max_entries = int(payload.get("max_entries", 200))
        target = safe_path(path, must_exist=True)
        if not target.is_dir():
            raise NotADirectoryError(f"Not a directory: {path}")

        entries = sorted(target.iterdir(), key=lambda item: item.name.lower())
        limited = entries[:max_entries]
        items = []
        for item in limited:
            item_type = "dir" if item.is_dir() else "file"
            rel = item.relative_to(self.workspace_root)
            items.append({"name": item.name, "path": str(rel), "type": item_type})

        return {
            "root": str(self.workspace_root),
            "path": str(target.relative_to(self.workspace_root)),
            "count": len(items),
            "truncated": len(entries) > len(limited),
            "items": items,
        }

    async def _read_workspace_file(self, payload: dict[str, Any]) -> dict[str, Any]:
        path = str(payload["path"])
        start_line = int(payload.get("start_line", 1))
        end_line = int(payload.get("end_line", 200))
        if start_line < 1:
            raise ValueError("start_line must be >= 1")
        if end_line < start_line:
            raise ValueError("end_line must be >= start_line")

        target = safe_path(path, must_exist=True)
        if not target.is_file():
            raise FileNotFoundError(f"Not a file: {path}")

        lines = target.read_text(encoding="utf-8").splitlines()
        selected = lines[start_line - 1:end_line]
        return {
            "path": str(target.relative_to(self.workspace_root)),
            "start_line": start_line,
            "end_line": end_line,
            "total_lines": len(lines),
            "content": "\n".join(selected),
        }

    async def _write_workspace_file(self, payload: dict[str, Any]) -> dict[str, Any]:
        path = str(payload["path"])
        content = str(payload["content"])
        overwrite = bool(payload.get("overwrite", True))
        target = safe_path(path)
        already_existed = target.exists()
        if already_existed and not overwrite:
            raise FileExistsError(f"File already exists: {path}")

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return {
            "path": str(target.relative_to(self.workspace_root)),
            "bytes_written": len(content.encode("utf-8")),
            "created": not already_existed,
        }

    async def _edit_workspace_file(self, payload: dict[str, Any]) -> dict[str, Any]:
        path = str(payload["path"])
        old_string = str(payload["old_string"])
        new_string = str(payload["new_string"])
        expected = int(payload.get("expected_replacements", 1))

        target = safe_path(path, must_exist=True)
        content = target.read_text(encoding="utf-8")
        occurrences = content.count(old_string)
        if occurrences == 0:
            raise ValueError("old_string not found")
        if occurrences != expected:
            raise ValueError(f"old_string occurs {occurrences} times, expected {expected}")

        target.write_text(content.replace(old_string, new_string), encoding="utf-8")
        return {"path": str(target.relative_to(self.workspace_root)), "replacements_made": occurrences}

    async def _create_workspace_directory(self, payload: dict[str, Any]) -> dict[str, Any]:
        path = str(payload["path"])
        target = safe_path(path)
        target.mkdir(parents=True, exist_ok=True)
        return {"path": str(target.relative_to(self.workspace_root)), "created": True}

    async def _delete_workspace_file(self, payload: dict[str, Any]) -> dict[str, Any]:
        path = str(payload["path"])
        target = safe_path(path, must_exist=True)
        if target.is_dir():
            raise IsADirectoryError(f"Refusing to delete directory: {path}")
        target.unlink()
        return {"path": str(target.relative_to(self.workspace_root)), "deleted": True}

    async def _run_dev_command(self, payload: dict[str, Any]) -> dict[str, Any]:
        command = str(payload["command"])
        cwd = str(payload.get("cwd", "."))
        timeout_s = float(payload.get("timeout_s", 120.0))

        working_dir = safe_path(cwd, must_exist=True)
        if not working_dir.is_dir():
            raise NotADirectoryError(f"Not a directory: {cwd}")

        result = await self.executor.run_dev_command(command, cwd=str(working_dir), timeout_s=timeout_s)
        return {
            "success": result.success,
            "output": result.output,
            "error": result.error,
            "command": command,
            "cwd": str(working_dir.relative_to(self.workspace_root)) or ".",
        }

    async def _search_workspace(self, payload: dict[str, Any]) -> dict[str, Any]:
        pattern = str(payload["pattern"])
        path = str(payload.get("path", "."))
        file_glob = str(payload.get("file_glob", "*"))
        is_regex = bool(payload.get("is_regex", False))
        case_sensitive = bool(payload.get("case_sensitive", False))
        max_results = int(payload.get("max_results", 200))

        root = safe_path(path, must_exist=True)
        flags = 0 if case_sensitive else re.IGNORECASE
        matcher = re.compile(pattern, flags) if is_regex else None
        needle = pattern if case_sensitive else pattern.lower()

        matches: list[dict[str, Any]] = []
        truncated = False

        for file_path in sorted(root.rglob(file_glob)):
            if len(matches) >= max_results:
                truncated = True
                break
            if not file_path.is_file():
                continue
            if any(part in _SEARCH_SKIP_DIRS for part in file_path.parts):
                continue
            try:
                text = file_path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue

            for line_no, line in enumerate(text.splitlines(), start=1):
                hit = matcher.search(line) if matcher else (needle in (line if case_sensitive else line.lower()))
                if hit:
                    matches.append({
                        "path": str(file_path.relative_to(self.workspace_root)),
                        "line": line_no,
                        "text": line.strip()[:300],
                    })
                    if len(matches) >= max_results:
                        truncated = True
                        break

        return {"pattern": pattern, "count": len(matches), "truncated": truncated, "matches": matches}

    async def _code_review_file(self, payload: dict[str, Any]) -> dict[str, Any]:
        path = str(payload["path"])
        target = safe_path(path, must_exist=True)
        if not target.is_file():
            raise FileNotFoundError(f"Not a file: {path}")

        content = target.read_text(encoding="utf-8")
        lines = content.splitlines()

        markers = [
            {"line": i + 1, "text": line.strip()}
            for i, line in enumerate(lines)
            if re.search(r"\b(TODO|FIXME|XXX|HACK)\b", line)
        ]
        bare_excepts = [i + 1 for i, line in enumerate(lines) if re.match(r"\s*except\s*:\s*$", line)]

        long_functions: list[dict[str, Any]] = []
        func_start = None
        func_name = ""
        for i, line in enumerate(lines):
            decl = re.match(r"\s*(def|async def|function)\s+(\w+)", line)
            if decl:
                if func_start is not None and i - func_start > 60:
                    long_functions.append({"name": func_name, "start_line": func_start + 1, "length": i - func_start})
                func_start = i
                func_name = decl.group(2)
        if func_start is not None and len(lines) - func_start > 60:
            long_functions.append({"name": func_name, "start_line": func_start + 1, "length": len(lines) - func_start})

        return {
            "path": str(target.relative_to(self.workspace_root)),
            "total_lines": len(lines),
            "todo_markers": markers,
            "bare_except_lines": bare_excepts,
            "long_functions": long_functions,
            "content": content,
        }

    async def _project_create(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.life_os.create_project(
            name=str(payload["name"]),
            objective=str(payload["objective"]),
            constraints=payload.get("constraints"),
            budget=payload.get("budget"),
            deadline=str(payload.get("deadline", "")),
        )

    def _safe_project_target(self, target_dir: str) -> Path:
        candidate = Path(target_dir).expanduser()
        if not candidate.is_absolute():
            candidate = (self.projects_root / candidate).resolve()
        else:
            candidate = candidate.resolve()

        if candidate != self.projects_root and self.projects_root not in candidate.parents:
            raise ValueError(f"Project path escapes projects root: {target_dir}")
        return candidate

    def _slugify(self, name: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
        return slug or "jarvis-project"

    async def _create_desktop_project(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name", "")).strip()
        if not name:
            raise ValueError("name is required")

        description = str(payload.get("description", "")).strip()
        template = str(payload.get("template", "python-basic")).strip().lower()
        target_dir = str(payload.get("target_dir", "")).strip()

        if template not in {"python-basic", "web-basic"}:
            raise ValueError("template must be one of: python-basic, web-basic")

        folder_name = self._slugify(name)
        target = self._safe_project_target(target_dir) if target_dir else self._safe_project_target(folder_name)
        if target.exists():
            raise FileExistsError(f"Project directory already exists: {target}")

        target.mkdir(parents=True, exist_ok=False)
        files_created: list[str] = []

        readme = (
            f"# {name}\n\n"
            f"{description or 'Scaffolded by JARVIS.'}\n"
        )

        if template == "python-basic":
            (target / "main.py").write_text(
                "def main():\n"
                "    print(\"Hello from your new JARVIS project!\")\n\n"
                "if __name__ == \"__main__\":\n"
                "    main()\n",
                encoding="utf-8",
            )
            (target / "README.md").write_text(
                readme + "\n## Run\n\n```bash\npython3 main.py\n```\n",
                encoding="utf-8",
            )
            files_created.extend(["main.py", "README.md"])
        else:
            (target / "index.html").write_text(
                "<!doctype html>\n"
                "<html lang=\"en\">\n"
                "  <head>\n"
                "    <meta charset=\"UTF-8\" />\n"
                "    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />\n"
                f"    <title>{name}</title>\n"
                "  </head>\n"
                "  <body>\n"
                "    <h1>Hello from your new JARVIS web project!</h1>\n"
                "  </body>\n"
                "</html>\n",
                encoding="utf-8",
            )
            (target / "README.md").write_text(
                readme + "\n## Open\n\nOpen `index.html` in your browser.\n",
                encoding="utf-8",
            )
            files_created.extend(["index.html", "README.md"])

        return {
            "name": name,
            "template": template,
            "project_root": str(target),
            "projects_root": str(self.projects_root),
            "files_created": files_created,
        }

    async def _project_list(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"projects": self.life_os.list_projects(status=payload.get("status"))}

    async def _project_add_note(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.life_os.add_project_note(project_id=str(payload["project_id"]), text=str(payload["text"]))

    async def _profile_get(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.profile_store.get()

    async def _profile_update(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.profile_store.update(
            name=payload.get("name"),
            preferred_tone=payload.get("preferred_tone"),
            coding_style_notes=payload.get("coding_style_notes"),
            goals=payload.get("goals"),
            constraints=payload.get("constraints"),
        )

    # ---------------- Computer control ----------------

    async def _run_tool_call(self, call: ToolCall) -> dict[str, Any]:
        result = await self.executor.execute(call)
        if not result.success:
            raise RuntimeError(result.error or result.output)
        return {"output": result.output}

    async def _open_app(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._run_tool_call(ToolCall("open_app", {"name": str(payload["name"])}))

    async def _web_search(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._run_tool_call(ToolCall(
            "web_search_and_open", {"query": str(payload["query"]), "new_tab": bool(payload.get("new_tab", True))},
        ))

    async def _open_and_type(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._run_tool_call(
            ToolCall("open_and_type", {"app": str(payload["app"]), "text": str(payload["text"])})
        )

    async def _read_screen(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._run_tool_call(ToolCall("read_screen", {}))

    async def _click_element(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._run_tool_call(ToolCall("click_element", {"target": str(payload["target"])}))

    async def _type_text(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._run_tool_call(ToolCall("type_text", {"text": str(payload["text"])}))

    async def _press_keys(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._run_tool_call(ToolCall("press_keys", {"keys": list(payload.get("keys", []))}))

    async def _switch_tab(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._run_tool_call(ToolCall("switch_tab", {"direction": payload.get("direction", "next")}))

    async def _scroll(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._run_tool_call(ToolCall("scroll", {"direction": str(payload["direction"])}))

    # ---------------- Calendar / Canvas / Reminders ----------------

    async def _calendar_list_events(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.google.list_events(
            calendar_id=payload.get("calendar_id", "primary"),
            max_results=int(payload.get("max_results", 20)),
            time_min=payload.get("time_min", ""),
        )

    async def _calendar_create_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.google.create_event(
            summary=str(payload["summary"]),
            start_iso=str(payload["start_iso"]),
            end_iso=str(payload["end_iso"]),
            calendar_id=payload.get("calendar_id", "primary"),
            description=payload.get("description", ""),
            location=payload.get("location", ""),
            recurrence=payload.get("recurrence"),
        )

    async def _calendar_update_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.google.update_event(
            event_id=str(payload["event_id"]),
            calendar_id=payload.get("calendar_id", "primary"),
            summary=payload.get("summary"),
            start_iso=payload.get("start_iso"),
            end_iso=payload.get("end_iso"),
            description=payload.get("description"),
            location=payload.get("location"),
            recurrence=payload.get("recurrence"),
        )

    async def _calendar_delete_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.google.delete_event(
            event_id=str(payload["event_id"]), calendar_id=payload.get("calendar_id", "primary"),
        )

    async def _canvas_list_upcoming_assignments(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.canvas.list_upcoming_assignments(days_ahead=int(payload.get("days_ahead", 14)))

    async def _canvas_list_grades(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.canvas.list_grades()

    async def _reminders_add(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.reminders.add_reminder(
            title=str(payload["title"]),
            due_date_iso=payload.get("due_date_iso", ""),
            notes=payload.get("notes", ""),
            list_name=payload.get("list_name", ""),
        )

    async def _reminders_list(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.reminders.list_reminders(
            list_name=payload.get("list_name", ""), include_completed=bool(payload.get("include_completed", False)),
        )

    async def _reminders_complete(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.reminders.complete_reminder(
            reminder_id=str(payload["reminder_id"]), list_name=payload.get("list_name", ""),
        )

    async def _daily_briefing_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.daily_briefing.run(
            days_ahead=int(payload.get("days_ahead", 7)),
            max_hours_per_day=float(payload.get("max_hours_per_day", 8.0)),
        )
