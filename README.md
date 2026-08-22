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
| **3. Agentic chaining** | Multi-step tasks needing judgment | A facet-routed local model reasons over tools exposed via **MCP** (`src/mcp/server.ts`) |
| **4. Vision-grounded fallback** | Actions with no clean API (GUI automation) | Screenshot + vision-model grounding (`ToolExecutor.clickElement`) |

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
never resident simultaneously. See `src/router/Router.ts::classifyFacet` for
the (deliberately non-LLM) routing logic and `src/engines/mesh/OllamaEngine.ts`
for the serving client. Config lives in `config/model-policy.yaml` under
`facets`.

## Conversation loop

- **Wake word**: local, always-on (`src/asr/KwsPorcupine.ts`)
- **STT**: local Whisper (`src/asr/AsrWhisper.ts`)
- **Reasoning**: routed through the tier-appropriate engine/facet
- **TTS**: streamed response (`src/conversation/ConversationHandler.ts`)

## Build status

This is an active local-first rebuild, not a finished product. What's real
today vs. scaffolded for what comes next:

- **Working**: wake word detection, local Whisper STT, direct-command
  parsing and macOS automation, the difficulty-based router/engine
  selection (`trivial`/`normal`/`hard` → local/heavy), TTS output.
- **Scaffolded, wired, pending real hardware/weights**: the facet mesh
  (`OllamaEngine` + `classifyFacet`) is implemented against Ollama's API but
  needs the three models pulled locally to run; the reflex vision tier
  (`MotionDetector` is fully functional against raw frame buffers,
  `ObjectDetector` ships a stub backend pending a real YOLO/ONNX model); the
  MCP tool server (`src/mcp/server.ts`) implements the real protocol against
  the existing tool set, pending a live client session.

## Tech stack

Node.js / TypeScript, `node-llama-cpp` (direct GGUF inference), Ollama
(mesh serving), Model Context Protocol SDK, Fastify, Porcupine (wake word),
Whisper (STT), Zod-validated YAML policy config.
