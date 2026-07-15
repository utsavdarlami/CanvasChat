import { StateCreator } from 'zustand';
import type { AppState } from '../appStore';
import type { GraphNode, GraphContext, EntityRecord } from '@/types/graph';
import type { LayoutDelta, GroupOverlay } from '@/types/api';
import { createGraphDataActions } from './graph/dataActions';
import { createGraphChatActions } from './graph/chatActions';
import { createGraphLifecycleActions } from './graph/lifecycleActions';

/** A single camera command consumed by EntityFlowView's unified camera effect. */
export type CameraCommand =
  | { kind: 'fitNodes'; nodeIds: string[] }
  | { kind: 'setViewport'; pan_x: number; pan_y: number; zoom: number }
  | { kind: 'fitBounds'; bounds: { x: number; y: number; width: number; height: number }; padding?: number };

export interface GraphState {
  // Data
  nodes: GraphNode[];
  graphMetadata: GraphContext | null;

  // Original uploaded data (for chat API)
  currentEntities: EntityRecord[] | null;

  // Set of node IDs whose positions were updated by the chat agent.
  // The merge effect in EntityFlowView checks this to pick up new positions
  // from initialNodes instead of preserving existing React Flow positions.
  chatUpdatedNodeIds: Set<string>;

  // One-shot node highlights requested by the chat agent (action: show_entity).
  highlightedNodeIds: Set<string>;
  highlightedNodeColors: Record<string, string>;
  // User-selected entities, preserved across displays for NL references like "move these".
  selectedEntityIds: Set<string>;
  /** Per-entity tags from the layout agent (synced across displays via Yjs). */
  entityTags: Record<string, string[]>;
  /** Group overlays with bounds and labels, emitted by grouping actions. */
  groupOverlays: GroupOverlay[];
  /** One-shot camera command consumed by EntityFlowView's single camera useEffect. */
  pendingCameraCommand: CameraCommand | null;

  // UI State
  isLoading: boolean;
  error: string | null;

  // Actions
  setGraphData: (data: import('@/types/graph').GraphData) => void;
  setOriginalData: (entities: EntityRecord[]) => void;
  updateNodePosition: (nodeId: string, x: number, y: number, fx?: number | null, fy?: number | null) => void;
  setNodePositionsBulk: (positions: Array<{ id: string; x: number; y: number; fx?: number | null; fy?: number | null }>) => void;
  updateNodeDisplay: (nodeId: string, displayId: string, x: number, y: number) => void;
  /** Apply incremental layout changes from the chat agent's layout_delta.
   *  Handles updated_nodes, added_nodes, removed_nodes. */
  applyLayoutDelta: (delta: LayoutDelta) => void;
  /** Clear the chatUpdatedNodeIds set (called after the merge effect consumes them). */
  clearChatUpdatedNodeIds: () => void;
  /** Set one-shot highlighted nodes from chat action.
   *  @param source - 'local' (default) broadcasts via Yjs; 'remote' skips broadcast. */
  setHighlightedNodeIds: (
    nodeIds: string[],
    nodeColors?: Record<string, string>,
    source?: 'local' | 'remote',
  ) => void;
  /** Clear one-shot highlighted nodes (typically on next user interaction).
   *  @param source - 'local' (default) broadcasts via Yjs; 'remote' skips broadcast. */
  clearHighlightedNodeIds: (source?: 'local' | 'remote') => void;
  /** Set selected entities from canvas interactions.
   *  @param source - 'local' (default) broadcasts via Yjs; 'remote' skips broadcast. */
  setSelectedEntityIds: (entityIds: string[], source?: 'local' | 'remote') => void;
  /** Clear selected entities.
   *  @param source - 'local' (default) broadcasts via Yjs; 'remote' skips broadcast. */
  clearSelectedEntityIds: (source?: 'local' | 'remote') => void;
  /** Replace entity tags from layout_delta / Yjs peer. */
  setEntityTags: (tags: Record<string, string[]>, source?: 'local' | 'remote') => void;
  /** Clear all entity tags (local clears broadcast). */
  clearEntityTags: (source?: 'local' | 'remote') => void;
  /** Append tags to one entity (local broadcasts via Yjs). Mirrors backend add tag semantics. */
  addEntityTags: (entityId: string, tags: string[], source?: 'local' | 'remote') => void;
  /** Remove tags from one entity by case-insensitive match (local broadcasts via Yjs). */
  removeEntityTags: (entityId: string, tags: string[], source?: 'local' | 'remote') => void;
  /** Set group overlays from a grouping action's layout_delta.
   *  @param source - 'local' (default) broadcasts via Yjs; 'remote' skips broadcast. */
  setGroupOverlays: (overlays: GroupOverlay[], source?: 'local' | 'remote') => void;
  /** Clear group overlays (on user interaction).
   *  @param source - 'local' (default) broadcasts via Yjs; 'remote' skips broadcast. */
  clearGroupOverlays: (source?: 'local' | 'remote') => void;
  /** Set a one-shot camera command for EntityFlowView to consume. */
  setPendingCameraCommand: (cmd: CameraCommand | null) => void;
  /** Remove a node by ID from nodes and currentEntities. */
  removeNode: (nodeId: string) => void;
  claimLocalNodes: (peerId: string) => void;
  updateNode: (nodeId: string, updates: Partial<GraphNode>) => void;
  addNode: (node: GraphNode) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  clearGraph: () => void;
}

export interface GraphSlice {
  graph: GraphState;
}

export const createGraphSlice: StateCreator<AppState, [], [], GraphSlice> = (set) => ({
  graph: {
    // Initial state
    nodes: [],
    graphMetadata: null,
    currentEntities: null,
    chatUpdatedNodeIds: new Set<string>(),
    highlightedNodeIds: new Set<string>(),
    highlightedNodeColors: {},
    selectedEntityIds: new Set<string>(),
    entityTags: {},
    groupOverlays: [],
    pendingCameraCommand: null,
    isLoading: false,
    error: null,

    // Actions
    ...createGraphDataActions(set),
    ...createGraphChatActions(set),
    ...createGraphLifecycleActions(set),
  }
});
