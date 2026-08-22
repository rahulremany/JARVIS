// src/vision/ReflexLoop.ts
//
// Ties the two reflex-tier pieces together and defines the one escalation
// path out of it: motion gates detection, detection gates whether the mesh
// (tier 3) ever gets called at all. Nothing in this file makes a model call
// unless somethingWorthReasoningAbout() says so -- that's what keeps the
// reflex tier free of network/LLM latency.
import { MotionDetector, type FrameBuffer } from './MotionDetector.js';
import { ObjectDetector, type Detection } from './ObjectDetector.js';
import { logger } from '../utils/logging.js';

export interface ReflexEvent {
  motionRatio: number;
  detections: Detection[];
  escalate: boolean;
}

export class ReflexLoop {
  private motion = new MotionDetector();
  private objects = new ObjectDetector();

  constructor(private onEscalate?: (event: ReflexEvent) => void) {}

  async processFrame(frame: FrameBuffer): Promise<ReflexEvent> {
    const motionResult = this.motion.process(frame);

    if (!motionResult.changed) {
      return { motionRatio: motionResult.changedPixelRatio, detections: [], escalate: false };
    }

    const detections = await this.objects.detect(frame);
    const escalate = this.somethingWorthReasoningAbout(detections);

    const event: ReflexEvent = { motionRatio: motionResult.changedPixelRatio, detections, escalate };

    if (escalate) {
      logger.debug('Reflex loop escalating to mesh:', {
        motionRatio: event.motionRatio,
        labels: detections.map(d => d.label)
      });
      this.onEscalate?.(event);
    }

    return event;
  }

  // Placeholder policy: escalate whenever the object detector finds anything
  // above a confidence bar. Real workshop rules (e.g. "only escalate for
  // hands near tool_bit") replace this once ObjectDetector has a real
  // backend behind it.
  private somethingWorthReasoningAbout(detections: Detection[]): boolean {
    return detections.some(d => d.confidence > 0.5);
  }
}
