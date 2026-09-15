#!/usr/bin/env python3
"""Ported from src/mcp/server.ts.

Tier-3 agentic layer: exposes the same actions DeviceActions/ToolExecutor
already run for tier-2 fast commands, but through the Model Context
Protocol so a reasoning model (a mesh facet, or Claude, or any other MCP
client) can chain several of them together with judgment in between --
"get the enclosure ready, slice it, queue the print" -- instead of only
ever executing one matched command at a time.

Run: python -m jarvis.mcp.server   (stdio transport; point an MCP client at it)
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from ..tools.canvas_adapter import CanvasAdapter
from ..tools.daily_briefing import DailyBriefingService
from ..tools.fitness_adapter import FitnessAdapter
from ..tools.google_adapter import GoogleAdapter
from ..tools.life_os import LifeOSService
from ..tools.reminders_adapter import RemindersAdapter
from ..tools.device_actions import DeviceActions, DeviceCommand
from ..tools.tool_executor import ToolCall, ToolExecutor
from ..session.user_profile import UserProfileStore
from ..tools.web_fetch import WebFetch
from ..utils.logging import logger

mcp = FastMCP("jarvis-workshop-tools")

_tool_executor = ToolExecutor()
_device_actions = DeviceActions()
_web_fetch = WebFetch()

WORKSPACE_ROOT = Path(os.environ.get("JARVIS_WORKSPACE_ROOT", Path.cwd())).resolve()
_life_os = LifeOSService(state_dir=WORKSPACE_ROOT / ".jarvis_state")
_profile_store = UserProfileStore(state_dir=WORKSPACE_ROOT / ".jarvis_state")
_google = GoogleAdapter()
_canvas = CanvasAdapter()
_fitness = FitnessAdapter()
_reminders = RemindersAdapter()
_daily_briefing = DailyBriefingService(canvas=_canvas, google=_google, reminders=_reminders, life_os=_life_os)


def _safe_path(path: str, must_exist: bool = False) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = (WORKSPACE_ROOT / candidate).resolve()
    else:
        candidate = candidate.resolve()

    if candidate != WORKSPACE_ROOT and WORKSPACE_ROOT not in candidate.parents:
        raise ValueError(f"Path escapes workspace root: {path}")

    if must_exist and not candidate.exists():
        raise FileNotFoundError(f"Path does not exist: {path}")

    return candidate


@mcp.tool()
async def open_app(name: str) -> str:
    """Open a named application on the local machine."""
    result = await _tool_executor.execute(ToolCall(action="open_app", params={"name": name}))
    return result.output


@mcp.tool()
async def run_shell(command: str) -> str:
    """Run a whitelisted, read-only shell command (ls, pwd, ps, df, ...)."""
    result = await _tool_executor.execute(ToolCall(action="run_shell", params={"command": command}))
    if not result.success:
        raise RuntimeError(result.error or result.output)
    return result.output


@mcp.tool()
async def device_command(type: str, action: str, parameters: Optional[dict[str, Any]] = None) -> str:
    """Execute a smart-home/workshop device action (lights, thermostat,
    security). Placeholder handlers today -- this is the hook real
    equipment control (printer, CNC, laser) will register into once the
    physical safety interlocks in front of it are built."""
    return await _device_actions.execute_command(DeviceCommand(type=type, action=action, parameters=parameters))  # type: ignore[arg-type]


@mcp.tool()
async def workspace_root() -> str:
    """Return the workspace root this MCP server is allowed to access."""
    return str(WORKSPACE_ROOT)


@mcp.tool()
async def list_workspace(path: str = ".", max_entries: int = 200) -> dict[str, Any]:
    """List files/folders inside the workspace (read-only, path-safe)."""
    target = _safe_path(path, must_exist=True)
    if not target.is_dir():
        raise NotADirectoryError(f"Not a directory: {path}")

    entries = sorted(target.iterdir(), key=lambda item: item.name.lower())
    limited = entries[:max_entries]
    rows = []
    for item in limited:
        item_type = "dir" if item.is_dir() else "file"
        rel = item.relative_to(WORKSPACE_ROOT)
        rows.append({"name": item.name, "path": str(rel), "type": item_type})

    return {
        "root": str(WORKSPACE_ROOT),
        "path": str(target.relative_to(WORKSPACE_ROOT)),
        "count": len(rows),
        "truncated": len(entries) > len(limited),
        "items": rows,
    }


@mcp.tool()
async def read_workspace_file(path: str, start_line: int = 1, end_line: int = 200) -> dict[str, Any]:
    """Read a file in the workspace with line-range controls (read-only, path-safe)."""
    if start_line < 1:
        raise ValueError("start_line must be >= 1")
    if end_line < start_line:
        raise ValueError("end_line must be >= start_line")

    target = _safe_path(path, must_exist=True)
    if not target.is_file():
        raise FileNotFoundError(f"Not a file: {path}")

    content = target.read_text(encoding="utf-8")
    lines = content.splitlines()
    selected = lines[start_line - 1:end_line]

    return {
        "path": str(target.relative_to(WORKSPACE_ROOT)),
        "start_line": start_line,
        "end_line": end_line,
        "total_lines": len(lines),
        "content": "\n".join(selected),
    }


# ---------------- Coding partner: write/edit code, run real dev commands ----------------
# Everything above this point (list_workspace/read_workspace_file) is
# read-only. These tools are what actually let JARVIS act as a programming
# partner -- create/modify files and run git/pip/npm/pytest/etc for real,
# scoped to WORKSPACE_ROOT and guarded by ToolExecutor's dangerous-pattern
# blocklist rather than a read-only allowlist.

@mcp.tool()
async def write_workspace_file(path: str, content: str, overwrite: bool = True) -> dict[str, Any]:
    """Create or overwrite a file in the workspace (path-safe). Parent
    directories are created automatically. Set overwrite=False to fail
    instead of clobbering an existing file."""
    target = _safe_path(path)
    already_existed = target.exists()
    if already_existed and not overwrite:
        raise FileExistsError(f"File already exists (pass overwrite=True to replace it): {path}")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")

    return {
        "path": str(target.relative_to(WORKSPACE_ROOT)),
        "bytes_written": len(content.encode("utf-8")),
        "created": not already_existed,
    }


@mcp.tool()
async def edit_workspace_file(path: str, old_string: str, new_string: str, expected_replacements: int = 1) -> dict[str, Any]:
    """Replace an exact literal string in a workspace file (like a surgical
    find/replace). old_string must match exactly expected_replacements times
    -- this guards against accidentally rewriting the wrong occurrence in a
    file with repeated text."""
    target = _safe_path(path, must_exist=True)
    if not target.is_file():
        raise FileNotFoundError(f"Not a file: {path}")

    content = target.read_text(encoding="utf-8")
    occurrences = content.count(old_string)
    if occurrences == 0:
        raise ValueError("old_string not found in file")
    if occurrences != expected_replacements:
        raise ValueError(f"old_string occurs {occurrences} times, expected {expected_replacements} -- make old_string more specific")

    updated = content.replace(old_string, new_string)
    target.write_text(updated, encoding="utf-8")

    return {
        "path": str(target.relative_to(WORKSPACE_ROOT)),
        "replacements_made": occurrences,
    }


@mcp.tool()
async def create_workspace_directory(path: str) -> dict[str, Any]:
    """Create a directory (and any missing parents) inside the workspace."""
    target = _safe_path(path)
    target.mkdir(parents=True, exist_ok=True)
    return {"path": str(target.relative_to(WORKSPACE_ROOT)), "created": True}


@mcp.tool()
async def delete_workspace_file(path: str) -> dict[str, Any]:
    """Delete a single file inside the workspace (path-safe). Refuses to
    delete directories -- remove files individually to avoid accidental
    mass-deletion."""
    target = _safe_path(path, must_exist=True)
    if target.is_dir():
        raise IsADirectoryError(f"Refusing to delete a directory: {path}. Delete files individually.")
    target.unlink()
    return {"path": str(Path(path)), "deleted": True}


@mcp.tool()
async def run_dev_command(command: str, cwd: str = ".", timeout_s: float = 120.0) -> dict[str, Any]:
    """Run a real development command -- git, python3, pip, npm, pytest,
    node, make, etc -- scoped to a directory inside the workspace. This is
    how JARVIS actually builds/tests/runs your code instead of just
    describing what to run. Blocked for destructive patterns (rm -rf, sudo,
    piping remote scripts into a shell, force-pushing) regardless of the
    base command."""
    working_dir = _safe_path(cwd, must_exist=True)
    if not working_dir.is_dir():
        raise NotADirectoryError(f"Not a directory: {cwd}")

    result = await _tool_executor.run_dev_command(command, cwd=str(working_dir), timeout_s=timeout_s)
    return {
        "success": result.success,
        "output": result.output,
        "error": result.error,
        "command": command,
        "cwd": str(working_dir.relative_to(WORKSPACE_ROOT)) or ".",
    }


_SEARCH_SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", ".pytest_cache",
    "dist", "build", ".mypy_cache", ".ruff_cache", ".jarvis_state",
}


@mcp.tool()
async def search_workspace(
    pattern: str,
    path: str = ".",
    file_glob: str = "*",
    is_regex: bool = False,
    case_sensitive: bool = False,
    max_results: int = 200,
) -> dict[str, Any]:
    """Search file contents across the workspace (grep-style) -- the code
    indexing/search primitive JARVIS needs to actually navigate a codebase
    instead of only reading files you name explicitly. Skips .git/
    node_modules/__pycache__/venvs/build output automatically."""
    import fnmatch
    import re as _re

    root = _safe_path(path, must_exist=True)
    flags = 0 if case_sensitive else _re.IGNORECASE
    matcher = _re.compile(pattern, flags) if is_regex else None
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
                    "path": str(file_path.relative_to(WORKSPACE_ROOT)),
                    "line": line_no,
                    "text": line.strip()[:300],
                })
                if len(matches) >= max_results:
                    truncated = True
                    break

    return {"pattern": pattern, "count": len(matches), "truncated": truncated, "matches": matches}


@mcp.tool()
async def code_review_file(path: str) -> dict[str, Any]:
    """Pull a file's full content plus lightweight structural signals (line
    count, TODO/FIXME markers, long-function heuristic, bare-except usage)
    for Claude to perform a real code review against -- the review judgment
    itself happens in the conversation, this tool just gathers everything
    needed to do it well in one call instead of several."""
    import re as _re

    target = _safe_path(path, must_exist=True)
    if not target.is_file():
        raise FileNotFoundError(f"Not a file: {path}")

    content = target.read_text(encoding="utf-8")
    lines = content.splitlines()

    markers = [
        {"line": i + 1, "text": line.strip()}
        for i, line in enumerate(lines)
        if _re.search(r"\b(TODO|FIXME|XXX|HACK)\b", line)
    ]
    bare_excepts = [i + 1 for i, line in enumerate(lines) if _re.match(r"\s*except\s*:\s*$", line)]

    # Rough "this function might be too long" heuristic for Python/JS-family
    # files: count consecutive non-blank lines at increasing indent after a
    # def/function declaration.
    long_functions: list[dict[str, Any]] = []
    func_start = None
    func_name = ""
    for i, line in enumerate(lines):
        decl = _re.match(r"\s*(def|async def|function)\s+(\w+)", line)
        if decl:
            if func_start is not None and i - func_start > 60:
                long_functions.append({"name": func_name, "start_line": func_start + 1, "length": i - func_start})
            func_start = i
            func_name = decl.group(2)
    if func_start is not None and len(lines) - func_start > 60:
        long_functions.append({"name": func_name, "start_line": func_start + 1, "length": len(lines) - func_start})

    return {
        "path": str(target.relative_to(WORKSPACE_ROOT)),
        "total_lines": len(lines),
        "todo_markers": markers,
        "bare_except_lines": bare_excepts,
        "long_functions": long_functions,
        "content": content,
    }


@mcp.tool()
async def fetch_webpage(url: str, extract_text: bool = True, max_chars: int = 12000) -> dict[str, Any]:
    """Fetch a webpage and optionally return extracted plain text for Claude context."""
    if not _web_fetch.is_valid_url(url):
        raise ValueError(f"Invalid URL: {url}")

    result = await _web_fetch.fetch_url(url)
    content = _web_fetch.extract_text(result.content) if extract_text else result.content

    return {
        "url": result.url,
        "status": result.status,
        "content_type": result.content_type,
        "title": _web_fetch.extract_title(result.content),
        "duration_ms": round(result.duration, 2),
        "truncated": len(content) > max_chars,
        "content": content[:max_chars],
    }


@mcp.tool()
async def fetch_many_webpages(urls: list[str], extract_text: bool = True, max_chars: int = 6000) -> list[dict[str, Any]]:
    """Fetch multiple webpages in parallel and return compact context payloads."""
    results = await _web_fetch.fetch_multiple(urls)
    payload: list[dict[str, Any]] = []
    for result in results:
        content = _web_fetch.extract_text(result.content) if extract_text else result.content
        payload.append({
            "url": result.url,
            "status": result.status,
            "content_type": result.content_type,
            "title": _web_fetch.extract_title(result.content),
            "duration_ms": round(result.duration, 2),
            "truncated": len(content) > max_chars,
            "content": content[:max_chars],
        })

    return payload


@mcp.tool()
async def fabrication_project_plan(
    project_name: str,
    objective: str,
    constraints: Optional[list[str]] = None,
    budget: Optional[float] = None,
    deadline: str = "",
) -> dict[str, Any]:
    """Create a structured fabrication/debug execution plan for a build project."""
    return _life_os.create_fabrication_plan(
        project_name=project_name,
        objective=objective,
        constraints=constraints,
        budget=budget,
        deadline=deadline,
    )


@mcp.tool()
async def computer_control(
    action: str,
    app: str = "",
    text: str = "",
    command: str = "",
    keys: Optional[list[str]] = None,
    target: str = "",
) -> str:
    """Execute high-level computer actions (open app, type, keypress, read screen, click target, shell)."""
    action_map = {
        "open_app": ToolCall(action="open_app", params={"name": app}),
        "open_and_type": ToolCall(action="open_and_type", params={"app": app, "text": text}),
        "type_text": ToolCall(action="type_text", params={"text": text}),
        "press_keys": ToolCall(action="press_keys", params={"keys": keys or []}),
        "read_screen": ToolCall(action="read_screen", params={}),
        "run_shell": ToolCall(action="run_shell", params={"command": command}),
        "click_element": ToolCall(action="click_element", params={"target": target}),
    }
    if action not in action_map:
        raise ValueError(f"Unsupported action: {action}")

    result = await _tool_executor.execute(action_map[action])
    if not result.success:
        raise RuntimeError(result.error or result.output)
    return result.output


@mcp.tool()
async def planner_add_item(
    title: str,
    details: str = "",
    due_date: str = "",
    estimate_hours: float = 1.0,
    source: str = "voice",
    tags: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Add a planning item for daily organization and follow-up execution."""
    return _life_os.add_task(
        title=title,
        details=details,
        due_date=due_date,
        estimate_hours=estimate_hours,
        source=source,
        tags=tags,
    )


@mcp.tool()
async def planner_list_items(status: str = "", limit: int = 50) -> list[dict[str, Any]]:
    """List planning items, optionally filtered by status."""
    normalized = status.strip() or None
    return _life_os.list_tasks(status=normalized, limit=limit)  # type: ignore[arg-type]


@mcp.tool()
async def planner_update_item(task_id: str, status: str) -> dict[str, Any]:
    """Update status on a planning item."""
    allowed = {"open", "in_progress", "blocked", "done"}
    if status not in allowed:
        raise ValueError(f"Invalid status: {status}. Allowed: {sorted(allowed)}")
    return _life_os.update_task_status(task_id=task_id, status=status)  # type: ignore[arg-type]


@mcp.tool()
async def planner_daily_brief(target_date: str = "", max_hours: float = 8.0) -> dict[str, Any]:
    """Build a daily plan from open/in-progress tasks within an hourly budget."""
    return _life_os.daily_plan(target_date=target_date, max_hours=max_hours)


@mcp.tool()
async def planner_estimate_canvas_workload(assignments: list[dict[str, Any]]) -> dict[str, Any]:
    """Estimate workload hours from Canvas assignment payloads."""
    return _life_os.estimate_canvas_workload(assignments)


@mcp.tool()
async def fitness_log_metrics(metrics: dict[str, float], source: str = "dashboard") -> dict[str, Any]:
    """Store a biometrics snapshot from your fitness dashboard."""
    return _life_os.add_fitness_entry(metrics=metrics, source=source)


@mcp.tool()
async def fitness_summary(days: int = 7) -> dict[str, Any]:
    """Summarize recent biometrics averages and latest reading."""
    return _life_os.fitness_summary(days=days)


@mcp.tool()
async def fitness_history(limit: int = 50) -> dict[str, Any]:
    """List recent biometrics entries, most recent first -- for the native
    JARVIS fitness panel's history view/chart."""
    return {"entries": _life_os.fitness_history(limit=limit)}


# ---------------- R&D project workspace ----------------
# A project bundles a fabrication plan with every artifact produced while
# building it (CAD files, circuit netlists, sim results, links) plus a notes
# timeline -- the "spine" a real build lives on, queryable as one whole
# instead of scattered across disconnected tool calls.

@mcp.tool()
async def project_create(
    name: str,
    objective: str,
    constraints: Optional[list[str]] = None,
    budget: Optional[float] = None,
    deadline: str = "",
) -> dict[str, Any]:
    """Start a new R&D project workspace -- generates a fabrication plan up
    front and gives you back a project_id to attach artifacts/notes to as
    you build (project_add_artifact, project_add_note)."""
    return _life_os.create_project(
        name=name, objective=objective, constraints=constraints, budget=budget, deadline=deadline,
    )


@mcp.tool()
async def project_list(status: Optional[str] = None) -> dict[str, Any]:
    """List R&D projects, most recently updated first. Optionally filter by
    status (idea/planning/building/testing/done/archived)."""
    return {"projects": _life_os.list_projects(status=status)}  # type: ignore[arg-type]


@mcp.tool()
async def project_get(project_id: str) -> dict[str, Any]:
    """Fetch one R&D project's full state: fabrication plan, artifacts, notes."""
    return _life_os.get_project(project_id)


@mcp.tool()
async def project_update_status(project_id: str, status: str) -> dict[str, Any]:
    """Update a project's status (idea/planning/building/testing/done/archived)."""
    allowed = {"idea", "planning", "building", "testing", "done", "archived"}
    if status not in allowed:
        raise ValueError(f"Invalid status: {status}. Allowed: {sorted(allowed)}")
    return _life_os.update_project_status(project_id=project_id, status=status)  # type: ignore[arg-type]


@mcp.tool()
async def project_add_artifact(
    project_id: str,
    artifact_type: str,
    name: str,
    path: str = "",
    url: str = "",
    notes: str = "",
) -> dict[str, Any]:
    """Attach an artifact to a project -- a CAD file, circuit netlist, sim
    result, fabrication doc, or reference link. artifact_type is freeform
    (e.g. "cad", "circuit", "sim_result", "file", "link")."""
    return _life_os.add_project_artifact(
        project_id=project_id, artifact_type=artifact_type, name=name, path=path, url=url, notes=notes,
    )


@mcp.tool()
async def project_add_note(project_id: str, text: str) -> dict[str, Any]:
    """Append a timestamped note to a project's running log."""
    return _life_os.add_project_note(project_id=project_id, text=text)


@mcp.tool()
async def profile_get() -> dict[str, Any]:
    """Return persistent user profile context (tone, goals, constraints,
    coding style notes) used by the intent-aware prompt layer."""
    return _profile_store.get()


@mcp.tool()
async def profile_update(
    name: Optional[str] = None,
    preferred_tone: Optional[str] = None,
    coding_style_notes: Optional[list[str]] = None,
    goals: Optional[list[str]] = None,
    constraints: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Update persistent user profile context to steer how JARVIS reasons,
    plans, and communicates across sessions."""
    return _profile_store.update(
        name=name,
        preferred_tone=preferred_tone,
        coding_style_notes=coding_style_notes,
        goals=goals,
        constraints=constraints,
    )


# ---------------- Phase 2: Calendar / Gmail / Canvas ----------------

@mcp.tool()
async def calendar_list_events(calendar_id: str = "primary", max_results: int = 20, time_min: str = "") -> dict[str, Any]:
    """List upcoming Google Calendar events."""
    return await _google.list_events(calendar_id=calendar_id, max_results=max_results, time_min=time_min)


@mcp.tool()
async def calendar_create_event(
    summary: str,
    start_iso: str,
    end_iso: str,
    calendar_id: str = "primary",
    description: str = "",
    location: str = "",
    recurrence: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Create a Google Calendar event (start_iso/end_iso are RFC3339, e.g.
    2026-09-01T14:00:00-04:00). Pass recurrence as RRULE strings, e.g.
    ["RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR"] for a recurring class/meeting."""
    return await _google.create_event(
        summary=summary, start_iso=start_iso, end_iso=end_iso,
        calendar_id=calendar_id, description=description, location=location,
        recurrence=recurrence,
    )


@mcp.tool()
async def calendar_update_event(
    event_id: str,
    calendar_id: str = "primary",
    summary: Optional[str] = None,
    start_iso: Optional[str] = None,
    end_iso: Optional[str] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
    recurrence: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Update fields on an existing Google Calendar event -- only pass the
    fields you want changed, everything else stays as-is. Use
    calendar_list_events first to find the event_id."""
    return await _google.update_event(
        event_id=event_id, calendar_id=calendar_id, summary=summary,
        start_iso=start_iso, end_iso=end_iso, description=description,
        location=location, recurrence=recurrence,
    )


@mcp.tool()
async def calendar_delete_event(event_id: str, calendar_id: str = "primary") -> dict[str, Any]:
    """Delete a Google Calendar event. Use calendar_list_events first to find the event_id."""
    return await _google.delete_event(event_id=event_id, calendar_id=calendar_id)


@mcp.tool()
async def email_scan_inbox(query: str = "is:unread", max_results: int = 10) -> dict[str, Any]:
    """Scan Gmail inbox (read-only) for messages matching a Gmail search query,
    returning subject/from/date/snippet for quick triage. Never sends/deletes."""
    return await _google.scan_inbox(query=query, max_results=max_results)


@mcp.tool()
async def canvas_list_courses() -> dict[str, Any]:
    """List active Canvas courses."""
    return await _canvas.list_courses()


@mcp.tool()
async def canvas_list_upcoming_assignments(days_ahead: int = 14) -> dict[str, Any]:
    """List upcoming Canvas assignments across active courses within a day window,
    pre-shaped for planner_estimate_canvas_workload."""
    return await _canvas.list_upcoming_assignments(days_ahead=days_ahead)


@mcp.tool()
async def canvas_estimate_workload(days_ahead: int = 14) -> dict[str, Any]:
    """Fetch upcoming Canvas assignments and estimate total workload hours in one call."""
    result = await _canvas.list_upcoming_assignments(days_ahead=days_ahead)
    return _life_os.estimate_canvas_workload(result.get("assignments", []))


@mcp.tool()
async def canvas_list_grades() -> dict[str, Any]:
    """Current grade per active Canvas course -- used to weigh which
    upcoming assignments deserve the most focus."""
    return await _canvas.list_grades()


@mcp.tool()
async def reminders_add(title: str, due_date_iso: str = "", notes: str = "", list_name: str = "") -> dict[str, Any]:
    """Add an item to Apple Reminders (local Reminders.app). Defaults to the
    "JARVIS" list; pass list_name to target a different one (e.g. "Classes")."""
    return await _reminders.add_reminder(title=title, due_date_iso=due_date_iso, notes=notes, list_name=list_name)


@mcp.tool()
async def reminders_list(list_name: str = "", include_completed: bool = False) -> dict[str, Any]:
    """List items in an Apple Reminders list (defaults to the "JARVIS" list)."""
    return await _reminders.list_reminders(list_name=list_name, include_completed=include_completed)


@mcp.tool()
async def reminders_complete(reminder_id: str, list_name: str = "") -> dict[str, Any]:
    """Mark an Apple Reminders item complete. Use reminders_list first to find the id."""
    return await _reminders.complete_reminder(reminder_id=reminder_id, list_name=list_name)


@mcp.tool()
async def daily_briefing_run(days_ahead: int = 7, max_hours_per_day: float = 8.0) -> dict[str, Any]:
    """Run the full daily assignment ingest: pulls upcoming Canvas
    assignments + current grades, estimates workload, pushes any new due
    dates to Google Calendar and classes to Apple Reminders (deduped
    against previously-synced assignments), and returns a spoken-friendly
    summary in summary_text. This is what powers the morning briefing --
    call it directly to get today's "what do I need to do" rundown."""
    return await _daily_briefing.run(days_ahead=days_ahead, max_hours_per_day=max_hours_per_day)


@mcp.tool()
async def homework_help() -> str:
    """Look at whatever's currently on screen (active app, window, and a
    vision-model description of visible content) so you can help the user
    who's stuck on it -- explain a problem, debug an error, walk through a
    concept. Call this whenever the user says something like "I'm stuck",
    "help me with this", or "I don't get this" without specifying what "this"
    is; the answer is on their screen."""
    result = await _tool_executor.execute(ToolCall(action="read_screen", params={}))
    if not result.success:
        raise RuntimeError(result.error or result.output)
    return result.output


@mcp.tool()
async def fitness_latest_recovery() -> dict[str, Any]:
    """Latest Garmin recovery snapshot from Volt (HRV, sleep score, resting HR, stress).
    Requires ./fitness.sh running -- see jarvis/services/fitness."""
    return await _fitness.latest_recovery()


@mcp.tool()
async def fitness_recovery_history(limit: int = 14) -> dict[str, Any]:
    """Recent Garmin recovery history from Volt, most recent last."""
    return await _fitness.recovery_history(limit=limit)


@mcp.tool()
async def fitness_list_workouts(limit: int = 14) -> dict[str, Any]:
    """Recent logged strength-training sessions from Volt (exercise, sets, reps, weight)."""
    return await _fitness.list_workouts(limit=limit)


@mcp.tool()
async def fitness_todays_workout() -> dict[str, Any]:
    """Volt's AI coach recommendation for today's workout, reasoned from recent
    training load and current recovery."""
    return await _fitness.todays_workout()


@mcp.tool()
async def fitness_save_workout_to_garmin(name: str, exercises: list[dict[str, Any]]) -> dict[str, Any]:
    """Push a workout to the user's Garmin Connect workout library so it's selectable
    on their watch. exercises: [{name, sets, reps, target_weight?, notes?}, ...]."""
    return await _fitness.save_workout_to_garmin(name=name, exercises=exercises)


@mcp.tool()
async def fitness_coach_chat(message: str) -> dict[str, Any]:
    """Ask Volt's coach a training question -- it has direct access to the user's
    training history, recovery data, and persistent memory of injuries/goals/equipment."""
    return await _fitness.coach_chat(message=message)


@mcp.tool()
async def fitness_nutrition_logs(limit: int = 14) -> dict[str, Any]:
    """Recent nutrition logs (calories/macros) synced from Cronometer via Volt."""
    return await _fitness.nutrition_logs(limit=limit)


def run() -> None:
    logger.info("MCP tool server listening on stdio (jarvis-workshop-tools)")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    run()
