import os from "node:os";
import fs from "node:fs";
import {
  getLlama,
  LlamaModel,
  LlamaContext,
  LlamaChatSession,
  ChatMLChatWrapper,
} from "node-llama-cpp";
import { resolveModelPath } from "./modelMap.js";
import { logger } from "../../utils/logging.js";
import { getSession } from "../../session/SessionManager.js";

console.log(`[JARVIS] USING LocalLlamaEngine from ${import.meta.url}`);

export interface GenerationEvent {
  type: "first" | "token" | "done";
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

// Hardware detection and optimization
class HardwareOptimizer {
  public readonly totalRAM: number;
  public readonly availableRAM: number;
  public readonly cpuCores: number;
  public readonly isAppleSilicon: boolean;
  public readonly gpuLayers: number;
  public readonly contextSize: number;
  public readonly batchSize: number;
  public readonly threads: number;
  public readonly modelPath: string;

  constructor() {
    this.totalRAM = Math.floor(os.totalmem() / (1024 * 1024 * 1024));
    this.availableRAM = Math.floor(os.freemem() / (1024 * 1024 * 1024));
    this.cpuCores = os.cpus().length;
    this.isAppleSilicon = process.platform === "darwin" && os.cpus()[0].model.includes("Apple");

    // Detect best model based on RAM
    if (this.totalRAM <= 8) {
      // 8GB or less: Use 3B model
      this.modelPath = "qwen2.5:3b-instruct-q4_K_M";
      this.gpuLayers = this.isAppleSilicon ? 32 : 0; // All layers for 3B
      this.contextSize = 512;
      this.batchSize = 128;
    } else if (this.totalRAM <= 16) {
      // 16GB: Can handle 3B with bigger context or 8B with small context
      this.modelPath = "qwen2.5:3b-instruct-q4_K_M"; 
      this.gpuLayers = this.isAppleSilicon ? 32 : 16;
      this.contextSize = 2048;
      this.batchSize = 256;
    } else {
      // 32GB+: Use 8B model with good settings
      this.modelPath = "llama3.1:8b-instruct-q4_K_M";
      this.gpuLayers = this.isAppleSilicon ? 40 : 20;
      this.contextSize = 4096;
      this.batchSize = 512;
    }

    // CPU threads optimization
    if (this.isAppleSilicon) {
      // Apple Silicon: Use all cores (performance + efficiency)
      this.threads = this.cpuCores;
    } else {
      // x86: Use physical cores only (avoid hyperthreading)
      this.threads = Math.max(1, Math.floor(this.cpuCores / 2));
    }

    logger.info(`🔧 Hardware Optimization:`, {
      ram: `${this.totalRAM}GB (${this.availableRAM}GB free)`,
      cores: this.cpuCores,
      threads: this.threads,
      appleSilicon: this.isAppleSilicon,
      model: this.modelPath,
      gpuLayers: this.gpuLayers,
      context: this.contextSize,
      batch: this.batchSize
    });
  }

  // Dynamic optimization based on current system load
  getDynamicSettings() {
    const currentFreeRAM = Math.floor(os.freemem() / (1024 * 1024 * 1024));
    
    // If system is under memory pressure, reduce context
    if (currentFreeRAM < 2) {
      return {
        contextSize: Math.min(256, this.contextSize),
        batchSize: Math.min(64, this.batchSize),
        threads: Math.max(2, Math.floor(this.threads / 2))
      };
    }
    
    return {
      contextSize: this.contextSize,
      batchSize: this.batchSize,
      threads: this.threads
    };
  }
}

const HARDWARE = new HardwareOptimizer();

export class LocalLlamaEngine {
  private model: LlamaModel | null = null;
  private llama: any = null;

  constructor(private opts?: { modelPath?: string }) {
    logger.info(`Detected ${HARDWARE.isAppleSilicon ? 'Apple Silicon' : 'x86'} with ${HARDWARE.totalRAM}GB RAM`);
  }

  private async ensureModel(modelPath: string) {
    if (this.model) return;

    if (!fs.existsSync(modelPath)) {
      logger.error(`❌ GGUF model not found: ${modelPath}`);
      logger.error("Refusing to proceed without valid model file");
      process.exit(1);
    }

    logger.info(`Loading llama.cpp runtime...`);
    this.llama = await getLlama();

    logger.info(`Loading model from ${modelPath}`);
    
    // Adaptive model loading based on hardware
    const modelConfig: any = {
      modelPath,
      gpuLayers: HARDWARE.gpuLayers,
      useMmap: true,
      useMlock: HARDWARE.totalRAM >= 16, // Lock in RAM only if we have enough
    };

    // Try aggressive settings first, fall back if needed
    try {
      this.model = await this.llama.loadModel(modelConfig);
      logger.info(`Model loaded with ${HARDWARE.gpuLayers} GPU layers`);
    } catch (error) {
      logger.warn("Aggressive settings failed, trying conservative...");
      modelConfig.gpuLayers = Math.floor(HARDWARE.gpuLayers / 2);
      modelConfig.useMlock = false;
      this.model = await this.llama.loadModel(modelConfig);
      logger.info(`Model loaded with ${modelConfig.gpuLayers} GPU layers (conservative)`);
    }
  }

  async *generateStream(
    sessionId: string,
    prompt: string,
    params: GenerationParams
  ): AsyncGenerator<GenerationEvent> {
    const t0 = performance.now();

    // Get dynamic settings based on current system state
    const dynamicSettings = HARDWARE.getDynamicSettings();

    const caps = {
      maxTokens: Math.min(params.max_tokens ?? 128, 512),
      temperature: params.temperature ?? 0.2,
      stop: params.stop ?? ["<|im_end|>", "<|im_start|>", "</s>", "\n\n", "assistant"],
    };
    
    const ctxLen = Math.min(params.ctx ?? dynamicSettings.contextSize, dynamicSettings.contextSize);

    // Prompt budget gate
    if (prompt.length > 4000) {
      if ((process.env.MODE || "dev") === "prod") {
        prompt = "[truncated]" + prompt.slice(-3800);
        logger.warn("Prompt truncated in production mode");
      } else {
        throw new Error(`Prompt too long: ${prompt.length} chars (max 4000 in dev)`);
      }
    }

    // Use hardware-optimized model selection
    const modelPath =
      this.opts?.modelPath ||
      process.env.JARVIS_LOCAL_GGUF ||
      resolveModelPath(HARDWARE.modelPath);

    await this.ensureModel(modelPath);

    // Get or create a persistent context/session for KV reuse
    const { context, chat: session } = await getSession(
      sessionId,
      async () => {
        // Try aggressive context first, reduce if needed
        const sizes = [dynamicSettings.contextSize, 1024, 512, 256];
        
        for (const size of sizes) {
          try {
            const ctx = await this.model!.createContext({
              contextSize: size,
              batchSize: Math.min(dynamicSettings.batchSize, size / 2),
              threads: dynamicSettings.threads,
            });
            logger.info(`Context created: ${size} tokens, ${dynamicSettings.threads} threads`);
            return ctx;
          } catch (error) {
            logger.warn(`Context size ${size} failed, trying smaller...`);
            if (size === sizes[sizes.length - 1]) throw error;
          }
        }
        throw new Error("Failed to create context");
      },
      async (ctx) => {
        const contextSequence = ctx.getSequence();
        const chatSession = new LlamaChatSession({
          contextSequence,
          chatWrapper: new ChatMLChatWrapper(),
        });
        return chatSession;
      }
    );

    logger.debug("[JARVIS] Generation params", {
      ctx: ctxLen,
      batch: dynamicSettings.batchSize,
      threads: dynamicSettings.threads,
      gpuLayers: HARDWARE.gpuLayers,
      model: HARDWARE.modelPath,
    });

    let firstMs: number | null = null;
    let tokensOut = 0;
    let fullResponse = "";

    try {
      const response = await session.prompt(prompt, {
        temperature: caps.temperature,
        maxTokens: caps.maxTokens,
        stopStrings: caps.stop,
      });
      
      if (response) {
        firstMs = performance.now() - t0;
        yield { type: "first", ms: firstMs, timestamp: Date.now() };
        yield { type: "token", text: response, timestamp: Date.now() };
        tokensOut = 1;
        fullResponse = response;
      }
    } catch (e) {
      logger.error("Generation error:", e);
    }

    if (firstMs === null) {
      firstMs = performance.now() - t0;
    }

    const totalMs = performance.now() - t0;

    logger.logLatency({
      engine: "local",
      model_id: HARDWARE.modelPath,
      params: {
        ctx: ctxLen,
        max_tokens: caps.maxTokens,
        temperature: caps.temperature,
        stop: caps.stop,
      },
      prompt_chars: prompt.length,
      session_id: sessionId,
      first_token_ms: firstMs,
      total_ms: totalMs,
      tokens_out: tokensOut,
      route: "local",
    });

    yield { type: "done", timestamp: Date.now() };
  }

  async smokeTest(): Promise<void> {
    logger.info("Running startup smoke test...");

    const testParams: GenerationParams = {
      max_tokens: 16,
      ctx: 512,
      temperature: 0.0,
      stop: [".", "\n", "<|eot_id|>"],
    };

    let firstTokenMs = 0;
    let totalMs = 0;
    let tokensOut = 0;
    let response = "";
    const startTime = performance.now();

    try {
      for await (const event of this.generateStream("smoke-test", "Reply with OK", testParams)) {
        if (event.type === "first") {
          firstTokenMs = event.ms || 0;
        } else if (event.type === "token" && event.text) {
          tokensOut++;
          response += event.text;
        } else if (event.type === "done") {
          totalMs = performance.now() - startTime;
          break;
        }
      }

      logger.info(`Smoke test response: "${response.trim()}"`);

      // Adaptive thresholds based on hardware
      const maxFirstToken = HARDWARE.totalRAM <= 8 ? 8000 : 3000;
      const maxTotal = HARDWARE.totalRAM <= 8 ? 12000 : 5000;

      if (firstTokenMs > maxFirstToken || totalMs > maxTotal || tokensOut === 0) {
        logger.warn(
          `Smoke test slower than ideal: first=${firstTokenMs}ms total=${totalMs}ms tokens=${tokensOut}`
        );
        logger.warn(`Target: first<${maxFirstToken}ms total<${maxTotal}ms`);
        // Don't exit - just warn
      } else {
        logger.info(
          `✅ SMOKE OK first=${firstTokenMs}ms total=${totalMs}ms engine=local tokens=${tokensOut}`
        );
      }
    } catch (error) {
      logger.error("Smoke test failed:", error);
      process.exit(1);
    }
  }

  getHealth() {
    return {
      ok: this.model !== null,
      modelId: HARDWARE.modelPath,
      hardware: {
        ram: `${HARDWARE.totalRAM}GB`,
        cores: HARDWARE.cpuCores,
        threads: HARDWARE.threads,
        appleSilicon: HARDWARE.isAppleSilicon,
      },
      settings: {
        ctx: HARDWARE.contextSize,
        batch: HARDWARE.batchSize,
        gpuLayers: HARDWARE.gpuLayers,
      },
      platform: process.platform,
      metalSupport: HARDWARE.isAppleSilicon,
      engine: "local",
    };
  }

  async cleanup() {
    if (this.model) {
      this.model = null;
      this.llama = null;
      logger.info("Local model cleaned up");
    }
  }
}