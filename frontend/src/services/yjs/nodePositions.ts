import * as Y from 'yjs';
import type { WebsocketProvider } from 'y-websocket';
import { useAppStore } from '@/stores/appStore';
import type { NodeUpdate } from '@/types/session';
import { resolveNodeUpdateKind, resolveNodeUpdateSpace } from '@/utils/nodeSyncProtocol';

let nodePositions: Y.Map<{
  x: number;
  y: number;
  displayId: string;
  kind?: NodeUpdate['kind'];
  space?: NodeUpdate['space'];
  preview?: boolean;
  mirror?: boolean;
}> | null = null;

/** Provider reference — needed for awareness-based ephemeral drag events. */
let currentProvider: WebsocketProvider | null = null;

type NodeMovedCallback = (update: NodeUpdate) => void;
let nodeMovedCallback: NodeMovedCallback | null = null;

/** Callback for ephemeral (awareness-based) drag updates from remote peers. */
type EphemeralDragCallback = (update: NodeUpdate) => void;
let ephemeralDragCallback: EphemeralDragCallback | null = null;

/** Awareness change handler reference — stored so we can remove it on teardown. */
let awarenessChangeHandler: ((_changes: { added: number[]; updated: number[]; removed: number[] }) => void) | null = null;

interface EmitNodeDragOptions {
  /** Override Yjs transaction origin (default: 'local' to suppress local echo). */
  origin?: string;
}

const DEFAULT_NODE_DRAG_ORIGIN = 'local';

export function setNodeMovedCallback(cb: NodeMovedCallback | null): void {
  nodeMovedCallback = cb;
}

/**
 * Subscribe to ephemeral drag updates broadcast via Yjs Awareness.
 * These are high-frequency position updates during active drags.
 */
export function setEphemeralDragCallback(cb: EphemeralDragCallback | null): void {
  ephemeralDragCallback = cb;
}

export function setupNodePositions(doc: Y.Doc, provider: WebsocketProvider) {
  nodePositions = doc.getMap('nodePositions');
  currentProvider = provider;

  // --- nodePositions observer: fire callback for committed changes ---
  // By default, local writes use origin='local' and are suppressed.
  // Callers may opt into local echo by using a different origin.
  nodePositions.observe((event, transaction) => {
    if (transaction.origin === DEFAULT_NODE_DRAG_ORIGIN) return; // skip local echo

    event.keysChanged.forEach((nodeId) => {
      const val = nodePositions!.get(nodeId);
      if (!val) return;
      const update: NodeUpdate = {
        id: nodeId,
        x: val.x,
        y: val.y,
        displayId: val.displayId,
        kind: val.kind,
        space: val.space,
        preview: val.preview ?? false,
        mirror: val.mirror ?? false,
      };

      if (nodeMovedCallback) {
        nodeMovedCallback(update);
      } else {
        const { updateNodeDisplay } = useAppStore.getState().graph;
        updateNodeDisplay(update.id, update.displayId, update.x, update.y);
      }
    });
  });

  // --- Awareness change handler: fire ephemeralDragCallback for remote drags ---
  const awareness = provider.awareness;
  const localClientID = doc.clientID;

  awarenessChangeHandler = ({ added, updated, removed }: { added: number[]; updated: number[]; removed: number[] }) => {
    if (!ephemeralDragCallback) return;

    // Only process clients whose awareness state actually changed.
    const changedClients = [...added, ...updated];

    for (const clientID of changedClients) {
      // Skip our own awareness state
      if (clientID === localClientID) continue;

      const state = awareness.getStates().get(clientID);
      if (!state?.dragState) continue;

      // dragState is an array of NodeUpdate items (batch format).
      // Process each item individually so the receiver handles them
      // the same way as before.
      const ds = state.dragState;
      if (Array.isArray(ds)) {
        for (const item of ds) {
          ephemeralDragCallback(item as NodeUpdate);
        }
      } else {
        // Legacy single-object format (backward compat)
        ephemeralDragCallback(ds as NodeUpdate);
      }
    }

    // When a remote peer's awareness is removed (disconnect / drag cleared),
    // we don't need to do anything — the persistent Y.Map already has the
    // committed position, and clearEphemeralDrag() on the sender side means
    // the dragState field simply disappears.
    // However, if a peer disconnects mid-drag, we should clean up any
    // ephemeral ghosts/mirrors. We do this by treating removal as a
    // "no dragState" signal — the receiver side will naturally stop
    // receiving updates and the ghost will remain until the next persistent
    // commit or manual cleanup.
    void removed;
  };

  awareness.on('change', awarenessChangeHandler);
}

export function teardownNodePositions() {
  // Remove awareness listener before clearing refs
  if (currentProvider && awarenessChangeHandler) {
    currentProvider.awareness.off('change', awarenessChangeHandler);
    awarenessChangeHandler = null;
  }
  nodePositions = null;
  currentProvider = null;
}

/**
 * Clear all persistent node positions from the CRDT map.
 * This should be called when loading a completely new graph to prevent
 * orphaned positions from previous datasets.
 */
export function clearAllNodePositions(): void {
  if (!nodePositions || !nodePositions.doc) return;

  nodePositions.doc.transact(() => {
    nodePositions!.clear();
  }, DEFAULT_NODE_DRAG_ORIGIN);
}

/**
 * Return a snapshot of the Yjs nodePositions CRDT map.
 * Used by the DiagnosticPanel for debugging.
 */
export function getNodePositionsSnapshot(): Map<string, { x: number; y: number; displayId: string; kind?: NodeUpdate['kind']; space?: NodeUpdate['space']; preview?: boolean; mirror?: boolean }> {
  const snap = new Map<string, { x: number; y: number; displayId: string; kind?: NodeUpdate['kind']; space?: NodeUpdate['space']; preview?: boolean; mirror?: boolean }>();
  if (!nodePositions) return snap;
  nodePositions.forEach((val, key) => {
    snap.set(key, { ...val });
  });
  return snap;
}

/**
 * Broadcast a **committed** (persistent) node position change via the shared
 * CRDT map. This should only be used for one-shot events:
 *   - Final position on drag stop
 *   - Cross-display transfer commit (preview: false)
 *   - Cancellation broadcasts
 *
 * High-frequency drag updates should use `emitNodeDragEphemeral` instead.
 *
 * Uses Yjs transaction origin 'local' by default for local echo suppression.
 */
export function emitNodeDrag(update: NodeUpdate, options: EmitNodeDragOptions = {}): void {
  if (!nodePositions || !nodePositions.doc) return;
  const kind = resolveNodeUpdateKind(update);
  const space = resolveNodeUpdateSpace(update, kind);
  const origin = options.origin ?? DEFAULT_NODE_DRAG_ORIGIN;

  nodePositions.doc.transact(() => {
    nodePositions!.set(update.id, {
      x: update.x,
      y: update.y,
      displayId: update.displayId,
      kind,
      space,
      preview: update.preview ?? false,
      mirror: update.mirror ?? false,
    });
  }, origin);
}

/**
 * Broadcast multiple **committed** node position changes in a single Yjs
 * transaction.  Remote peers receive one observer callback for the entire
 * batch instead of N individual callbacks, dramatically reducing the
 * re-rendering cascade on the receiving side.
 *
 * Use this instead of calling `emitNodeDrag` in a loop.
 */
export function emitNodeDragBatch(updates: NodeUpdate[], options: EmitNodeDragOptions = {}): void {
  if (!nodePositions || !nodePositions.doc || !updates.length) return;
  const origin = options.origin ?? DEFAULT_NODE_DRAG_ORIGIN;

  nodePositions.doc.transact(() => {
    for (const update of updates) {
      const kind = resolveNodeUpdateKind(update);
      const space = resolveNodeUpdateSpace(update, kind);
      nodePositions!.set(update.id, {
        x: update.x,
        y: update.y,
        displayId: update.displayId,
        kind,
        space,
        preview: update.preview ?? false,
        mirror: update.mirror ?? false,
      });
    }
  }, origin);
}

/**
 * Broadcast **multiple** high-frequency ephemeral drag updates via Yjs
 * Awareness in a single awareness state change.
 *
 * Unlike emitNodeDragEphemeral (which can only carry one node), this sets
 * dragState to an array of items, allowing all dragged nodes to be
 * communicated to remote peers in one shot.
 */
export function emitNodeDragEphemeralBatch(updates: NodeUpdate[]): void {
  if (!currentProvider || !updates.length) return;

  const items = updates.map(update => {
    const kind = resolveNodeUpdateKind(update);
    const space = resolveNodeUpdateSpace(update, kind);
    return {
      id: update.id,
      x: update.x,
      y: update.y,
      displayId: update.displayId,
      kind,
      space,
      preview: update.preview ?? false,
      mirror: update.mirror ?? false,
    };
  });

  currentProvider.awareness.setLocalStateField('dragState', items);
}

/**
 * Broadcast a **high-frequency ephemeral** drag update via Yjs Awareness.
 *
 * Unlike `emitNodeDrag` (which writes to the persistent Y.Map and bloats
 * CRDT history), this sets the update as part of the local awareness state.
 * Awareness data is transient — it is NOT persisted, NOT part of the
 * document history, and is automatically cleaned up when the peer disconnects.
 *
 * Used for:
 *   - Normal within-display drag sync (line-by-line position during drag)
 *   - Cross-display live preview (preview: true)
 *   - Drag mirror / boundary overlap (mirror: true)
 *
 * Note: For multi-node drags, prefer emitNodeDragEphemeralBatch to avoid
 * each call overwriting the previous node's data.
 */
export function emitNodeDragEphemeral(update: NodeUpdate): void {
  emitNodeDragEphemeralBatch([update]);
}

/**
 * Clear the ephemeral drag state from awareness.
 * Should be called when a drag ends (on drag stop) so remote peers
 * stop receiving stale drag data.
 * Uses setLocalStateField(null) to remove only the dragState key.
 */
export function clearEphemeralDrag(): void {
  if (!currentProvider) return;
  currentProvider.awareness.setLocalStateField('dragState', null);
}
