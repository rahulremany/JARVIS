import { readFileSync } from 'fs';
import { parse } from 'yaml';
import { Policy, type PolicyConfig } from './schema.js';
import { logger } from '../utils/logging.js';

export function loadPolicy(path: string = 'config/model-policy.yaml'): PolicyConfig {
  try {
    const fileContent = readFileSync(path, 'utf8');
    const parsed = parse(fileContent);
    const validated = Policy.parse(parsed);
    
    logger.info('✅ Policy loaded from', path);
    return validated;
  } catch (error) {
    logger.error('Failed to load policy:', error);
    throw new Error(`Failed to load policy from ${path}: ${error}`);
  }
}
