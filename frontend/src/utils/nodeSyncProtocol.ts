import type { NodeCoordinateSpace, NodeUpdate, NodeUpdateKind } from '@/types/session';

/**
 * Resolve event kind from the modern explicit field, with a legacy fallback
 * for old preview/mirror boolean payloads.
 */
export function resolveNodeUpdateKind(update: NodeUpdate): NodeUpdateKind {
  if (update.kind) return update.kind;
  if (update.mirror) return 'mirror';
  if (update.preview) return 'preview';
  return 'commit';
}

/**
 * Resolve coordinate space from explicit field, with sane defaults by event kind.
 */
export function resolveNodeUpdateSpace(
  update: NodeUpdate,
  kind: NodeUpdateKind
): NodeCoordinateSpace {
  if (update.space) return update.space;
  if (kind === 'preview' || kind === 'preview-clear' || kind === 'mirror' || kind === 'mirror-clear') {
    return 'screen';
  }
  return 'canvas';
}

/**
 * Convert canvas coordinates into screen coordinates for a specific viewport.
 */
export function canvasToScreen(
  pos: { x: number; y: number },
  viewport: { x: number; y: number; zoom: number }
): { x: number; y: number } {
  return {
    x: pos.x * viewport.zoom + viewport.x,
    y: pos.y * viewport.zoom + viewport.y,
  };
}

/**
 * Convert screen coordinates into canvas coordinates for a specific viewport.
 */
export function screenToCanvas(
  pos: { x: number; y: number },
  viewport: { x: number; y: number; zoom: number }
): { x: number; y: number } {
  return {
    x: (pos.x - viewport.x) / viewport.zoom,
    y: (pos.y - viewport.y) / viewport.zoom,
  };
}
