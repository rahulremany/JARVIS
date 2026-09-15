#!/usr/bin/env bash
# Launcher for the Volt fitness tracker.
# Starts the FastAPI backend and the Vite frontend, waits for both,
# opens the dashboard, and shuts both down on Ctrl+C.
set -euo pipefail

JARVIS_ROOT="/Users/rahulremany/Desktop/JARVIS"
BACKEND_DIR="$JARVIS_ROOT/jarvis/services/fitness"
FRONTEND_DIR="$JARVIS_ROOT/frontend/fitness"
BACKEND_PORT="${FITNESS_BACKEND_PORT:-8000}"
FRONTEND_PORT="${FITNESS_FRONTEND_PORT:-5173}"
LOG_DIR="$JARVIS_ROOT/.jarvis_state/fitness_logs"
PIDS=()

# Job control puts each background job in its own process group, so a single
# kill on -PGID takes down the whole tree (npm -> vite, uvicorn workers)
# instead of orphaning the children.
set -m

mkdir -p "$LOG_DIR"

port_busy() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }

cleanup() {
  trap - INT TERM EXIT
  exec 2>/dev/null   # silence bash's "Terminated: 15" job notices
  echo
  echo "→ shutting down"
  for pid in "${PIDS[@]:-}"; do
    [ -n "$pid" ] && kill -TERM -- "-$pid" 2>/dev/null || true
  done
  # Give them a moment to exit cleanly, then make sure they are gone.
  sleep 1
  for pid in "${PIDS[@]:-}"; do
    [ -n "$pid" ] && kill -KILL -- "-$pid" 2>/dev/null || true
  done
}
trap cleanup INT TERM EXIT

wait_for() { # url, label
  for _ in $(seq 1 60); do
    curl -sf -o /dev/null "$1" && return 0
    sleep 0.5
  done
  echo "  ✗ $2 did not come up — check $LOG_DIR" >&2
  return 1
}

# --- dependencies (first run only) ---
if [ ! -x "$BACKEND_DIR/.venv/bin/python" ]; then
  echo "→ creating backend venv"
  python3 -m venv "$BACKEND_DIR/.venv"
  "$BACKEND_DIR/.venv/bin/pip" install -q -r "$BACKEND_DIR/requirements.txt"
fi
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  echo "→ installing frontend deps"
  (cd "$FRONTEND_DIR" && npm install)
fi

# --- backend ---
if port_busy "$BACKEND_PORT"; then
  echo "→ backend already running on :$BACKEND_PORT"
else
  echo "→ starting backend on :$BACKEND_PORT"
  (cd "$BACKEND_DIR" && exec .venv/bin/python -m uvicorn app.main:app \
      --host 127.0.0.1 --port "$BACKEND_PORT") >"$LOG_DIR/backend.log" 2>&1 &
  PIDS+=("$!")
fi
wait_for "http://localhost:$BACKEND_PORT/health" "backend"
echo "  ✓ backend ready"

# --- frontend ---
if port_busy "$FRONTEND_PORT"; then
  echo "→ frontend already running on :$FRONTEND_PORT"
else
  echo "→ starting frontend on :$FRONTEND_PORT"
  (cd "$FRONTEND_DIR" && PORT="$FRONTEND_PORT" \
      exec node_modules/.bin/vite --host 127.0.0.1) \
      >"$LOG_DIR/frontend.log" 2>&1 &
  PIDS+=("$!")
fi
wait_for "http://localhost:$FRONTEND_PORT/" "frontend"
echo "  ✓ frontend ready"

open "http://localhost:$FRONTEND_PORT/"
echo
echo "Volt is running at http://localhost:$FRONTEND_PORT  (Ctrl+C to stop)"
echo "Logs: $LOG_DIR/backend.log, $LOG_DIR/frontend.log"

# Idle here until Ctrl+C; cleanup trap tears everything down.
if [ "${#PIDS[@]}" -gt 0 ]; then wait; else while :; do sleep 3600; done; fi
