import { memo, useEffect, useMemo, useRef, useState } from 'react';
import { parse, View } from 'vega';
import {
  getCompiledVegaSpec,
  cacheCanvasSnapshot,
  getCanvasSnapshot,
  getSharedVegaLoader,
  requestRenderSlot,
  releaseRenderSlot,
  yieldToMain,
} from './vegaSpecCache';
import { useSnapshotStore } from '../../stores/snapshotStore';

interface LazyVegaChartProps {
  spec: Record<string, unknown>;
  options?: Record<string, unknown>;
}

const OBSERVER_ROOT_MARGIN = '320px';
const FALLBACK_PLACEHOLDER_HEIGHT = 180;

function resolvePlaceholderHeight(spec: Record<string, unknown>): number {
  const directHeight = typeof spec.height === 'number' ? spec.height : null;
  const config =
    typeof spec.config === 'object' && spec.config !== null
      ? (spec.config as { height?: number })
      : null;
  const configHeight = typeof config?.height === 'number' ? config.height : null;
  return Math.max(directHeight ?? configHeight ?? FALLBACK_PLACEHOLDER_HEIGHT, 120);
}

function LazyVegaChartComponent({ spec }: LazyVegaChartProps) {
  const [visible, setVisible] = useState(false);
  const [rendered, setRendered] = useState(false);
  const isRecording = useSnapshotStore((state) => state.isRecording);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<HTMLDivElement | null>(null);
  const viewRef = useRef<View | null>(null);
  const placeholderHeight = useMemo(() => resolvePlaceholderHeight(spec), [spec]);

  // Pre-compile the spec (cached — usually instant after first compile)
  const compiledSpec = useMemo(() => {
    try {
      return getCompiledVegaSpec(spec);
    } catch {
      console.warn('[LazyVegaChart] Failed to pre-compile spec, falling back to raw spec');
      return spec;
    }
  }, [spec]);

  // Canvas snapshot for instant placeholder. Kept as state (not memo) so we
  // can refresh it the moment the current render completes — this puts the
  // <img> into the DOM on first render, which matters for rrweb: the live
  // canvas is blocked from recording, so the snapshot <img> is the only
  // thing replay can show for this chart.
  const [cachedSnapshot, setCachedSnapshot] = useState<string | null>(
    () => getCanvasSnapshot(spec),
  );
  useEffect(() => {
    setCachedSnapshot(getCanvasSnapshot(spec));
  }, [spec]);

  // --- Gate 1: IntersectionObserver visibility check ---
  useEffect(() => {
    if (visible) return;

    const element = containerRef.current;
    if (!element) return;

    if (typeof IntersectionObserver === 'undefined') {
      setVisible(true);
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { root: null, rootMargin: OBSERVER_ROOT_MARGIN, threshold: 0.01 },
    );

    observer.observe(element);
    return () => observer.disconnect();
  }, [visible]);

  // --- Gate 2: Interaction-aware queue → render with yield points ---
  // This effect only depends on `visible` and `compiledSpec`, NOT on render state.
  // The async render lifecycle runs to completion without re-triggering.
  useEffect(() => {
    if (!visible) return;

    let cancelled = false;
    let slotAcquired = false;
    const { promise: slotReady, cancel: cancelSlot } = requestRenderSlot();

    (async () => {
      await slotReady;
      slotAcquired = true;
      if (cancelled) {
        return;
      }

      try {
        // Step 1: vega.parse() — synchronous, ~30-150ms
        const runtime = parse(compiledSpec);

        // YIELD: let browser process any pending input events (pan, drag, click)
        await yieldToMain();
        if (cancelled) {
          return;
        }

        // Step 2: Create View + initialize — synchronous, ~10-30ms
        const target = chartRef.current;
        if (!target || cancelled) {
          return;
        }

        // Finalize any previous view before creating a new one
        viewRef.current?.finalize();

        const view = new View(runtime, {
          renderer: 'canvas',
          container: target,
          hover: true,
          loader: getSharedVegaLoader(),
        });
        viewRef.current = view;

        // YIELD: let browser breathe before expensive dataflow evaluation
        await yieldToMain();
        if (cancelled) {
          view.finalize();
          viewRef.current = null;
          return;
        }

        // Step 3: runAsync() — evaluates dataflow + renders canvas, ~50-200ms
        await view.runAsync();

        if (cancelled) {
          view.finalize();
          viewRef.current = null;
          return;
        }

        // Capture canvas snapshot for cross-display transfer cache and for
        // rrweb replay (see comment on `cachedSnapshot` state above).
        try {
          const canvas = target.querySelector('canvas');
          if (canvas) {
            const dataUrl = canvas.toDataURL('image/png');
            cacheCanvasSnapshot(spec, dataUrl);
            if (!cancelled) {
              setCachedSnapshot(dataUrl);
            }
          }
        } catch {
          // tainted canvas — ignore
        }

        setRendered(true);
      } catch (err) {
        console.error('[LazyVegaChart] Render failed:', err);
      } finally {
        if (slotAcquired) {
          releaseRenderSlot();
        }
      }
    })();

    return () => {
      cancelled = true;
      cancelSlot();
      // Finalize view on cleanup
      viewRef.current?.finalize();
      viewRef.current = null;
    };
  }, [visible, compiledSpec, spec]);

  // --- ResizeObserver: resize Vega View when container size changes ---
  useEffect(() => {
    const container = containerRef.current;
    const view = viewRef.current;
    if (!container || !view || !rendered) return;

    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      const { width, height } = entry.contentRect;
      if (width > 0 && height > 0) {
        view.width(width).height(height).runAsync();
      }
    });

    observer.observe(container);
    return () => observer.disconnect();
  }, [rendered]);

  const shouldShowSnapshot = isRecording && cachedSnapshot !== null;
  const showChart = visible && !shouldShowSnapshot;

  const renderPlaceholder = () => {
    // Recording mode: show only the snapshot image (single chart surface).
    if (shouldShowSnapshot && cachedSnapshot) {
      return (
        <div className="lazy-vega-chart__snapshot">
          <img
            src={cachedSnapshot}
            alt="Chart preview"
            style={{ width: '100%', height: 'auto', display: 'block' }}
          />
          {!rendered && (
            <div className="lazy-vega-chart__snapshot-overlay">Rendering...</div>
          )}
        </div>
      );
    }
    if (isRecording) return null;
    if (rendered) return null;
    return (
      <div
        className="lazy-vega-chart__placeholder"
        style={{ minHeight: placeholderHeight }}
      >
        {visible ? 'Chart queued...' : 'Chart loading...'}
      </div>
    );
  };

  return (
    <div ref={containerRef} className="lazy-vega-chart">
      {renderPlaceholder()}
      {/* Chart div is always in DOM so the ref is available when rendering starts.
          Hidden until visible so Vega has a laid-out container to render into.
          The `lazy-vega-chart__canvas` class is the rrweb blockClass target: the
          live canvas mutations stay out of the recording while the sibling
          snapshot <img> remains visible for replay. */}
      <div
        ref={chartRef}
        className="lazy-vega-chart__canvas"
        style={{ display: showChart ? 'block' : 'none' }}
      />
    </div>
  );
}

export const LazyVegaChart = memo(
  LazyVegaChartComponent,
  (prev, next) => prev.spec === next.spec && prev.options === next.options,
);
