# JARVIS — Local-First AI Assistant Mesh

A voice-driven personal assistant that runs entirely on-device (Apple Silicon),
routing each request to whichever local specialist model — or non-model
reflex — is actually suited to it, instead of sending everything through one
general-purpose model or a metered cloud API.

## Why local-first

Built for a single 16GB-unified-memory machine with no ongoing API budget.
Every design choice below follows from that: small quantized models instead
of one large one, non-LLM reflexes wherever a classical algorithm is faster
and cheaper than a model call, and load/evict scheduling instead of holding
everything in memory at once.

## Architecture: four tiers, ordered by speed

| Tier | What it does | How |
|---|---|---|
| **1. Reflex** | "Is anything happening" | Pixel-diffing (`MotionDetector`) gates a pluggable object detector (`ObjectDetector`) — no model call at all |
| **2. Fast commands** | "Open Chrome", "set a timer" | Local intent-matching (`Router.classify` + `DeviceActions`) executes directly, no LLM in the loop |
| **3. Agentic chaining** | Multi-step tasks needing judgment | A facet-routed local model reasons over tools exposed via **MCP** (`jarvis/mcp/server.py`) |
| **4. Vision-grounded fallback** | Actions with no clean API (GUI automation) | Screenshot + vision-model grounding (`ToolExecutor.click_element`) |

Tier 3 is where the **model mesh** lives — see below.

## The model mesh

Rather than one model handling every request, requests are classified by
*task type* (not just difficulty) and routed to a specialist:

| Facet | Task | Model | Resident |
|---|---|---|---|
| `planner` | Brainstorming, outlines, project breakdown | Qwen 3.5 9B Instruct (4-bit) | On demand |
| `coder` | Code generation, debugging, refactors | Qwen2.5-Coder 7B Instruct (4-bit) | On demand |
| `fast` | Autocomplete, commit messages, quick utility | Llama 3.2 3B (4-bit) | Always loaded |

All three are served through **Ollama**, which handles per-model load/evict
so the three specialists share a 16GB RAM budget without a hand-rolled
scheduler — `fast` stays warm, `planner`/`coder` swap in on demand and are
never resident simultaneously. See `jarvis/router/router.py::classify_facet`
for the (deliberately non-LLM) routing logic and
`jarvis/engines/mesh/ollama_engine.py` for the serving client. Config lives
in `config/model-policy.yaml` under `facets`.

## Conversation loop

- **Wake word**: local, always-on (`jarvis/asr/kws_porcupine.py`)
- **STT**: local Whisper (`jarvis/asr/asr_whisper.py`)
- **Reasoning**: routed through the tier-appropriate engine/facet
- **TTS**: streamed response (`jarvis/conversation/conversation_handler.py`)

`wake_system_integrated.py` is the standalone voice loop -- wake word →
record → Whisper → backend call → speak, including the "yes sir" filler and
the follow-up listening window -- talking to the backend over plain HTTP on
`localhost:3000`.

## Running it

```
python3 -m jarvis.main          # or ./start_backend.sh -- FastAPI backend
python3 -m jarvis.mcp.server    # MCP tool server (stdio transport)
python3 wake_system_integrated.py  # standalone voice loop
pytest tests_py/                # test suite
```

## Build status

This is an active local-first build, not a finished product. What's real
today vs. scaffolded for what comes next:

- **Working**: wake word detection (`jarvis/asr/kws_porcupine.py`, real
  `pvporcupine` binding), Whisper STT (`jarvis/asr/asr_whisper.py`, real
  `openai-whisper` binding), direct-command parsing and macOS automation,
  the difficulty-based router/engine selection (`trivial`/`normal`/`hard` →
  local/heavy), TTS output, the standalone `wake_system_integrated.py` voice
  loop.
- **Scaffolded, wired, pending real hardware/weights**: the facet mesh
  (`OllamaEngine` + `classify_facet`) is implemented against Ollama's API
  but needs the three models pulled locally to run; the reflex vision tier
  (`MotionDetector` is fully functional against raw frame buffers,
  `ObjectDetector` ships a stub backend pending a real YOLO/ONNX model); the
  MCP tool server (`jarvis/mcp/server.py`) implements the real protocol
  against the existing tool set, pending a live client session.

## Tech stack

Python, FastAPI, `llama-cpp-python` (direct GGUF inference), Ollama (mesh
serving), Model Context Protocol SDK, Pydantic-validated YAML policy config,
Porcupine (wake word), Whisper (STT), NumPy (reflex-tier vision).
