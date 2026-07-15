/**
 * Singleton service managing the Vega render worker.
 *
 * Interaction gate: render requests are held while the user is dragging/panning.
 * This stops the worker from doing expensive CSV-fetch + transform work during
 * drag, keeping the worker thread free for whatever the browser needs.
 * When interaction ends, the held requests fire in order.
 */

type RenderCallback = (result: { url?: string; error?: string }) => void;

let worker: Worker | null = null;
const callbacks = new Map<string, RenderCallback>();

// Track object URLs so we can revoke them on worker reset
const activeUrls = new Set<string>();

function getWorker(): Worker {
  if (worker) return worker;
  worker = new Worker(
    new URL('./vegaRenderWorker.ts', import.meta.url),
    { type: 'module' },
  );
  worker.onmessage = async ({ data }) => {
    const cb = callbacks.get(data.id);
    if (!cb) return;
    callbacks.delete(data.id);

    if (data.type === 'error') {
      cb({ error: data.message });
    } else {
      // Create an Object URL from the blob — cheap, no base64 encoding
      const url = URL.createObjectURL(data.blob as Blob);
      activeUrls.add(url);
      cb({ url });
    }
  };
  worker.onerror = (e) => console.error('[VegaWorker]', e.message);
  return worker;
}

// ---------------------------------------------------------------------------
// Interaction gate
// ---------------------------------------------------------------------------
let _interacting = false;
const deferred: Array<() => void> = [];

/** Call with true on drag/pan start, false on end. Mirrors setUserInteracting. */
export function setWorkerInteracting(interacting: boolean): void {
  _interacting = interacting;
  if (!interacting) {
    // Stagger flushes 80ms apart to prevent CPU burst when 18 charts fire at once
    const pending = deferred.splice(0);
    pending.forEach((fn, i) => {
      if (i === 0) fn();
      else setTimeout(fn, i * 80);
    });
  }
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------
let idCounter = 0;

export function renderVegaChart(
  spec: Record<string, unknown>,
  width: number,
  height: number,
): { id: string; promise: Promise<string>; cancel: () => void } {
  const id = `v${++idCounter}`;
  let cancelled = false;

  // Hoist send so cancel() can find and remove it from the deferred queue
  const send = () => {
    if (cancelled) { callbacks.delete(id); return; }
    getWorker().postMessage({ id, type: 'render', spec, width, height });
  };

  const promise = new Promise<string>((resolve, reject) => {
    callbacks.set(id, ({ url, error }) => {
      if (cancelled) {
        if (url) { URL.revokeObjectURL(url); activeUrls.delete(url); }
        return;
      }
      if (error) reject(new Error(error));
      else resolve(url!);
    });

    if (_interacting) deferred.push(send);
    else send();
  });

  return {
    id,
    promise,
    cancel: () => {
      cancelled = true;
      callbacks.delete(id);
      const idx = deferred.indexOf(send);
      if (idx !== -1) deferred.splice(idx, 1);
    },
  };
}

export function finalizeWorkerChart(id: string): void {
  worker?.postMessage({ id, type: 'finalize' });
}

export function clearVegaWorker(): void {
  // Revoke all outstanding object URLs
  for (const url of activeUrls) URL.revokeObjectURL(url);
  activeUrls.clear();
  worker?.terminate();
  worker = null;
  callbacks.clear();
  deferred.length = 0;
  _interacting = false;
}
