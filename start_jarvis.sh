#!/bin/bash
# JARVIS Complete Startup Script

echo "🤖 Starting JARVIS Complete System..."
echo "====================================="

# Activate Python virtual environment
if [ -d "jarvis_env" ]; then
    echo "🐍 Activating Python virtual environment..."
    source jarvis_env/bin/activate
else
    echo "❌ Python virtual environment not found. Please run: python3 -m venv jarvis_env"
    exit 1
fi

# Check if backend is running
echo "🔍 Checking backend status..."
if curl -s http://localhost:3000/health/summary > /dev/null 2>&1; then
    echo "✅ Backend is already running"
else
    echo "❌ Backend not running. Please start it first with: ./start_backend.sh"
    exit 1
fi

# Start the Python wake system (environment variables will be loaded automatically)
echo "🎤 Starting JARVIS wake word system..."
python3 wake_system_integrated.py
