import * as Y from 'yjs';
import { WebsocketProvider } from 'y-websocket';
import { useAppStore } from '@/stores/appStore';
import type { Peer } from '@/types/session';

import { setupAwareness, teardownAwareness } from './awareness';
import { setupNodePositions, teardownNodePositions } from './nodePositions';
import { setupGraphData, teardownGraphData, broadcastGraphData } from './graphData';
import { setupUIState, teardownUIState } from './uiState';
import { setupTimeline, teardownTimeline } from './timeline';

let doc: Y.Doc | null = null;
let provider: WebsocketProvider | null = null;
function getDefaultYjsUrl(): string {
  const envUrl = import.meta.env.VITE_YJS_SERVER_URL;

  // Explicitly set to a URL — use it
  if (envUrl) return envUrl;

  // Explicitly set but empty (production behind reverse proxy) — derive from current origin
  if (envUrl !== undefined) {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${proto}//${window.location.host}/yjs`;
  }

  // Not set at all — local dev
  return 'ws://localhost:1234';
}

let serverUrl: string = getDefaultYjsUrl();

/**
 * Store the server URL. Actual connection is deferred to joinRoom().
 * Auto-converts http(s):// to ws(s)://.
 */
export function connectSocket(url: string): void {
  serverUrl = url
    .replace(/^http:\/\//, 'ws://')
    .replace(/^https:\/\//, 'wss://');
}

/**
 * Tear down the Yjs doc, provider, and all observers. Resets module state.
 */
export function disconnectSocket(): void {
  if (provider) {
    provider.awareness.setLocalState(null);
    provider.disconnect();
    provider.destroy();
    provider = null;
  }
  if (doc) {
    doc.destroy();
    doc = null;
  }

  teardownAwareness();
  teardownNodePositions();
  teardownGraphData();
  teardownUIState();
  teardownTimeline();
  const { setConnected } = useAppStore.getState().session;
  setConnected(false);
}

/**
 * Join (or create) a room. Creates a Y.Doc, connects the WebsocketProvider,
 * sets awareness local state, and wires up all observers.
 */
export function joinRoom(roomId: string, peer: Omit<Peer, 'id'>): void {
  // Clean up any previous session
  if (provider) {
    disconnectSocket();
  }

  doc = new Y.Doc();
  const localPeerId = `yjs-${doc.clientID}`;

  // Connect
  provider = new WebsocketProvider(serverUrl, roomId, doc);

  // --- Connection status (TCP-level) ---
  provider.on('status', (event: { status: string }) => {
    if (event.status === 'disconnected') {
      useAppStore.getState().session.setConnected(false);
    }
  });

  // --- Sync event: fires when the Yjs doc has received the server's state ---
  // This is the safe point to decide whether to push or pull initial graph data.
  // Using 'sync' instead of 'status=connected' prevents race conditions where
  // two peers connect simultaneously and overwrite each other's data.
  provider.on('sync', (isSynced: boolean) => {
    if (!isSynced) return;

    const session = useAppStore.getState().session;
    session.setConnected(true);
    session.setLocalPeerId(localPeerId);

    // Check if the remote doc already has graph data (another peer was first)
    const remoteGraphNodes = doc!.getMap('sharedGraphNodes');
    const remoteHasData = remoteGraphNodes.size > 0;

    // Claim any nodes loaded before connection (displayId === '__local__' or 'local')
    const state = useAppStore.getState();
    const hasUnclaimedNodes = state.graph.nodes.some(n => n.displayId === '__local__' || n.displayId === 'local');

    if (hasUnclaimedNodes && !remoteHasData) {
      // We have local data and the room is empty — claim and broadcast
      state.graph.claimLocalNodes(localPeerId);
      const updatedGraph = useAppStore.getState().graph;
      broadcastGraphData({
        nodes: updatedGraph.nodes,
        graph: updatedGraph.graphMetadata ?? undefined,
      });
    } else if (hasUnclaimedNodes && remoteHasData) {
      // Room already has data from another peer — just claim our local IDs
      // without broadcasting (the remote data will arrive via observers)
      state.graph.claimLocalNodes(localPeerId);
    }

    useAppStore.getState().timeline.initializeTimeline();
  });

  setupAwareness(doc, provider, localPeerId, peer);
  setupNodePositions(doc, provider);
  setupGraphData(doc);
  setupUIState(doc);
  setupTimeline(doc);
}

/**
 * Check if the WebSocket provider is currently connected.
 */
export function isConnected(): boolean {
  return provider?.wsconnected ?? false;
}
