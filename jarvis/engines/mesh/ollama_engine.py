"""Ported from src/engines/mesh/OllamaEngine.ts.

Serving layer for the task-routed local model mesh. Ollama hosts all three
facet models (planner / coder / fast) behind one local HTTP API and handles
load-on-first-request + idle eviction itself -- this is what lets a 16GB
machine run three different specialist models without a custom
load/unload scheduler. The router picks *which* model to call; Ollama
decides whether it needs to be paged in.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Optional

import httpx

from ...router.router import Facet
from ...utils.logging import logger
from ..local.local_llama_engine import GenerationEvent, GenerationParams


@dataclass
class FacetModelMap:
    planner: str = "qwen3.5:9b-instruct-q4_K_M"
    coder: str = "qwen2.5-coder:7b-instruct-q4_K_M"
    fast: str = "llama3.2:3b-instruct-q4_K_M"

    def __getitem__(self, facet: Facet) -> str:
        return getattr(self, facet)


class OllamaEngine:
    def __init__(self, base_url: Optional[str] = None, facet_models: Optional[FacetModelMap] = None) -> None:
        self.base_url = base_url or os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        self.facet_models = facet_models or FacetModelMap()

    def model_for(self, facet: Facet) -> str:
        return self.facet_models[facet]

    async def generate_stream(
        self, facet: Facet, prompt: str, params: Optional[GenerationParams] = None
    ) -> AsyncGenerator[GenerationEvent, None]:
        params = params or GenerationParams()
        model = self.model_for(facet)
        t0 = time.perf_counter()
        first_ms: Optional[float] = None
        tokens_out = 0

        body = {
            "model": model,
            "prompt": prompt,
            "stream": True,
            "options": {
                "num_ctx": params.ctx or 2048,
                "num_predict": params.max_tokens or 256,
                "temperature": params.temperature if params.temperature is not None else 0.2,
                "stop": params.stop or [],
            },
        }

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream("POST", f"{self.base_url}/api/generate", json=body) as response:
                    if response.status_code != 200:
                        raise RuntimeError(f"Ollama API error: {response.status_code}")

                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        parsed = json.loads(line)

                        if parsed.get("response"):
                            if first_ms is None:
                                first_ms = (time.perf_counter() - t0) * 1000
                                yield GenerationEvent(type="first", ms=first_ms, timestamp=time.time() * 1000)
                            tokens_out += 1
                            yield GenerationEvent(type="token", text=parsed["response"], timestamp=time.time() * 1000)

                        if parsed.get("done"):
                            break
        except Exception as error:  # noqa: BLE001
            logger.error(f"Ollama mesh generation failed (facet={facet}, model={model}):", error)
            raise
        finally:
            total_ms = (time.perf_counter() - t0) * 1000
            logger.log_latency({
                "engine": "ollama_mesh", "model_id": model,
                "params": {"ctx": params.ctx or 2048, "max_tokens": params.max_tokens or 256,
                           "temperature": params.temperature or 0.2, "stop": params.stop or []},
                "prompt_chars": len(prompt), "session_id": "mesh",
                "first_token_ms": first_ms or total_ms, "total_ms": total_ms,
                "tokens_out": tokens_out, "route": facet,
            })
            yield GenerationEvent(type="done", timestamp=time.time() * 1000)

    async def list_loaded(self) -> list[str]:
        """Ollama's own idle-eviction handles memory pressure; this just
        reports which facet models are currently resident, for the health
        endpoint."""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.base_url}/api/ps")
            if response.status_code != 200:
                return []
            return [m["name"] for m in response.json().get("models", [])]
        except httpx.HTTPError:
            return []

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.base_url}/api/tags")
            return response.status_code == 200
        except httpx.HTTPError:
            return False
