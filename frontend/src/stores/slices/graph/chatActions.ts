import type { LayoutDelta, GroupOverlay } from '@/types/api';
import {
  applyDeltaAddedNodes,
  applyDeltaRemovedNodes,
  applyDeltaUpdatedNodes,
} from './graphHelpers';
import type { GraphState, CameraCommand } from '../graphSlice';
import type { AppSet } from './actionFactoryTypes';
import { broadcastUIState } from '@/services/yjs/uiState';
import { getEntityId } from '@/utils/entityId';

const TAG_SEPARATOR_RE = /[_\s]+/g;

function normalizeTagLabel(raw: string): string {
  return raw.trim().replace(TAG_SEPARATOR_RE, ' ').trim();
}

function canonicalTagKey(raw: string): string {
  const normalized = normalizeTagLabel(raw);
  return normalized ? normalized.toLowerCase() : '';
}

function normalizeTagList(raw: unknown[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const item of raw) {
    if (typeof item !== 'string') continue;
    const normalized = normalizeTagLabel(item);
    const key = canonicalTagKey(normalized);
    if (!key || seen.has(key)) continue;
    seen.add(key);
    out.push(normalized);
  }
  return out;
}

function filterEntityTagsForGraph(
  tags: Record<string, string[]>,
  nodes: { entity_id?: string; id: string }[],
): Record<string, string[]> {
  const valid = new Set(nodes.map((n) => getEntityId(n)));
  const next: Record<string, string[]> = {};
  for (const [entityId, list] of Object.entries(tags)) {
    if (!valid.has(entityId) || !Array.isArray(list) || list.length === 0) continue;
    const cleaned = normalizeTagList(list);
    if (cleaned.length > 0) {
      next[entityId] = cleaned;
    }
  }
  return next;
}

function normalizeTagsFromServer(tags: Record<string, string[]>): Record<string, string[]> {
  const next: Record<string, string[]> = {};
  for (const [k, v] of Object.entries(tags)) {
    if (!Array.isArray(v)) continue;
    const cleaned = normalizeTagList(v);
    if (cleaned.length) next[k] = cleaned;
  }
  return next;
}

/** Matches backend tag canonicalization: trim + collapse spaces/underscores + case-insensitive dedupe. */
function normalizeTagStringsForAdd(raw: string[]): string[] {
  return normalizeTagList(raw);
}

function mergeEntityTagLists(existing: string[], incoming: string[]): string[] {
  return normalizeTagList([...existing, ...incoming]);
}

function sanitizeHighlightColors(
  nodeIds: string[],
  nodeColors: Record<string, string> | undefined,
): Record<string, string> {
  if (!nodeColors) return {};
  const validIds = new Set(nodeIds);
  const next: Record<string, string> = {};
  for (const [nodeId, color] of Object.entries(nodeColors)) {
    if (!validIds.has(nodeId) || typeof color !== 'string') continue;
    const trimmed = color.trim();
    if (!trimmed) continue;
    next[nodeId] = trimmed;
  }
  return next;
}

type GraphChatActionKeys =
  | 'applyLayoutDelta'
  | 'clearChatUpdatedNodeIds'
  | 'setHighlightedNodeIds'
  | 'clearHighlightedNodeIds'
  | 'setSelectedEntityIds'
  | 'clearSelectedEntityIds'
  | 'setEntityTags'
  | 'clearEntityTags'
  | 'addEntityTags'
  | 'removeEntityTags'
  | 'setGroupOverlays'
  | 'clearGroupOverlays'
  | 'setPendingCameraCommand';

export function createGraphChatActions(set: AppSet): Pick<GraphState, GraphChatActionKeys> {
  return {
    applyLayoutDelta: (delta: LayoutDelta) => {
      set((state) => {
        const displayId = state.session.localPeerId ?? '__local__';

        // 1. Update nodes
        const { newNodes: nodes1, affectedIds } = applyDeltaUpdatedNodes(
          delta, state.graph.nodes
        );

        // 2. Remove nodes
        const { newNodes: nodes2, newEntities: entities1 } = applyDeltaRemovedNodes(
          delta, nodes1, state.graph.currentEntities
        );

        // 3. Add nodes
        const { newNodes: nodes3, newEntities: entities2 } = applyDeltaAddedNodes(
          delta, nodes2, entities1, displayId, affectedIds
        );

        const validEntityIds = new Set(
          nodes3.map((node) => node.entity_id || node.id)
        );
        const nextSelectedEntityIds = new Set(
          [...state.graph.selectedEntityIds].filter((id) => validEntityIds.has(id))
        );

        const prunedTags = filterEntityTagsForGraph(state.graph.entityTags, nodes3);

        return {
          graph: {
            ...state.graph,
            nodes: nodes3,
            currentEntities: entities2 ?? state.graph.currentEntities,
            chatUpdatedNodeIds: affectedIds,
            selectedEntityIds: nextSelectedEntityIds,
            entityTags: prunedTags,
          }
        };
      });
    },

    clearChatUpdatedNodeIds: () => {
      set((state) => {
        if (state.graph.chatUpdatedNodeIds.size === 0) return state;
        return {
          graph: {
            ...state.graph,
            chatUpdatedNodeIds: new Set<string>(),
          }
        };
      });
    },

    setHighlightedNodeIds: (
      nodeIds: string[],
      nodeColors: Record<string, string> = {},
      source: 'local' | 'remote' = 'local',
    ) => {
      const normalizedNodeIds = Array.from(new Set(nodeIds.map((id) => String(id))));
      const sanitizedColors = sanitizeHighlightColors(normalizedNodeIds, nodeColors);
      set((state) => ({
        graph: {
          ...state.graph,
          highlightedNodeIds: new Set(normalizedNodeIds),
          highlightedNodeColors: sanitizedColors,
        }
      }));
      if (source === 'local') {
        broadcastUIState('highlightedNodeIds', normalizedNodeIds);
        broadcastUIState('highlightedNodeColors', JSON.stringify(sanitizedColors));
      }
    },

    clearHighlightedNodeIds: (source: 'local' | 'remote' = 'local') => {
      set((state) => {
        if (
          state.graph.highlightedNodeIds.size === 0
          && Object.keys(state.graph.highlightedNodeColors).length === 0
        ) {
          return state;
        }
        return {
          graph: {
            ...state.graph,
            highlightedNodeIds: new Set<string>(),
            highlightedNodeColors: {},
          }
        };
      });
      if (source === 'local') {
        broadcastUIState('highlightedNodeIds', []);
        broadcastUIState('highlightedNodeColors', JSON.stringify({}));
      }
    },

    setSelectedEntityIds: (entityIds: string[], source: 'local' | 'remote' = 'local') => {
      const normalized = Array.from(new Set(entityIds.map((id) => String(id))));
      set((state) => {
        const hasSameValues = normalized.length === state.graph.selectedEntityIds.size
          && normalized.every((id) => state.graph.selectedEntityIds.has(id));
        if (hasSameValues) return state;

        return {
          graph: {
            ...state.graph,
            selectedEntityIds: new Set(normalized),
          }
        };
      });
      if (source === 'local') {
        broadcastUIState('selectedEntityIds', normalized);
      }
    },

    clearSelectedEntityIds: (source: 'local' | 'remote' = 'local') => {
      set((state) => {
        if (state.graph.selectedEntityIds.size === 0) return state;
        return {
          graph: {
            ...state.graph,
            selectedEntityIds: new Set<string>(),
          }
        };
      });
      if (source === 'local') {
        broadcastUIState('selectedEntityIds', []);
      }
    },

    setEntityTags: (tags: Record<string, string[]>, source: 'local' | 'remote' = 'local') => {
      let broadcastPayload: string | null = null;
      set((state) => {
        const normalized = normalizeTagsFromServer(tags);
        const prev = state.graph.entityTags;
        if (JSON.stringify(normalized) === JSON.stringify(prev)) return state;
        broadcastPayload = JSON.stringify(normalized);
        return {
          graph: {
            ...state.graph,
            entityTags: normalized,
          },
        };
      });
      if (source === 'local' && broadcastPayload !== null) {
        broadcastUIState('entityTags', broadcastPayload);
      }
    },

    clearEntityTags: (source: 'local' | 'remote' = 'local') => {
      let cleared = false;
      set((state) => {
        if (Object.keys(state.graph.entityTags).length === 0) return state;
        cleared = true;
        return {
          graph: {
            ...state.graph,
            entityTags: {},
          },
        };
      });
      if (source === 'local' && cleared) {
        broadcastUIState('entityTags', JSON.stringify({}));
      }
    },

    addEntityTags: (
      entityId: string,
      tags: string[],
      source: 'local' | 'remote' = 'local',
    ) => {
      let broadcastPayload: string | null = null;
      set((state) => {
        const validIds = new Set(state.graph.nodes.map((n) => getEntityId(n)));
        if (!validIds.has(entityId)) return state;

        const incoming = normalizeTagStringsForAdd(tags);
        if (incoming.length === 0) return state;

        const existing = state.graph.entityTags[entityId] ?? [];
        const merged = mergeEntityTagLists(existing, incoming);
        const nextRecord = { ...state.graph.entityTags, [entityId]: merged };
        const normalized = normalizeTagsFromServer(nextRecord);
        const prev = state.graph.entityTags;
        if (JSON.stringify(normalized) === JSON.stringify(prev)) return state;
        broadcastPayload = JSON.stringify(normalized);
        return {
          graph: {
            ...state.graph,
            entityTags: normalized,
          },
        };
      });
      if (source === 'local' && broadcastPayload !== null) {
        broadcastUIState('entityTags', broadcastPayload);
      }
    },

    removeEntityTags: (
      entityId: string,
      tags: string[],
      source: 'local' | 'remote' = 'local',
    ) => {
      let broadcastPayload: string | null = null;
      set((state) => {
        const toRemove = new Set(
          tags
            .filter((t) => typeof t === 'string')
            .map((t) => canonicalTagKey(t))
            .filter((t) => t.length > 0),
        );
        if (toRemove.size === 0) return state;

        const existing = state.graph.entityTags[entityId];
        if (!Array.isArray(existing) || existing.length === 0) return state;

        const kept = existing.filter(
          (t) => typeof t === 'string' && !toRemove.has(canonicalTagKey(t)),
        );
        const nextRecord = { ...state.graph.entityTags };
        if (kept.length === 0) {
          delete nextRecord[entityId];
        } else {
          nextRecord[entityId] = kept;
        }
        const normalized = normalizeTagsFromServer(nextRecord);
        const prev = state.graph.entityTags;
        if (JSON.stringify(normalized) === JSON.stringify(prev)) return state;
        broadcastPayload = JSON.stringify(normalized);
        return {
          graph: {
            ...state.graph,
            entityTags: normalized,
          },
        };
      });
      if (source === 'local' && broadcastPayload !== null) {
        broadcastUIState('entityTags', broadcastPayload);
      }
    },

    setGroupOverlays: (overlays: GroupOverlay[], source: 'local' | 'remote' = 'local') => {
      set((state) => ({
        graph: {
          ...state.graph,
          groupOverlays: overlays,
        },
      }));
      if (source === 'local') {
        broadcastUIState('groupOverlays', JSON.stringify(overlays));
      }
    },

    clearGroupOverlays: (source: 'local' | 'remote' = 'local') => {
      set((state) => {
        if (state.graph.groupOverlays.length === 0) return state;
        return {
          graph: {
            ...state.graph,
            groupOverlays: [],
          },
        };
      });
      if (source === 'local') {
        broadcastUIState('groupOverlays', JSON.stringify([]));
      }
    },

    setPendingCameraCommand: (cmd: CameraCommand | null) => {
      set((state) => ({
        graph: {
          ...state.graph,
          pendingCameraCommand: cmd,
        },
      }));
    },
  };
}
