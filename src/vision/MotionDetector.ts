// src/vision/MotionDetector.ts
//
// Tier-1 reflex layer. Deliberately not an LLM, not even the fast-utility
// model -- this is plain pixel-diffing so "is anything happening" resolves
// in well under a millisecond and never touches the model mesh at all. Its
// only job is to gate whether ObjectDetector (and, beyond that, the mesh)
// gets invoked for a given frame.
export interface MotionResult {
  changed: boolean;
  changedPixelRatio: number;
  boundingBox: { x: number; y: number; width: number; height: number } | null;
}

export interface FrameBuffer {
  data: Uint8ClampedArray; // grayscale, one byte per pixel
  width: number;
  height: number;
}

export class MotionDetector {
  private previousFrame: FrameBuffer | null = null;

  constructor(
    private pixelDiffThreshold: number = 25, // per-pixel intensity delta to count as "changed"
    private triggerRatio: number = 0.01 // fraction of frame that must change to fire
  ) {}

  /** Feed the next grayscale frame; returns whether it differs enough from the last one to matter. */
  process(frame: FrameBuffer): MotionResult {
    if (!this.previousFrame || this.previousFrame.width !== frame.width || this.previousFrame.height !== frame.height) {
      this.previousFrame = frame;
      return { changed: false, changedPixelRatio: 0, boundingBox: null };
    }

    const { width, height, data } = frame;
    const prev = this.previousFrame.data;

    let changedCount = 0;
    let minX = width, minY = height, maxX = 0, maxY = 0;

    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        const i = y * width + x;
        if (Math.abs(data[i] - prev[i]) > this.pixelDiffThreshold) {
          changedCount++;
          if (x < minX) minX = x;
          if (x > maxX) maxX = x;
          if (y < minY) minY = y;
          if (y > maxY) maxY = y;
        }
      }
    }

    this.previousFrame = frame;
    const changedPixelRatio = changedCount / (width * height);
    const changed = changedPixelRatio > this.triggerRatio;

    return {
      changed,
      changedPixelRatio,
      boundingBox: changed ? { x: minX, y: minY, width: maxX - minX, height: maxY - minY } : null
    };
  }

  reset(): void {
    this.previousFrame = null;
  }
}
