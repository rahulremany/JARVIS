import { logger } from '../utils/logging.js';

export interface AsrConfig {
  modelSize: 'tiny' | 'base' | 'small' | 'medium' | 'large';
  language?: string;
  temperature?: number;
  initialPrompt?: string;
}

export interface AsrResult {
  text: string;
  confidence: number;
  language: string;
  duration: number;
  timestamp: number;
}

export class AsrWhisper {
  private config: AsrConfig;
  private whisper: any = null; // Will be loaded dynamically

  constructor(config: AsrConfig) {
    this.config = {
      modelSize: 'base',
      language: 'en',
      temperature: 0.0,
      initialPrompt: 'Hello, I am JARVIS. How may I help you?',
      ...config
    };
  }

  async initialize(): Promise<void> {
    try {
      // Dynamic import of whisper (assuming whisper-node or similar)
      // Note: This would need actual whisper integration
      logger.info('Initializing Whisper ASR...', {
        modelSize: this.config.modelSize,
        language: this.config.language
      });
      
      // Placeholder for actual whisper initialization
      // In production, this would load the actual Whisper model
      this.whisper = {
        transcribe: this.mockTranscribe.bind(this)
      };
      
      logger.info('Whisper ASR initialized successfully');
      
    } catch (error) {
      logger.error('Failed to initialize Whisper:', error);
      throw new Error(`Whisper initialization failed: ${error}`);
    }
  }

  async transcribe(audioData: Float32Array, sampleRate: number = 16000): Promise<AsrResult> {
    if (!this.whisper) {
      throw new Error('Whisper not initialized');
    }

    const startTime = performance.now();
    
    try {
      logger.debug(`Transcribing audio: ${audioData.length} samples at ${sampleRate}Hz`);
      
      // Validate audio data
      if (audioData.length === 0) {
        throw new Error('Empty audio data');
      }
      
      // Check for minimum audio length (e.g., 0.1 seconds)
      const minSamples = sampleRate * 0.1;
      if (audioData.length < minSamples) {
        logger.warn('Audio too short for reliable transcription');
      }
      
      // Calculate audio level to detect silence
      const audioLevel = this.calculateAudioLevel(audioData);
      if (audioLevel < 0.001) {
        logger.debug('Audio appears to be mostly silence');
        return {
          text: '',
          confidence: 0.0,
          language: this.config.language || 'en',
          duration: performance.now() - startTime,
          timestamp: Date.now()
        };
      }
      
      // Perform transcription
      const result = await this.whisper.transcribe(audioData, {
        language: this.config.language,
        temperature: this.config.temperature,
        initialPrompt: this.config.initialPrompt,
        sampleRate
      });
      
      const duration = performance.now() - startTime;
      
      logger.debug(`Transcription completed in ${duration.toFixed(1)}ms: "${result.text}"`);
      
      return {
        text: result.text.trim(),
        confidence: result.confidence || 0.8,
        language: result.language || this.config.language || 'en',
        duration,
        timestamp: Date.now()
      };
      
    } catch (error) {
      logger.error('Transcription failed:', error);
      throw error;
    }
  }

  private calculateAudioLevel(audioData: Float32Array): number {
    let sum = 0;
    for (let i = 0; i < audioData.length; i++) {
      sum += Math.abs(audioData[i]);
    }
    return sum / audioData.length;
  }

  // Mock transcribe for development/testing
  private async mockTranscribe(audioData: Float32Array, options: any): Promise<any> {
    // Simulate processing time
    await new Promise(resolve => setTimeout(resolve, 100 + Math.random() * 400));
    
    const audioLevel = this.calculateAudioLevel(audioData);
    
    if (audioLevel < 0.001) {
      return { text: '', confidence: 0.0, language: 'en' };
    }
    
    // Mock responses based on audio characteristics
    const responses = [
      'Hello JARVIS',
      'What time is it',
      'Turn on the lights',
      'Play some music',
      'What\'s the weather like',
      'Set a timer for 5 minutes',
      'How are you doing',
      'Thank you'
    ];
    
    const randomResponse = responses[Math.floor(Math.random() * responses.length)];
    
    return {
      text: randomResponse,
      confidence: 0.8 + Math.random() * 0.2,
      language: 'en'
    };
  }

  // Convert audio format if needed
  convertToFloat32(audioData: Int16Array): Float32Array {
    const float32Data = new Float32Array(audioData.length);
    for (let i = 0; i < audioData.length; i++) {
      float32Data[i] = audioData[i] / 32768.0; // Convert from int16 to float32
    }
    return float32Data;
  }

  // Preprocess audio (e.g., normalize, filter)
  preprocessAudio(audioData: Float32Array): Float32Array {
    // Apply basic normalization
    const maxValue = Math.max(...audioData.map(Math.abs));
    if (maxValue > 0) {
      const scaleFactor = 0.95 / maxValue;
      return audioData.map(sample => sample * scaleFactor);
    }
    return audioData;
  }

  cleanup(): void {
    if (this.whisper) {
      this.whisper = null;
      logger.info('Whisper ASR cleaned up');
    }
  }

  // Get supported languages
  static getSupportedLanguages(): string[] {
    return [
      'en', 'es', 'fr', 'de', 'it', 'pt', 'ru', 'ja', 'ko', 'zh',
      'ar', 'hi', 'tr', 'pl', 'nl', 'sv', 'da', 'no', 'fi'
    ];
  }

  // Get model size recommendations
  static getModelRecommendations(): Record<string, string> {
    return {
      'tiny': 'Fastest, least accurate (~40MB)',
      'base': 'Good balance of speed and accuracy (~150MB)',
      'small': 'Better accuracy, slower (~500MB)',
      'medium': 'High accuracy, much slower (~1.5GB)',
      'large': 'Best accuracy, very slow (~3GB)'
    };
  }
}
