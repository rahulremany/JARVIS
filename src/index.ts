#!/usr/bin/env node

import { LocalLlamaEngine } from './engines/local/LocalLlamaEngine.js';
import { VllmEngine } from './engines/heavy/VllmEngine.js';
import { SessionManager } from './session/SessionManager.js';
import { EngineSelector } from './router/EngineSelector.js';
import { DeviceActions } from './tools/DeviceActions.js';
import { loadPolicy } from './policy/loadPolicy.js';
import { loadEnv } from './utils/env.js';
import { logger } from './utils/logging.js';
import { validateModels } from './engines/local/modelMap.js';
import { ConversationHandler } from './conversation/ConversationHandler.js';
import fastify from 'fastify';

class JarvisApp {
  private localEngine!: LocalLlamaEngine;
  private vllmEngine: VllmEngine | null = null;
  private sessionManager!: SessionManager;
  private engineSelector!: EngineSelector;
  private deviceActions!: DeviceActions;
  private server!: ReturnType<typeof fastify>;
  private conversationHandler!: ConversationHandler;

  async initialize(): Promise<void> {
    console.log('\n🤖 JARVIS - Personal AI Assistant');
    console.log('=================================\n');

    // Load environment and policy
    const env = loadEnv();
    logger.setLevel(env.LOG_LEVEL);
    
    if (env.MODE === 'prod') {
      logger.setSampleRate(0.05); // 1/20 sampling in production
    }

    const policy = loadPolicy();

    // Validate models exist
    validateModels();

    // Initialize engines
    logger.info('🔥 Initializing LocalLlamaEngine...');
    this.localEngine = new LocalLlamaEngine();

    // Initialize vLLM engine if configured
    if (policy.endpoints.vllm_base_url) {
      logger.info('⚡ Initializing VllmEngine...');
      this.vllmEngine = new VllmEngine(policy.endpoints.vllm_base_url);
      await this.vllmEngine.healthCheck();
    } else {
      logger.info('⚡ vLLM not configured - heavy tier disabled');
    }

    // Initialize other components
    this.sessionManager = new SessionManager();
    this.engineSelector = new EngineSelector(this.localEngine, this.vllmEngine, policy);
    this.deviceActions = new DeviceActions();

    // Run smoke test
    await this.localEngine.smokeTest();

    // Initialize web server
    await this.initializeServer(env.PORT);

    this.conversationHandler = new ConversationHandler({
        enableTTS: true
    });

    logger.info('✅ JARVIS initialization complete');
  }

  private async initializeServer(port: number): Promise<void> {
    this.server = fastify({ logger: false });

    // Health endpoints
    this.server.get('/health/local', async () => {
      return this.localEngine.getHealth();
    });

    this.server.get('/health/heavy', async () => {
      return this.vllmEngine?.getHealth() || { ok: false, reason: 'not_configured' };
    });

    this.server.get('/health/summary', async () => {
      const stats = logger.getLatencyStats();
      return {
        local: this.localEngine.getHealth(),
        heavy: this.vllmEngine?.getHealth() || { ok: false, reason: 'not_configured' },
        sessions: this.sessionManager.getSessionCount(),
        latency_stats: stats,
        recent_logs: logger.getLatencyLogs().slice(-10)
      };
    });

    // Chat endpoint
    this.server.post('/chat', async (request: any, reply: any) => {
      const { prompt, session_id = 'default' } = request.body;
      
      if (!prompt?.trim()) {
        reply.code(400);
        return { error: 'Prompt is required' };
      }

      try {
        // Update session with user message
        this.sessionManager.appendUser(session_id, prompt);
        
        // Get engine selection and generate response
        const result = await this.engineSelector.generateWithFallback(prompt, session_id);
        
        if (result.type === 'direct_command') {
          // Handle direct device commands
          const deviceResult = await this.deviceActions.executeDirectCommand(prompt);
          
          // Update session with assistant response
          this.sessionManager.appendAssistant(session_id, deviceResult.message);
          
          return {
            type: 'direct_command',
            response: deviceResult.message,
            action: deviceResult.action,
            device: deviceResult.device,
            success: deviceResult.success
          };
        } else {
          // Handle LLM responses
          reply.type('text/plain');
          
          let fullResponse = '';
          for await (const event of result.stream!) {
            if (event.type === 'token') {
              reply.raw.write(event.token);
              fullResponse += event.token;
            } else if (event.type === 'done') {
              reply.raw.end();
              
              // Update session with assistant response
              this.sessionManager.appendAssistant(session_id, fullResponse);
              break;
            }
          }
        }
      } catch (error) {
        logger.error('Chat endpoint error:', error);
        reply.code(500);
        return { error: 'Internal server error' };
      }
    });

    this.server.post('/chat/test', async (request: any, reply: any) => {
        const { text, session_id = 'default' } = request.body;
        
        if (!text?.trim()) {
          reply.code(400);
          return { error: 'Text is required' };
        }
  
        try {
          // Update session
          this.sessionManager.appendUser(session_id, text);
          
          // Process and speak response
          const response = await this.conversationHandler.handleTextInput(
            text,
            this.localEngine,
            session_id
          );
          
          // Update session
          this.sessionManager.appendAssistant(session_id, response);
          
          return {
            user: text,
            jarvis: response,
            session_id,
            timestamp: Date.now()
          };
        } catch (error) {
          logger.error('Chat test error:', error);
          reply.code(500);
          return { error: 'Internal server error' };
        }
      });

      // Direct TTS endpoint (no LLM processing)
      this.server.post('/chat/speak', async (request: any, reply: any) => {
        const { text } = request.body;
        
        if (!text?.trim()) {
          reply.code(400);
          return { error: 'Text is required' };
        }

        try {
          await this.conversationHandler.processAndSpeak(text, 'system');
          return { success: true, spoken: text };
        } catch (error) {
          logger.error('Speak error:', error);
          reply.code(500);
          return { error: 'Failed to speak' };
        }
      });

      this.server.post('/chat/clear', async (request: any, reply: any) => {
        const { session_id = 'default' } = request.body;
        this.sessionManager.reset(session_id);
        return { message: 'Session cleared', session_id };
      });

    // Start server
    try {
      await this.server.listen({ port, host: '127.0.0.1' });
      logger.info(`🌐 Server listening on http://127.0.0.1:${port}`);
      logger.info(`🔍 Health check: http://127.0.0.1:${port}/health/summary`);
    } catch (error) {
      logger.error('Failed to start server:', error);
      process.exit(1);
    }
  }

  async shutdown(): Promise<void> {
    logger.info('🛑 Shutting down JARVIS...');
    
    if (this.server) {
      await this.server.close();
    }
    
    logger.info('👋 JARVIS shutdown complete');
  }
}

// Main execution
async function main() {
  // Ensure this is the only entry point
  const currentFile = new URL(import.meta.url).pathname;
  if (process.argv[1] !== currentFile && !process.argv[1].endsWith('src/index.ts')) {
    console.error('❌ Error: This script must be run as the main entry point');
    console.error('Use: npm run dev or tsx src/index.ts');
    process.exit(1);
  }

  const app = new JarvisApp();
  
  // Handle graceful shutdown
  process.on('SIGINT', async () => {
    await app.shutdown();
    process.exit(0);
  });

  process.on('SIGTERM', async () => {
    await app.shutdown();
    process.exit(0);
  });

  try {
    await app.initialize();
  } catch (error) {
    console.error('❌ Failed to initialize JARVIS:', error);
    process.exit(1);
  }
}

// Run if this is the main module
if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch(console.error);
}

export { JarvisApp };
