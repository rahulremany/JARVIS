import os
from pathlib import Path

from jarvis.router.intent_interpreter import IntentInterpreter
from jarvis.router.engine_selector import EngineSelector


class DummyEngine:
    async def generate_stream(self, *args, **kwargs):
        if False:
            yield None


def test_intent_interpreter_programming_request_maps_to_tools():
    interpreter = IntentInterpreter()
    brief = interpreter.interpret("help me debug this code and run tests fast")

    assert brief.domain == "software_engineering"
    assert "run_dev_command" in brief.likely_tools
    assert "code_review_file" in brief.likely_tools
    assert "prioritize_speed" in brief.constraints


def test_engine_selector_composes_profile_and_intent_context(tmp_path: Path):
    os.environ["JARVIS_WORKSPACE_ROOT"] = str(tmp_path)

    selector = EngineSelector(claude_engine=DummyEngine())
    selector.profile_store.update(
        name="Ada",
        goals=["build weather station"],
        constraints=["minimal_changes"],
    )

    prompt = selector._compose_system_prompt("help me debug code and run tests")
    assert "User Profile Context" in prompt
    assert "Ada" in prompt
    assert "build weather station" in prompt
    assert "Interpreted Intent" in prompt
    assert "software_engineering" in prompt


def test_intent_interpreter_suggests_desktop_project_scaffold_tool():
    interpreter = IntentInterpreter()
    brief = interpreter.interpret("Create a starter project for a basic hello-world app")

    assert "create_desktop_project" in brief.likely_tools
