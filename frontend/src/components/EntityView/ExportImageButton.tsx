/**
 * ExportImageButton - PNG export of the VISIBLE Entity View canvas.
 *
 * Renders only a transient toast (via a portal so it isn't captured); the
 * action is triggered by the Ctrl+Shift+Y keyboard shortcut. It rasterizes the
 * bounded `.react-flow` pane at its current pan/zoom and size — i.e. exactly
 * what is on screen — to a PNG via html-to-image. UI chrome (controls/panels)
 * is excluded.
 *
 * PNG is exported at EXPORT_SCALE× device resolution: crisp when zoomed in,
 * but a small fraction of the size of an SVG export (which would inline all
 * computed styles + fonts as text, easily tens of MB). Raise EXPORT_SCALE for
 * sharper output at the cost of file size.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useReactFlow } from '@xyflow/react';
import { toPng } from 'html-to-image';

// Output resolution multiplier. 2 = "retina" sharpness; 3 for more zoom detail.
const EXPORT_SCALE = 3;
const TOAST_MS = 2800;

function downloadDataUrl(filename: string, dataUrl: string): void {
  const a = document.createElement('a');
  a.href = dataUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

// Exclude React Flow UI chrome from the capture; keep nodes/background/overlays.
function shouldInclude(node: HTMLElement): boolean {
  const cls = node.classList;
  if (!cls) return true;
  return !(
    cls.contains('react-flow__controls') ||
    cls.contains('react-flow__attribution') ||
    cls.contains('react-flow__minimap') ||
    cls.contains('react-flow__panel')
  );
}

export const ExportImageButton: React.FC = () => {
  const { getNodes } = useReactFlow();
  const [toast, setToast] = useState<{ text: string; ok: boolean } | null>(null);
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showToast = useCallback((text: string, ok: boolean) => {
    setToast({ text, ok });
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    toastTimerRef.current = setTimeout(() => setToast(null), TOAST_MS);
  }, []);

  const handleExport = useCallback(async () => {
    if (getNodes().length === 0) {
      console.warn('[ExportImageButton] No nodes to export');
      showToast('Nothing to export — no nodes on this display', false);
      return;
    }

    // The bounded, viewport-sized pane. Its `overflow: hidden` clips to exactly
    // the visible area, and the inner viewport keeps its live pan/zoom.
    const paneEl = document.querySelector<HTMLElement>('.react-flow');
    if (!paneEl) {
      showToast('Canvas not ready', false);
      return;
    }

    const width = paneEl.clientWidth;
    const height = paneEl.clientHeight;
    if (width <= 0 || height <= 0) {
      showToast('Canvas has no visible area', false);
      return;
    }

    showToast('Capturing…', true);
    try {
      const dataUrl = await toPng(paneEl, {
        backgroundColor: '#ffffff',
        width,
        height,
        pixelRatio: EXPORT_SCALE,
        filter: shouldInclude,
      });

      const date = new Date().toISOString().replace(/[:.]/g, '-');
      const filename = `entity-view-${date}.png`;
      downloadDataUrl(filename, dataUrl);
      console.log('[ExportImageButton] Exported', filename);
      showToast(`Saved ${filename}`, true);
    } catch (err) {
      console.error('[ExportImageButton] SVG export failed:', err);
      showToast(`Export failed: ${(err as Error).message}`, false);
    }
  }, [getNodes, showToast]);

  // Keyboard shortcut: Ctrl+Shift+Y captures the visible canvas as PNG.
  // Capture phase + window target so nothing intercepts it first.
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const isY = e.code === 'KeyY' || e.key === 'y' || e.key === 'Y';
      if (e.ctrlKey && e.shiftKey && isY) {
        console.log('[ExportImageButton] Ctrl+Shift+Y captured → exporting PNG');
        e.preventDefault();
        e.stopPropagation();
        void handleExport();
      }
    };
    window.addEventListener('keydown', onKeyDown, true);
    return () => window.removeEventListener('keydown', onKeyDown, true);
  }, [handleExport]);

  // Cleanup toast timer on unmount.
  useEffect(() => () => {
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
  }, []);

  if (!toast) return null;

  // Portal to body so the toast is not a descendant of `.react-flow` and thus
  // never appears in the captured image.
  return createPortal(
    <div
      style={{
        position: 'fixed',
        bottom: 16,
        right: 16,
        zIndex: 9999,
        padding: '8px 14px',
        fontSize: 13,
        fontWeight: 500,
        color: '#fff',
        background: toast.ok ? 'rgba(22,163,74,0.95)' : 'rgba(220,38,38,0.95)',
        borderRadius: 8,
        boxShadow: '0 2px 8px rgba(0,0,0,0.25)',
        pointerEvents: 'none',
        maxWidth: 360,
      }}
    >
      {toast.text}
    </div>,
    document.body,
  );
};
