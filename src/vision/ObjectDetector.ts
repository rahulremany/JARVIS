// src/vision/ObjectDetector.ts
//
// Second half of the reflex tier: once MotionDetector says a region changed,
// this answers "what is it" -- a dedicated detector, not an LLM call, so it
// stays fast enough to run per-frame. Pluggable by design: swap `backend` for
// a real ONNX Runtime + YOLO session without touching call sites in Router/
// EngineSelector. Ships with a `stub` backend so the interface and the
// reflex -> escalate flow are runnable end-to-end before model weights and
// a camera are wired up.
export interface Detection {
  label: string;
  confidence: number;
  box: { x: number; y: number; width: number; height: number };
}

export interface ObjectDetectorBackend {
  detect(frame: FrameInput): Promise<Detection[]>;
}

export interface FrameInput {
  data: Uint8ClampedArray;
  width: number;
  height: number;
}

/**
 * Stub backend: returns no detections, but exercises the real call shape so
 * the rest of the reflex pipeline (motion -> detect -> escalate-to-mesh) is
 * demonstrable without bundling model weights into the repo. Replace with a
 * YOLOv8/v11 ONNX session for real per-frame object recognition.
 */
export class StubObjectDetector implements ObjectDetectorBackend {
  async detect(_frame: FrameInput): Promise<Detection[]> {
    return [];
  }
}

export class ObjectDetector {
  constructor(private backend: ObjectDetectorBackend = new StubObjectDetector()) {}

  async detect(frame: FrameInput): Promise<Detection[]> {
    return this.backend.detect(frame);
  }

  /** Swap in a real backend (e.g. an ONNX Runtime YOLO session) at runtime. */
  setBackend(backend: ObjectDetectorBackend): void {
    this.backend = backend;
  }
}
