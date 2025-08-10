# JARVIS - Personal AI Assistant

*"Yes sir, how may I assist you?"*

A local-first, privacy-focused AI assistant inspired by Iron Man's JARVIS. Built with TypeScript for high performance, featuring voice activation, natural conversation, and deep system integration.

## Features

- **🗣️ Voice-Activated**: Wake word detection with "Jarvis"
- **🔐 Privacy-First**: All processing happens locally, no data leaves your device
- **💬 Conversational**: Natural, human-like interactions with context awareness
- **⚡ High Performance**: Direct llama.cpp integration with Metal acceleration on Apple Silicon
- **🔧 Extensible**: Modular TypeScript architecture for cross-platform deployment
- **🧠 Intelligent**: Tiered model system (router/primary/heavy) for optimal performance

## Quick Start

### Prerequisites
- **Node.js** ≥18
- **macOS** (for Metal acceleration) or Linux
- **GGUF models** (automatically validated on startup)

### Installation

1. **Clone and setup**:
   ```bash
   git clone https://github.com/rahulremany/JARVIS.git
   cd JARVIS
   npm install  # Required: Installs all dependencies (~2 minutes)
   ```

2. **Download AI Models**:
   ```bash
   # Create models directory
   mkdir -p models
   
   # Download required GGUF model (example - replace with your preferred model)
   # For Llama 3.1 8B Instruct Q4_K_M (~4.6GB):
   wget -O models/llama-3.1-8b-instruct-q4_k_m.gguf \
     "https://huggingface.co/bartowski/Meta-Llama-3.1-8B-Instruct-GGUF/resolve/main/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf"
   
   # Or download manually from: https://huggingface.co/bartowski/Meta-Llama-3.1-8B-Instruct-GGUF
   ```

3. **Environment setup**:
   ```bash
   cp env.example .env
   # Edit .env with your API keys (ElevenLabs, Porcupine)
   ```

3. **Run in development**:
   ```bash
   npm run dev
   ```

4. **Health check**:
   ```bash
   curl http://localhost:3000/health/summary
   ```

### How to Run Bench
```bash
npm run bench
```

### How to Point at vLLM
Edit `config/model-policy.yaml` and set:
```yaml
endpoints:
  vllm_base_url: "http://your-vllm-server:8000"
```

## Architecture

### Core Components
- **LocalLlamaEngine**: Direct llama.cpp bindings with Metal acceleration
- **VllmEngine**: Heavy model client for complex queries
- **SessionManager**: KV-cache reuse and conversation context
- **Router**: Smart query classification (direct_command/trivial/normal/hard)
- **EngineSelector**: Route queries to optimal models with fallback

### Model Policy
- **Router**: phi3:mini for quick classification
- **Primary**: llama3.1:8b-instruct-q4_K_M for most queries  
- **Heavy**: mixtral:8x7b models for complex reasoning (via vLLM)

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
curl -X POST http://localhost:3000/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Hello JARVIS", "session_id": "test"}'
```

## Common Errors

### Missing GGUF Files
```
❌ Missing model: llama3.1:8b-instruct-q4_K_M
Expected path: /path/to/models/llama-3.1-8b-instruct-q4_k_m.gguf
```
**Solution**: Download required models to the `models/` directory

### Metal Not Working
```
⚠️ Metal layers not used - performance may be degraded
```
**Solution**: Ensure you're on macOS with M1/M2 and n_gpu_layers = -1

### Wrong Base URL
```
❌ vLLM unreachable at http://localhost:8000
```
**Solution**: Check vLLM server is running and update `config/model-policy.yaml`

## Development

### File Structure
```
/src/
  index.ts                      # Main entry point
  /engines/local/               # llama.cpp integration
  /engines/heavy/               # vLLM client
  /session/                     # Context management
  /router/                      # Query routing
  /tools/                       # Device actions, web fetch
  /utils/                       # Logging, timing utilities

/tests/                         # Unit tests and benchmarks
/config/                        # Model policy configuration
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

### Pre-commit Protection
The repository enforces strict file organization. Only these files may be created/edited for core functionality:
- `/src/engines/local/LocalLlamaEngine.ts`
- `/src/engines/heavy/VllmEngine.ts`
- `/src/session/SessionManager.ts`
- `/src/router/Router.ts`
- `/src/router/EngineSelector.ts`
- `/src/policy/loadPolicy.ts`
- `/src/utils/logging.ts`
- `/src/index.ts`

## Voice System Integration

The current TypeScript engine integrates with the existing Python voice system:
- **Wake Word**: `wake_system.py` handles Porcupine wake word detection
- **TTS**: ElevenLabs integration for JARVIS voice output
- **API Bridge**: HTTP endpoints connect voice system to TypeScript engine

## Roadmap

1. **✅ Phase 1**: High-performance TypeScript engine
2. **🔄 Phase 2**: Voice system integration (Python → TypeScript)
3. **📋 Phase 3**: Advanced device automation
4. **🌐 Phase 4**: Cross-platform deployment

## License

MIT License - Personal project, feel free to fork and adapt.

---

**⚡ Ready to build the future of personal AI? Let's make JARVIS real.**