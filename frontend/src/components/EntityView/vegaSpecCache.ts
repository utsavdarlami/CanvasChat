/**
 * Vega chart caching and interaction-aware render scheduling.
 *
 * Four caches:
 *  1. Compiled spec cache: vega-lite spec → compiled vega spec (skips compile())
 *  2. Canvas snapshot cache: spec → PNG dataURL (instant placeholder for transfers)
 *  3. Vega data-load cache: URL → loaded text (dedupes repeated CSV/JSON fetches)
 *  4. Interaction-aware render queue: pauses chart rendering during user interaction
 */
import { compile } from 'vega-lite';
import type { TopLevelSpec } from 'vega-lite';
import { loader as createVegaLoader } from 'vega';
import type { Loader } from 'vega';
import { clearVegaWorker } from './vegaWorkerService';

const MAX_CACHE_SIZE = 64;
const MAX_DATA_LOAD_CACHE_SIZE = 8;

// ---------------------------------------------------------------------------
// 1. Compiled spec cache
// ---------------------------------------------------------------------------
interface CacheEntry {
  vegaSpec: Record<string, unknown>;
  accessedAt: number;
}

interface DataLoadCacheEntry {
  promise: Promise<string>;
  accessedAt: number;
}

const cache = new Map<string, CacheEntry>();
const dataLoadCache = new Map<string, DataLoadCacheEntry>();
let sharedVegaLoader: Loader | null = null;

// O(1) fast path: same object reference → skip JSON.stringify entirely.
// Spec object references are typically stable while panning/dragging.
let compiledByRef = new WeakMap<object, Record<string, unknown>>();

function specKey(spec: Record<string, unknown>): string {
  return JSON.stringify(spec);
}

function evictIfNeeded(): void {
  if (cache.size <= MAX_CACHE_SIZE) return;
  let oldestKey: string | null = null;
  let oldestTime = Infinity;
  for (const [key, entry] of cache) {
    if (entry.accessedAt < oldestTime) {
      oldestTime = entry.accessedAt;
      oldestKey = key;
    }
  }
  if (oldestKey) cache.delete(oldestKey);
}

/** Clear all vega caches, render queue, and terminate the render worker. */
export function clearAllCaches(): void {
  cache.clear();
  snapshotCache.clear();
  dataLoadCache.clear();
  compiledByRef = new WeakMap<object, Record<string, unknown>>();
  queue.length = 0;
  activeCount = 0;
  _interacting = false;
  clearVegaWorker();
}

export function getCompiledVegaSpec(
  vlSpec: Record<string, unknown>,
): Record<string, unknown> {
  const refHit = compiledByRef.get(vlSpec);
  if (refHit) return refHit;

  const key = specKey(vlSpec);
  const cached = cache.get(key);
  if (cached) {
    cached.accessedAt = Date.now();
    compiledByRef.set(vlSpec, cached.vegaSpec);
    return cached.vegaSpec;
  }

  // Inject autosize so the full chart (axes, labels, legends) fits within
  // the stated width/height — prevents clipping inside React Flow nodes.
  const specWithAutosize = {
    ...vlSpec,
    autosize: { type: 'fit', contains: 'padding' },
  };

  const result = compile(specWithAutosize as unknown as TopLevelSpec);
  const vegaSpec = result.spec as Record<string, unknown>;

  evictIfNeeded();
  cache.set(key, { vegaSpec, accessedAt: Date.now() });
  compiledByRef.set(vlSpec, vegaSpec);
  return vegaSpec;
}

// ---------------------------------------------------------------------------
// 2. Canvas snapshot cache
// ---------------------------------------------------------------------------
const snapshotCache = new Map<string, string>();

export function cacheCanvasSnapshot(
  vlSpec: Record<string, unknown>,
  dataUrl: string,
): void {
  const key = specKey(vlSpec);
  snapshotCache.set(key, dataUrl);
  if (snapshotCache.size > MAX_CACHE_SIZE) {
    const firstKey = snapshotCache.keys().next().value;
    if (firstKey) snapshotCache.delete(firstKey);
  }
}

export function getCanvasSnapshot(
  vlSpec: Record<string, unknown>,
): string | null {
  return snapshotCache.get(specKey(vlSpec)) ?? null;
}

// ---------------------------------------------------------------------------
// 3. Shared Vega data loader cache
// ---------------------------------------------------------------------------

function getOptionString(
  options: Parameters<Loader['load']>[1],
  key: string,
): string | undefined {
  if (!options || typeof options !== 'object') return undefined;
  const value = (options as Record<string, unknown>)[key];
  return typeof value === 'string' ? value : undefined;
}

function toAbsoluteLoadUri(
  uri: string,
  options: Parameters<Loader['load']>[1],
): string {
  const baseUrl = getOptionString(options, 'baseUrl') ?? getOptionString(options, 'baseURL');
  if (!baseUrl) return uri;
  try {
    return new URL(uri, baseUrl).toString();
  } catch {
    return `${baseUrl}::${uri}`;
  }
}

function dataLoadCacheKey(
  uri: string,
  options: Parameters<Loader['load']>[1],
): string {
  const context = getOptionString(options, 'context') ?? '';
  const response = getOptionString(options, 'response') ?? '';
  const mode = getOptionString(options, 'mode') ?? '';
  const target = getOptionString(options, 'target') ?? '';
  const defaultProtocol = getOptionString(options, 'defaultProtocol') ?? '';
  return `${context}|${response}|${mode}|${target}|${defaultProtocol}|${toAbsoluteLoadUri(uri, options)}`;
}

function evictDataLoadCacheIfNeeded(): void {
  if (dataLoadCache.size <= MAX_DATA_LOAD_CACHE_SIZE) return;
  let oldestKey: string | null = null;
  let oldestTime = Infinity;
  for (const [key, entry] of dataLoadCache) {
    if (entry.accessedAt < oldestTime) {
      oldestTime = entry.accessedAt;
      oldestKey = key;
    }
  }
  if (oldestKey) dataLoadCache.delete(oldestKey);
}

export function getSharedVegaLoader(): Loader {
  if (sharedVegaLoader) return sharedVegaLoader;

  const baseLoader = createVegaLoader();
  const load: Loader['load'] = (uri, options) => {
    const context = getOptionString(options, 'context');
    if (context && context !== 'dataflow') {
      return baseLoader.load(uri, options);
    }

    const key = dataLoadCacheKey(uri, options);
    const cached = dataLoadCache.get(key);
    if (cached) {
      cached.accessedAt = Date.now();
      return cached.promise;
    }

    const promise = baseLoader.load(uri, options).catch((error) => {
      dataLoadCache.delete(key);
      throw error;
    });
    dataLoadCache.set(key, { promise, accessedAt: Date.now() });
    evictDataLoadCacheIfNeeded();
    return promise;
  };

  sharedVegaLoader = {
    load,
    sanitize: (uri, options) => baseLoader.sanitize(uri, options),
    http: (uri, options) => baseLoader.http(uri, options),
    file: (filename) => baseLoader.file(filename),
  };
  return sharedVegaLoader;
}

// ---------------------------------------------------------------------------
// 4. Interaction-aware render queue
// ---------------------------------------------------------------------------

let _interacting = false;

/** Call when user starts panning/dragging. Pauses chart render queue. */
export function setUserInteracting(interacting: boolean): void {
  _interacting = interacting;
  // When interaction ends, kick the queue in case charts are waiting
  if (!interacting) flushQueue();
}

export function isUserInteracting(): boolean {
  return _interacting;
}

type QueueEntry = {
  resolve: () => void;
  cancelled: boolean;
};

const queue: QueueEntry[] = [];
let activeCount = 0;
const MAX_CONCURRENT = 1; // Only 1 embed at a time for maximum responsiveness

function flushQueue(): void {
  while (activeCount < MAX_CONCURRENT && queue.length > 0) {
    const entry = queue.shift()!;
    if (entry.cancelled) continue;
    activeCount++;
    entry.resolve();
    return; // Only start one — the next will be flushed after yield
  }
}

/**
 * Request a render slot. Returns a promise that resolves when it's this
 * chart's turn to render, and a cancel function.
 *
 * The queue is interaction-aware: it won't dequeue while the user is
 * panning or dragging. It uses requestIdleCallback (with setTimeout
 * fallback) so charts only render during browser idle time.
 */
export function requestRenderSlot(): { promise: Promise<void>; cancel: () => void } {
  const entry: QueueEntry = {
    resolve: () => {},
    cancelled: false,
  };

  const promise = new Promise<void>((resolve) => {
    entry.resolve = resolve;
  });

  if (!_interacting && activeCount < MAX_CONCURRENT) {
    activeCount++;
    entry.resolve();
  } else {
    queue.push(entry);
  }

  return {
    promise,
    cancel: () => {
      entry.cancelled = true;
    },
  };
}

/**
 * Release a render slot after chart finishes rendering.
 * Schedules the next chart via requestIdleCallback to yield the main thread.
 */
export function releaseRenderSlot(): void {
  activeCount = Math.max(0, activeCount - 1);
  scheduleFlush();
}

function scheduleFlush(): void {
  if (_interacting) return; // Will be flushed when interaction ends
  if (queue.length === 0) return;

  // Use requestIdleCallback so next chart waits for browser idle time
  if (typeof requestIdleCallback === 'function') {
    requestIdleCallback(() => {
      if (!_interacting) flushQueue();
    }, { timeout: 200 }); // Max 200ms wait before forcing
  } else {
    setTimeout(() => {
      if (!_interacting) flushQueue();
    }, 32); // ~2 frames fallback
  }
}

/** Yield main thread — allows browser to process input events between heavy steps. */
export function yieldToMain(): Promise<void> {
  return new Promise((resolve) => {
    // scheduler.yield() is ideal but not widely available yet; setTimeout(0) works
    setTimeout(resolve, 0);
  });
}
