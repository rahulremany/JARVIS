from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal, Optional


TaskStatus = Literal["open", "in_progress", "blocked", "done"]


@dataclass
class PlannerTask:
    id: str
    title: str
    details: str = ""
    due_date: str = ""
    estimate_hours: float = 1.0
    status: TaskStatus = "open"
    source: str = "manual"
    tags: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class FitnessEntry:
    timestamp: str
    source: str
    metrics: dict[str, float]


ProjectStatus = Literal["idea", "planning", "building", "testing", "done", "archived"]


@dataclass
class ProjectArtifact:
    id: str
    type: str  # "cad", "circuit", "sim_result", "fabrication_plan", "file", "link"
    name: str
    path: str = ""
    url: str = ""
    notes: str = ""
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class ProjectNote:
    timestamp: str
    text: str


@dataclass
class ResearchProject:
    id: str
    name: str
    objective: str
    status: ProjectStatus = "idea"
    constraints: list[str] = field(default_factory=list)
    budget: Optional[float] = None
    deadline: str = ""
    fabrication_plan: Optional[dict[str, Any]] = None
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    notes: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class LifeOSService:
    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.tasks_path = self.state_dir / "planner_tasks.json"
        self.fitness_path = self.state_dir / "fitness_metrics.json"
        self.projects_path = self.state_dir / "research_projects.json"
        self.canvas_synced_path = self.state_dir / "canvas_synced.json"

    def _load_json(self, path: Path, fallback: Any) -> Any:
        if not path.exists():
            return fallback
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return fallback

    def _save_json(self, path: Path, value: Any) -> None:
        path.write_text(json.dumps(value, indent=2), encoding="utf-8")

    def _load_tasks(self) -> list[dict[str, Any]]:
        return self._load_json(self.tasks_path, [])

    def _save_tasks(self, tasks: list[dict[str, Any]]) -> None:
        self._save_json(self.tasks_path, tasks)

    def _load_fitness(self) -> list[dict[str, Any]]:
        return self._load_json(self.fitness_path, [])

    def _save_fitness(self, entries: list[dict[str, Any]]) -> None:
        self._save_json(self.fitness_path, entries)

    def _load_projects(self) -> list[dict[str, Any]]:
        return self._load_json(self.projects_path, [])

    def _save_projects(self, projects: list[dict[str, Any]]) -> None:
        self._save_json(self.projects_path, projects)

    # ---------------- Canvas sync bookkeeping ----------------
    # Tracks which Canvas assignments already got a calendar event + reminder
    # created for them, so a daily briefing run doesn't re-create duplicates
    # every time it re-fetches the same upcoming assignment.

    def get_synced_canvas_ids(self) -> set[str]:
        return set(self._load_json(self.canvas_synced_path, []))

    def mark_canvas_synced(self, assignment_keys: list[str]) -> None:
        existing = self.get_synced_canvas_ids()
        existing.update(assignment_keys)
        self._save_json(self.canvas_synced_path, sorted(existing))

    def add_task(
        self,
        title: str,
        details: str = "",
        due_date: str = "",
        estimate_hours: float = 1.0,
        source: str = "voice",
        tags: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        tasks = self._load_tasks()
        task_id = f"task-{int(datetime.utcnow().timestamp() * 1000)}"
        task = PlannerTask(
            id=task_id,
            title=title.strip(),
            details=details.strip(),
            due_date=due_date.strip(),
            estimate_hours=max(0.25, float(estimate_hours)),
            source=source.strip() or "voice",
            tags=[tag.strip() for tag in (tags or []) if tag.strip()],
        )
        tasks.append(asdict(task))
        self._save_tasks(tasks)
        return asdict(task)

    def list_tasks(self, status: Optional[TaskStatus] = None, limit: int = 50) -> list[dict[str, Any]]:
        tasks = self._load_tasks()
        if status:
            tasks = [task for task in tasks if task.get("status") == status]
        tasks.sort(key=lambda task: (task.get("due_date", "") or "9999-99-99", task.get("created_at", "")))
        return tasks[: max(1, min(limit, 500))]

    def update_task_status(self, task_id: str, status: TaskStatus) -> dict[str, Any]:
        tasks = self._load_tasks()
        for task in tasks:
            if task.get("id") == task_id:
                task["status"] = status
                self._save_tasks(tasks)
                return task
        raise ValueError(f"Task not found: {task_id}")

    def daily_plan(self, target_date: str = "", max_hours: float = 8.0) -> dict[str, Any]:
        date_key = target_date.strip() or datetime.utcnow().date().isoformat()
        backlog = [task for task in self._load_tasks() if task.get("status") in ("open", "in_progress")]
        backlog.sort(key=lambda task: (task.get("due_date", "") or "9999-99-99", task.get("estimate_hours", 1.0)))

        selected: list[dict[str, Any]] = []
        planned_hours = 0.0
        budget = max(1.0, float(max_hours))
        for task in backlog:
            estimate = float(task.get("estimate_hours", 1.0))
            if planned_hours + estimate > budget and selected:
                continue
            selected.append(task)
            planned_hours += estimate
            if planned_hours >= budget:
                break

        return {
            "date": date_key,
            "max_hours": budget,
            "planned_hours": round(planned_hours, 2),
            "tasks": selected,
        }

    def estimate_canvas_workload(self, assignments: list[dict[str, Any]]) -> dict[str, Any]:
        total_hours = 0.0
        details: list[dict[str, Any]] = []

        for item in assignments:
            title = str(item.get("title", "Untitled"))
            points = float(item.get("points", 0) or 0)
            complexity = str(item.get("complexity", "normal")).lower()
            base = 0.75 + (points / 20.0)
            if complexity in ("hard", "high"):
                base *= 1.8
            elif complexity in ("easy", "low"):
                base *= 0.8
            estimate = round(max(0.5, base), 2)
            total_hours += estimate
            details.append({
                "title": title,
                "estimated_hours": estimate,
                "due_date": item.get("due_date", ""),
            })

        return {
            "count": len(details),
            "total_estimated_hours": round(total_hours, 2),
            "assignments": details,
        }

    def create_fabrication_plan(
        self,
        project_name: str,
        objective: str,
        constraints: Optional[list[str]] = None,
        budget: Optional[float] = None,
        deadline: str = "",
    ) -> dict[str, Any]:
        constraints = [entry.strip() for entry in (constraints or []) if entry.strip()]
        steps = [
            "Define requirements and acceptance criteria",
            "Draft materials/BOM and sourcing list",
            "Create fabrication setup checklist",
            "Prototype first pass and capture issues",
            "Run debug + calibration cycle",
            "Finalize build notes and handoff checklist",
        ]
        risk_checks = [
            "Power/thermal safety validated",
            "Tooling and fixture alignment verified",
            "Materials tolerances confirmed",
            "Fallback plan for failed part or missed lead time",
        ]

        return {
            "project_name": project_name,
            "objective": objective,
            "constraints": constraints,
            "budget": budget,
            "deadline": deadline,
            "phases": [
                {"name": "Plan", "tasks": steps[:2]},
                {"name": "Build", "tasks": steps[2:4]},
                {"name": "Debug", "tasks": steps[4:5]},
                {"name": "Ship", "tasks": steps[5:]},
            ],
            "risk_checks": risk_checks,
            "next_actions": [
                "Lock BOM and order long-lead parts",
                "Schedule build block on calendar",
                "Create test checklist before first fabrication run",
            ],
        }

    def add_fitness_entry(self, metrics: dict[str, float], source: str = "dashboard") -> dict[str, Any]:
        normalized = {k: float(v) for k, v in metrics.items()}
        entry = FitnessEntry(
            timestamp=datetime.utcnow().isoformat(),
            source=source,
            metrics=normalized,
        )
        entries = self._load_fitness()
        entries.append(asdict(entry))
        self._save_fitness(entries)
        return asdict(entry)

    def fitness_history(self, limit: int = 50) -> list[dict[str, Any]]:
        entries = self._load_fitness()
        entries.sort(key=lambda entry: entry.get("timestamp", ""))
        if limit > 0:
            entries = entries[-limit:]
        return list(reversed(entries))

    def fitness_summary(self, days: int = 7) -> dict[str, Any]:
        entries = self._load_fitness()
        if not entries:
            return {"days": days, "count": 0, "averages": {}, "latest": None}

        cutoff = datetime.utcnow() - timedelta(days=max(1, days))
        recent = []
        for entry in entries:
            timestamp = entry.get("timestamp")
            try:
                dt = datetime.fromisoformat(timestamp)
            except Exception:
                continue
            if dt >= cutoff:
                recent.append(entry)

        if not recent:
            return {"days": days, "count": 0, "averages": {}, "latest": entries[-1]}

        sums: dict[str, float] = {}
        counts: dict[str, int] = {}
        for entry in recent:
            metrics = entry.get("metrics", {})
            for key, value in metrics.items():
                sums[key] = sums.get(key, 0.0) + float(value)
                counts[key] = counts.get(key, 0) + 1

        averages = {key: round(sums[key] / counts[key], 3) for key in sums}
        return {
            "days": days,
            "count": len(recent),
            "averages": averages,
            "latest": recent[-1],
        }

    # ---------------- R&D project workspace ----------------
    # A ResearchProject is the "spine" a build lives on: its fabrication plan,
    # every artifact produced along the way (CAD files, circuit netlists, sim
    # results, links), and a running notes timeline -- all queryable together
    # instead of scattered across disconnected tool calls.

    def create_project(
        self,
        name: str,
        objective: str,
        constraints: Optional[list[str]] = None,
        budget: Optional[float] = None,
        deadline: str = "",
    ) -> dict[str, Any]:
        constraints = [entry.strip() for entry in (constraints or []) if entry.strip()]
        fabrication_plan = self.create_fabrication_plan(
            project_name=name, objective=objective, constraints=constraints, budget=budget, deadline=deadline,
        )

        project_id = f"project-{int(datetime.utcnow().timestamp() * 1000)}"
        project = ResearchProject(
            id=project_id,
            name=name.strip(),
            objective=objective.strip(),
            constraints=constraints,
            budget=budget,
            deadline=deadline.strip(),
            fabrication_plan=fabrication_plan,
        )

        projects = self._load_projects()
        projects.append(asdict(project))
        self._save_projects(projects)
        return asdict(project)

    def list_projects(self, status: Optional[ProjectStatus] = None) -> list[dict[str, Any]]:
        projects = self._load_projects()
        if status:
            projects = [p for p in projects if p.get("status") == status]
        projects.sort(key=lambda p: p.get("updated_at", ""), reverse=True)
        return projects

    def get_project(self, project_id: str) -> dict[str, Any]:
        for project in self._load_projects():
            if project.get("id") == project_id:
                return project
        raise ValueError(f"Project not found: {project_id}")

    def _mutate_project(self, project_id: str, mutator) -> dict[str, Any]:
        projects = self._load_projects()
        for project in projects:
            if project.get("id") == project_id:
                mutator(project)
                project["updated_at"] = datetime.utcnow().isoformat()
                self._save_projects(projects)
                return project
        raise ValueError(f"Project not found: {project_id}")

    def update_project_status(self, project_id: str, status: ProjectStatus) -> dict[str, Any]:
        return self._mutate_project(project_id, lambda p: p.__setitem__("status", status))

    def add_project_artifact(
        self,
        project_id: str,
        artifact_type: str,
        name: str,
        path: str = "",
        url: str = "",
        notes: str = "",
    ) -> dict[str, Any]:
        artifact = ProjectArtifact(
            id=f"artifact-{int(datetime.utcnow().timestamp() * 1000)}",
            type=artifact_type.strip(),
            name=name.strip(),
            path=path.strip(),
            url=url.strip(),
            notes=notes.strip(),
        )
        artifact_dict = asdict(artifact)

        def _mutator(project: dict[str, Any]) -> None:
            project.setdefault("artifacts", []).append(artifact_dict)

        return self._mutate_project(project_id, _mutator)

    def add_project_note(self, project_id: str, text: str) -> dict[str, Any]:
        note = ProjectNote(timestamp=datetime.utcnow().isoformat(), text=text.strip())
        note_dict = asdict(note)

        def _mutator(project: dict[str, Any]) -> None:
            project.setdefault("notes", []).append(note_dict)

        return self._mutate_project(project_id, _mutator)
