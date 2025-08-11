# JARVIS - Personal AI Assistant

*"Yes sir, how may I assist you?"*

A local-first, privacy-focused AI assistant inspired by Iron Man's JARVIS. Built with TypeScript for high performance, featuring voice activation, natural conversation, and deep system integration. Complete with integrated voice pipeline and intelligent conversation handling.

## Features

- **🗣️ Voice-Activated**: Wake word detection with "Jarvis" using Porcupine
- **🎤 Speech Recognition**: OpenAI Whisper integration for accurate transcription
- **🔊 Text-to-Speech**: ElevenLabs integration for natural JARVIS voice
- **🔐 Privacy-First**: All processing happens locally, no data leaves your device
- **💬 Conversational**: Natural follow-up conversations with intelligent conversation ending detection
- **⚡ High Performance**: Direct llama.cpp integration with Metal acceleration on Apple Silicon
- **🔧 Extensible**: Modular TypeScript architecture with Python voice system integration
- **🧠 Intelligent**: Tiered model system (router/primary/heavy) for optimal performance
- **🛠️ Device Control**: Built-in device actions and automation capabilities
- **🌐 Web Integration**: HTTP API endpoints for external integrations

## Quick Start

### Prerequisites
- **Node.js** ≥18
- **Python** 3.8+ with virtual environment
- **macOS** (for Metal acceleration) or Linux
- **GGUF models** (automatically validated on startup)
- **API Keys**: ElevenLabs (TTS) and Porcupine (wake word detection)

### Installation

1. **Clone and setup**:
   ```bash
   git clone https://github.com/rahulremany/jarvis_ai.git
   cd jarvis_ai
   npm install  # Required: Installs all TypeScript dependencies (~2 minutes)
   ```

2. **Setup Python environment**:
   ```bash
   python3 -m venv jarvis_env
   source jarvis_env/bin/activate  # On Windows: jarvis_env\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Download AI Models**:
   ```bash
   # Create models directory
   mkdir -p models
   
   # Download required GGUF model (example - replace with your preferred model)
   # For Llama 3.1 8B Instruct Q4_K_M (~4.6GB):
   wget -O models/llama-3.1-8b-instruct-q4_k_m.gguf \
     "https://huggingface.co/bartowski/Meta-Llama-3.1-8B-Instruct-GGUF/resolve/main/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf"
   
   # Or download manually from: https://huggingface.co/bartowski/Meta-Llama-3.1-8B-Instruct-GGUF
   ```

4. **Environment setup**:
   ```bash
   # Copy the environment template and edit with your API keys
   cp env.example .env
   # Edit .env with your actual API keys:
   # - ELEVEN_API_KEY (from ElevenLabs)
   # - PORCUPINE_ACCESS_KEY (from Picovoice Console)
   # - JARVIS_VOICE_ID (ElevenLabs voice ID)
   # - OPENAI_API_KEY (if using OpenAI models)
   ```

5. **Start JARVIS (Two terminals)**:

   **Terminal 1 - Backend**:
   ```bash
   ./start_backend.sh
   ```

   **Terminal 2 - Voice System**:
   ```bash
   ./start_jarvis.sh
   ```

## Usage

### Voice Commands
1. Say **"Jarvis"** to wake the system
2. Speak your command or question
3. Continue conversation without wake word for 10 seconds
4. Say "that's all", "thank you", "goodbye", or "I'm done" to end conversation

### Example Conversation Flow
```
You: "Jarvis, what's 2+2?"
JARVIS: "4"
You: "What about 5+5?" (no wake word needed!)
JARVIS: "10"
You: "Thank you, that's all"
JARVIS: Returns to sleep mode
```

### Testing and Development

#### Health Check
```bash
curl http://localhost:3000/health/summary
```

#### Run Benchmarks
```bash
npm run bench
```

#### Run Tests
```bash
npm test
```

#### Direct Chat API
```bash
curl -X POST http://localhost:3000/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Hello JARVIS", "session_id": "test"}'
```

### Configuration

#### vLLM Heavy Model Setup
Edit `config/model-policy.yaml` and set:
```yaml
endpoints:
  vllm_base_url: "http://your-vllm-server:8000"
```

## Architecture

### Core Components

#### TypeScript Backend
- **LocalLlamaEngine**: Direct llama.cpp bindings with Metal acceleration
- **VllmEngine**: Heavy model client for complex queries via HTTP
- **SessionManager**: KV-cache reuse and conversation context management
- **Router**: Smart query classification (direct_command/trivial/normal/hard)
- **EngineSelector**: Route queries to optimal models with fallback logic
- **ConversationHandler**: Manages TTS integration and conversation flow
- **DeviceActions**: System automation and device control
- **ToolExecutor**: Extensible tool system for various actions

#### Python Voice System
- **JARVISVoice**: ElevenLabs TTS integration with natural voice synthesis
- **JARVISWakeSystem**: Porcupine wake word detection with "Jarvis" trigger
- **JARVISWhisper**: OpenAI Whisper integration for speech-to-text
- **ConversationManager**: Intelligent follow-up conversation handling

### Model Policy
- **Router**: llama3.1:8b-instruct-q4_K_M for quick classification (512 context, 32 tokens max)
- **Primary**: llama3.1:8b-instruct-q4_K_M for most queries (1536 context, 256 tokens max)
- **Heavy**: mixtral:8x7b models for complex reasoning via vLLM (4096 context, 512 tokens max)

### Performance Targets
- **First token**: ≤1000ms (local), ≤1200ms (vLLM)
- **Total response**: ≤3500ms (local), ≤15s (heavy)
- **Direct commands**: ≤1s (bypass LLM entirely)

## API Endpoints

### Health Checks
```bash
# Local engine status
curl http://localhost:3000/health/local

# Heavy engine status  
curl http://localhost:3000/health/heavy

# Full system summary with latency stats
curl http://localhost:3000/health/summary
```

### Chat Interface
```bash
# Main chat endpoint (streaming response)
curl -X POST http://localhost:3000/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Hello JARVIS", "session_id": "test"}'

# Test endpoint with TTS integration
curl -X POST http://localhost:3000/chat/test \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello JARVIS", "session_id": "test"}'

# Direct TTS endpoint (no LLM processing)
curl -X POST http://localhost:3000/chat/speak \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello there!"}'

# Clear session
curl -X POST http://localhost:3000/chat/clear \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test"}'
```

## Common Issues & Troubleshooting

### Missing GGUF Files
```
❌ Missing model: llama3.1:8b-instruct-q4_K_M
Expected path: /path/to/models/llama-3.1-8b-instruct-q4_k_m.gguf
```
**Solution**: Download required models to the `models/` directory

### Environment Variables Not Loaded
```
❌ ELEVEN_API_KEY not set
❌ PORCUPINE_ACCESS_KEY not set
```
**Solution**: Create `.env` file with your API keys or use the startup scripts

### Backend Not Running
```
❌ Backend not running. Please start it first with: ./start_backend.sh
```
**Solution**: Start the TypeScript backend before the voice system

### Metal Not Working
```
⚠️ Metal layers not used - performance may be degraded
```
**Solution**: Ensure you're on macOS with Apple Silicon and n_gpu_layers = -1

### Python Dependencies Missing
```
ModuleNotFoundError: No module named 'pvporcupine'
```
**Solution**: Activate virtual environment and install requirements:
```bash
source jarvis_env/bin/activate
pip install -r requirements.txt
```

### Wrong vLLM Base URL
```
❌ vLLM unreachable at http://localhost:8000
```
**Solution**: Check vLLM server is running and update `config/model-policy.yaml`

## Development

### File Structure
```
jarvis_ai/
├── src/                        # TypeScript backend source
│   ├── index.ts               # Main entry point & HTTP server
│   ├── engines/               # AI model integrations
│   │   ├── local/            # llama.cpp bindings
│   │   └── heavy/            # vLLM client
│   ├── conversation/         # TTS integration & conversation handling
│   ├── session/              # Context management & KV-cache
│   ├── router/               # Query classification & routing
│   ├── tools/                # Device actions, web fetch, extensible tools
│   ├── policy/               # Configuration loading & validation
│   ├── asr/                  # Speech recognition components
│   └── utils/                # Logging, timing, environment utilities
├── config/                    # Model policy & configuration
├── tests/                     # Unit tests & benchmarks
├── models/                    # GGUF model storage
├── jarvis_env/               # Python virtual environment
├── wake_system_integrated.py # Python voice system (wake word + ASR + TTS)
├── start_backend.sh          # Backend startup script
├── start_jarvis.sh           # Complete system startup script
└── requirements.txt          # Python dependencies
```

### Testing
```bash
# Unit tests
npm test

# Latency benchmarks  
npm run bench

# Build check
npm run build
```

### Development Commands
```bash
# Development mode (auto-reload)
npm run dev

# Build TypeScript
npm run build

# Run tests
npm test

# Run latency benchmarks
npm run bench

# Check system health
npm run health
```

## System Integration

### Voice Pipeline
The system uses a sophisticated voice pipeline connecting Python and TypeScript components:

1. **Wake Word Detection** (Python): Porcupine detects "Jarvis" wake word
2. **Speech Recognition** (Python): OpenAI Whisper transcribes speech to text
3. **Text Processing** (TypeScript): Backend processes queries through AI models
4. **Response Generation** (TypeScript): Streaming responses with conversation context
5. **Text-to-Speech** (Python): ElevenLabs synthesizes natural voice responses
6. **Follow-up Management** (Python): Intelligent conversation flow control

### API Bridge
HTTP endpoints connect the voice system to the TypeScript backend:
- `/chat/test` - Full processing with TTS integration
- `/chat/speak` - Direct TTS without LLM processing
- `/chat/clear` - Session management
- `/health/*` - System monitoring

## Current Status & Roadmap

### ✅ Completed Features
- High-performance TypeScript backend with llama.cpp integration
- Complete voice pipeline (wake word + ASR + TTS)
- Intelligent conversation flow with follow-up detection
- Session management and context retention
- Device automation capabilities
- HTTP API endpoints for integration
- Tiered model system with fallback logic
- Comprehensive error handling and logging

### 🔄 Current Phase: Production Optimization
- Performance tuning and latency optimization
- Enhanced device automation capabilities
- Advanced conversation management

### 📋 Future Phases
- **Phase 3**: Advanced device automation and smart home integration
- **Phase 4**: Cross-platform deployment (Windows, Linux)
- **Phase 5**: Mobile companion app
- **Phase 6**: Multi-user support and personalization

## License

MIT License - Personal project, feel free to fork and adapt.

---

**⚡ Ready to build the future of personal AI? Let's make JARVIS real.**