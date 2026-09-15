from pathlib import Path

import pytest

from jarvis.tools.life_os import LifeOSService


def _service(tmp_path: Path) -> LifeOSService:
    return LifeOSService(state_dir=tmp_path / ".state")


def test_add_and_list_task(tmp_path: Path):
    service = _service(tmp_path)
    created = service.add_task(
        title="Debug laser cutter feed",
        details="Tune stepper current and retest",
        due_date="2026-09-02",
        estimate_hours=2.5,
        tags=["fabrication", "debug"],
    )

    tasks = service.list_tasks()
    assert len(tasks) == 1
    assert tasks[0]["id"] == created["id"]
    assert tasks[0]["title"] == "Debug laser cutter feed"


def test_update_task_status(tmp_path: Path):
    service = _service(tmp_path)
    created = service.add_task("Build enclosure")
    updated = service.update_task_status(created["id"], "in_progress")

    assert updated["status"] == "in_progress"
    listed = service.list_tasks(status="in_progress")
    assert len(listed) == 1


def test_canvas_sync_bookkeeping(tmp_path: Path):
    service = _service(tmp_path)
    assert service.get_synced_canvas_ids() == set()

    service.mark_canvas_synced(["Course A::HW1::2026-09-05"])
    assert service.get_synced_canvas_ids() == {"Course A::HW1::2026-09-05"}

    service.mark_canvas_synced(["Course A::HW2::2026-09-06"])
    assert service.get_synced_canvas_ids() == {
        "Course A::HW1::2026-09-05", "Course A::HW2::2026-09-06",
    }


def test_daily_plan_respects_hour_budget(tmp_path: Path):
    service = _service(tmp_path)
    service.add_task("Task A", estimate_hours=2)
    service.add_task("Task B", estimate_hours=3)
    service.add_task("Task C", estimate_hours=4)

    plan = service.daily_plan(max_hours=5)
    assert plan["planned_hours"] <= 5
    assert len(plan["tasks"]) >= 1


def test_estimate_canvas_workload(tmp_path: Path):
    service = _service(tmp_path)
    result = service.estimate_canvas_workload([
        {"title": "Lab Report", "points": 100, "complexity": "hard"},
        {"title": "Quiz", "points": 20, "complexity": "easy"},
    ])

    assert result["count"] == 2
    assert result["total_estimated_hours"] > 0


def test_fabrication_plan_shape(tmp_path: Path):
    service = _service(tmp_path)
    plan = service.create_fabrication_plan(
        project_name="Desk CNC Jig",
        objective="Create repeatable alignment jig",
        constraints=["budget under 200", "finish this week"],
        budget=200,
        deadline="2026-09-07",
    )

    assert plan["project_name"] == "Desk CNC Jig"
    assert len(plan["phases"]) == 4
    assert len(plan["risk_checks"]) > 0


def test_fitness_log_and_summary(tmp_path: Path):
    service = _service(tmp_path)
    service.add_fitness_entry({"hr": 62, "sleep_hours": 7.5})
    service.add_fitness_entry({"hr": 66, "sleep_hours": 6.5})

    summary = service.fitness_summary(days=7)
    assert summary["count"] >= 2
    assert "hr" in summary["averages"]


def test_create_project_generates_fabrication_plan(tmp_path: Path):
    service = _service(tmp_path)
    project = service.create_project(
        name="Holographic Monitor",
        objective="Design a desktop holographic projector",
        constraints=["budget under 500"],
        budget=500,
        deadline="2026-12-01",
    )

    assert project["name"] == "Holographic Monitor"
    assert project["status"] == "idea"
    assert project["fabrication_plan"]["project_name"] == "Holographic Monitor"
    assert len(project["fabrication_plan"]["phases"]) == 4
    assert project["artifacts"] == []
    assert project["notes"] == []


def test_project_list_get_and_status_update(tmp_path: Path):
    service = _service(tmp_path)
    created = service.create_project(name="Handless Mouse", objective="Eye + hand tracking cursor control")

    listed = service.list_projects()
    assert len(listed) == 1
    assert listed[0]["id"] == created["id"]

    fetched = service.get_project(created["id"])
    assert fetched["id"] == created["id"]

    updated = service.update_project_status(created["id"], "building")
    assert updated["status"] == "building"

    filtered = service.list_projects(status="building")
    assert len(filtered) == 1

    with pytest.raises(ValueError):
        service.get_project("nonexistent")


def test_project_add_artifact_and_note(tmp_path: Path):
    service = _service(tmp_path)
    created = service.create_project(name="Circuit Board", objective="IR sensor breakout")

    updated = service.add_project_artifact(
        created["id"], artifact_type="circuit", name="ir_sensor.sch", notes="First draft schematic",
    )
    assert len(updated["artifacts"]) == 1
    assert updated["artifacts"][0]["type"] == "circuit"

    updated = service.add_project_note(created["id"], "Ordered parts from DigiKey")
    assert len(updated["notes"]) == 1
    assert updated["notes"][0]["text"] == "Ordered parts from DigiKey"

    with pytest.raises(ValueError):
        service.add_project_note("nonexistent", "test")
