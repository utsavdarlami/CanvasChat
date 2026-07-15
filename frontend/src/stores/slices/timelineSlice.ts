import { StateCreator } from 'zustand';
import type { AppState } from '../appStore';
import type { GraphNode } from '@/types/graph';
import { emitNodeDragBatch } from '@/services/yjsService';
import {
  broadcastTimelineEntry,
  clearRemoteTimeline,
  setOnRemoteEntry,
  setOnRemoteClear,
  getAllRemoteEntries,
  type TimelineEntry as YjsTimelineEntry
} from '@/services/yjs/timeline';

import { broadcastUIState } from '@/services/yjs/uiState';

export interface TimelineEntry {
  id: string;
  timestamp: number;
  label: string;
  source: 'drag' | 'chat';
  snapshot: GraphNode[];
}

export interface TimelineState {
  entries: TimelineEntry[];
  currentIndex: number;
  maxEntries: number;
  isTimelineOpen: boolean;
  lastSnapshotTime: number;
  isInitialized: boolean;

  initializeTimeline: () => void;
  recordSnapshot: (label: string, source: 'drag' | 'chat', nodes?: GraphNode[]) => void;
  jumpToEntry: (index: number) => void;
  setRemoteCurrentIndex: (index: number) => void;
  toggleTimeline: () => void;
  clearTimeline: () => void;
  getCurrentSnapshot: () => GraphNode[];
  mergeRemoteEntry: (entry: TimelineEntry) => void;
}

export interface TimelineSlice {
  timeline: TimelineState;
}

const SNAPSHOT_COOLDOWN_MS = 500;

function generateId(): string {
  return `timeline-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
}

function deepCloneNodes(nodes: GraphNode[]): GraphNode[] {
  return JSON.parse(JSON.stringify(nodes));
}

export const createTimelineSlice: StateCreator<AppState, [], [], TimelineSlice> = (set, get) => ({
  timeline: {
    entries: [],
    currentIndex: -1,
    maxEntries: 50,
    isTimelineOpen: false,
    lastSnapshotTime: 0,
    isInitialized: false,

    initializeTimeline: () => {
      if (get().timeline.isInitialized) return;

      setOnRemoteEntry((entry: YjsTimelineEntry) => {
        get().timeline.mergeRemoteEntry(entry as TimelineEntry);
      });

      setOnRemoteClear(() => {
        set((state) => ({
          timeline: {
            ...state.timeline,
            entries: [],
            currentIndex: -1,
            lastSnapshotTime: 0,
          },
        }));
      });

      const remoteEntries = getAllRemoteEntries();
      if (remoteEntries.length > 0) {
        set((state) => ({
          timeline: {
            ...state.timeline,
            entries: remoteEntries as TimelineEntry[],
            currentIndex: remoteEntries.length - 1,
            isInitialized: true,
          },
        }));
      } else {
        set((state) => ({
          timeline: {
            ...state.timeline,
            isInitialized: true,
          },
        }));
      }
    },

    recordSnapshot: (label: string, source: 'drag' | 'chat', nodes?: GraphNode[]) => {
      const state = get();
      const now = Date.now();

      if (now - state.timeline.lastSnapshotTime < SNAPSHOT_COOLDOWN_MS) {
        return;
      }

      const currentNodes = nodes ?? state.graph.nodes;
      if (!currentNodes || currentNodes.length === 0) {
        console.warn('[Timeline] No nodes to snapshot');
        return;
      }

      console.log('[Timeline] Recording snapshot:', label, source, 'nodes:', currentNodes.length);

      const newEntry: TimelineEntry = {
        id: generateId(),
        timestamp: now,
        label,
        source,
        snapshot: deepCloneNodes(currentNodes),
      };

      set((state) => {
        let entries = [...state.timeline.entries];
        let currentIndex = state.timeline.currentIndex;

        if (currentIndex >= 0 && currentIndex < entries.length - 1) {
          entries = entries.slice(0, currentIndex + 1);
        }

        entries.push(newEntry);

        if (entries.length > state.timeline.maxEntries) {
          entries = entries.slice(entries.length - state.timeline.maxEntries);
        }

        currentIndex = entries.length - 1;

        const shouldAutoOpen = state.timeline.entries.length === 0;

        return {
          timeline: {
            ...state.timeline,
            entries,
            currentIndex,
            lastSnapshotTime: now,
          },
          ui: shouldAutoOpen 
            ? { ...state.ui, leftSidebarTab: 'timeline' as const, leftSidebarOpen: true }
            : state.ui,
        };
      });

      broadcastTimelineEntry(newEntry);
    },

    jumpToEntry: (index: number) => {
      const state = get();
      const { entries } = state.timeline;

      if (index < 0 || index >= entries.length) {
        console.warn('[Timeline] Invalid jump index:', index);
        return;
      }

      const targetEntry = entries[index];
      const targetSnapshot = deepCloneNodes(targetEntry.snapshot);

      set((state) => ({
        timeline: {
          ...state.timeline,
          currentIndex: index,
        },
        graph: {
          ...state.graph,
          nodes: targetSnapshot,
          chatUpdatedNodeIds: new Set(targetSnapshot.map(n => n.id)),
        },
      }));

      const { session } = get();
      if (session.isConnected) {
        broadcastUIState('timelineIndex', index.toString());
        const localDisplayId = session.localPeerId ?? '__local__';
        
        const yjsUpdates = targetSnapshot.map((node) => ({
          id: node.id,
          x: node.x,
          y: node.y,
          displayId: node.displayId ?? localDisplayId,
          kind: 'commit' as const,
          space: 'canvas' as const,
        }));

        emitNodeDragBatch(yjsUpdates);
      }
    },

    setRemoteCurrentIndex: (index: number) => {
      const state = get();
      const { entries } = state.timeline;

      if (index < 0 || index >= entries.length) return;

      const targetEntry = entries[index];
      const targetSnapshot = deepCloneNodes(targetEntry.snapshot);

      set((state) => ({
        timeline: {
          ...state.timeline,
          currentIndex: index,
        },
        graph: {
          ...state.graph,
          nodes: targetSnapshot,
          chatUpdatedNodeIds: new Set(targetSnapshot.map(n => n.id)),
        },
      }));
    },

    toggleTimeline: () => {
      set((state) => ({
        timeline: {
          ...state.timeline,
          isTimelineOpen: !state.timeline.isTimelineOpen,
        },
      }));
    },

    clearTimeline: () => {
      set((state) => ({
        timeline: {
          ...state.timeline,
          entries: [],
          currentIndex: -1,
          lastSnapshotTime: 0,
        },
      }));

      clearRemoteTimeline();
    },

    getCurrentSnapshot: () => {
      const state = get();
      return deepCloneNodes(state.graph.nodes);
    },

    mergeRemoteEntry: (entry: TimelineEntry) => {
      const state = get();
      const existingIds = new Set(state.timeline.entries.map(e => e.id));
      
      if (existingIds.has(entry.id)) {
        return;
      }

      set((state) => {
        let entries = [...state.timeline.entries];
        entries.push(entry);
        entries = entries.sort((a, b) => a.timestamp - b.timestamp);

        if (entries.length > state.timeline.maxEntries) {
          entries = entries.slice(entries.length - state.timeline.maxEntries);
        }

        return {
          timeline: {
            ...state.timeline,
            entries,
            currentIndex: entries.length - 1,
          },
        };
      });
    },
  },
});
