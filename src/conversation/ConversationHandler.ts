// src/conversation/ConversationHandler.ts
import { LocalLlamaEngine } from '../engines/local/LocalLlamaEngine.js';
import { logger } from '../utils/logging.js';
import { ToolExecutor, ToolCall } from '../tools/ToolExecutor.js';
import { exec } from 'child_process';
import { promisify } from 'util';
import fs from 'fs';
import path from 'path';

const execAsync = promisify(exec);

export interface ConversationConfig {
  elevenLabsApiKey?: string;
  elevenLabsVoiceId?: string;
  enableTTS?: boolean;
  enableTools?: boolean;
}

export class ConversationHandler {
  private config: ConversationConfig;
  private isSpeaking = false;
  private toolExecutor: ToolExecutor;

  constructor(config?: ConversationConfig) {
    this.config = {
      elevenLabsApiKey: config?.elevenLabsApiKey || process.env.ELEVEN_API_KEY,
      elevenLabsVoiceId: config?.elevenLabsVoiceId || process.env.JARVIS_VOICE_ID || 'LE42bqYwZicKpZRastCO',
      enableTTS: config?.enableTTS ?? true,
      enableTools: config?.enableTools ?? true
    };

    this.toolExecutor = new ToolExecutor();

    if (this.config.enableTTS && !this.config.elevenLabsApiKey) {
      logger.warn('TTS enabled but ELEVEN_API_KEY not set - will use macOS say command as fallback');
    }
  }

  /**
   * Handle conversation from text input with reliable tool detection
   */
  async handleTextInput(
    text: string, 
    llmEngine: LocalLlamaEngine,
    sessionId: string = 'default'
  ): Promise<string> {
    try {
      // First, try direct tool detection (more reliable than LLM for 3B model)
      const directTool = this.detectDirectToolCall(text);
    
    if (directTool) {
      logger.info(`Direct tool detected: ${directTool.action}`);
      
      // Give immediate feedback
      if (this.config.enableTTS) {
        const feedbackMessage = this.getToolFeedbackMessage(directTool);
        if (feedbackMessage) {
          this.processAndSpeak(feedbackMessage, 'system').catch(() => {});
        }
      }
      
      const toolResult = await this.toolExecutor.execute(directTool);
      
      // Generate a natural response based on the tool result
      const finalResponse = await this.generateToolResultResponse(
        text, 
        toolResult, 
        llmEngine, 
        sessionId
      );
      
      await this.processAndSpeak(finalResponse, sessionId);
      return finalResponse;
    }

    // If no direct tool needed, use regular conversation
    const prompt = `You are JARVIS, a helpful AI assistant. You are concise and professional.
Never reference Tony Stark, Iron Man, or Marvel. Keep responses brief and natural.

User: ${text}
JARVIS:`;
    
    let response = '';
    
    for await (const event of llmEngine.generateStream(sessionId, prompt, {
      max_tokens: 150,
      temperature: 0.7
    })) {
      if (event.type === 'token' && event.text) {
        response += event.text;
      }
    }
    
    response = response.trim();
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
 * Detect direct tool calls using reliable patterns (3B model scope + basic interactions)
 */
private detectDirectToolCall(text: string): ToolCall | null {
  const lower = text.toLowerCase();
  
  // Time detection - 3B can handle this instantly
  if ((lower.includes('time') || lower.includes('clock')) && 
      (lower.includes('what') || lower.includes('current'))) {
    return { action: 'get_time', params: {} };
  }
  
  // Screen reading - 3B routes to vision API
  if (lower.includes('screen') && 
      (lower.includes('what') || lower.includes('on') || lower.includes('see'))) {
    return { action: 'read_screen', params: {} };
  }
  
  // Web search - 3B can handle this
  if (lower.includes('search') || lower.includes('google') || lower.includes('look up')) {
    const searchMatch = text.match(/(?:search|google|look up)\s+(?:for\s+)?(.+)/i);
    if (searchMatch) {
      return { action: 'web_search_and_open', params: { query: searchMatch[1] } };
    }
  }
  
  // App opening - 3B can handle this
  if (lower.includes('open') && !lower.includes('search')) {
    const appMatch = text.match(/open\s+(\w+)/i);
    if (appMatch) {
      return { action: 'open_app', params: { name: appMatch[1] } };
    }
  }
  
  // Basic interactions - 3B can route these
  
  // Clicking
  if (lower.includes('click')) {
    const clickMatch = text.match(/click\s+(?:on\s+)?(.+)/i);
    if (clickMatch) {
      return { action: 'click_element', params: { target: clickMatch[1] } };
    }
  }
  
  // Typing in specific places
  if (lower.includes('type') && (lower.includes('in') || lower.includes('into'))) {
    const typeInMatch = text.match(/type\s+(.+?)\s+(?:in|into)\s+(.+)/i);
    if (typeInMatch) {
      return { action: 'type_in_field', params: { text: typeInMatch[1], field: typeInMatch[2] } };
    }
  }
  
  // Simple typing
  if (lower.includes('type')) {
    const typeMatch = text.match(/type\s+(.+)/i);
    if (typeMatch) {
      return { action: 'type_text', params: { text: typeMatch[1] } };
    }
  }
  
  // Scrolling
  if (lower.includes('scroll')) {
    if (lower.includes('down')) {
      return { action: 'scroll', params: { direction: 'down' } };
    } else if (lower.includes('up')) {
      return { action: 'scroll', params: { direction: 'up' } };
    }
    return { action: 'scroll', params: { direction: 'down' } }; // default
  }
  
  // Press key combinations
  if (lower.includes('press')) {
    const keyMatch = text.match(/press\s+(.+)/i);
    if (keyMatch) {
      const keys = keyMatch[1].split(/\s+(?:and|plus|\+)\s+/);
      return { action: 'press_keys', params: { keys } };
    }
  }
  
  // Complex compound actions
  if (lower.includes('open') && lower.includes('and') && lower.includes('type')) {
    const openTypeMatch = text.match(/open\s+(\w+)\s+and\s+type\s+(.+)/i);
    if (openTypeMatch) {
      return { action: 'open_and_type', params: { app: openTypeMatch[1], text: openTypeMatch[2] } };
    }
  }
  
  // Math should route to 8B, so return null for that
  // Complex reasoning should route to 8B, so return null for that
  
  return null;
}

/**
 * Get contextual feedback message for tool execution (3B scope + interactions)
 */
private getToolFeedbackMessage(toolCall: ToolCall): string | null {
  switch (toolCall.action) {
    case 'get_time':
      return null; // Time is instant
    case 'open_app':
      return `One moment sir, opening ${toolCall.params.name}`;
    case 'read_screen':
      return "One moment sir, analyzing your screen";
    case 'web_search_and_open':
      return "One moment sir, opening browser and searching";
    case 'click_element':
      return `One moment sir, clicking on ${toolCall.params.target}`;
    case 'type_in_field':
      return `One moment sir, typing in ${toolCall.params.field}`;
    case 'type_text':
      return "One moment sir, typing text";
    case 'open_and_type':
      return `One moment sir, opening ${toolCall.params.app} and typing text`;
    case 'scroll':
      return null; // Scrolling is instant
    case 'press_keys':
      return null; // Key presses are instant
    default:
      return null;
  }
}

/**
 * Generate natural response based on tool result
 */
private async generateToolResultResponse(
  originalQuery: string,
  toolResult: any,
  engine: LocalLlamaEngine,
  sessionId: string
): Promise<string> {
  if (!toolResult.success) {
    return `I apologize, but I wasn't able to ${toolResult.action.replace('_', ' ')}. ${toolResult.error || 'Please try again.'}`;
  }

  // For some tools, just return the result directly
  if (toolResult.action === 'get_time' || toolResult.action === 'calculate') {
    return toolResult.output;
  }

  // For other tools, generate a natural response
  const prompt = `The user asked: "${originalQuery}"
I executed the action and got this result: ${toolResult.output}

Respond naturally as JARVIS, confirming what was done. Keep it brief:`;

  try {
    let response = '';
    for await (const event of engine.generateStream(sessionId + '_tool', prompt, {
      max_tokens: 50,
      temperature: 0.7
    })) {
      if (event.type === 'token' && event.text) {
        response += event.text;
      }
    }
    return response.trim();
  } catch (error) {
    // Fallback to simple confirmation
    return `Done. ${toolResult.output}`;
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