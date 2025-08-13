# Jarvis – Voice-First AI Assistant

Jarvis is a real-time, always-listening AI assistant designed for natural, conversational interaction using speech.  
It combines speech recognition, large language models, and speech synthesis into an integrated, hands-free system.

## Tech Stack

- **Speech-to-Text (STT):** OpenAI Whisper / Wispr
- **Language Model (LLM Core):** OpenAI, Anthropic, or Local (Qwen, LLaMA)
- **Text-to-Speech (TTS):** ElevenLabs / Coqui
- **Backend:** Python, FastAPI
- **Audio I/O:** Microphone input & speaker output
- **Deployment:** Local execution with modular architecture for cloud expansion

## Features

- **Wake Word Detection:** Hands-free activation by saying “Jarvis”
- **Real-Time STT:** Converts speech to text with high accuracy
- **Natural Language Understanding:** Processes requests through a pluggable LLM core
- **Dynamic Skills & Tools:**
  - Information lookup
  - Scheduling and reminders
  - Custom command execution
- **TTS Output:** Responds in natural-sounding synthesized speech
- **Sleep Mode:** Ability to pause listening until reactivated

## Architecture

![Jarvis Architecture](docs/jarvis_architecture.png)

**Flow:**
1. Microphone captures user audio upon wake word detection.
2. STT engine transcribes speech to text.
3. LLM core processes the query, optionally invoking custom tools.
4. Response is synthesized via TTS.
5. Audio is played through speakers.

## Example Session

![Jarvis Terminal Session](docs/jarvis_terminal.png)

**Conversation Flow:**
1. User: “Jarvis, introduce yourself.”  
   **Jarvis:** “I’m here to assist with your queries and tasks. How can I help you today?”
2. User: “Summarize what you can do.”  
   **Jarvis:** “I can help with scheduling, notifications, research, information lookup, and more.”
3. User: “That’s all.”  
   **Jarvis:** *Enters sleep mode.*

## Project Goals

- Explore **multimodal AI system design**.
- Demonstrate integration of **real-time audio pipelines**.
- Show **modular AI architecture** that supports switching between cloud and local LLMs.
- Build a **resume-ready portfolio project** highlighting:
  - Speech recognition
  - LLM integration
  - Speech synthesis
  - Event-driven application design

## Future Enhancements

- Context retention across sessions
- Multi-language support
- Visual interface for hybrid voice+screen workflows
- Integration with IoT devices and automation APIs
