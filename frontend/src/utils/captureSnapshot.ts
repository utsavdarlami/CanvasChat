import { record } from 'rrweb';
import { isRecorderActive } from '../stores/snapshotStore';

/**
 * Tags the active rrweb session with a custom event marker. Used to annotate
 * the replay timeline with semantic labels (e.g. 'user_drag', 'pan',
 * 'zoom_out', 'ai_update') so specific moments can be jumped to or exported
 * later as PNGs.
 *
 * No-op when no session is being recorded. Runtime cost per call is a single
 * event push into the rrweb buffer — safe to call from drag/pan/zoom end
 * handlers without any debouncing.
 *
 * @param triggerSource - Short semantic tag for the event.
 * @param payload - Optional structured data attached to the marker.
 */
export const captureSnapshot = (
  triggerSource: string = 'action',
  payload?: Record<string, unknown>,
): void => {
  if (!isRecorderActive()) return;
  try {
    record.addCustomEvent(triggerSource, payload ?? {});
  } catch (err) {
    console.warn('[Study Recording] addCustomEvent failed:', err);
  }
};
