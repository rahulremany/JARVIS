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

export const FacetDef = z.object({
  model: z.string(),
  engine: z.enum(['ollama', 'llama_cpp', 'vllm']),
  always_loaded: z.boolean().default(false),
  max_tokens: z.number(),
  ctx: z.number(),
  temperature: z.number()
});

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
  // Task-routed mesh: which specialist model handles which kind of work,
  // independent of the trivial/normal/hard difficulty axis above.
  facets: z.object({
    planner: FacetDef,
    coder: FacetDef,
    fast: FacetDef
  }).optional(),
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
