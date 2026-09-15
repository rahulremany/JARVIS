from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.tools.agent_tools import AgentToolRegistry


@pytest.mark.asyncio
async def test_agent_tools_write_read_edit_delete_file(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JARVIS_WORKSPACE_ROOT", str(tmp_path))
    registry = AgentToolRegistry()

    await registry.invoke("write_workspace_file", {
        "path": "notes/test.txt",
        "content": "hello world",
        "overwrite": True,
    })

    read = await registry.invoke("read_workspace_file", {"path": "notes/test.txt", "start_line": 1, "end_line": 10})
    assert "hello world" in read["content"]

    edited = await registry.invoke("edit_workspace_file", {
        "path": "notes/test.txt",
        "old_string": "world",
        "new_string": "jarvis",
        "expected_replacements": 1,
    })
    assert edited["replacements_made"] == 1

    read2 = await registry.invoke("read_workspace_file", {"path": "notes/test.txt", "start_line": 1, "end_line": 10})
    assert "hello jarvis" in read2["content"]

    deleted = await registry.invoke("delete_workspace_file", {"path": "notes/test.txt"})
    assert deleted["deleted"] is True


@pytest.mark.asyncio
async def test_agent_tools_profile_roundtrip(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JARVIS_WORKSPACE_ROOT", str(tmp_path))
    registry = AgentToolRegistry()

    await registry.invoke("profile_update", {
        "name": "Rahul",
        "preferred_tone": "direct",
        "goals": ["build camera mouse"],
    })

    profile = await registry.invoke("profile_get", {})
    assert profile["name"] == "Rahul"
    assert profile["goals"] == ["build camera mouse"]


@pytest.mark.asyncio
async def test_agent_tools_project_create_and_note(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JARVIS_WORKSPACE_ROOT", str(tmp_path))
    registry = AgentToolRegistry()

    project = await registry.invoke("project_create", {
        "name": "Camera Mouse",
        "objective": "Hand gestures control macOS cursor",
    })

    updated = await registry.invoke("project_add_note", {
        "project_id": project["id"],
        "text": "Need stable pinch gesture detector",
    })

    assert updated["id"] == project["id"]
    assert len(updated["notes"]) == 1


@pytest.mark.asyncio
async def test_create_desktop_project_defaults_to_projects_root(tmp_path: Path, monkeypatch):
    workspace_root = tmp_path / "workspace"
    projects_root = tmp_path / "Desktop"
    monkeypatch.setenv("JARVIS_WORKSPACE_ROOT", str(workspace_root))
    monkeypatch.setenv("JARVIS_PROJECTS_ROOT", str(projects_root))
    registry = AgentToolRegistry()

    created = await registry.invoke("create_desktop_project", {
        "name": "Basic Greeter",
        "description": "Tiny starter app",
    })

    project_root = Path(created["project_root"])
    assert project_root.parent == projects_root
    assert project_root.name == "basic-greeter"
    assert (project_root / "main.py").exists()
    assert (project_root / "README.md").exists()


@pytest.mark.asyncio
async def test_create_desktop_project_rejects_escape_path(tmp_path: Path, monkeypatch):
    workspace_root = tmp_path / "workspace"
    projects_root = tmp_path / "Desktop"
    monkeypatch.setenv("JARVIS_WORKSPACE_ROOT", str(workspace_root))
    monkeypatch.setenv("JARVIS_PROJECTS_ROOT", str(projects_root))
    registry = AgentToolRegistry()

    with pytest.raises(ValueError):
        await registry.invoke("create_desktop_project", {
            "name": "Unsafe",
            "target_dir": "../outside",
        })
