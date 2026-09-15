from pathlib import Path

import pytest


@pytest.fixture()
def server_module():
    pytest.importorskip("mcp.server.fastmcp")
    from jarvis.mcp import server

    return server


def test_safe_path_allows_workspace_relative(tmp_path: Path, server_module):
    server_module.WORKSPACE_ROOT = tmp_path.resolve()
    target = tmp_path / "notes.txt"
    target.write_text("hello", encoding="utf-8")

    resolved = server_module._safe_path("notes.txt", must_exist=True)
    assert resolved == target.resolve()


def test_safe_path_rejects_workspace_escape(tmp_path: Path, server_module):
    server_module.WORKSPACE_ROOT = tmp_path.resolve()

    with pytest.raises(ValueError):
        server_module._safe_path("../outside.txt")


def test_safe_path_requires_existing_when_flag_set(tmp_path: Path, server_module):
    server_module.WORKSPACE_ROOT = tmp_path.resolve()

    with pytest.raises(FileNotFoundError):
        server_module._safe_path("missing.txt", must_exist=True)
