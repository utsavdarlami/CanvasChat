// @ts-nocheck
// Web Worker: full Vega render pipeline off the main thread.
//
// Polyfills must be set BEFORE any Vega API calls.
// Vega does NOT access document/window at module-import time (it targets Node.js
// too), so static imports are fine — the polyfills below run synchronously at
// module evaluation, before the first message handler fires.

if (typeof document === 'undefined') {
  const noop = () => {};
  // OffscreenCanvas satisfies Vega's getContext('2d') call for font measurement.
  globalThis.document = {
    createElement: (tag) =>
      tag === 'canvas'
        ? new OffscreenCanvas(300, 150)
        : { style: {}, addEventListener: noop, removeEventListener: noop, appendChild: noop },
    createElementNS: () => ({ setAttribute: noop, appendChild: noop, setAttributeNS: noop }),
    body: { addEventListener: noop, removeEventListener: noop, style: {} },
  };
  globalThis.window = {
    addEventListener: noop,
    removeEventListener: noop,
    devicePixelRatio: 1,
  };
}

import { parse, View, Warn } from 'vega';

const views = new Map();

self.onmessage = async ({ data }) => {
  const { id, type } = data;
  try {
    if (type === 'render') {
      // Finalize any previous view for this slot
      views.get(id)?.finalize();

      const runtime = parse(data.spec);
      // renderer:'none' means no canvas is created yet — dataflow + data loading only.
      const view = new View(runtime, { logLevel: Warn, renderer: 'none', hover: false });
      view.width(data.width).height(data.height);

      // runAsync: loads CSV data, runs transforms/aggregations, builds scene graph
      await view.runAsync();
      views.set(id, view);

      // toCanvas() creates a fresh OffscreenCanvas (via our document.createElement
      // polyfill), renders the scene graph to it, and returns it.
      // This works for all chart types including scatter plots with 5000+ points
      // (bitmap vs SVG avoids huge DOM node counts).
      const canvas = await view.toCanvas(1);
      const blob = await (canvas).convertToBlob({ type: 'image/jpeg', quality: 0.88 });
      self.postMessage({ id, type: 'done', blob });

    } else if (type === 'finalize') {
      views.get(id)?.finalize();
      views.delete(id);
    }
  } catch (err) {
    self.postMessage({ id, type: 'error', message: String(err) });
  }
};
