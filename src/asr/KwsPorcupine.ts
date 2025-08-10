import { logger } from '../utils/logging.js';

export interface KwsConfig {
  accessKey: string;
  keywords: string[];
  sensitivities: number[];
  sampleRate: number;
}

export interface KwsResult {
  detected: boolean;
  keyword: string;
  index: number;
  timestamp: number;
}

export class KwsPorcupine {
  private config: KwsConfig;
  private porcupine: any = null; // Will be loaded dynamically

  constructor(config: KwsConfig) {
    this.config = config;
  }

  async initialize(): Promise<void> {
    try {
      // Dynamic import of pvporcupine (Node.js binding)
      const pvporcupine = await import('pvporcupine');
      
      this.porcupine = pvporcupine.create({
        accessKey: this.config.accessKey,
        keywords: this.config.keywords,
        sensitivities: this.config.sensitivities
      });
      
      logger.info('Porcupine wake word detection initialized', {
        keywords: this.config.keywords,
        sensitivities: this.config.sensitivities,
        frameLength: this.porcupine.frameLength,
        sampleRate: this.porcupine.sampleRate
      });
      
    } catch (error) {
      logger.error('Failed to initialize Porcupine:', error);
      throw new Error(`Porcupine initialization failed: ${error}`);
    }
  }

  processFrame(audioFrame: Int16Array): KwsResult {
    if (!this.porcupine) {
      throw new Error('Porcupine not initialized');
    }

    try {
      const keywordIndex = this.porcupine.process(audioFrame);
      
      if (keywordIndex >= 0) {
        const keyword = this.config.keywords[keywordIndex];
        logger.debug(`Wake word detected: ${keyword} (index: ${keywordIndex})`);
        
        return {
          detected: true,
          keyword,
          index: keywordIndex,
          timestamp: Date.now()
        };
      }
      
      return {
        detected: false,
        keyword: '',
        index: -1,
        timestamp: Date.now()
      };
      
    } catch (error) {
      logger.error('Porcupine processing error:', error);
      throw error;
    }
  }

  getFrameLength(): number {
    return this.porcupine?.frameLength || 512;
  }

  getSampleRate(): number {
    return this.porcupine?.sampleRate || 16000;
  }

  cleanup(): void {
    if (this.porcupine) {
      try {
        this.porcupine.delete();
        this.porcupine = null;
        logger.info('Porcupine cleaned up');
      } catch (error) {
        logger.error('Error cleaning up Porcupine:', error);
      }
    }
  }

  // Static method to validate access key format
  static validateAccessKey(accessKey: string): boolean {
    // Porcupine access keys are base64-encoded and typically quite long
    return accessKey.length > 20 && /^[A-Za-z0-9+/=]+$/.test(accessKey);
  }

  // Static method to get default keywords
  static getBuiltinKeywords(): string[] {
    return [
      'jarvis', 'hey jarvis', 'computer', 'alexa', 'hey siri',
      'ok google', 'bumblebee', 'grasshopper', 'hey barista'
    ];
  }
}
