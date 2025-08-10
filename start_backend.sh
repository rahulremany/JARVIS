#!/bin/bash
# JARVIS Backend Startup Script with Environment Loading

echo "🚀 Starting JARVIS Backend..."

# Load environment variables from .env file if it exists
if [ -f .env ]; then
    echo "✅ Loading environment variables from .env"
    export $(grep -v '^#' .env | xargs)
else
    echo "⚠️  No .env file found"
fi

# Verify key environment variables are set
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

# Start the backend
echo "🌐 Starting Node.js backend..."
npm run dev
