import { existsSync } from 'fs';
import { resolve } from 'path';
import os from 'os';

export interface ModelMetadata {
  id: string;
  path: string;
  sizeGB: number;
  minRAMGB: number;
  recommendedRAMGB: number;
  parameters: string;
  quantization: string;
  capabilities: string[];
  speed: 'fast' | 'medium' | 'slow';
  quality: 'good' | 'better' | 'best';
}

export const MODEL_CATALOG: ModelMetadata[] = [
  {
    id: "qwen2.5:3b-instruct-q4_K_M",
    path: "models/qwen2.5-3b-instruct-q4_k_m.gguf",
    sizeGB: 2.0,
    minRAMGB: 4,
    recommendedRAMGB: 6,
    parameters: "3B",
    quantization: "Q4_K_M",
    capabilities: ["chat", "instruct", "reasoning", "code"],
    speed: "fast",
    quality: "good"
  },
  {
    id: "llama3.1:8b-instruct-q4_K_M",
    path: "models/llama-3.1-8b-instruct-q4_k_m.gguf",
    sizeGB: 4.6,
    minRAMGB: 6,
    recommendedRAMGB: 8,
    parameters: "8B",
    quantization: "Q4_K_M", 
    capabilities: ["chat", "instruct", "reasoning", "code", "analysis"],
    speed: "medium",
    quality: "better"
  },
  {
    id: "phi3:mini",
    path: "models/phi3-mini-4k-instruct-q4_0.gguf",
    sizeGB: 2.1,
    minRAMGB: 4,
    recommendedRAMGB: 6,
    parameters: "3.8B",
    quantization: "Q4_0",
    capabilities: ["chat", "instruct", "code"],
    speed: "fast",
    quality: "good"
  },
  {
    id: "mixtral:8x7b-instruct-q4_K_M",
    path: "models/mixtral-8x7b-instruct-q4_k_m.gguf",
    sizeGB: 26.4,
    minRAMGB: 32,
    recommendedRAMGB: 64,
    parameters: "46.7B",
    quantization: "Q4_K_M",
    capabilities: ["chat", "instruct", "reasoning", "code", "analysis", "multilingual"],
    speed: "slow",
    quality: "best"
  }
];

// Legacy MODEL_MAP for backwards compatibility
export const MODEL_MAP: Record<string, string> = Object.fromEntries(
  MODEL_CATALOG.map(model => [model.id, model.path])
);

export function getSystemRAM(): number {
  return Math.round(os.totalmem() / (1024 * 1024 * 1024)); // Convert to GB
}

export function detectBestModel(): ModelMetadata {
  const systemRAM = getSystemRAM();
  const availableModels = MODEL_CATALOG.filter(model => 
    existsSync(resolve(model.path))
  );

  if (availableModels.length === 0) {
    throw new Error('No GGUF models found on system');
  }

  console.log(`[JARVIS] 🔍 System RAM: ${systemRAM}GB`);
  console.log(`[JARVIS] 📋 Available models: ${availableModels.map(m => m.id).join(', ')}`);

  // Find models that fit in system RAM
  const compatibleModels = availableModels.filter(model => 
    model.minRAMGB <= systemRAM
  );

  if (compatibleModels.length === 0) {
    console.warn(`[JARVIS] ⚠️  No models meet minimum RAM requirement. Using smallest available.`);
    return availableModels.sort((a, b) => a.minRAMGB - b.minRAMGB)[0];
  }

  // Find models with recommended RAM
  const optimalModels = compatibleModels.filter(model => 
    model.recommendedRAMGB <= systemRAM
  );

  let selectedModel: ModelMetadata;

  if (optimalModels.length > 0) {
    // Pick the largest model that fits comfortably
    selectedModel = optimalModels.sort((a, b) => b.sizeGB - a.sizeGB)[0];
  } else {
    // Pick the largest model that meets minimum requirements
    selectedModel = compatibleModels.sort((a, b) => b.sizeGB - a.sizeGB)[0];
  }

  console.log(`[JARVIS] 🎯 Selected optimal model: ${selectedModel.id}`);
  console.log(`[JARVIS] 📊 Model specs: ${selectedModel.parameters} params, ${selectedModel.sizeGB}GB, ${selectedModel.speed} speed, ${selectedModel.quality} quality`);
  console.log(`[JARVIS] 🔧 Capabilities: ${selectedModel.capabilities.join(', ')}`);

  return selectedModel;
}

export function validateModels(): void {
  console.log('[JARVIS] 🔍 Validating GGUF models...');
  
  const availableModels = MODEL_CATALOG.filter(model => {
    const absolutePath = resolve(model.path);
    const exists = existsSync(absolutePath);
    
    if (!exists) {
      console.log(`[JARVIS] ⚠️  Missing optional model: ${model.id}`);
      console.log(`[JARVIS] Expected path: ${absolutePath}`);
      return false;
    }
    
    if (!absolutePath.endsWith('.gguf')) {
      console.error(`[JARVIS] ❌ Invalid model format: ${model.id} (must be .gguf)`);
      console.error(`[JARVIS] Path: ${absolutePath}`);
      process.exit(1);
    }
    
    console.log(`[JARVIS] ✅ Found: ${model.id} -> ${absolutePath}`);
    return true;
  });

  if (availableModels.length === 0) {
    console.error(`[JARVIS] ❌ No GGUF models found!`);
    console.error(`[JARVIS] Please download at least one model to continue.`);
    console.error(`[JARVIS] Recommended for ${getSystemRAM()}GB RAM:`);
    
    const recommendations = MODEL_CATALOG
      .filter(m => m.recommendedRAMGB <= getSystemRAM())
      .sort((a, b) => b.sizeGB - a.sizeGB);
    
    recommendations.forEach(model => {
      console.error(`[JARVIS]   - ${model.id}: ${model.parameters} params (${model.sizeGB}GB)`);
    });
    
    process.exit(1);
  }

  console.log(`[JARVIS] ✅ Found ${availableModels.length}/${MODEL_CATALOG.length} models`);
}

export function resolveModelPath(modelId: string): string {
  const model = MODEL_CATALOG.find(m => m.id === modelId);
  if (!model) {
    throw new Error(`Unknown model ID: ${modelId}. Available: ${MODEL_CATALOG.map(m => m.id).join(', ')}`);
  }
  return resolve(model.path);
}

export function getModelMetadata(modelId: string): ModelMetadata {
  const model = MODEL_CATALOG.find(m => m.id === modelId);
  if (!model) {
    throw new Error(`Unknown model ID: ${modelId}`);
  }
  return model;
}
