"""Shared workspace root + path-safety helper.

Single source of truth so every tool (the live agent loop in
jarvis/tools/agent_tools.py, and the external-facing MCP server in
jarvis/mcp/server.py) enforces the exact same "can't escape the workspace
root" rule instead of two copies of this logic drifting apart.
"""
from __future__ import annotations

import os
from pathlib import Path

WORKSPACE_ROOT = Path(os.environ.get("JARVIS_WORKSPACE_ROOT", Path.cwd())).resolve()


def safe_path(path: str, must_exist: bool = False) -> Path:
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
