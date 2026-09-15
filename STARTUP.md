# 🤖 JARVIS Quick Startup Guide

## Environment Variables Auto-Loading ✅

JARVIS now automatically loads API keys from your existing `.env` file! No more manual environment variable setup.

## One-time setup

```bash
# Python 3.11 or 3.12 -- NOT 3.14, openai-whisper's torch dependency has no
# wheels for it yet. Check what you have with: python3.12 --version
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"

# Desktop app
cd frontend && npm install && cd ..
```

Then fill in `.env` (copy from `env.example` if you don't have one yet) --
at minimum `ANTHROPIC_API_KEY`. `ELEVEN_API_KEY`/`GOOGLE_*`/`CANVAS_*` are
optional (features they gate just no-op/skip without them).

## Quick Start (1 command)

```bash
cd frontend && npm start
```

That's it -- the desktop app now owns the whole stack. On launch it:
- ✅ Starts the Python (FastAPI) backend (`.venv/bin/python3 -m jarvis.main`), unless one's already running, in which case it just reuses it
- ✅ Waits for the backend to report healthy
- ✅ Starts the wake-word/voice pipeline (`wake_system_integrated.py`)
- ✅ Opens the JARVIS window, and jumps it to the front whenever you say the wake word

Backend and voice logs stream into the same terminal, prefixed `[backend]`/`[voice]`.
Closing the app (or quitting it) stops both child processes -- no orphaned
processes left running in the background.

### Manual / debug mode (optional)

If you want the backend and voice pipeline in their own terminals instead
(e.g. to restart one without killing the other, or without the desktop app
at all):

```bash
./start_backend.sh   # Terminal 1
./start_jarvis.sh    # Terminal 2 (checks that the backend is already up)
```

The desktop app detects an already-running backend and won't spawn a
duplicate, but running `start_jarvis.sh`'s voice pipeline *and* the app's
own would fight over the microphone -- use one or the other, not both.

## New Features 🎉

### Follow-Up Conversations
- Say "Jarvis" for the first command
- After JARVIS responds, continue talking without saying "Jarvis" again
- Follow-up mode lasts 10 seconds, then returns to wake word mode

### Smart Conversation Ending
- Say things like "that's all", "thank you", "goodbye", "I'm done"
- JARVIS intelligently detects when you want to end the conversation
- Returns to wake word mode automatically

## Daily Briefing (Canvas -> Calendar/Reminders)

Pulls upcoming Canvas assignments + grades, pushes new due dates to Google
Calendar, adds classes to a "Classes" Apple Reminders list, and speaks a
summary. Requires `GOOGLE_*`/`CANVAS_*` in `.env` (see `env.example`), and
Reminders access granted to Terminal the first time it runs (System
Settings -> Privacy & Security -> Reminders).

- One-off: `curl -X POST http://127.0.0.1:3000/daily/briefing -d '{}'`
- Scheduled: see `scripts/daily_briefing.sh` and
  `scripts/com.jarvis.dailybriefing.plist.example` for a launchd setup that
  fires it every morning while the backend is running.

## Usage Flow
1. Say: **"Jarvis, what's 2+2?"**
2. JARVIS: *"4"*
3. You: **"What about 5+5?"** (no wake word needed!)
4. JARVIS: *"10"* 
5. You: **"Thank you, that's all"**
6. JARVIS: *Returns to sleep mode*

## Troubleshooting

### If environment variables still not loaded:
- Check that `.env` file exists with at least `ANTHROPIC_API_KEY` set
- `jarvis/main.py` and `wake_system_integrated.py` both load `.env` themselves on startup

### Manual environment loading (if needed):
```bash
export $(grep -v '^#' .env | xargs)
.venv/bin/python3 -m jarvis.main          # backend
.venv/bin/python3 wake_system_integrated.py  # voice pipeline
```

## File Structure
- `frontend/main.js` - Desktop app; on launch, spawns and owns the backend + voice pipeline
- `start_backend.sh` - Backend only, for manual/debug mode
- `start_jarvis.sh` - Voice pipeline only, for manual/debug mode
- `wake_system_integrated.py` - Main voice system (auto-loads .env)
