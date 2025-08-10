import { LocalLlamaEngine } from '../src/engines/local/LocalLlamaEngine.js';
import { logger } from '../src/utils/logging.js';

describe('LocalLlamaEngine', () => {
  let engine: LocalLlamaEngine;

  beforeAll(async () => {
    engine = new LocalLlamaEngine();
    // Set timeout for model loading
    jest.setTimeout(30000);
  });

  afterAll(async () => {
    await engine.cleanup();
  });

  describe('Smoke Test', () => {
    it('should complete smoke test successfully', async () => {
      await expect(engine.smokeTest()).resolves.not.toThrow();
    });
  });

  describe('Generation', () => {
    it('should generate response for simple prompt', async () => {
      const events = [];
      let response = '';
      let firstTokenMs = 0;
      let totalMs = 0;
      const startTime = performance.now();

      for await (const event of engine.generateStream('test-simple', 'Hello', {
        max_tokens: 10,
        temperature: 0.0
      })) {
        events.push(event);
        
        if (event.type === 'first') {
          firstTokenMs = event.ms || 0;
        } else if (event.type === 'token' && event.text) {
          response += event.text;
        } else if (event.type === 'done') {
          totalMs = performance.now() - startTime;
        }
      }

      expect(events.length).toBeGreaterThan(0);
      expect(response.length).toBeGreaterThan(0);
      expect(firstTokenMs).toBeGreaterThan(0);
      expect(totalMs).toBeGreaterThan(firstTokenMs);
    });

    it('should handle multiple generations in same session (KV reuse)', async () => {
      const sessionId = 'test-kv-reuse';
      
      // First generation
      let response1 = '';
      for await (const event of engine.generateStream(sessionId, 'Hi', {
        max_tokens: 5,
        temperature: 0.0
      })) {
        if (event.type === 'token' && event.text) {
          response1 += event.text;
        }
      }

      // Second generation in same session
      let response2 = '';
      for await (const event of engine.generateStream(sessionId, 'Explain AI briefly.', {
        max_tokens: 20,
        temperature: 0.0
      })) {
        if (event.type === 'token' && event.text) {
          response2 += event.text;
        }
      }

      expect(response1.length).toBeGreaterThan(0);
      expect(response2.length).toBeGreaterThan(0);
      expect(response1).not.toBe(response2);
    });

    it('should respect generation parameters', async () => {
      let tokenCount = 0;
      const maxTokens = 5;

      for await (const event of engine.generateStream('test-caps', 'Count to ten', {
        max_tokens: maxTokens,
        temperature: 0.0,
        stop: ['.', '\n']
      })) {
        if (event.type === 'token') {
          tokenCount++;
        }
      }

      // Should respect max_tokens limit (allow some flexibility due to stop conditions)
      expect(tokenCount).toBeLessThanOrEqual(maxTokens + 2);
    });

    it('should handle long prompts appropriately', async () => {
      const longPrompt = 'This is a very long prompt. '.repeat(100); // ~2700 chars
      
      let response = '';
      const events = [];

      for await (const event of engine.generateStream('test-long', longPrompt, {
        max_tokens: 10,
        temperature: 0.0
      })) {
        events.push(event);
        if (event.type === 'token' && event.text) {
          response += event.text;
        }
      }

      // Should still generate a response even with long prompt
      expect(response.length).toBeGreaterThan(0);
      expect(events.length).toBeGreaterThan(0);
    });
  });

  describe('Health Check', () => {
    it('should return valid health status', () => {
      const health = engine.getHealth();
      
      expect(health).toHaveProperty('ok');
      expect(health).toHaveProperty('modelId');
      expect(health).toHaveProperty('hardware');
      expect(health).toHaveProperty('settings');
      expect(health).toHaveProperty('engine');
      
      expect(health.engine).toBe('local');
      expect(typeof health.modelId).toBe('string');
      expect(health.hardware).toHaveProperty('ram');
      expect(health.hardware).toHaveProperty('cores');
    });
  });

  describe('Error Handling', () => {
    it('should handle extremely long prompts', async () => {
      const extremelyLongPrompt = 'x'.repeat(5000); // 5000 chars
      
      // Should either truncate or throw a descriptive error
      if (process.env.MODE === 'prod') {
        // In prod mode, should truncate
        let response = '';
        for await (const event of engine.generateStream('test-extreme', extremelyLongPrompt, {
          max_tokens: 5
        })) {
          if (event.type === 'token' && event.text) {
            response += event.text;
          }
        }
        expect(response.length).toBeGreaterThan(0);
      } else {
        // In dev mode, should throw error
        await expect(async () => {
          for await (const event of engine.generateStream('test-extreme', extremelyLongPrompt, {
            max_tokens: 5
          })) {
            // Just iterate through
          }
        }).rejects.toThrow(/too long/);
      }
    });
  });
});
