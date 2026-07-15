import { create } from 'zustand';
import { record } from 'rrweb';
import type { eventWithTime } from '@rrweb/types';
import { useAppStore } from './appStore';

interface SnapshotState {
  dirHandle: FileSystemDirectoryHandle | null;
  isRecording: boolean;
  useFallbackMode: boolean;
  eventCount: number;
  startRecording: () => Promise<void>;
  stopRecording: () => Promise<void>;
}

// Module-scoped recorder state. Kept outside the zustand store so the rrweb
// event buffer (which can hit thousands of entries) never triggers React
// re-renders.
let events: eventWithTime[] = [];
let stopFn: (() => void) | null = null;
let sessionStartedAt: number | null = null;

function beginRecorder(onEvent?: () => void): void {
  events = [];
  sessionStartedAt = Date.now();
  stopFn = record({
    emit(event) {
      events.push(event);
      onEvent?.();
    },
    recordCanvas: false,
    collectFonts: false,
    // Vega charts are huge SVG/canvas subtrees that mount/unmount as the user
    // pans (IntersectionObserver in LazyVegaChart). Recording each mount/unmount
    // as a DOM mutation dominates the event stream and is the main cause of
    // progressive slowdown over long sessions. We block only the live canvas
    // host (`lazy-vega-chart__canvas`), not the outer wrapper, so the sibling
    // `lazy-vega-chart__snapshot` <img> (cached PNG of the last render) stays
    // in the recording and replay shows a static chart image instead of a
    // blank placeholder.
    blockClass: 'lazy-vega-chart__canvas',
    // Sampling keeps chat/typing fluid: 'last' coalesces rapid input events
    // so each keystroke isn't an individual serialize+push on the main thread.
    // mousemove/scroll throttles trim dense streams that don't add replay value.
    sampling: {
      input: 'last',
      mousemove: 150,
      scroll: 150,
      media: 800,
      mouseInteraction: {
        MouseUp: false,
        MouseDown: false,
        Focus: false,
        Blur: false,
        TouchStart: false,
        TouchEnd: false,
      },
    },
    // Strip head/script noise we'd never watch back; cuts full-snapshot size
    // and serialization cost on every DOM checkout.
    slimDOMOptions: {
      script: true,
      comment: true,
      headFavicon: true,
      headWhitespace: true,
      headMetaDescKeywords: true,
      headMetaSocial: true,
      headMetaRobots: true,
      headMetaHttpEquiv: true,
      headMetaAuthorship: true,
      headMetaVerification: true,
    },
  }) ?? null;
}

function endRecorder(): eventWithTime[] {
  if (stopFn) {
    stopFn();
    stopFn = null;
  }
  const collected = events;
  events = [];
  return collected;
}

function buildFilename(): string {
  const roomId = useAppStore.getState().session.roomId || 'offline';
  const date = new Date(sessionStartedAt ?? Date.now()).toISOString().replace(/[:.]/g, '-');
  return `session-${roomId}-${date}.rrweb.json`;
}

async function writeSession(
  collected: eventWithTime[],
  dirHandle: FileSystemDirectoryHandle | null,
  useFallbackMode: boolean,
): Promise<void> {
  if (collected.length === 0) return;

  const payload = JSON.stringify({
    version: 1,
    startedAt: sessionStartedAt,
    endedAt: Date.now(),
    roomId: useAppStore.getState().session.roomId || 'offline',
    events: collected,
  });
  const blob = new Blob([payload], { type: 'application/json' });
  const filename = buildFilename();

  if (useFallbackMode || !dirHandle) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    console.log(`[Study Recording] Session downloaded: ${filename} (${collected.length} events)`);
    return;
  }

  // @ts-ignore - File System Access API
  const fileHandle = await dirHandle.getFileHandle(filename, { create: true });
  // @ts-ignore
  const writable = await fileHandle.createWritable();
  await writable.write(blob);
  await writable.close();
  console.log(`[Study Recording] Session saved: ${filename} (${collected.length} events)`);
}

export const useSnapshotStore = create<SnapshotState>((set, get) => ({
  dirHandle: null,
  isRecording: false,
  useFallbackMode: false,
  eventCount: 0,

  startRecording: async () => {
    if (get().isRecording) return;

    let dirHandle: FileSystemDirectoryHandle | null = null;
    let useFallbackMode = false;

    if (!('showDirectoryPicker' in window)) {
      console.warn('File System Access API not supported. Falling back to standard downloads.');
      useFallbackMode = true;
    } else {
      try {
        // @ts-ignore - File System Access API
        dirHandle = await window.showDirectoryPicker({ mode: 'readwrite' });
      } catch (err) {
        if (err instanceof Error && err.name === 'AbortError') {
          // User cancelled the picker; abort start.
          return;
        }
        console.warn('Directory picker failed; using download fallback.', err);
        useFallbackMode = true;
      }
    }

    set({ dirHandle, useFallbackMode, isRecording: true, eventCount: 0 });

    // Throttle eventCount updates so UI re-renders stay cheap even under
    // heavy event streams. We only publish the count at most ~4x/sec.
    let lastPublish = 0;
    beginRecorder(() => {
      const now = performance.now();
      if (now - lastPublish > 250) {
        lastPublish = now;
        set({ eventCount: events.length });
      }
    });
  },

  stopRecording: async () => {
    if (!get().isRecording) return;
    const { dirHandle, useFallbackMode } = get();
    const collected = endRecorder();
    set({ isRecording: false, dirHandle: null, useFallbackMode: false, eventCount: 0 });
    try {
      await writeSession(collected, dirHandle, useFallbackMode);
    } catch (err) {
      console.error('[Study Recording] Failed to write session file:', err);
    }
    sessionStartedAt = null;
  },
}));

// Exposed for the captureSnapshot shim so it can tag the active session
// without going through the zustand subscription path.
export function isRecorderActive(): boolean {
  return stopFn !== null;
}
