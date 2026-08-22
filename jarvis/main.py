#!/usr/bin/env python3
"""Ported from src/index.ts -- FastAPI entrypoint (replaces the Fastify server)."""
from __future__ import annotations

import sys

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse

load_dotenv()

from .conversation.conversation_handler import ConversationHandler  # noqa: E402
from .engines.heavy.vllm_engine import VllmEngine  # noqa: E402
from .engines.local.local_llama_engine import LocalLlamaEngine  # noqa: E402
from .engines.local.model_map import MODEL_CATALOG  # noqa: E402
from .policy.load_policy import load_policy  # noqa: E402
from .router.engine_selector import EngineSelector  # noqa: E402
from .session.session_manager import SessionManager  # noqa: E402
from .tools.device_actions import DeviceActions  # noqa: E402
from .utils.env import load_env  # noqa: E402
from .utils.logging import logger  # noqa: E402

app = FastAPI(title="JARVIS")

local_engine: LocalLlamaEngine
vllm_engine: VllmEngine | None = None
session_manager: SessionManager
engine_selector: EngineSelector
device_actions: DeviceActions
conversation_handler: ConversationHandler


def validate_models() -> None:
    import os

    logger.info("[JARVIS] 🔍 Validating GGUF models...")
    available = [m for m in MODEL_CATALOG if os.path.exists(m.path)]
    for m in available:
        logger.info(f"[JARVIS] ✅ Found: {m.id} -> {os.path.abspath(m.path)}")
    if not available:
        logger.error("[JARVIS] ❌ No GGUF models found!")
        logger.error("[JARVIS] Please download at least one model to continue.")
        sys.exit(1)


@app.on_event("startup")
async def initialize() -> None:
    global local_engine, vllm_engine, session_manager, engine_selector, device_actions, conversation_handler

    print("\n🤖 JARVIS - Personal AI Assistant")
    print("=================================\n")

    env = load_env()
    logger.set_level(env.log_level)  # type: ignore[arg-type]
    if env.mode == "prod":
        logger.set_sample_rate(0.05)

    policy = load_policy()
    validate_models()

    logger.info("🔥 Initializing LocalLlamaEngine...")
    local_engine = LocalLlamaEngine()

    if policy.endpoints.vllm_base_url:
        logger.info("⚡ Initializing VllmEngine...")
        vllm_engine = VllmEngine(policy.endpoints.vllm_base_url)
        await vllm_engine.health_check()
    else:
        logger.info("⚡ vLLM not configured - heavy tier disabled")

    session_manager = SessionManager()
    engine_selector = EngineSelector(local_engine, vllm_engine, policy)
    device_actions = DeviceActions()

    await local_engine.smoke_test()

    conversation_handler = ConversationHandler()

    logger.info("✅ JARVIS initialization complete")


@app.get("/health/local")
async def health_local():
    return local_engine.get_health()


@app.get("/health/heavy")
async def health_heavy():
    return vllm_engine.get_health() if vllm_engine else {"ok": False, "reason": "not_configured"}


@app.get("/health/summary")
async def health_summary():
    return {
        "local": local_engine.get_health(),
        "heavy": vllm_engine.get_health() if vllm_engine else {"ok": False, "reason": "not_configured"},
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
            if event.type == "token" and event.text:
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

    session_manager.append_user(session_id, text)
    response = await conversation_handler.handle_text_input(text, local_engine, session_id)
    session_manager.append_assistant(session_id, response)

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


@app.post("/chat/clear")
async def chat_clear(request: Request):
    body = await request.json()
    session_id = body.get("session_id", "default")
    session_manager.reset(session_id)
    return {"message": "Session cleared", "session_id": session_id}


def run() -> None:
    env = load_env()
    uvicorn.run("jarvis.main:app", host="127.0.0.1", port=env.port, log_level="info")


if __name__ == "__main__":
    run()
