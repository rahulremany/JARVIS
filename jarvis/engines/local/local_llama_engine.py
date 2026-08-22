"""Ported from src/engines/local/LocalLlamaEngine.ts (node-llama-cpp -> llama-cpp-python)."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Literal, Optional

from ...utils.logging import logger
from .model_map import get_system_ram_gb, is_apple_silicon, resolve_model_path

GenerationEventType = Literal["first", "token", "done"]


@dataclass
class GenerationEvent:
    type: GenerationEventType
    text: Optional[str] = None
    timestamp: float = 0.0
    ms: Optional[float] = None


@dataclass
class GenerationParams:
    max_tokens: Optional[int] = None
    ctx: Optional[int] = None
    temperature: Optional[float] = None
    stop: Optional[list[str]] = None


class _HardwareOptimizer:
    """Picks model + llama.cpp settings from available RAM, mirroring the
    TS HardwareOptimizer class."""

    def __init__(self) -> None:
        self.total_ram = get_system_ram_gb()
        self.is_apple_silicon = is_apple_silicon()
        self.cpu_threads = os.cpu_count() or 4

        if self.total_ram <= 8:
            self.model_id = "qwen2.5:3b-instruct-q4_K_M"
            self.gpu_layers = 32 if self.is_apple_silicon else 0
            self.context_size = 512
        elif self.total_ram <= 16:
            self.model_id = "qwen2.5:3b-instruct-q4_K_M"
            self.gpu_layers = 32 if self.is_apple_silicon else 16
            self.context_size = 2048
        else:
            self.model_id = "llama3.1:8b-instruct-q4_K_M"
            self.gpu_layers = 40 if self.is_apple_silicon else 20
            self.context_size = 4096

        self.threads = self.cpu_threads if self.is_apple_silicon else max(1, self.cpu_threads // 2)

        logger.info("🔧 Hardware Optimization:", {
            "ram": f"{self.total_ram}GB", "threads": self.threads,
            "appleSilicon": self.is_apple_silicon, "model": self.model_id,
            "gpuLayers": self.gpu_layers, "context": self.context_size,
        })


HARDWARE = _HardwareOptimizer()


class LocalLlamaEngine:
    def __init__(self, model_path: Optional[str] = None) -> None:
        self._model_path_override = model_path
        self._llm: Any = None  # lazily-loaded llama_cpp.Llama instance
        logger.info(f"Detected {'Apple Silicon' if HARDWARE.is_apple_silicon else 'x86'} with {HARDWARE.total_ram}GB RAM")

    def _ensure_model(self, model_path: str) -> None:
        if self._llm is not None:
            return

        if not os.path.exists(model_path):
            logger.error(f"❌ GGUF model not found: {model_path}")
            raise SystemExit("Refusing to proceed without valid model file")

        from llama_cpp import Llama  # imported lazily -- optional heavy dependency

        logger.info(f"Loading model from {model_path}")
        try:
            self._llm = Llama(
                model_path=model_path,
                n_gpu_layers=HARDWARE.gpu_layers,
                n_ctx=HARDWARE.context_size,
                n_threads=HARDWARE.threads,
                use_mmap=True,
                use_mlock=HARDWARE.total_ram >= 16,
            )
            logger.info(f"Model loaded with {HARDWARE.gpu_layers} GPU layers")
        except Exception:  # noqa: BLE001
            logger.warn("Aggressive settings failed, trying conservative...")
            self._llm = Llama(
                model_path=model_path,
                n_gpu_layers=HARDWARE.gpu_layers // 2,
                n_ctx=HARDWARE.context_size,
                n_threads=HARDWARE.threads,
                use_mmap=True,
                use_mlock=False,
            )

    async def generate_stream(
        self, session_id: str, prompt: str, params: GenerationParams
    ) -> AsyncGenerator[GenerationEvent, None]:
        t0 = time.perf_counter()

        max_tokens = min(params.max_tokens or 128, 512)
        temperature = params.temperature if params.temperature is not None else 0.2
        stop = params.stop or ["<|im_end|>", "<|im_start|>", "</s>", "\n\n", "assistant"]
        ctx_len = min(params.ctx or HARDWARE.context_size, HARDWARE.context_size)

        if len(prompt) > 4000:
            if os.environ.get("MODE", "dev") == "prod":
                prompt = "[truncated]" + prompt[-3800:]
                logger.warn("Prompt truncated in production mode")
            else:
                raise ValueError(f"Prompt too long: {len(prompt)} chars (max 4000 in dev)")

        model_path = self._model_path_override or os.environ.get("JARVIS_LOCAL_GGUF") or resolve_model_path(HARDWARE.model_id)
        self._ensure_model(model_path)

        first_ms: Optional[float] = None
        tokens_out = 0
        full_response = ""

        try:
            result = self._llm(
                prompt, max_tokens=max_tokens, temperature=temperature, stop=stop,
            )
            text = result["choices"][0]["text"]
            if text:
                first_ms = (time.perf_counter() - t0) * 1000
                yield GenerationEvent(type="first", ms=first_ms, timestamp=time.time() * 1000)
                yield GenerationEvent(type="token", text=text, timestamp=time.time() * 1000)
                tokens_out = 1
                full_response = text
        except Exception as error:  # noqa: BLE001
            logger.error("Generation error:", error)

        if first_ms is None:
            first_ms = (time.perf_counter() - t0) * 1000

        total_ms = (time.perf_counter() - t0) * 1000

        logger.log_latency({
            "engine": "local", "model_id": HARDWARE.model_id,
            "params": {"ctx": ctx_len, "max_tokens": max_tokens, "temperature": temperature, "stop": stop},
            "prompt_chars": len(prompt), "session_id": session_id,
            "first_token_ms": first_ms, "total_ms": total_ms,
            "tokens_out": tokens_out, "route": "local",
        })

        yield GenerationEvent(type="done", timestamp=time.time() * 1000)

    async def smoke_test(self) -> None:
        logger.info("Running startup smoke test...")
        params = GenerationParams(max_tokens=16, ctx=512, temperature=0.0, stop=[".", "\n"])

        start = time.perf_counter()
        first_token_ms = 0.0
        response = ""
        tokens_out = 0

        async for event in self.generate_stream("smoke-test", "Reply with OK", params):
            if event.type == "first":
                first_token_ms = event.ms or 0
            elif event.type == "token" and event.text:
                tokens_out += 1
                response += event.text
            elif event.type == "done":
                break

        total_ms = (time.perf_counter() - start) * 1000
        max_first_token = 8000 if HARDWARE.total_ram <= 8 else 3000
        max_total = 12000 if HARDWARE.total_ram <= 8 else 5000

        if first_token_ms > max_first_token or total_ms > max_total or tokens_out == 0:
            logger.warn(f"Smoke test slower than ideal: first={first_token_ms}ms total={total_ms}ms tokens={tokens_out}")
        else:
            logger.info(f"✅ SMOKE OK first={first_token_ms}ms total={total_ms}ms engine=local tokens={tokens_out}")

    def get_health(self) -> dict[str, Any]:
        return {
            "ok": self._llm is not None,
            "modelId": HARDWARE.model_id,
            "hardware": {"ram": f"{HARDWARE.total_ram}GB", "threads": HARDWARE.threads, "appleSilicon": HARDWARE.is_apple_silicon},
            "settings": {"ctx": HARDWARE.context_size, "gpuLayers": HARDWARE.gpu_layers},
            "engine": "local",
        }

    async def cleanup(self) -> None:
        self._llm = None
        logger.info("Local model cleaned up")
