import { fetch } from 'undici';
import { logger } from '../../utils/logging.js';

export interface GenerationEvent {
  type: 'first' | 'token' | 'done';
  token?: string;
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

export class VllmEngine {
  constructor(private baseUrl: string) {
    if (!baseUrl) {
      throw new Error('vLLM base URL is required');
    }
  }

  async *generateStream(
    prompt: string,
    params: GenerationParams,
    modelId: string
  ): AsyncGenerator<GenerationEvent> {
    const t0 = performance.now();
    
    const requestBody = {
      model: modelId,
      prompt,
      max_tokens: params.max_tokens ?? 512,
      temperature: params.temperature ?? 0.3,
      stop: params.stop ?? [],
      stream: true
    };

    let firstMs: number | null = null;
    let tokensOut = 0;

    try {
      const response = await fetch(`${this.baseUrl}/v1/completions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody),
      });

      if (!response.ok) {
        throw new Error(`vLLM API error: ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('No response body');
      }

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6).trim();
            if (data === '[DONE]') {
              break;
            }

            try {
              const parsed = JSON.parse(data);
              const choice = parsed.choices?.[0];
              if (choice?.text) {
                if (firstMs === null) {
                  firstMs = performance.now() - t0;
                  yield { type: 'first', ms: firstMs, timestamp: Date.now() };
                }

                tokensOut++;
                yield { 
                  type: 'token', 
                  text: choice.text, 
                  timestamp: Date.now() 
                };
              }
            } catch (parseError) {
              logger.warn('Failed to parse SSE data:', parseError);
            }
          }
        }
      }
    } catch (error) {
      logger.error('vLLM generation error:', error);
      throw error;
    } finally {
      const totalMs = performance.now() - t0;
      
      logger.logLatency({
        engine: 'vllm',
        model_id: modelId,
        params: {
          ctx: params.ctx ?? 4096,
          max_tokens: params.max_tokens ?? 512,
          temperature: params.temperature ?? 0.3,
          stop: params.stop ?? []
        },
        prompt_chars: prompt.length,
        session_id: 'vllm-session',
        first_token_ms: firstMs ?? totalMs,
        total_ms: totalMs,
        tokens_out: tokensOut,
        route: 'heavy',
      });

      yield { type: 'done', timestamp: Date.now() };
    }
  }

  async healthCheck(): Promise<boolean> {
    try {
      const response = await fetch(`${this.baseUrl}/health`, {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' }
      });
      return response.ok;
    } catch {
      return false;
    }
  }

  getHealth() {
    return {
      ok: true,
      baseUrl: this.baseUrl,
      engine: 'vllm'
    };
  }
}
