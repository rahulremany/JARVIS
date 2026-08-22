#!/bin/bash
# JARVIS Backend Startup Script

echo "🚀 Starting JARVIS Backend (Python)..."

if [ -f .env ]; then
    echo "✅ Loading environment variables from .env"
    export $(grep -v '^#' .env | xargs)
else
    echo "⚠️  No .env file found"
fi

if [ -z "$ELEVEN_API_KEY" ]; then
    echo "❌ ELEVEN_API_KEY not set"
else
    echo "✅ ELEVEN_API_KEY loaded: ${ELEVEN_API_KEY:0:10}..."
fi

if [ -z "$PORCUPINE_ACCESS_KEY" ]; then
    echo "❌ PORCUPINE_ACCESS_KEY not set"
else
    echo "✅ PORCUPINE_ACCESS_KEY loaded: ${PORCUPINE_ACCESS_KEY:0:10}..."
fi

echo "🌐 Starting Python (FastAPI) backend..."
python3 -m jarvis.main
