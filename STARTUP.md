# 🤖 JARVIS Quick Startup Guide

## Environment Variables Auto-Loading ✅

JARVIS now automatically loads API keys from your existing `.env` file! No more manual environment variable setup.

## Quick Start (2 Terminal Windows)

### Terminal 1: Start Backend
```bash
./start_backend.sh
```
This will:
- ✅ Load ELEVEN_API_KEY and PORCUPINE_ACCESS_KEY from .env
- ✅ Start the Node.js backend with proper environment variables
- ✅ Show confirmation that keys are loaded

### Terminal 2: Start JARVIS Voice System
```bash
./start_jarvis.sh
```
This will:
- ✅ Activate the Python virtual environment
- ✅ Check that backend is running
- ✅ Start the wake word system with auto-loaded environment variables

## New Features 🎉

### Follow-Up Conversations
- Say "Jarvis" for the first command
- After JARVIS responds, continue talking without saying "Jarvis" again
- Follow-up mode lasts 10 seconds, then returns to wake word mode

### Smart Conversation Ending
- Say things like "that's all", "thank you", "goodbye", "I'm done"
- JARVIS intelligently detects when you want to end the conversation
- Returns to wake word mode automatically

## Usage Flow
1. Say: **"Jarvis, what's 2+2?"**
2. JARVIS: *"4"*
3. You: **"What about 5+5?"** (no wake word needed!)
4. JARVIS: *"10"* 
5. You: **"Thank you, that's all"**
6. JARVIS: *Returns to sleep mode*

## Troubleshooting

### If environment variables still not loaded:
- Check that `.env` file exists with ELEVEN_API_KEY and PORCUPINE_ACCESS_KEY
- Make sure you're using the startup scripts (they handle environment loading)

### Manual environment loading (if needed):
```bash
# For backend
source set_env.sh
npm run dev

# For Python (in jarvis_env)
export $(grep -v '^#' .env | xargs)
python wake_system_integrated.py
```

## File Structure
- `start_backend.sh` - Backend startup with auto environment loading
- `start_jarvis.sh` - Complete JARVIS startup script  
- `set_env.sh` - Manual environment variable setup (fallback)
- `wake_system_integrated.py` - Main voice system (auto-loads .env)
