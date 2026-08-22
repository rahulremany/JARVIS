// src/engines/mesh/OllamaEngine.ts
//
// Serving layer for the task-routed local model mesh. Ollama hosts all three
// facet models (planner / coder / fast) behind one local HTTP API and handles
// load-on-first-request + idle eviction itself -- this is what lets a 16GB
// machine run three different specialist models without a custom
// load/unload scheduler. The router picks *which* model to call; Ollama
// decides whether it needs to be paged in.
import { fetch } from 'undici';
import { logger } from '../../utils/logging.js';
import type { Facet } from '../../router/Router.js';

export interface GenerationEvent {
  type: 'first' | 'token' | 'done';
  text?: string;
  timestamp: number;
  ms?: number;
}

export interface GenerationParams {
  max_tokens?: number;
  ctx?: number;
  temperature?: number;
  stop?: string[];
}

export interface FacetModelMap {
  planner: string;
  coder: string;
  fast: string;
}

export class OllamaEngine {
  constructor(
    private baseUrl: string = process.env.OLLAMA_BASE_URL || 'http://127.0.0.1:11434',
    private facetModels: FacetModelMap = {
      planner: 'qwen3.5:9b-instruct-q4_K_M',
      coder: 'qwen2.5-coder:7b-instruct-q4_K_M',
      fast: 'llama3.2:3b-instruct-q4_K_M'
    }
  ) {}

  modelFor(facet: Facet): string {
    return this.facetModels[facet];
  }

  async *generateStream(
    facet: Facet,
    prompt: string,
    params: GenerationParams = {}
  ): AsyncGenerator<GenerationEvent> {
    const model = this.modelFor(facet);
    const t0 = performance.now();
    let firstMs: number | null = null;
    let tokensOut = 0;

    const body = {
      model,
      prompt,
      stream: true,
      options: {
        num_ctx: params.ctx ?? 2048,
        num_predict: params.max_tokens ?? 256,
        temperature: params.temperature ?? 0.2,
        stop: params.stop ?? []
      }
    };

    try {
      const response = await fetch(`${this.baseUrl}/api/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });

      if (!response.ok || !response.body) {
        throw new Error(`Ollama API error: ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.trim()) continue;
          const parsed = JSON.parse(line);

          if (parsed.response) {
            if (firstMs === null) {
              firstMs = performance.now() - t0;
              yield { type: 'first', ms: firstMs, timestamp: Date.now() };
            }
            tokensOut++;
            yield { type: 'token', text: parsed.response, timestamp: Date.now() };
          }

          if (parsed.done) {
            break;
          }
        }
      }
    } catch (error) {
      logger.error(`Ollama mesh generation failed (facet=${facet}, model=${model}):`, error);
      throw error;
    } finally {
      const totalMs = performance.now() - t0;
      logger.logLatency({
        engine: 'ollama_mesh',
        model_id: model,
        params: {
          ctx: params.ctx ?? 2048,
          max_tokens: params.max_tokens ?? 256,
          temperature: params.temperature ?? 0.2,
          stop: params.stop ?? []
        },
        prompt_chars: prompt.length,
        session_id: 'mesh',
        first_token_ms: firstMs ?? totalMs,
        total_ms: totalMs,
        tokens_out: tokensOut,
        route: facet
      });
      yield { type: 'done', timestamp: Date.now() };
    }
  }

  // Ollama's own idle-eviction handles memory pressure; this just reports
  // which facet models are currently resident, for the health endpoint.
  async listLoaded(): Promise<string[]> {
    try {
      const response = await fetch(`${this.baseUrl}/api/ps`);
      if (!response.ok) return [];
      const data = (await response.json()) as { models?: { name: string }[] };
      return (data.models ?? []).map(m => m.name);
    } catch {
      return [];
    }
  }

  async healthCheck(): Promise<boolean> {
    try {
      const response = await fetch(`${this.baseUrl}/api/tags`);
      return response.ok;
    } catch {
      return false;
    }
  }
}
