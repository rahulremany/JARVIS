# Volt — Personal Training & Recovery Dashboard

A personal, single-user replacement for Garmin Connect: pulls your Garmin recovery and strength-training data automatically, layers an AI coach on top of it (Claude), and can push AI-suggested workouts straight back to your watch's workout library. Nutrition tracking is a manual, on-demand pull from Cronometer.

Not a general-purpose product — built for one account, one user, one Mac.

## What it does

- **Garmin sync (automatic).** Pulls recovery data (HRV, sleep score, resting HR, stress) and strength-training sessions (exercise, sets, reps, weight) from Garmin Connect. Syncs 7 days back on every launch, then a lighter 2-day refresh every hour while the app stays open, plus on every page reload.
- **AI coach (Claude Sonnet 5).** Reads your last 14 days of training + latest recovery data and recommends today's workout with reasoning. Chat interface can also log workouts/nutrition and answer training questions, with a persistent plain-text memory (`backend/coach_memory.txt`) of durable facts (injuries, goals, equipment) that carries across sessions.
- **Save to Garmin.** Uploads a workout (AI-suggested or coach-chat-built) to your Garmin Connect workout library and queues it for your watch — no calendar scheduling, just makes it selectable like one you built yourself. Exercise names are resolved against Garmin's ~1,500-exercise catalog. Can auto-save the day's suggested workout on launch (toggle via `GARMIN_AUTO_SAVE_WORKOUT`).
- **Nutrition via Cronometer (manual only).** Pulls daily calorie/macro/micronutrient totals from Cronometer. Deliberately **not automatic** — Cronometer rate-limits its export endpoints, so sync only runs when you click the button, and a persisted daily counter (visible in the UI) stops you from exceeding the budget.
- **Progress tracking.** Estimated 1RM (Epley formula) and volume trends over time.

## Architecture

```
Garmin Connect ──┐                    ┌── Claude API (coaching, chat, vision)
                  ├─► FastAPI backend ─┤
Cronometer ───────┘   (SQLite, single ├── React/Vite frontend (PWA-style)
                       source of truth)
```

- **Backend:** FastAPI + SQLAlchemy + SQLite (`backend/core.db`, one file, no external DB).
- **Frontend:** React + Vite + Tailwind, single-page app.
- **Garmin & Cronometer integrations are both unofficial** — they log in as you and speak the same endpoints their own web/mobile apps use (`python-garminconnect`, `cronometer-mcp`), not published APIs. Expect occasional breakage if either service changes its frontend.

## Requirements

- macOS (the launcher script uses `open` and expects a local Python/Node toolchain)
- Python 3.14, Node.js + npm
- A Garmin Connect account
- A Cronometer **Gold** account (required for export access)
- An Anthropic API key

## Setup

```bash
git clone https://github.com/rahulremany/fitness-tracker-garmin.git
cd fitness-tracker-garmin

cp backend/.env.example backend/.env
# fill in: GARMIN_EMAIL, GARMIN_PASSWORD, ANTHROPIC_API_KEY,
#          CRONOMETER_EMAIL, CRONOMETER_PASSWORD

cp frontend/.env.example frontend/.env   # default (localhost:8000) is fine

./fitness.sh
```

First run creates the Python venv, installs backend dependencies, and runs `npm install` for the frontend automatically. After that, just run `fitness.sh` (or symlink it as `fitness` on your `$PATH`) to launch both services and open the dashboard.

## Environment variables

| Variable | Purpose |
|---|---|
| `GARMIN_EMAIL` / `GARMIN_PASSWORD` | Garmin Connect login (unofficial client) |
| `ANTHROPIC_API_KEY` | Coaching, chat, and meal-photo vision calls |
| `CRONOMETER_EMAIL` / `CRONOMETER_PASSWORD` | Cronometer login (Gold account required) |
| `GARMIN_AUTOSYNC_INTERVAL_HOURS` | Hourly refresh cadence while the app is open (default `1`) |
| `GARMIN_STARTUP_SYNC_DAYS` | How far back the launch sync reaches (default `7`) |
| `GARMIN_AUTO_SAVE_WORKOUT` | Set `0` to disable auto-saving the day's suggested workout to Garmin on launch (default `1`) |
| `CRONOMETER_DAILY_SYNC_LIMIT` | Manual Cronometer syncs allowed per day (default `5` — each sync spends 2 of Cronometer's rate-limited export calls) |
| `CRONOMETER_LOOKBACK_DAYS` | Days of history pulled per Cronometer sync (default `7`) |

## Known limitations

- **Unofficial integrations.** Both Garmin and Cronometer access go through reverse-engineered client libraries, not sanctioned APIs. Credentials are your real account login, not an API key.
- **Cronometer sync is manual and rate-limited.** There is no automatic Cronometer sync anywhere in the app, by design — only a button click, gated by a daily budget shown in the UI.
- **Single-user only.** No auth, no multi-tenancy — this is meant to run locally for one person.
- **No mobile app / App Store build.** It's a local web app; add it to your phone's home screen if you want app-like access on the same network.
