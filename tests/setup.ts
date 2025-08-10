// Jest setup file for JARVIS tests

import { logger } from '../src/utils/logging.js';

// Set log level to error to reduce noise during tests
logger.setLevel('error');

// Global test timeout
jest.setTimeout(30000);

// Mock environment variables for tests
process.env.MODE = 'dev';
process.env.LOG_LEVEL = 'error';
process.env.USE_OLLAMA = 'false';

// Global test setup
beforeAll(() => {
  console.log('🧪 Starting JARVIS test suite...');
});

afterAll(() => {
  console.log('✅ JARVIS test suite completed');
});
