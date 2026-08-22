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

from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from ..tools.device_actions import DeviceActions, DeviceCommand
from ..tools.tool_executor import ToolCall, ToolExecutor
from ..utils.logging import logger

mcp = FastMCP("jarvis-workshop-tools")

_tool_executor = ToolExecutor()
_device_actions = DeviceActions()


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


def run() -> None:
    logger.info("MCP tool server listening on stdio (jarvis-workshop-tools)")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    run()
