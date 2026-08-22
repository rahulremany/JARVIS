"""Ported from src/router/Router.ts."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Optional

from ..tools.device_actions import DeviceActions, DeviceCommand
from ..utils.logging import logger

RouteClass = Literal["direct_command", "trivial", "normal", "hard"]

# Which specialist model in the local mesh should handle this request.
# Orthogonal to RouteClass: a request can be "hard" difficulty and still be
# a "coder" facet, or "trivial" and still be a "planner" facet.
Facet = Literal["planner", "coder", "fast"]


@dataclass
class RouteResult:
    route_class: RouteClass
    confidence: float
    reasoning: str
    device_command: Optional[DeviceCommand] = None


class Router:
    def __init__(self) -> None:
        self.device_actions = DeviceActions()

        self.hard_keywords = [
            "multi-step", "full design", "long plan", "refactor large file",
            "architect", "comprehensive", "detailed analysis", "compare multiple",
            "research", "write a report", "create a document", "plan a project",
        ]

        self.direct_command_keywords = [
            "turn on", "turn off", "play music", "stop music", "lock doors",
            "unlock doors", "set temperature", "dim lights", "brighten lights",
            "arm security", "disarm security",
        ]

        # Keywords that indicate a coding/debugging task -> the coder facet
        self.coder_keywords = [
            "code", "function", "class", "algorithm", "implement", "debug",
            "refactor", "unit test", "stack trace", "syntax error", "compile",
            "regex", "script", "boilerplate", "git commit", "api endpoint",
        ]

        # Keywords that indicate planning/brainstorming -> the planner facet
        self.planner_keywords = [
            "plan", "outline", "brainstorm", "kanban", "roadmap", "folder structure",
            "break down", "steps to", "architecture", "design doc", "project goal",
            "compare", "pros and cons", "strategy",
        ]

    def classify(self, text: str) -> RouteResult:
        lower = text.lower().strip()
        logger.debug("Classifying input:", text)

        device_command = self.device_actions.parse_command(text)
        if device_command:
            return RouteResult("direct_command", 0.95, "Detected device/automation command", device_command)

        if any(k in lower for k in self.direct_command_keywords):
            return RouteResult("direct_command", 0.9, "Contains direct command keywords")

        if any(k in lower for k in self.hard_keywords):
            return RouteResult("hard", 0.9, "Contains complexity keywords indicating hard query")

        if len(text) < 10:
            return RouteResult("trivial", 0.7, "Very short input likely trivial")

        if len(text) > 200:
            return RouteResult("hard", 0.8, "Long input suggests complex query")

        question_words = ["what", "why", "how", "when", "where", "who"]
        if any(w in lower for w in question_words):
            if re.match(r"^(what is|what's|who is|who's|when is|when's|where is|where's)", lower):
                return RouteResult("trivial", 0.8, "Simple factual question")
            if "how" in lower and any(w in lower for w in ("work", "implement", "design")):
                return RouteResult("hard", 0.8, "Complex how-to or explanation question")

        if any(w in lower for w in ("code", "function", "class", "algorithm", "implement", "debug")):
            if any(w in lower for w in ("simple", "basic", "quick")):
                return RouteResult("normal", 0.7, "Simple technical query")
            return RouteResult("hard", 0.8, "Technical/coding query")

        if re.search(r"\d+", lower) and any(w in lower for w in ("calculate", "compute", "+", "-", "*", "/")):
            return RouteResult("trivial", 0.8, "Simple calculation")

        return RouteResult("normal", 0.6, "Default classification for conversational input")

    def classify_facet(self, text: str) -> Facet:
        """Classify which mesh specialist should serve this request. Cheap
        keyword pass by design -- routing itself must never cost a model
        invocation."""
        lower = text.lower()

        if any(k in lower for k in self.coder_keywords):
            return "coder"
        if any(k in lower for k in self.planner_keywords):
            return "planner"
        # Short, throwaway requests (autocomplete, summarize-this, quick
        # lookup) default to the always-loaded fast-utility model.
        if len(text) < 120:
            return "fast"
        return "planner"

    def get_engine_tier(self, route_class: RouteClass) -> Literal["router", "primary", "heavy"]:
        if route_class in ("direct_command", "trivial"):
            return "router"
        if route_class == "normal":
            return "primary"
        if route_class == "hard":
            return "heavy"
        return "primary"
