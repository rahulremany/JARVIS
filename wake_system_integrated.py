#!/usr/bin/env python3
"""
JARVIS - Integrated Wake Word + ASR + Backend System
Complete pipeline: Wake → Listen → Transcribe → Process → Speak
"""

import numpy as np
import pvporcupine
import sounddevice as sd
import whisper
import time
import os
import requests
import json
from collections import deque
import threading
import queue

def load_env_variables():
    """Load environment variables from multiple sources"""
    # Try to load from .env file if it exists
    env_file_paths = ['.env', '.env.local', 'config.env']
    
    for env_file in env_file_paths:
        if os.path.exists(env_file):
            print(f"✅ Loading environment variables from {env_file}")
            with open(env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        # Remove quotes if present
                        value = value.strip().strip('"').strip("'")
                        os.environ[key.strip()] = value
            return True
    
    # Fallback: Set hardcoded values if no env file found
    if not os.getenv('ELEVEN_API_KEY') or not os.getenv('PORCUPINE_ACCESS_KEY'):
        print("⚠️  No .env file found, setting hardcoded environment variables")
        os.environ['ELEVEN_API_KEY'] = 'sk_8cfb858b5cb92cbae9dbd1bd03059eae8de3ee5ea2d87ae5'
        os.environ['PORCUPINE_ACCESS_KEY'] = 'X/oCDj0hcbuwCCLjZUmu1p7fdBjBN4Vti6rcBvSp9ycmJguOG9kEZQ=='
        os.environ['JARVIS_VOICE_ID'] = 'LE42bqYwZicKpZRastCO'
        return True
    
    return False

class JARVISVoice:
    """JARVIS Voice System - Uses backend TTS"""
    def __init__(self):
        self.backend_url = "http://localhost:3000"
        
    def speak_via_backend(self, text):
        """Let the backend handle TTS"""
        # Backend already has ElevenLabs integration
        pass

class WhisperASR:
    """Whisper ASR for speech-to-text"""
    def __init__(self, model_size="base"):
        print(f"Loading Whisper {model_size} model...")
        self.model = whisper.load_model(model_size)
        print("Whisper model loaded")
        
    def transcribe(self, audio_data, sample_rate=16000):
        """Transcribe audio to text"""
        # Whisper expects float32 audio
        if audio_data.dtype != np.float32:
            audio_data = audio_data.astype(np.float32) / 32768.0
            
        # Normalize audio volume to help with quiet speech
        audio_data = audio_data / np.max(np.abs(audio_data)) if np.max(np.abs(audio_data)) > 0 else audio_data
        
        # Pad/trim to 30 seconds as Whisper expects
        audio_data = whisper.pad_or_trim(audio_data)
        
        # Transcribe with more aggressive settings
        result = self.model.transcribe(
            audio_data,
            language="en",
            fp16=False,  # Use FP32 for M1 Macs
            no_speech_threshold=0.3,  # Lower threshold for quieter speech
            condition_on_previous_text=False,  # Don't condition on previous text
            word_timestamps=False,
            initial_prompt="Hello, what's the weather? How are you? What time is it?"  # Help with context
        )
        
        return result["text"].strip()

class JARVISIntegrated:
    """Integrated JARVIS System with full pipeline"""
    
    def __init__(self):
        """Initialize all components"""
        self.sample_rate = 16000
        self.backend_url = "http://localhost:3000"
        self.session_id = "jarvis_main"
        
        # Porcupine wake word
        self.access_key = os.getenv('PORCUPINE_ACCESS_KEY')
        if not self.access_key:
            raise ValueError("PORCUPINE_ACCESS_KEY environment variable not set")
        
        self.porcupine = pvporcupine.create(
            access_key=self.access_key,
            keywords=["jarvis"],
            sensitivities=[0.7]  # More sensitive to catch wake word better
        )
        
        # Whisper ASR
        self.whisper = WhisperASR(model_size="base")  # base is good balance of speed/quality
        
        # Audio buffers and settings
        self.frame_buffer = []
        self.recording_buffer = []
        self.is_recording = False
        self.is_speaking = False
        self.recording_start_time = 0
        self.silence_threshold = 0.003  # Lower = more sensitive to quiet speech
        self.silence_duration = 0
        self.max_recording_time = 15  # Max 15 seconds per command
        self.min_recording_time = 1.0  # Min 1 second to avoid cutting off
        self.energy_history = []  # Track energy to better detect speech
        
        # Follow-up mode settings
        self.follow_up_mode = False
        self.follow_up_start_time = 0
        self.follow_up_timeout = 10  # Wait 10 seconds for follow-up command
        self.follow_up_silence_threshold = 0.002  # Very sensitive threshold for follow-up
        self._recording_restart_scheduled = False  # Prevent duplicate restarts
        
        # Voice protection against feedback
        self.jarvis_speaking_end_time = 0  # Timestamp when JARVIS finishes speaking
        self.recent_jarvis_responses = []  # Track recent responses for content filtering
        
        # Threading for async processing
        self.command_queue = queue.Queue()
        self.processing_thread = threading.Thread(target=self._process_commands, daemon=True)
        self.processing_thread.start()
        
        # Audio stream
        self.stream = None
        
        print("🎤 Audio detection settings:")
        print(f"   Silence threshold: {self.silence_threshold}")
        print(f"   Follow-up threshold: {self.follow_up_silence_threshold}")
        print(f"   Min recording time: {self.min_recording_time}s")
        print(f"   Max recording time: {self.max_recording_time}s")
        
    def _audio_callback(self, indata, frames, time_info, status):
        """Audio callback - handles wake word and recording"""
        audio_chunk = indata[:, 0]
        
        # Check if we're in speech protection period (JARVIS recently spoke)
        current_time = time.time()
        if current_time < self.jarvis_speaking_end_time:
            # JARVIS is still speaking - don't process audio
            return
        
        # Always add to frame buffer for wake word detection
        self.frame_buffer.extend(audio_chunk)
        
        # If recording, also add to recording buffer
        if self.is_recording:
            self.recording_buffer.extend(audio_chunk)
            
            # Calculate energy and keep track of recent history
            chunk_energy = np.mean(np.abs(audio_chunk))
            self.energy_history.append(chunk_energy)
            if len(self.energy_history) > 10:
                self.energy_history.pop(0)
            
            # Dynamic silence detection based on recent audio
            avg_recent_energy = np.mean(self.energy_history) if self.energy_history else 0
            dynamic_threshold = max(self.silence_threshold, avg_recent_energy * 0.1)
            
            if chunk_energy < dynamic_threshold:
                self.silence_duration += len(audio_chunk) / self.sample_rate
                
                # Stop recording after 3 seconds of silence
                if self.silence_duration > 3.0:
                    self._stop_recording()
            else:
                self.silence_duration = 0
            
            # Stop recording after max time
            current_time = time.time()
            if current_time - self.recording_start_time > self.max_recording_time:
                self._stop_recording()
        
        # Continuous listening mode: automatically restart recording after each response
        if self.follow_up_mode and not self.is_recording and not self.is_speaking:
            current_time = time.time()
            if current_time - self.follow_up_start_time > self.follow_up_timeout:
                print("⏰ Follow-up timeout - returning to wake word mode")
                self.follow_up_mode = False
            elif not self._recording_restart_scheduled:
                # Start recording immediately - no time delays
                print("🎙️ Now listening for your command...")
                self._recording_restart_scheduled = True
                self._start_recording(skip_confirmation=True)
                return
        
        # Process wake word detection (only when not in follow-up mode, not recording, and not speaking)
        if not self.follow_up_mode and not self.is_recording and not self.is_speaking:
            while len(self.frame_buffer) >= self.porcupine.frame_length:
                frame = np.array(self.frame_buffer[:self.porcupine.frame_length])
                self.frame_buffer[:] = self.frame_buffer[self.porcupine.frame_length:]
                
                # Convert to int16 for Porcupine
                audio_int16 = (frame * 32768).astype(np.int16)
                keyword_index = self.porcupine.process(audio_int16)
                
                if keyword_index >= 0:
                    print("\n🎤 Wake word detected! Listening...")
                    self._start_recording()
    
    def _start_recording(self, skip_confirmation=False):
        """Start recording user command"""
        if not skip_confirmation:
            # Play "Yes sir?" first (only for wake word activation)
            threading.Thread(target=self._play_listening_sound, daemon=True).start()
            
            # Wait for "Yes sir?" to finish
            time.sleep(1.2)
        
        # Start recording
        self.is_recording = True
        self.recording_buffer = []  # Fresh buffer
        self.recording_start_time = time.time()
        self.silence_duration = 0
        self.energy_history = []  # Reset energy history
        print("🎙️ Now listening for your command...")
    
    def _stop_recording(self):
        """Stop recording and process the command"""
        if not self.is_recording:
            return
            
        self.is_recording = False
        
        # Check minimum recording length
        recording_duration = len(self.recording_buffer) / self.sample_rate
        if recording_duration < self.min_recording_time:
            print(f"Recording too short ({recording_duration:.1f}s), ignoring...")
            return
        
        print(f"📝 Processing {recording_duration:.1f}s of audio...")
        
        # Convert to numpy array
        audio_data = np.array(self.recording_buffer, dtype=np.float32)
        
        # Basic audio validation
        max_amplitude = np.max(np.abs(audio_data))
        if max_amplitude < 0.001:
            print("Audio too quiet, ignoring...")
            return
        
        print(f"🔊 Audio level: {max_amplitude:.4f}")
        
        # Queue for processing
        self.command_queue.put(audio_data)
    
    def _is_conversation_end_fast(self, text):
        """Detect if the user wants to end the conversation using only keyword detection"""
        text_lower = text.lower().strip()
        
        # Check for obvious ending phrases only (no AI analysis to avoid interference)
        obvious_endings = [
            "that's all", "thats all", "that is all",
            "thank you", "thanks", "bye", "goodbye", "good bye",
            "that's it", "thats it", "that is it",
            "i'm done", "im done", "done for now", "finished",
            "stop", "stop listening", "go to sleep", "sleep mode",
            "that's enough", "thats enough", "enough",
            "never mind", "nevermind", "cancel", "forget it",
            "goodnight", "good night", "see you later", "talk to you later"
        ]
        
        for ending in obvious_endings:
            if ending in text_lower:
                return True
        
        return False
    
    def _is_jarvis_speech(self, text):
        """Detect if the transcription is JARVIS's own voice"""
        text_lower = text.lower().strip()
        
        # Filter obvious artifacts
        if (text_lower.startswith("you") or 
            "tony stark" in text_lower or
            "iron man" in text_lower or
            "jarvis" in text_lower[:20]):  # Skip if "jarvis" in first 20 chars
            return True
        
        # Check if it matches recent JARVIS responses (similarity check)
        for recent_response in self.recent_jarvis_responses:
            if self._text_similarity(text_lower, recent_response.lower()) > 0.7:
                return True
        
        # JARVIS-specific speech patterns
        jarvis_patterns = [
            "the answer is", "the answer to", "i can assist", "i can help",
            "is there anything else", "would you like", "i'm happy to help",
            "user, i'm happy", "however, i must clarify", "could you please",
            "feel free to", "i'll do my best", "provide a helpful response",
            "appears to be missing", "doesn't seem to be", "to perform the calculation"
        ]
        
        for pattern in jarvis_patterns:
            if pattern in text_lower:
                return True
        
        # Check for mathematical response patterns
        if any(phrase in text_lower for phrase in ["plus", "minus", "equals", "calculation", "operator"]):
            if any(phrase in text_lower for phrase in ["the answer", "result", "equals"]):
                return True
        
        return False
    
    def _text_similarity(self, text1, text2):
        """Simple text similarity using word overlap"""
        words1 = set(text1.split())
        words2 = set(text2.split())
        if not words1 or not words2:
            return 0
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        return len(intersection) / len(union)
    
    def _play_listening_sound(self):
        """Play 'Yes sir?' using the backend's TTS"""
        self.is_speaking = True
        try:
            # Use backend's TTS endpoint (with your cloned voice)
            response = requests.post(
                f"{self.backend_url}/chat/speak",
                json={"text": "Yes sir?"},
                timeout=5
            )
            # Wait a bit for audio to finish
            time.sleep(1.0)
        except Exception as e:
            print(f"TTS error: {e}")
        finally:
            self.is_speaking = False
            # Mark when JARVIS finished speaking for voice protection
            self.jarvis_speaking_end_time = time.time()
    
    def _process_commands(self):
        """Process commands in background thread"""
        while True:
            try:
                # Get audio data from queue
                audio_data = self.command_queue.get(timeout=1)
                
                # Clear any old session data first
                try:
                    requests.post(
                        f"{self.backend_url}/chat/clear",
                        json={"session_id": self.session_id},
                        timeout=2
                    )
                except:
                    pass  # Don't worry if clear fails
                
                # Transcribe with Whisper
                print("🎯 Transcribing...")
                start_time = time.time()
                transcription = self.whisper.transcribe(audio_data, self.sample_rate)
                transcribe_time = time.time() - start_time
                
                if not transcription or len(transcription.strip()) < 2:
                    print("No speech detected in transcription")
                    continue
                
                # Clean up transcription and filter out JARVIS speech
                transcription = transcription.strip()
                
                # Enhanced JARVIS speech detection
                if self._is_jarvis_speech(transcription):
                    print("🚫 Filtered out JARVIS speech feedback")
                    continue
                
                # Check if user wants to end the conversation (only use fast detection to avoid interference)
                if self._is_conversation_end_fast(transcription):
                    print("👋 Conversation ended by user - returning to wake word mode")
                    self.follow_up_mode = False
                    print("💤 JARVIS is now sleeping. Say 'Jarvis' to wake me up.")
                    continue
                
                print(f"📝 You said: \"{transcription}\" (transcribed in {transcribe_time:.2f}s)")
                
                # Send to backend for processing
                print("🤖 Processing with JARVIS...")
                response = requests.post(
                    f"{self.backend_url}/chat/test",
                    json={
                        "text": transcription,
                        "session_id": self.session_id
                    },
                    timeout=45  # Increase timeout for longer responses
                )
                
                if response.status_code == 200:
                    result = response.json()
                    jarvis_response = result.get("jarvis", "")
                    print(f"🔊 JARVIS: \"{jarvis_response}\"")
                    # Backend already handles TTS
                    
                    # Track JARVIS response for voice recognition
                    self.recent_jarvis_responses.append(jarvis_response)
                    if len(self.recent_jarvis_responses) > 5:  # Keep only last 5 responses
                        self.recent_jarvis_responses.pop(0)
                    
                    # No delay - start listening immediately after TTS (backend handles TTS)
                    # The backend TTS call has finished by the time we get here, so start immediately
                    self.jarvis_speaking_end_time = time.time()  # TTS is done, start immediately
                    
                    # Enable continuous listening mode (re-enter recording loop instantly)
                    self.follow_up_mode = True
                    self.follow_up_start_time = time.time()  # Reset timeout timer
                    self._follow_up_recording_started = False  # Reset flag to trigger new recording
                    self._recording_restart_scheduled = False  # Reset restart flag
                    # Will immediately show "Now listening for your command..." and start recording
                else:
                    print(f"Backend error: {response.status_code}")
                    if response.status_code == 400:
                        print("Bad request - check if backend is running properly")
                    
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Processing error: {e}")
    
    def start(self):
        """Start JARVIS"""
        print("\n" + "="*50)
        print("🤖 JARVIS INTEGRATED SYSTEM")
        print("="*50)
        print("✅ Wake word: 'Jarvis'")
        print("✅ ASR: Whisper")
        print("✅ Backend: Connected to localhost:3000")
        print("✅ TTS: ElevenLabs via backend")
        print("\n💡 Say 'Jarvis' followed by your command")
        print("🎤 Speak clearly and wait for 'Yes sir?' before speaking")
        print("🔄 After JARVIS responds, it will automatically re-listen for your next command")
        print("⏰ Continuous listening lasts 10 seconds, then returns to wake word mode")
        print("🛑 Say 'that's all', 'thank you', 'goodbye', or 'I'm done' to end the conversation")
        print("="*50 + "\n")
        
        self.stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype=np.float32,
            callback=self._audio_callback,
            blocksize=512
        )
        self.stream.start()
        
        try:
            while True:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\n👋 Shutting down JARVIS...")
        
        self.stop()
    
    def stop(self):
        """Stop JARVIS"""
        if self.stream:
            self.stream.stop()
            self.stream.close()
        if self.porcupine:
            self.porcupine.delete()
        print("JARVIS shutdown complete")

def main():
    """Main function"""
    # Load environment variables first
    load_env_variables()
    
    # Check if backend is running
    try:
        response = requests.get("http://localhost:3000/health/summary", timeout=2)
        if response.status_code != 200:
            raise Exception("Backend not responding")
        print("✅ Backend is running")
    except:
        print("❌ Error: JARVIS backend not running!")
        print("Please run 'npm run dev' first")
        return
    
    try:
        jarvis = JARVISIntegrated()
        jarvis.start()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()