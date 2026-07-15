import { StateCreator } from 'zustand';
import type { AppState } from '../appStore';
import type { Peer } from '@/types/session';
import { computeManualDesktop, type VirtualDesktop } from '@/utils/peerArrangement';

/** Callback signature for broadcasting layout changes to the Yjs peerLayouts Y.Map. */
export type LayoutChangeCallback = (x: number, y: number, width: number, height: number, tags: string[]) => void;

export interface SessionState {
  peers: Map<string, Peer>;
  localPeer: Omit<Peer, 'id'>;
  localPeerId: string | null;
  isConnected: boolean;
  roomId: string | null;
  serverUrl: string;
  virtualDesktop: VirtualDesktop | null;
  // Actions
  setServerUrl: (url: string) => void;
  setRoomId: (id: string) => void;
  setConnected: (connected: boolean) => void;
  setLocalPeerConfig: (x: number, y: number, width: number, height: number, tags: string[]) => void;
  setLocalPeerCamera: (x: number, y: number, zoom: number) => void;
  updateLocalPeerDimensions: (width: number, height: number) => void;
  setIdentifying: (identifying: boolean) => void;
  syncRoomState: (peers: Peer[]) => void;
  addPeer: (peer: Peer) => void;
  updatePeer: (id: string, updates: Partial<Peer>) => void;
  removePeer: (id: string) => void;
  setLocalPeerId: (id: string) => void;
  recomputeLayout: () => void;
  /** Register/unregister a callback that broadcasts layout changes to Yjs peerLayouts. */
  setOnLayoutChange: (cb: LayoutChangeCallback | null) => void;
}

export interface SessionSlice {
  session: SessionState;
}

// Module-level callback holder (not stored in Zustand state to avoid serialization issues)
let _onLayoutChange: LayoutChangeCallback | null = null;

export const createSessionSlice: StateCreator<AppState, [], [], SessionSlice> = (set, get) => ({
  session: {
    peers: new Map(),
    virtualDesktop: null,
    localPeer: (() => {
      const isClient = typeof window !== 'undefined';
      const ua = isClient ? navigator.userAgent : '';
      const isMobile = /Mobi|Android/i.test(ua);
      const isTablet = /Tablet|iPad/i.test(ua);
      return {
        x: 0,
        y: 0,
        width: isClient ? window.innerWidth : 1920,
        height: isClient ? window.innerHeight : 1080,
        tags: [],
        isSelf: true,
        camera: { x: 0, y: 0, zoom: 1 },
        devicePixelRatio: isClient ? window.devicePixelRatio : 1,
        deviceType: (isMobile ? 'mobile' : isTablet ? 'tablet' : 'desktop') as 'mobile' | 'tablet' | 'desktop',
        orientation: isClient ? screen.orientation?.type : 'landscape-primary',
        touchEnabled: isClient ? ('ontouchstart' in window) : false,
      };
    })(),
    localPeerId: null,
    isConnected: false,
    roomId: null,
    serverUrl: (() => {
      const envUrl = import.meta.env.VITE_YJS_SERVER_URL;
      if (envUrl) return envUrl;
      if (envUrl !== undefined && typeof window !== 'undefined') {
        const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        return `${proto}//${window.location.host}/yjs`;
      }
      return 'ws://localhost:1234';
    })(),

    setServerUrl: (url: string) => {
      set((state) => ({
        session: { ...state.session, serverUrl: url },
      }));
    },

    setRoomId: (id: string) => {
      set((state) => ({
        session: { ...state.session, roomId: id },
      }));
    },

    setConnected: (connected: boolean) => {
      set((state) => ({
        session: { ...state.session, isConnected: connected },
      }));
    },

    setLocalPeerConfig: (x, y, width, height, tags) => {
      set((state) => {
        const localPeer = { ...state.session.localPeer, x, y, width, height, tags };
        // Also update the peers map entry so recomputeLayout sees the new position
        const peers = new Map(state.session.peers);
        const { localPeerId } = state.session;
        if (localPeerId) {
          const existing = peers.get(localPeerId);
          if (existing) {
            peers.set(localPeerId, { ...existing, x, y, width, height, tags });
          }
        }
        return {
          session: { ...state.session, localPeer, peers },
        };
      });
      get().session.recomputeLayout();
      // Broadcast layout change to persistent Yjs peerLayouts Y.Map
      if (_onLayoutChange) {
        _onLayoutChange(x, y, width, height, tags);
      }
    },

    setLocalPeerCamera: (x, y, zoom) => {
      set((state) => ({
        session: {
          ...state.session,
          localPeer: { ...state.session.localPeer, camera: { x, y, zoom } },
        },
      }));
    },
    
    updateLocalPeerDimensions: (width, height) => {
      let changed = false;
      set((state) => {
        if (state.session.localPeer.width === width && state.session.localPeer.height === height) {
          return state;
        }
        changed = true;
        const peers = new Map(state.session.peers);
        const { localPeerId } = state.session;
        if (localPeerId) {
          const existing = peers.get(localPeerId);
          if (existing) {
            peers.set(localPeerId, { ...existing, width, height });
          }
        }
        return {
          session: {
            ...state.session,
            peers,
            localPeer: { ...state.session.localPeer, width, height },
          },
        };
      });
      if (!changed) return;
      get().session.recomputeLayout();
      // Persist viewport size changes to shared peerLayouts so virtual desktop
      // and agent display context don't drift to stale dimensions.
      if (_onLayoutChange) {
        const { localPeer } = get().session;
        _onLayoutChange(localPeer.x, localPeer.y, localPeer.width, localPeer.height, localPeer.tags);
      }
    },
    
    // Helper to toggle identifying state
    setIdentifying: (identifying: boolean) => {
      set((state) => {
        const peers = new Map(state.session.peers);
        const { localPeerId } = state.session;
        
        // Optimistically update the peers map to ensure UI consistency immediately
        if (localPeerId) {
          const existing = peers.get(localPeerId);
          if (existing) {
            peers.set(localPeerId, { ...existing, isIdentifying: identifying });
          }
        }

        return {
          session: {
            ...state.session,
            peers,
            localPeer: { ...state.session.localPeer, isIdentifying: identifying },
          },
        };
      });
    },

    syncRoomState: (peers: Peer[]) => {
      set((state) => {
        const { localPeerId } = state.session;
        const map = new Map<string, Peer>();
        peers.forEach((p) => {
          const isSelf = p.id === localPeerId;
          map.set(p.id, { ...p, isSelf });
        });
        return { session: { ...state.session, peers: map } };
      });
      // Recompute after peers map is updated
      get().session.recomputeLayout();
    },

    addPeer: (peer: Peer) => {
      set((state) => {
        const peers = new Map(state.session.peers);
        const isSelf = state.session.localPeerId ? peer.id === state.session.localPeerId : false;
        peers.set(peer.id, { ...peer, isSelf });
        return { session: { ...state.session, peers } };
      });
      get().session.recomputeLayout();
    },

    updatePeer: (id: string, updates: Partial<Peer>) => {
      set((state) => {
        const peers = new Map(state.session.peers);
        const existing = peers.get(id);
        if (existing) {
          const isSelf = id === state.session.localPeerId;
          peers.set(id, { ...existing, ...updates, isSelf });
        }
        return { session: { ...state.session, peers } };
      });
      get().session.recomputeLayout();
    },

    removePeer: (id: string) => {
      set((state) => {
        const peers = new Map(state.session.peers);
        peers.delete(id);
        return { session: { ...state.session, peers } };
      });
      get().session.recomputeLayout();
    },

    setLocalPeerId: (id: string) => {
      set((state) => {
        // Store the id and add/update the local peer entry in the peers map
        const peers = new Map(state.session.peers);
        peers.set(id, { id, ...state.session.localPeer, isSelf: true });
        return { session: { ...state.session, localPeerId: id, peers } };
      });
    },

    recomputeLayout: () => {
      set((state) => {
        const { peers, localPeerId, localPeer } = state.session;
        // Use localPeer as the authoritative source for the local peer's
        // position/dimensions — the peers map entry can be stale if the
        // peerLayouts Y.Map hasn't round-tripped yet.
        const peerList = Array.from(peers.values()).map(p =>
          (localPeerId && p.id === localPeerId)
            ? { ...p, x: localPeer.x, y: localPeer.y, width: localPeer.width, height: localPeer.height, tags: localPeer.tags }
            : p
        );
        const desktop = computeManualDesktop(peerList);

        // Guard: if the computed desktop is structurally identical to the
        // current one, return unchanged state so Zustand skips notification.
        const prev = state.session.virtualDesktop;
        if (
          prev === desktop || // both null, or same reference
          (prev && desktop &&
            prev.totalWidth === desktop.totalWidth &&
            prev.totalHeight === desktop.totalHeight &&
            prev.peers.length === desktop.peers.length &&
            prev.peers.every((p, i) => {
              const d = desktop.peers[i];
              return p.id === d.id && p.x === d.x && p.y === d.y &&
                     p.width === d.width && p.height === d.height &&
                     p.tags.length === d.tags.length &&
                     p.tags.every((t, j) => t === d.tags[j]);
            }))
        ) {
          return state;
        }

        return { session: { ...state.session, virtualDesktop: desktop } };
      });
    },

    setOnLayoutChange: (cb: LayoutChangeCallback | null) => {
      _onLayoutChange = cb;
    },
  },
});
