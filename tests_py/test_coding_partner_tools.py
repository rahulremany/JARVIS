"""Tests for the coding-partner MCP tools -- write/edit/delete files, run
real dev commands, search across the workspace, and gather code-review
context. These exercise the underlying ToolExecutor/server logic directly
rather than going through the MCP stdio transport."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from jarvis.tools.tool_executor import ToolExecutor


def test_dev_commands_allowlist_includes_common_tooling():
    assert "git" in ToolExecutor.DEV_COMMANDS
    assert "pytest" in ToolExecutor.DEV_COMMANDS
    assert "npm" in ToolExecutor.DEV_COMMANDS
    assert "python3" in ToolExecutor.DEV_COMMANDS


@pytest.mark.asyncio
async def test_run_dev_command_executes_allowed_binary(tmp_path: Path):
    executor = ToolExecutor()
    result = await executor.run_dev_command("echo hello-jarvis", cwd=str(tmp_path))
    assert result.success is True
    assert "hello-jarvis" in result.output


@pytest.mark.asyncio
async def test_run_dev_command_rejects_non_allowlisted_binary(tmp_path: Path):
    executor = ToolExecutor()
    result = await executor.run_dev_command("curl https://example.com", cwd=str(tmp_path))
    assert result.success is False
    assert "not in the dev commands allowlist" in result.output


@pytest.mark.asyncio
async def test_run_dev_command_blocks_dangerous_patterns(tmp_path: Path):
    executor = ToolExecutor()
    result = await executor.run_dev_command("git push --force", cwd=str(tmp_path))
    assert result.success is False
    assert "safety pattern" in result.output.lower()


@pytest.mark.asyncio
async def test_run_dev_command_times_out(tmp_path: Path):
    executor = ToolExecutor()
    result = await executor.run_dev_command("python3 -c \"import time; time.sleep(5)\"", cwd=str(tmp_path), timeout_s=0.2)
    assert result.success is False
    assert "timed out" in result.output.lower()


@pytest.mark.asyncio
async def test_run_dev_command_reports_nonzero_exit(tmp_path: Path):
    executor = ToolExecutor()
    result = await executor.run_dev_command("python3 -c \"import sys; sys.exit(1)\"", cwd=str(tmp_path))
    assert result.success is False
    assert result.error == "Exit code 1"
