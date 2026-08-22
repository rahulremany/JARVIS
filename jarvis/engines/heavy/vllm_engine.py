"""Ported from src/engines/heavy/VllmEngine.ts."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Optional

import httpx

from ...utils.logging import logger
from ..local.local_llama_engine import GenerationEvent, GenerationParams


class VllmEngine:
    def __init__(self, base_url: str) -> None:
        if not base_url:
            raise ValueError("vLLM base URL is required")
        self.base_url = base_url

    async def generate_stream(
        self, prompt: str, params: GenerationParams, model_id: str
    ) -> AsyncGenerator[GenerationEvent, None]:
        t0 = time.perf_counter()
        first_ms: Optional[float] = None
        tokens_out = 0

        body: dict[str, Any] = {
            "model": model_id,
            "prompt": prompt,
            "max_tokens": params.max_tokens or 512,
            "temperature": params.temperature if params.temperature is not None else 0.3,
            "stop": params.stop or [],
            "stream": True,
        }

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                async with client.stream("POST", f"{self.base_url}/v1/completions", json=body) as response:
                    if response.status_code != 200:
                        raise RuntimeError(f"vLLM API error: {response.status_code}")

                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data = line[6:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            parsed = json.loads(data)
                            text = parsed.get("choices", [{}])[0].get("text")
                            if text:
                                if first_ms is None:
                                    first_ms = (time.perf_counter() - t0) * 1000
                                    yield GenerationEvent(type="first", ms=first_ms, timestamp=time.time() * 1000)
                                tokens_out += 1
                                yield GenerationEvent(type="token", text=text, timestamp=time.time() * 1000)
                        except json.JSONDecodeError:
                            logger.warn("Failed to parse SSE data")
        except Exception as error:  # noqa: BLE001
            logger.error("vLLM generation error:", error)
            raise
        finally:
            total_ms = (time.perf_counter() - t0) * 1000
            logger.log_latency({
                "engine": "vllm", "model_id": model_id,
                "params": {"ctx": params.ctx or 4096, "max_tokens": params.max_tokens or 512,
                           "temperature": params.temperature or 0.3, "stop": params.stop or []},
                "prompt_chars": len(prompt), "session_id": "vllm-session",
                "first_token_ms": first_ms or total_ms, "total_ms": total_ms,
                "tokens_out": tokens_out, "route": "heavy",
            })
            yield GenerationEvent(type="done", timestamp=time.time() * 1000)

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.base_url}/health")
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    def get_health(self) -> dict[str, Any]:
        return {"ok": True, "baseUrl": self.base_url, "engine": "vllm"}
