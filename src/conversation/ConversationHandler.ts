// src/conversation/ConversationHandler.ts

import { LocalLlamaEngine } from '../engines/local/LocalLlamaEngine.js';
import { logger } from '../utils/logging.js';
import { exec } from 'child_process';
import { promisify } from 'util';
import fs from 'fs';
import path from 'path';

const execAsync = promisify(exec);

export interface ConversationConfig {
  elevenLabsApiKey?: string;
  elevenLabsVoiceId?: string;
  enableTTS?: boolean;
}

export class ConversationHandler {
  private config: ConversationConfig;
  private isSpeaking = false;

  constructor(config?: ConversationConfig) {
    this.config = {
      elevenLabsApiKey: config?.elevenLabsApiKey || process.env.ELEVEN_API_KEY,
      elevenLabsVoiceId: config?.elevenLabsVoiceId || process.env.JARVIS_VOICE_ID || 'LE42bqYwZicKpZRastCO',
      enableTTS: config?.enableTTS ?? true
    };

    if (this.config.enableTTS && !this.config.elevenLabsApiKey) {
      logger.warn('TTS enabled but ELEVEN_API_KEY not set - will use macOS say command as fallback');
    }
  }

  /**
   * Process LLM response and convert to speech
   */
  async processAndSpeak(response: string, sessionId: string): Promise<void> {
    if (!this.config.enableTTS) {
      logger.info(`JARVIS says: "${response}"`);
      return;
    }

    // Clean up response for speech
    const spokenText = this.cleanForSpeech(response);
    
    if (this.config.elevenLabsApiKey) {
      await this.speakWithElevenLabs(spokenText);
    } else {
      // Fallback to macOS say command
      await this.speakWithMacOS(spokenText);
    }
  }

  /**
   * Clean text for speech output
   */
  private cleanForSpeech(text: string): string {
    // Remove special tokens
    text = text.replace(/<\|.*?\|>/g, '');
    text = text.replace(/\|im_end\|/g, '');
    text = text.replace(/\|im_start\|/g, '');
    text = text.replace(/assistant/g, '');
    
    // Remove markdown
    text = text.replace(/[*_~`]/g, '');
    
    // Remove code blocks
    text = text.replace(/```[\s\S]*?```/g, 'code block');
    
    // Remove URLs
    text = text.replace(/https?:\/\/[^\s]+/g, 'link');
    
    // Clean up multiple spaces and newlines
    text = text.replace(/\s+/g, ' ').trim();
    
    return text;
  }

  /**
   * Speak using ElevenLabs API
   */
  private async speakWithElevenLabs(text: string): Promise<void> {
    if (this.isSpeaking) {
      logger.warn('Already speaking, skipping...');
      return;
    }

    this.isSpeaking = true;
    
    try {
      const url = `https://api.elevenlabs.io/v1/text-to-speech/${this.config.elevenLabsVoiceId}`;
      
      // Using fetch instead of axios since it's built into Node 18+
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Accept': 'audio/mpeg',
          'Content-Type': 'application/json',
          'xi-api-key': this.config.elevenLabsApiKey!
        },
        body: JSON.stringify({
          text,
          model_id: 'eleven_monolingual_v1',
          voice_settings: {
            stability: 0.6,
            similarity_boost: 1.0,
            style: 0.0,
            use_speaker_boost: true
          }
        })
      });

      if (!response.ok) {
        throw new Error(`ElevenLabs API error: ${response.status}`);
      }

      // Save audio to temp file
      const audioBuffer = await response.arrayBuffer();
      const tempFile = path.join('/tmp', `jarvis_${Date.now()}.mp3`);
      fs.writeFileSync(tempFile, Buffer.from(audioBuffer));
      
      // Play audio with increased volume
      await execAsync(`afplay -v 2 "${tempFile}"`);
      
      // Clean up
      fs.unlinkSync(tempFile);
      
      logger.info('TTS playback complete');
    } catch (error) {
      logger.error('ElevenLabs TTS error:', error);
      // Don't fallback - just log the error so we know what's wrong
      logger.error('TTS failed - check your ELEVEN_API_KEY');
    } finally {
      this.isSpeaking = false;
    }
  }

  /**
   * Fallback TTS using macOS say command
   */
  private async speakWithMacOS(text: string): Promise<void> {
    if (this.isSpeaking) return;
    
    this.isSpeaking = true;
    
    try {
      // Use Daniel voice (British accent, closer to JARVIS)
      await execAsync(`say -v Daniel "${text.replace(/"/g, '\\"')}"`);
      logger.info('macOS TTS playback complete');
    } catch (error) {
      logger.error('macOS say command failed:', error);
    } finally {
      this.isSpeaking = false;
    }
  }

  /**
   * Handle conversation from text input (for testing)
   */
  async handleTextInput(
    text: string, 
    llmEngine: LocalLlamaEngine,
    sessionId: string = 'default'
  ): Promise<string> {
    try {
      // Generate response using existing LLM engine
      let response = '';
      
      const prompt = `You are JARVIS, a personal AI assistant. You are helpful, concise, and professional.
Never reference Tony Stark, Iron Man, or Marvel characters. You assist real users with real tasks.
Keep responses brief and focused. Remember user preferences and names when told.

User: ${text}
Assistant:`;
      
      for await (const event of llmEngine.generateStream(sessionId, prompt, {
        max_tokens: 150,
        temperature: 0.7
      })) {
        if (event.type === 'token' && event.text) {
          response += event.text;
        }
      }
      
      response = response.trim();
      
      // Speak the response
      await this.processAndSpeak(response, sessionId);
      
      return response;
    } catch (error) {
      logger.error('Conversation error:', error);
      const errorMessage = "I apologize, I encountered an error.";
      await this.processAndSpeak(errorMessage, sessionId);
      return errorMessage;
    }
  }

  /**
   * Stop any ongoing speech
   */
  async stopSpeaking(): Promise<void> {
    if (this.isSpeaking) {
      try {
        // Kill any afplay or say processes
        await execAsync('pkill -f afplay || true');
        await execAsync('pkill -f say || true');
        this.isSpeaking = false;
      } catch (error) {
        logger.error('Error stopping speech:', error);
      }
    }
  }
}