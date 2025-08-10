import { logger } from './logging.js';

export interface EnvConfig {
  MODE: string;
  USE_OLLAMA: boolean;
  VLLM_BASE_URL: string;
  LOG_LEVEL: string;
  OLLAMA_KEEP_ALIVE: string;
  PORT: number;
}

export function loadEnv(): EnvConfig {
  const config: EnvConfig = {
    MODE: process.env.MODE || 'dev',
    USE_OLLAMA: process.env.USE_OLLAMA === 'true',
    VLLM_BASE_URL: process.env.VLLM_BASE_URL || '',
    LOG_LEVEL: process.env.LOG_LEVEL || 'info',
    OLLAMA_KEEP_ALIVE: process.env.OLLAMA_KEEP_ALIVE || '5m',
    PORT: parseInt(process.env.PORT || '3000', 10)
  };

  // Validate port
  if (isNaN(config.PORT) || config.PORT < 1 || config.PORT > 65535) {
    logger.warn(`Invalid PORT value: ${process.env.PORT}, using default 3000`);
    config.PORT = 3000;
  }

  return config;
}
