#!/bin/bash
# Hits the running JARVIS server's /daily/briefing endpoint -- meant to be
# fired once a morning by launchd (see scripts/com.jarvis.dailybriefing.plist)
# or a plain crontab entry. Requires JARVIS's main server to already be
# running (jarvis/main.py) since this just calls its HTTP API.
set -euo pipefail

JARVIS_PORT="${JARVIS_PORT:-3000}"

curl -sS -X POST "http://127.0.0.1:${JARVIS_PORT}/daily/briefing" \
  -H "Content-Type: application/json" \
  -d '{"days_ahead": 7, "speak": true}'
