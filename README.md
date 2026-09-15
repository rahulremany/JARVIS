# J.A.R.V.I.S.

A voice-driven personal AI assistant for macOS — wake word, real-time speech,
and a Claude-powered agent that actually *does things* on the machine
(opens apps, drives a browser, manages your calendar and reminders,
transcribes lectures into study notes) instead of just describing what it
would do. Built as a real daily-use tool, not a demo.

One command (`npm start`) launches the whole stack: FastAPI backend, local
speech pipeline, and an Electron desktop app that jumps to the front the
instant you say "Jarvis."

## Highlights

- **Real tool-use agent, not a scripted command parser.** Claude drives an
  actual multi-round tool-calling loop (calendar, file system, dev
  commands, browser/OS control) and decides for itself which tools to call
  and in what order — including judgment calls like "should this search
  open a new browser tab, or reuse the one I already have open" based on
  conversation context.
- **Prompt caching wired in for cost, not just correctness** — system
  prompt, ~35 tool schemas, and growing conversation history all carry
  cache breakpoints, since those are re-sent on every single request.
- **Fully local speech pipeline**: wake-word detection (openWakeWord) and
  transcription (OpenAI's open-source Whisper model) both run on-device —
  no cloud STT dependency, no per-request transcription cost.
- **Real integrations, not stubs**: Google Calendar (OAuth2, direct REST),
  Canvas LMS (assignments + grades), Apple Reminders (AppleScript), and a
  companion fitness tracker service — all exposed as tools the agent can
  actually call.
- **Batch-transcribe-and-reformat lecture notes**: record a class or
  meeting with no length cap, then one Whisper pass + one Claude call turns
  the raw transcript into organized, exam-ready study notes.
- **A persona with an actual spec.** `script.md` defines the agent's voice
  as a set of reference dialogues and distilled behavioral principles (go
  quiet while working, lead with the headline, one sharp clarifying
  question, own mistakes plainly) — the system prompt implements it
  directly, not vibes.
- Sentence-pipelined TTS (synthesize the next sentence while the current
  one plays — sub-second time-to-first-audio instead of waiting on the
  whole response), a serialized speech queue instead of a
  silently-drops-audio race, and a particle-field UI that visibly reacts
  while the agent is actually speaking.
- 60+ automated tests (`pytest`), all mocked at the network/subprocess
  boundary — no API cost to run the suite.

## Architecture

```
  wake_system_integrated.py                    Electron desktop app
  (mic -> wake word -> Whisper)   -- wake -->   (frontend/) -- spawns and
                                  <- speaking -- owns the backend + voice
              |                                 pipeline, jumps to front
              | HTTP                            on wake word
              v
  ------------------------------------------------------------------
  FastAPI backend (jarvis/main.py)
  ConversationHandler -> Claude tool-use loop -> AgentToolRegistry
  Session memory  |  prompt caching  |  TTS (ElevenLabs / macOS say)
  ------------------------------------------------------------------
              |
   -----------+-------------------+-------------------------
   |                              |                          |
   v                              v                          v
Google / Canvas /         macOS automation            MCP tool server
Reminders adapters        (AppleScript, screen         (jarvis/mcp/server.py)
                           vision via Claude)           -- stdio transport for
                                                         external MCP clients
```

### Model routing

`Router.classify` (`jarvis/router/router.py`) is a cheap, non-LLM
keyword/heuristic pass — routing itself never costs a model call — and maps
each request to a Claude model via `config/model-policy.yaml`:

| Route class | Model | Use |
|---|---|---|
| `direct_command` / `trivial` | Claude Haiku 4.5 | Quick factual lookups, one-liners |
| `normal` | Claude Sonnet 5 | Everyday conversation, tool-use loop |
| `hard` | Claude Opus 5 | Multi-step reasoning, planning, coding, research |

No local model weights anywhere — reasoning is 100% the Anthropic API.

## What it can do

- **Voice conversation** with real memory across a session (not
  reconstructed per-turn), wake-word activation, and follow-up mode (keep
  talking without repeating the wake word).
- **Computer control**: open apps, drive the browser (search, tab
  management), read/describe what's on screen (Claude vision), click UI
  elements, run allowlisted shell/dev commands.
- **Daily assignment ingest**: pulls Canvas assignments + grades, pushes
  new due dates to Google Calendar, adds classes to Apple Reminders,
  estimates workload, and can speak a morning briefing on a schedule.
- **Calendar management**: create/update/delete events, recurring events.
- **Lecture/meeting transcription** → structured study notes.
- **R&D project workspace**: fabrication plans, artifact/notes tracking for
  hardware projects.
- **Coding partner**: read/write/edit files, run real dev commands
  (git/pytest/npm/...), search a codebase — sandboxed to a workspace root.

## Tech stack

**Backend:** Python, FastAPI, Anthropic API (`anthropic` SDK), Model
Context Protocol SDK, Pydantic-validated YAML policy config.
**Speech:** openWakeWord (wake word), OpenAI Whisper (local STT),
ElevenLabs / macOS `say` (TTS).
**Desktop app:** Electron, vanilla JS (no framework), Canvas 2D (particle
field).
**Integrations:** Google Calendar API (OAuth2), Canvas LMS API, Apple
Reminders (AppleScript/osascript).

## Running it

```bash
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
cd frontend && npm install && cd ..
cp env.example .env   # fill in ANTHROPIC_API_KEY at minimum

cd frontend && npm start   # spawns the backend + voice pipeline, opens the app
```

See `STARTUP.md` for the full setup guide (including per-integration setup
for Calendar/Canvas/Reminders) and manual/debug-mode instructions for
running the backend and voice pipeline in separate terminals.

```bash
pytest tests_py/   # full test suite, no API cost (mocked at the network/subprocess boundary)
```

## Status

Actively developed, personal daily-use project — not a polished product.
The reflex-tier vision pipeline (`jarvis/vision/`: motion-gated object
detection) is implemented against raw frame buffers but pending a real
detector backend. Everything described above as "live" is real, working
code with test coverage, not a stub.
