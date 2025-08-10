#!/usr/bin/env tsx

import { LocalLlamaEngine } from '../src/engines/local/LocalLlamaEngine.js';
import { calculatePercentiles } from '../src/utils/timing.js';
import { logger } from '../src/utils/logging.js';

interface BenchCase {
  name: string;
  prompt: string;
  expectedOutputPattern?: RegExp;
  maxTokens?: number;
}

const BENCH_CASES: BenchCase[] = [
  {
    name: 'Device Control',
    prompt: 'Turn on the living room lights',
    expectedOutputPattern: /light|on|turn/i,
    maxTokens: 50
  },
  {
    name: 'Quick Info',
    prompt: 'What time is it right now?',
    expectedOutputPattern: /time|clock|hour/i,
    maxTokens: 30
  },
  {
    name: 'Simple Math',
    prompt: 'What is 15 + 27?',
    expectedOutputPattern: /42|forty.two/i,
    maxTokens: 20
  },
  {
    name: 'General Chat',
    prompt: 'How are you doing today?',
    expectedOutputPattern: /good|fine|well|helping/i,
    maxTokens: 100
  },
  {
    name: 'Code Question',
    prompt: 'How do you declare a variable in JavaScript?',
    expectedOutputPattern: /var|let|const|declare/i,
    maxTokens: 150
  }
];

async function runBenchmark(): Promise<void> {
  console.log('\n🚀 JARVIS Latency Benchmark');
  console.log('===============================\n');

  const currentFile = new URL(import.meta.url).pathname;
  if (!process.argv[1].includes('latency.bench')) {
    console.error('❌ Error: This script must be run via npm run bench');
    process.exit(1);
  }

  // Initialize engine
  logger.info('Initializing LocalLlamaEngine for benchmarking...');
  const engine = new LocalLlamaEngine();
  
  // Warm up with a simple test
  logger.info('Warming up engine...');
  const warmupResults = [];
  for await (const event of engine.generateStream('warmup', 'Hello', { max_tokens: 5, temperature: 0.0 })) {
    if (event.type === 'token') {
      warmupResults.push(event.text);
    }
  }
  logger.info(`Warmup complete: "${warmupResults.join('')}"`);

  // Run benchmark cases
  const results: Array<{
    case: string;
    firstTokenMs: number;
    totalMs: number;
    tokensOut: number;
    tokensPerSecond: number;
    accuracy: boolean;
    response: string;
  }> = [];

  for (const benchCase of BENCH_CASES) {
    logger.info(`\n📊 Running: ${benchCase.name}`);
    logger.info(`Prompt: "${benchCase.prompt}"`);

    const startTime = performance.now();
    let firstTokenMs = 0;
    let tokensOut = 0;
    let response = '';
    let firstTokenRecorded = false;

    try {
      for await (const event of engine.generateStream(
        `bench-${benchCase.name.toLowerCase().replace(/\s+/g, '-')}`,
        benchCase.prompt,
        {
          max_tokens: benchCase.maxTokens || 100,
          temperature: 0.2,
          stop: ['.', '\n\n', '?', '!']
        }
      )) {
        if (event.type === 'first') {
          firstTokenMs = event.ms || 0;
          firstTokenRecorded = true;
        } else if (event.type === 'token' && event.text) {
          if (!firstTokenRecorded) {
            firstTokenMs = performance.now() - startTime;
            firstTokenRecorded = true;
          }
          tokensOut++;
          response += event.text;
        }
      }

      const totalMs = performance.now() - startTime;
      const tokensPerSecond = tokensOut > 0 ? (tokensOut / totalMs) * 1000 : 0;
      
      // Check accuracy against expected pattern
      const accuracy = benchCase.expectedOutputPattern 
        ? benchCase.expectedOutputPattern.test(response)
        : true; // Default to true if no pattern specified

      results.push({
        case: benchCase.name,
        firstTokenMs,
        totalMs,
        tokensOut,
        tokensPerSecond,
        accuracy,
        response: response.trim()
      });

      console.log(`✅ Response: "${response.trim()}"`);
      console.log(`📈 Metrics: first=${firstTokenMs.toFixed(1)}ms total=${totalMs.toFixed(1)}ms tokens=${tokensOut} speed=${tokensPerSecond.toFixed(1)}t/s accuracy=${accuracy ? '✓' : '✗'}`);

    } catch (error) {
      logger.error(`❌ Benchmark case "${benchCase.name}" failed:`, error);
      results.push({
        case: benchCase.name,
        firstTokenMs: 0,
        totalMs: 0,
        tokensOut: 0,
        tokensPerSecond: 0,
        accuracy: false,
        response: 'ERROR'
      });
    }
  }

  // Calculate aggregate statistics
  const validResults = results.filter(r => r.totalMs > 0);
  
  if (validResults.length === 0) {
    console.error('❌ No valid benchmark results');
    process.exit(1);
  }

  const firstTokenTimes = validResults.map(r => r.firstTokenMs);
  const totalTimes = validResults.map(r => r.totalMs);
  const tokenCounts = validResults.map(r => r.tokensOut);
  const speeds = validResults.map(r => r.tokensPerSecond);
  const accuracyRate = results.filter(r => r.accuracy).length / results.length;

  const firstTokenPercentiles = calculatePercentiles(firstTokenTimes, [50, 95]);
  const totalTimePercentiles = calculatePercentiles(totalTimes, [50, 95]);
  
  // Print summary
  console.log('\n📊 BENCHMARK SUMMARY');
  console.log('====================');
  console.log(`Cases run: ${results.length}`);
  console.log(`Success rate: ${validResults.length}/${results.length} (${((validResults.length/results.length)*100).toFixed(1)}%)`);
  console.log(`Accuracy rate: ${(accuracyRate*100).toFixed(1)}%`);
  console.log('');
  console.log('⏱️  LATENCY:');
  console.log(`  First token p50: ${firstTokenPercentiles.p50.toFixed(1)}ms`);
  console.log(`  First token p95: ${firstTokenPercentiles.p95.toFixed(1)}ms`);
  console.log(`  Total time p50: ${totalTimePercentiles.p50.toFixed(1)}ms`);
  console.log(`  Total time p95: ${totalTimePercentiles.p95.toFixed(1)}ms`);
  console.log('');
  console.log('🚀 THROUGHPUT:');
  console.log(`  Avg tokens/sec: ${speeds.reduce((a,b) => a+b, 0) / speeds.length.toFixed(1)}`);
  console.log(`  Avg tokens out: ${(tokenCounts.reduce((a,b) => a+b, 0) / tokenCounts.length).toFixed(1)}`);

  // Check performance targets
  console.log('\n🎯 PERFORMANCE TARGETS:');
  const firstTokenTarget = 3000; // 3s for first token
  const totalTimeTarget = 8000;  // 8s total
  const accuracyTarget = 0.8;    // 80% accuracy

  const firstTokenPass = firstTokenPercentiles.p95 <= firstTokenTarget;
  const totalTimePass = totalTimePercentiles.p95 <= totalTimeTarget;
  const accuracyPass = accuracyRate >= accuracyTarget;

  console.log(`  First token p95 ≤ ${firstTokenTarget}ms: ${firstTokenPass ? '✅' : '❌'} (${firstTokenPercentiles.p95.toFixed(1)}ms)`);
  console.log(`  Total time p95 ≤ ${totalTimeTarget}ms: ${totalTimePass ? '✅' : '❌'} (${totalTimePercentiles.p95.toFixed(1)}ms)`);
  console.log(`  Accuracy ≥ ${(accuracyTarget*100).toFixed(0)}%: ${accuracyPass ? '✅' : '❌'} (${(accuracyRate*100).toFixed(1)}%)`);

  const allTargetsMet = firstTokenPass && totalTimePass && accuracyPass;
  console.log(`\n🏆 Overall: ${allTargetsMet ? '✅ PASS' : '❌ FAIL'}`);

  // Cleanup
  await engine.cleanup();

  // Exit with appropriate code
  process.exit(allTargetsMet ? 0 : 1);
}

if (import.meta.url === `file://${process.argv[1]}`) {
  runBenchmark().catch(console.error);
}
