from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class IntentBrief:
    goal: str
    domain: str
    likely_tools: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)
    confidence: float = 0.6

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class IntentInterpreter:
    """Best-effort semantic interpreter for short, underspecified prompts.

    This does not rely on exact trigger phrases. It infers a structured task
    brief the model can use to act with less back-and-forth.
    """

    def interpret(self, text: str) -> IntentBrief:
        lower = text.lower().strip()

        domain = self._infer_domain(lower)
        tools = self._infer_tools(lower, domain)
        constraints = self._infer_constraints(lower)
        success = self._infer_success(lower, domain)
        confidence = self._confidence(lower, domain, tools)

        goal = text.strip() or "Handle the user's request"
        return IntentBrief(
            goal=goal,
            domain=domain,
            likely_tools=tools,
            constraints=constraints,
            success_criteria=success,
            confidence=confidence,
        )

    def _infer_domain(self, text: str) -> str:
        if any(token in text for token in ("code", "debug", "refactor", "test", "build", "program")):
            return "software_engineering"
        if any(token in text for token in ("calendar", "email", "canvas", "schedule", "plan")):
            return "planning_organization"
        if any(token in text for token in ("fabricat", "cad", "circuit", "prototype", "monitor")):
            return "rd_fabrication"
        return "general"

    def _infer_tools(self, text: str, domain: str) -> list[str]:
        tools: list[str] = []

        if domain == "software_engineering":
            tools.extend(["search_workspace", "read_workspace_file", "edit_workspace_file", "run_dev_command", "code_review_file"])
        if domain == "planning_organization":
            tools.extend(["planner_add_item", "planner_daily_brief", "calendar_list_events", "email_scan_inbox", "canvas_estimate_workload"])
        if domain == "rd_fabrication":
            tools.extend(["project_create", "project_add_artifact", "project_add_note", "fabrication_project_plan"])

        if any(token in text for token in ("run", "execute", "test")) and "run_dev_command" not in tools:
            tools.append("run_dev_command")
        if any(token in text for token in ("search", "find", "where")) and "search_workspace" not in tools:
            tools.append("search_workspace")
        if any(token in text for token in ("create", "scaffold", "starter", "boilerplate")) and "project" in text:
            tools.append("create_desktop_project")

        # Preserve deterministic order and remove duplicates.
        seen = set()
        ordered: list[str] = []
        for tool in tools:
            if tool not in seen:
                seen.add(tool)
                ordered.append(tool)
        return ordered

    def _infer_constraints(self, text: str) -> list[str]:
        constraints: list[str] = []
        if any(token in text for token in ("fast", "asap", "quick", "soon")):
            constraints.append("prioritize_speed")
        if any(token in text for token in ("safe", "careful", "secure", "don't break")):
            constraints.append("prioritize_safety")
        if any(token in text for token in ("minimal", "small", "surgical")):
            constraints.append("minimal_changes")
        return constraints

    def _infer_success(self, text: str, domain: str) -> list[str]:
        if domain == "software_engineering":
            return [
                "Changes compile or lint cleanly",
                "Relevant tests pass",
                "Result is explained with next steps",
            ]
        if domain == "rd_fabrication":
            return [
                "A structured build plan is produced",
                "Artifacts and notes are attached to project workspace",
                "Risks and assumptions are explicit",
            ]
        return ["User objective is completed with clear output"]

    def _confidence(self, text: str, domain: str, tools: list[str]) -> float:
        score = 0.45
        if domain != "general":
            score += 0.2
        if len(tools) >= 3:
            score += 0.2
        if len(text) >= 20:
            score += 0.1
        return min(score, 0.95)
