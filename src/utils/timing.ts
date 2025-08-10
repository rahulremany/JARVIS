export class Stopwatch {
  private startTime: number = 0;
  private endTime: number = 0;

  start(): void {
    this.startTime = performance.now();
  }

  stop(): number {
    this.endTime = performance.now();
    return this.elapsed();
  }

  elapsed(): number {
    if (this.endTime === 0) {
      return performance.now() - this.startTime;
    }
    return this.endTime - this.startTime;
  }

  reset(): void {
    this.startTime = 0;
    this.endTime = 0;
  }
}

export function calculatePercentiles(
  values: number[], 
  percentiles: number[]
): Record<string, number> {
  if (values.length === 0) {
    return Object.fromEntries(percentiles.map(p => [`p${p}`, 0]));
  }

  const sorted = [...values].sort((a, b) => a - b);
  const result: Record<string, number> = {};

  for (const p of percentiles) {
    const index = (p / 100) * (sorted.length - 1);
    const lower = Math.floor(index);
    const upper = Math.ceil(index);
    const weight = index % 1;

    if (lower === upper) {
      result[`p${p}`] = sorted[lower];
    } else {
      result[`p${p}`] = sorted[lower] * (1 - weight) + sorted[upper] * weight;
    }
  }

  return result;
}

export function timeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  return Promise.race([
    promise,
    new Promise<never>((_, reject) => 
      setTimeout(() => reject(new Error(`Timeout after ${ms}ms`)), ms)
    )
  ]);
}
