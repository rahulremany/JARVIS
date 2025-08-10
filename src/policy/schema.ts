import { z } from 'zod';

export const GenParams = z.object({
  max_tokens: z.number().optional(),
  ctx: z.number().optional(),
  temperature: z.number().optional(),
  timeout_ms: z.number().optional()
});

export const ModelDef = z.object({
  candidates: z.array(z.string()).optional(),
  candidates_cpu: z.array(z.string()).optional()
}).merge(GenParams);

export const Policy = z.object({
  routing: z.object({
    escalate_tags: z.array(z.string()),
    hard_keywords: z.array(z.string()),
    default_class: z.enum(['trivial', 'normal', 'hard'])
  }),
  models: z.object({
    router: ModelDef,
    primary: ModelDef,
    heavy: ModelDef
  }),
  autotune: z.object({
    first_token_threshold_ms: z.number(),
    total_threshold_ms: z.number(),
    success_rate_threshold: z.number()
  }),
  policy: z.object({
    mode: z.enum(['dev', 'prod']),
    fallback_enabled: z.boolean(),
    log_routing_decisions: z.boolean()
  }),
  endpoints: z.object({
    vllm_base_url: z.string()
  })
});

export type PolicyConfig = z.infer<typeof Policy>;
