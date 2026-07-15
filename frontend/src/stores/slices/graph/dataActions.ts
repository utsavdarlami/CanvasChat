import type { GraphData, GraphNode, EntityRecord } from '@/types/graph';
import { broadcastNodeUpdate } from '@/services/yjsService';
import {
  applyNodeUpdate,
} from './graphHelpers';
import type { GraphState } from '../graphSlice';
import type { AppSet } from './actionFactoryTypes';

type GraphDataActionKeys =
  | 'setGraphData'
  | 'setOriginalData'
  | 'updateNodePosition'
  | 'setNodePositionsBulk'
  | 'updateNodeDisplay'
  | 'removeNode'
  | 'claimLocalNodes'
  | 'updateNode'
  | 'addNode';

export function createGraphDataActions(set: AppSet): Pick<GraphState, GraphDataActionKeys> {
  return {
    setGraphData: (data: GraphData) => {
      set((state) => {
        // Assign displayId = localPeerId to every node loaded on this peer.
        // If not connected, use a sentinel value '__local__' so nodes are
        // still filterable once a connection is established.
        const displayId = state.session.localPeerId ?? '__local__';
        const nodesWithDisplay = data.nodes.map(n => ({
          ...n,
          entity_id: String(n.entity_id || n.id),
          id: String(n.entity_id || n.id),
          // Backend graph exports use snake_case (`display_id`); preserve it
          // so full-layout fallbacks don't collapse every node onto local display.
          displayId: (n.displayId ?? n.display_id) != null
            ? String(n.displayId ?? n.display_id)
            : displayId,
        }));

        return {
          graph: {
            ...state.graph,
            nodes: nodesWithDisplay,
            graphMetadata: data.graph || null,
            chatUpdatedNodeIds: new Set<string>(),
            highlightedNodeIds: new Set<string>(),
            highlightedNodeColors: {},
            selectedEntityIds: new Set<string>(),
            entityTags: {},
            groupOverlays: [],
            pendingCameraCommand: null,
            error: null,
          }
        };
      });
    },

    setOriginalData: (entities: EntityRecord[]) => {
      set((state) => ({
        graph: {
          ...state.graph,
          currentEntities: entities,
        }
      }));
    },

    updateNodePosition: (nodeId: string, x: number, y: number, fx?: number | null, fy?: number | null) => {
      set((state) => {
        const { updatedNodes } = applyNodeUpdate(
          state.graph.nodes,
          null,
          nodeId,
          (n) => ({ x, y, fx: fx !== undefined ? fx : n.fx, fy: fy !== undefined ? fy : n.fy })
        );

        return {
          graph: {
            ...state.graph,
            nodes: updatedNodes,
          }
        };
      });
    },

    setNodePositionsBulk: (positions) => {
      if (!positions.length) return;

      set((state) => {
        const updatesById = new Map(
          positions.map((position) => [position.id, position])
        );

        const updatedNodes = state.graph.nodes.map((node) => {
          const next = updatesById.get(node.id);
          if (!next) return node;

          return {
            ...node,
            x: next.x,
            y: next.y,
            fx: next.fx !== undefined ? next.fx : node.fx,
            fy: next.fy !== undefined ? next.fy : node.fy,
          };
        });

        return {
          graph: {
            ...state.graph,
            nodes: updatedNodes,
          }
        };
      });
    },

    updateNodeDisplay: (nodeId: string, displayId: string, x: number, y: number) => {
      set((state) => {
        const { updatedNodes } = applyNodeUpdate(
          state.graph.nodes,
          null,
          nodeId,
          () => ({ displayId, x, y })
        );

        return {
          graph: {
            ...state.graph,
            nodes: updatedNodes,
          }
        };
      });
    },

    removeNode: (nodeId: string) => {
      set((state) => {
        const nodeToRemove = state.graph.nodes.find(n => n.id === nodeId || n.entity_id === nodeId);
        if (!nodeToRemove) return state;

        const removedId = nodeToRemove.id;

        // Remove from nodes
        const updatedNodes = state.graph.nodes.filter(n => n.id !== removedId);

        // Update currentEntities
        const updatedEntities = state.graph.currentEntities
          ? state.graph.currentEntities.filter((e) => (e.id || e.entity_id) !== removedId && (e.entity_id || e.id) !== nodeId)
          : null;
        const removedEntityId = nodeToRemove.entity_id || nodeToRemove.id;
        const nextSelectedEntityIds = new Set(
          [...state.graph.selectedEntityIds].filter((id) => id !== removedEntityId && id !== removedId)
        );

        return {
          graph: {
            ...state.graph,
            nodes: updatedNodes,
            currentEntities: updatedEntities,
            selectedEntityIds: nextSelectedEntityIds,
          }
        };
      });
    },

    claimLocalNodes: (peerId: string) => {
      set((state) => ({
        graph: {
          ...state.graph,
          nodes: state.graph.nodes.map((node) =>
            node.displayId === '__local__' || node.displayId === 'local'
              ? { ...node, displayId: peerId }
              : node
          ),
        }
      }));
    },

    updateNode: (nodeId: string, updates: Partial<GraphNode>) => {
      set((state) => {
        const { updatedNodes, updatedEntities } = applyNodeUpdate(
          state.graph.nodes,
          state.graph.currentEntities,
          nodeId,
          () => updates
        );

        return {
          graph: {
            ...state.graph,
            nodes: updatedNodes,
            currentEntities: updatedEntities,
          }
        };
      });
      broadcastNodeUpdate(nodeId, updates);
    },

    addNode: (node: GraphNode) => {
      set((state) => ({
        graph: {
          ...state.graph,
          nodes: [...state.graph.nodes, node],
          currentEntities: state.graph.currentEntities
            ? [...state.graph.currentEntities, node]
            : [node],
        }
      }));
    },
  };
}
