import * as Y from 'yjs';
import { WebsocketProvider } from 'y-websocket';
import { useAppStore } from '@/stores/appStore';
import type { Peer } from '@/types/session';

/**
 * Persistent layout data stored in a Y.Map.
 * Any peer can write any peer's entry (e.g. Peer A repositions Peer B).
 */
export interface PeerLayoutEntry {
  x: number;
  y: number;
  width: number;
  height: number;
  tags: string[];
}

let peerLayouts: Y.Map<PeerLayoutEntry> | null = null;
let currentProvider: WebsocketProvider | null = null;

/**
 * Merge awareness presence data with persistent peerLayouts data,
 * then push the merged peer list into the Zustand session store.
 */
function rebuildAndSync(): void {
  if (!currentProvider || !peerLayouts) return;

  const states = currentProvider.awareness.getStates();
  const peers: Peer[] = [];

  states.forEach((state, clientID) => {
    if (!state?.peer) return;
    const awarenessData = state.peer as Omit<Peer, 'id'>;
    const peerId = `yjs-${clientID}`;

    // Layout fields come from the persistent peerLayouts map (source of truth).
    // Ephemeral fields (isIdentifying, camera, device info) come from awareness.
    const layout = peerLayouts!.get(peerId);

    peers.push({
      // Ephemeral presence data from awareness
      ...awarenessData,
      id: peerId,
      // Persistent layout data overrides awareness (if available)
      ...(layout ? {
        x: layout.x,
        y: layout.y,
        width: layout.width,
        height: layout.height,
        tags: layout.tags,
      } : {}),
    });
  });

  const session = useAppStore.getState().session;
  session.syncRoomState(peers);
}

export function setupAwareness(
  doc: Y.Doc,
  provider: WebsocketProvider,
  localPeerId: string,
  initialPeer: Omit<Peer, 'id'>,
): void {
  currentProvider = provider;
  peerLayouts = doc.getMap('peerLayouts');

  // --- Write initial layout to persistent map ---
  doc.transact(() => {
    peerLayouts!.set(localPeerId, {
      x: initialPeer.x,
      y: initialPeer.y,
      width: initialPeer.width,
      height: initialPeer.height,
      tags: initialPeer.tags,
    });
  }, 'local');

  // --- Awareness: set local ephemeral state ---
  // Only ephemeral/transient fields go here (isIdentifying, camera, device info).
  // Layout fields are authoritative from peerLayouts, but we include them in
  // awareness too for backward compatibility during the initial sync window.
  // Uses setLocalStateField to only touch the 'peer' key.
  provider.awareness.setLocalStateField('peer', initialPeer);

  // --- Awareness change handler ---
  // Detects peer join/leave and triggers a merged rebuild.
  // We skip events that only update the local client's own state (e.g. dragState,
  // camera) to avoid a ~20Hz rebuildAndSync cascade during node drags.
  provider.awareness.on('change', ({ added, updated, removed }: { added: number[]; updated: number[]; removed: number[] }) => {
    if (!currentProvider || !peerLayouts) return;

    // If the only change is an update to our own client, skip the rebuild —
    // our own awareness mutations (drag state, camera) don't affect the peer map.
    const localClientID = currentProvider.awareness.clientID;
    const isLocalOnly =
      added.length === 0 &&
      removed.length === 0 &&
      updated.length === 1 &&
      updated[0] === localClientID;
    if (isLocalOnly) return;

    // Clean up peerLayouts entries for peers that have left.
    const activeClientIds = new Set<string>();
    currentProvider.awareness.getStates().forEach((_state, clientID) => {
      activeClientIds.add(`yjs-${clientID}`);
    });

    // Delete layout entries for departed peers
    const layoutKeys = Array.from(peerLayouts.keys());
    for (const key of layoutKeys) {
      if (!activeClientIds.has(key)) {
        peerLayouts.doc!.transact(() => {
          peerLayouts!.delete(key);
        }, 'local');
      }
    }

    rebuildAndSync();
  });

  // --- peerLayouts observer: react to remote layout changes ---
  peerLayouts.observe((event, transaction) => {
    if (transaction.origin === 'local') return;

    // A remote peer changed layout data — rebuild the merged peers list.
    // If the local peer's position was changed by a remote peer (e.g. Peer A
    // dragged us in the mini-map), update localPeer in the Zustand store.
    if (event.keysChanged.has(localPeerId)) {
      const entry = peerLayouts!.get(localPeerId);
      if (entry) {
        const session = useAppStore.getState().session;
        const lp = session.localPeer;
        session.setLocalPeerConfig(entry.x, entry.y, entry.width, entry.height, entry.tags);

        // Re-broadcast ephemeral awareness so other observers see updated presence
        currentProvider!.awareness.setLocalStateField('peer',
          { ...lp, x: entry.x, y: entry.y, width: entry.width, height: entry.height, tags: entry.tags },
        );
      }
    }

    rebuildAndSync();
  });

  // Register broadcast callback so Zustand setLocalPeerConfig can push layout
  // changes to the persistent Y.Map without importing Yjs directly.
  const session = useAppStore.getState().session;
  session.setOnLayoutChange((x, y, width, height, tags) => {
    broadcastLayout(localPeerId, { x, y, width, height, tags });
  });
}

export function teardownAwareness(): void {
  // Unregister the layout change callback
  const session = useAppStore.getState().session;
  session.setOnLayoutChange(null);

  peerLayouts = null;
  currentProvider = null;
}

/**
 * Write layout data to the persistent peerLayouts Y.Map.
 * Uses 'local' transaction origin for echo suppression.
 */
function broadcastLayout(peerId: string, layout: PeerLayoutEntry): void {
  if (!peerLayouts || !peerLayouts.doc) return;
  peerLayouts.doc.transact(() => {
    peerLayouts!.set(peerId, layout);
  }, 'local');
}

/**
 * Update ephemeral presence data only (awareness).
 * Does NOT write to the persistent peerLayouts Y.Map.
 *
 * Use this for transient state changes like camera updates, isIdentifying
 * toggle, or any field that doesn't need to persist across reconnections.
 *
 * Layout changes (x, y, width, height, tags) are broadcast separately
 * through the sessionSlice _onLayoutChange → broadcastLayout path.
 *
 * Uses setLocalStateField to avoid replacing the full awareness state,
 * which reduces unnecessary awareness change events on remote peers.
 */
export function updatePeerPresence(peer: Omit<Peer, 'id'>): void {
  if (!currentProvider) return;
  currentProvider.awareness.setLocalStateField('peer', peer);
}

/**
 * @deprecated Use updatePeerPresence for ephemeral data. Layout is broadcast
 * automatically via sessionSlice._onLayoutChange → broadcastLayout.
 * This alias exists only for backward compatibility during migration.
 */
export const updatePeer = updatePeerPresence;

/**
 * Reposition any peer (local or remote) by writing to the persistent peerLayouts map.
 * Any peer can write any other peer's position — no RPC workaround needed.
 */
export function setPeerLayout(peerId: string, x: number, y: number): void {
  if (!peerLayouts || !peerLayouts.doc) return;

  // Preserve existing width/height/tags if the entry already exists
  const existing = peerLayouts.get(peerId);
  const layout: PeerLayoutEntry = {
    x,
    y,
    width: existing?.width ?? 1920,
    height: existing?.height ?? 1080,
    tags: existing?.tags ?? [],
  };

  peerLayouts.doc.transact(() => {
    peerLayouts!.set(peerId, layout);
  }, 'local');
}
