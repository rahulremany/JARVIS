#!/usr/bin/env python3
"""Ported from src/index.ts -- FastAPI entrypoint (replaces the Fastify server)."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse

load_dotenv()

from .asr.asr_whisper import AsrWhisper  # noqa: E402
from .conversation.conversation_handler import ConversationHandler  # noqa: E402
from .engines.claude.claude_engine import ClaudeEngine  # noqa: E402
from .policy.load_policy import load_policy  # noqa: E402
from .router.engine_selector import EngineSelector  # noqa: E402
from .session.session_manager import SessionManager  # noqa: E402
from .session.user_profile import UserProfileStore  # noqa: E402
from .tools.canvas_adapter import CanvasAdapter  # noqa: E402
from .tools.daily_briefing import DailyBriefingService  # noqa: E402
from .tools.device_actions import DeviceActions  # noqa: E402
from .tools.google_adapter import GoogleAdapter  # noqa: E402
from .tools.life_os import LifeOSService  # noqa: E402
from .tools.reminders_adapter import RemindersAdapter  # noqa: E402
from .utils.env import load_env  # noqa: E402
from .utils.logging import logger  # noqa: E402

# Same state directory the MCP server (jarvis/mcp/server.py) writes to, so the
# Electron UI and MCP-driven tool calls read/write the same JSON store.
WORKSPACE_ROOT = Path(os.environ.get("JARVIS_WORKSPACE_ROOT", Path.cwd())).resolve()
life_os = LifeOSService(state_dir=WORKSPACE_ROOT / ".jarvis_state")
profile_store = UserProfileStore(state_dir=WORKSPACE_ROOT / ".jarvis_state")
daily_briefing = DailyBriefingService(
    canvas=CanvasAdapter(), google=GoogleAdapter(), reminders=RemindersAdapter(), life_os=life_os,
)

app = FastAPI(title="JARVIS")

# The Electron frontend is a separate local process (file:// / localhost origin) --
# this backend only ever runs on the user's own machine, so a wide-open CORS
# policy doesn't expose anything beyond what's already reachable on localhost.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

claude_engine: ClaudeEngine
session_manager: SessionManager
engine_selector: EngineSelector
device_actions: DeviceActions
conversation_handler: ConversationHandler
asr_whisper: Optional[AsrWhisper] = None


@app.on_event("startup")
async def initialize() -> None:
    global claude_engine, session_manager, engine_selector, device_actions, conversation_handler, asr_whisper

    print("\n🤖 JARVIS - Personal AI Assistant")
    print("=================================\n")

    env = load_env()
    logger.set_level(env.log_level)  # type: ignore[arg-type]
    if env.mode == "prod":
        logger.set_sample_rate(0.05)

    policy = load_policy()

    if not env.anthropic_api_key:
        logger.error("[JARVIS] ❌ ANTHROPIC_API_KEY not set!")
        logger.error("[JARVIS] Add it to your .env file to continue.")
        sys.exit(1)

    logger.info("🔥 Initializing ClaudeEngine...")
    claude_engine = ClaudeEngine(env.anthropic_api_key)

    session_manager = SessionManager()
    engine_selector = EngineSelector(claude_engine, policy, session_manager)
    device_actions = DeviceActions()

    await claude_engine.smoke_test(policy.models.router.id)

    conversation_handler = ConversationHandler(session_manager=session_manager)

    try:
        logger.info("🎙️ Loading Whisper ASR (mic transcription)...")
        asr_whisper = AsrWhisper()
        asr_whisper.initialize()
    except Exception as error:  # noqa: BLE001
        logger.warn("Whisper failed to load -- /transcribe will be unavailable:", error)
        asr_whisper = None

    logger.info("✅ JARVIS initialization complete")


@app.get("/health/claude")
async def health_claude():
    return claude_engine.get_health()


@app.get("/health/summary")
async def health_summary():
    return {
        "claude": claude_engine.get_health(),
        "sessions": session_manager.get_session_count(),
        "latency_stats": logger.get_latency_stats(),
        "recent_logs": logger.get_latency_logs()[-10:],
    }


@app.post("/chat")
async def chat(request: Request):
    body = await request.json()
    prompt, session_id = body.get("prompt", ""), body.get("session_id", "default")

    if not prompt.strip():
        return JSONResponse({"error": "Prompt is required"}, status_code=400)

    session_manager.append_user(session_id, prompt)
    result = await engine_selector.generate_with_fallback(prompt, session_id)

    if result["type"] == "direct_command":
        device_result = await device_actions.execute_direct_command(prompt)
        session_manager.append_assistant(session_id, device_result["message"])
        return {
            "type": "direct_command", "response": device_result["message"],
            "action": device_result["action"], "device": device_result["device"],
            "success": device_result["success"],
        }

    async def token_stream():
        full_response = ""
        async for event in result["stream"]:
            if event.type == "narration" and event.text:
                # Surface in-progress status live in the stream (e.g. "checking
                # your calendar...") without polluting the stored session
                # history -- only the final answer gets remembered as what
                # JARVIS actually said.
                yield f"[{event.text}]\n"
            elif event.type == "token" and event.text:
                full_response += event.text
                yield event.text
        session_manager.append_assistant(session_id, full_response)

    return StreamingResponse(token_stream(), media_type="text/plain")


@app.post("/chat/test")
async def chat_test(request: Request):
    body = await request.json()
    text, session_id = body.get("text", ""), body.get("session_id", "default")

    if not text.strip():
        return JSONResponse({"error": "Text is required"}, status_code=400)

    # ConversationHandler.handle_text_input owns session history bookkeeping
    # itself now (shares this same session_manager instance) -- don't
    # double-append here.
    response = await conversation_handler.handle_text_input(text, claude_engine, session_id)

    import time
    return {"user": text, "jarvis": response, "session_id": session_id, "timestamp": time.time() * 1000}


@app.post("/chat/speak")
async def chat_speak(request: Request):
    body = await request.json()
    text = body.get("text", "")
    if not text.strip():
        return JSONResponse({"error": "Text is required"}, status_code=400)

    await conversation_handler.process_and_speak(text, "system")
    return {"success": True, "spoken": text}


@app.post("/daily/briefing")
async def run_daily_briefing(request: Request):
    """Runs the daily assignment ingest (Canvas -> calendar/reminders sync +
    workload summary) and speaks the result. Meant to be hit once a day by a
    launchd/cron job -- see scripts/daily_briefing.sh -- but safe to call
    on demand from the frontend too."""
    body = await request.json() if await request.body() else {}
    days_ahead = body.get("days_ahead", 7)
    speak = body.get("speak", True)

    result = await daily_briefing.run(days_ahead=days_ahead)

    if speak and result["summary_text"]:
        await conversation_handler.process_and_speak(result["summary_text"], "system")

    return result


@app.post("/transcribe")
async def transcribe(file: UploadFile):
    if asr_whisper is None:
        return JSONResponse({"error": "Whisper is not available on this server"}, status_code=503)

    import os as _os
    import tempfile

    import whisper

    audio_bytes = await file.read()
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        audio = whisper.load_audio(tmp_path)  # ffmpeg-based decode -- handles the webm/opus MediaRecorder sends
        result = asr_whisper.transcribe(audio, sample_rate=16000)
        return {"text": result.text, "duration_ms": result.duration}
    finally:
        _os.remove(tmp_path)


@app.post("/notes/lecture")
async def lecture_notes(file: UploadFile, title: str = ""):
    """Voice transcription mode: a whole recording (lecture/meeting, no
    length cap) in, organized study notes out. Uses transcribe_long_form
    (no 30s cap, unlike /transcribe) then a single batched Claude call --
    see jarvis/tools/lecture_notes.py for why batched instead of updated
    continuously through the recording. Local Whisper transcription only,
    no cost; a several-minute wait for a long recording is expected."""
    if asr_whisper is None:
        return JSONResponse({"error": "Whisper is not available on this server"}, status_code=503)

    import os as _os
    import tempfile
    import time as _time

    import whisper

    from .tools.lecture_notes import build_lecture_notes

    audio_bytes = await file.read()
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        audio = whisper.load_audio(tmp_path)
        transcribe_start = _time.perf_counter()
        result = asr_whisper.transcribe_long_form(audio, sample_rate=16000)
        transcribe_ms = (_time.perf_counter() - transcribe_start) * 1000

        notes = await build_lecture_notes(claude_engine, result.text, title=title or None)

        return {
            "transcript": result.text,
            "notes": notes,
            "transcribe_ms": transcribe_ms,
        }
    finally:
        _os.remove(tmp_path)


@app.post("/chat/clear")
async def chat_clear(request: Request):
    body = await request.json()
    session_id = body.get("session_id", "default")
    session_manager.reset(session_id)
    return {"message": "Session cleared", "session_id": session_id}


@app.get("/projects")
async def list_projects(status: Optional[str] = None):
    return {"projects": life_os.list_projects(status=status)}  # type: ignore[arg-type]


@app.get("/projects/{project_id}")
async def get_project(project_id: str):
    try:
        return life_os.get_project(project_id)
    except ValueError as error:
        return JSONResponse({"error": str(error)}, status_code=404)


@app.post("/projects")
async def create_project(request: Request):
    body = await request.json()
    name = body.get("name", "")
    objective = body.get("objective", "")
    if not name.strip() or not objective.strip():
        return JSONResponse({"error": "name and objective are required"}, status_code=400)
    return life_os.create_project(
        name=name, objective=objective,
        constraints=body.get("constraints"), budget=body.get("budget"), deadline=body.get("deadline", ""),
    )


@app.post("/projects/{project_id}/status")
async def update_project_status(project_id: str, request: Request):
    body = await request.json()
    status = body.get("status", "")
    try:
        return life_os.update_project_status(project_id=project_id, status=status)  # type: ignore[arg-type]
    except ValueError as error:
        return JSONResponse({"error": str(error)}, status_code=404)


@app.post("/projects/{project_id}/artifacts")
async def add_project_artifact(project_id: str, request: Request):
    body = await request.json()
    try:
        return life_os.add_project_artifact(
            project_id=project_id,
            artifact_type=body.get("type", "file"),
            name=body.get("name", ""),
            path=body.get("path", ""),
            url=body.get("url", ""),
            notes=body.get("notes", ""),
        )
    except ValueError as error:
        return JSONResponse({"error": str(error)}, status_code=404)


@app.post("/projects/{project_id}/notes")
async def add_project_note(project_id: str, request: Request):
    body = await request.json()
    try:
        return life_os.add_project_note(project_id=project_id, text=body.get("text", ""))
    except ValueError as error:
        return JSONResponse({"error": str(error)}, status_code=404)


@app.get("/profile")
async def get_profile():
    return profile_store.get()


@app.post("/profile")
async def update_profile(request: Request):
    body = await request.json()
    return profile_store.update(
        name=body.get("name"),
        preferred_tone=body.get("preferred_tone"),
        coding_style_notes=body.get("coding_style_notes"),
        goals=body.get("goals"),
        constraints=body.get("constraints"),
    )


def run() -> None:
    env = load_env()
    uvicorn.run("jarvis.main:app", host="127.0.0.1", port=env.port, log_level="info")


if __name__ == "__main__":
    run()
