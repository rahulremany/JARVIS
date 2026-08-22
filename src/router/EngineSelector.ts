import { logger } from '../utils/logging.js';
import { Router, type RouteClass, type Facet } from './Router.js';
import { LocalLlamaEngine } from '../engines/local/LocalLlamaEngine.js';
import { VllmEngine } from '../engines/heavy/VllmEngine.js';
import { OllamaEngine } from '../engines/mesh/OllamaEngine.js';
import { DeviceActions } from '../tools/DeviceActions.js';
import { loadPolicy } from '../policy/loadPolicy.js';
import type { PolicyConfig } from '../policy/schema.js';

export interface GenerationParams {
  max_tokens?: number;
  ctx?: number;
  temperature?: number;
  stop?: string[];
}

export interface GenerationEvent {
  type: 'first' | 'token' | 'done';
  text?: string;
  timestamp: number;
  ms?: number;
}

export class EngineSelector {
  private localEngine: LocalLlamaEngine;
  private heavyEngine: VllmEngine | null = null;
  private meshEngine: OllamaEngine | null = null;
  private router = new Router();
  private deviceActions = new DeviceActions();
  private policy: PolicyConfig;

  constructor(localEngine?: LocalLlamaEngine, heavyEngine?: VllmEngine | null, policy?: PolicyConfig) {
    this.policy = policy || loadPolicy();
    this.localEngine = localEngine || new LocalLlamaEngine();
    this.heavyEngine = heavyEngine || null;

    if (!this.heavyEngine && this.policy.endpoints.vllm_base_url) {
      this.heavyEngine = new VllmEngine(this.policy.endpoints.vllm_base_url);
    }

    // Mesh engine only comes up if the policy actually declares facets --
    // keeps this a no-op for anyone still running the plain trivial/normal/hard
    // policy shape.
    if (this.policy.facets) {
      this.meshEngine = new OllamaEngine(undefined, {
        planner: this.policy.facets.planner.model,
        coder: this.policy.facets.coder.model,
        fast: this.policy.facets.fast.model
      });
    }
  }

  // Task-routed mesh entry point: classify by facet (what kind of work this
  // is), not by difficulty, and dispatch straight to the specialist model.
  async *generateFacetStream(
    prompt: string,
    params: GenerationParams = {}
  ): AsyncGenerator<GenerationEvent & { facet?: Facet }> {
    if (!this.meshEngine || !this.policy.facets) {
      throw new Error('Model mesh not configured -- add a `facets` block to model-policy.yaml');
    }

    const facet = this.router.classifyFacet(prompt);
    const facetConfig = this.policy.facets[facet];

    if (this.policy.policy.log_routing_decisions) {
      logger.info('Facet route decision:', { input: prompt.substring(0, 100), facet, model: facetConfig.model });
    }

    const finalParams: GenerationParams = {
      max_tokens: params.max_tokens ?? facetConfig.max_tokens,
      ctx: params.ctx ?? facetConfig.ctx,
      temperature: params.temperature ?? facetConfig.temperature,
      stop: params.stop
    };

    for await (const event of this.meshEngine.generateStream(facet, prompt, finalParams)) {
      yield { ...event, facet };
    }
  }

  async *generateStream(
    sessionId: string,
    prompt: string,
    params: GenerationParams = {}
  ): AsyncGenerator<GenerationEvent> {
    const routeResult = this.router.classify(prompt);

    if (this.policy.policy.log_routing_decisions) {
      logger.info('Route decision:', {
        input: prompt.substring(0, 100),
        route: routeResult,
        tier: this.router.getEngineTier(routeResult.class)
      });
    }

    // Handle direct device commands
    if (routeResult.class === 'direct_command' && routeResult.deviceCommand) {
      try {
        const result = await this.deviceActions.executeCommand(routeResult.deviceCommand);
        yield { type: 'first', timestamp: Date.now(), ms: 50 };
        yield { type: 'token', text: result, timestamp: Date.now() };
        yield { type: 'done', timestamp: Date.now() };
        return;
      } catch (error) {
        logger.error('Device command failed:', error);
        // Fall through to LLM generation
      }
    }

    const tier = this.router.getEngineTier(routeResult.class);
    const modelConfig = this.policy.models[tier];
    
    // Merge params with policy defaults
    const finalParams: GenerationParams = {
      max_tokens: params.max_tokens ?? modelConfig.max_tokens,
      ctx: params.ctx ?? modelConfig.ctx,
      temperature: params.temperature ?? modelConfig.temperature,
      stop: params.stop
    };

    try {
      if (tier === 'heavy' && this.heavyEngine) {
        logger.debug('Using heavy engine (vLLM)');
        const modelId = modelConfig.candidates_cpu?.[0] || 'mixtral:8x7b-instruct-q4_K_M';
        
        yield* this.heavyEngine.generateStream(prompt, finalParams, modelId);
      } else {
        logger.debug(`Using local engine (tier: ${tier})`);
        yield* this.localEngine.generateStream(sessionId, prompt, finalParams);
      }
    } catch (error) {
      logger.error(`Generation failed on ${tier} tier:`, error);
      
      // Fallback to local engine if enabled
      if (this.policy.policy.fallback_enabled && tier !== 'primary') {
        logger.warn('Falling back to local engine');
        try {
          yield* this.localEngine.generateStream(sessionId, prompt, finalParams);
        } catch (fallbackError) {
          logger.error('Fallback also failed:', fallbackError);
          throw fallbackError;
        }
      } else {
        throw error;
      }
    }
  }

  async getHealth() {
    const localHealth = this.localEngine.getHealth();
    const heavyHealth = this.heavyEngine ? this.heavyEngine.getHealth() : null;
    
    return {
      local: localHealth,
      heavy: heavyHealth,
      routing: {
        policy_mode: this.policy.policy.mode,
        fallback_enabled: this.policy.policy.fallback_enabled
      }
    };
  }

  async cleanup() {
    await this.localEngine.cleanup();
  }

  // Additional methods needed by index.ts
  async generateWithFallback(prompt: string, sessionId: string) {
    const routeResult = this.router.classify(prompt);
    
    if (routeResult.class === 'direct_command') {
      return {
        type: 'direct_command',
        deviceCommand: routeResult.deviceCommand
      };
    }
    
    return {
      type: 'llm',
      stream: this.generateStream(sessionId, prompt)
    };
  }
}