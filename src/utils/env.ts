import { logger } from './logging.js';

export interface EnvConfig {
  MODE: string;
  USE_OLLAMA: boolean;
  VLLM_BASE_URL: string;
  LOG_LEVEL: string;
  OLLAMA_KEEP_ALIVE: string;
  PORT: number;
  ELEVEN_API_KEY: string;
  PORCUPINE_ACCESS_KEY: string;
  JARVIS_VOICE_ID: string;
  OPENAI_API_KEY: string;
}

export function loadEnv(): EnvConfig {
  const config: EnvConfig = {
    MODE: process.env.MODE || 'dev',
    USE_OLLAMA: process.env.USE_OLLAMA === 'true',
    VLLM_BASE_URL: process.env.VLLM_BASE_URL || '',
    LOG_LEVEL: process.env.LOG_LEVEL || 'info',
    OLLAMA_KEEP_ALIVE: process.env.OLLAMA_KEEP_ALIVE || '5m',
    PORT: parseInt(process.env.PORT || '3000', 10),
    ELEVEN_API_KEY: process.env.ELEVEN_API_KEY || '',
    PORCUPINE_ACCESS_KEY: process.env.PORCUPINE_ACCESS_KEY || '',
    JARVIS_VOICE_ID: process.env.JARVIS_VOICE_ID || 'LE42bqYwZicKpZRastCO',
    OPENAI_API_KEY: process.env.OPENAI_API_KEY || ''
  };

  // Validate port
  if (isNaN(config.PORT) || config.PORT < 1 || config.PORT > 65535) {
    logger.warn(`Invalid PORT value: ${process.env.PORT}, using default 3000`);
    config.PORT = 3000;
  }

  // Log API key status (without exposing keys)
  if (config.ELEVEN_API_KEY) {
    logger.info(`✅ ELEVEN_API_KEY loaded: ${config.ELEVEN_API_KEY.substring(0, 10)}...`);
  } else {
    logger.warn('❌ ELEVEN_API_KEY not found in environment');
  }

  if (config.PORCUPINE_ACCESS_KEY) {
    logger.info(`✅ PORCUPINE_ACCESS_KEY loaded: ${config.PORCUPINE_ACCESS_KEY.substring(0, 10)}...`);
  } else {
    logger.warn('❌ PORCUPINE_ACCESS_KEY not found in environment');
  }

  if (config.OPENAI_API_KEY) {
    logger.info(`✅ OPENAI_API_KEY loaded: ${config.OPENAI_API_KEY.substring(0, 10)}...`);
  } else {
    logger.warn('❌ OPENAI_API_KEY not found in environment');
  }

  return config;
}
