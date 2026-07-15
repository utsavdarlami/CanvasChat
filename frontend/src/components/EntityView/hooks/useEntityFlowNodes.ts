/**
 * useEntityFlowNodes - Transforms graph data into React Flow nodes.
 *
 * Handles:
 * - Computing node dimensions
 * - Building React Flow Node[] array (positions are canvas coords, used directly)
 */
import { useMemo, useRef } from 'react';
import { Node } from '@xyflow/react';

import { getNodeDimensions } from '../entityNodeUtils';
import { ENTITY_FLOW_CONSTANTS } from '@/utils/constants';
import type { GraphNode, PartitionData, EntityRecord } from '@/types/graph';
import type { NodeDimensionsMap } from '../types';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const {
  FALLBACK_NODE_SPACING,
  DEFAULT_NODE_WIDTH,
  DEFAULT_NODE_HEIGHT,
} = ENTITY_FLOW_CONSTANTS;

const DEFAULT_DIMENSIONS = { width: DEFAULT_NODE_WIDTH, height: DEFAULT_NODE_HEIGHT };

// ---------------------------------------------------------------------------
// Pure helpers
// ---------------------------------------------------------------------------

/** Build a map of node ID to computed dimensions. */
function buildDimensionsMap(
  nodes: GraphNode[],
  currentEntities: EntityRecord[]
): NodeDimensionsMap {
  const map = new Map<string, { width: number; height: number }>();
  for (const node of nodes) {
    map.set(node.id, getNodeDimensions(node, currentEntities));
  }
  return map;
}

// ---------------------------------------------------------------------------
// Hook output type
// ---------------------------------------------------------------------------

export interface EntityFlowNodesResult {
  /** React Flow nodes mapped from graph state. Positions are raw — collision
   *  resolution is performed once in EntityFlowView on full reset, not here. */
  initialNodes: Node[];
  /** Map of node ID → dimensions */
  dimensionsMap: NodeDimensionsMap;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useEntityFlowNodes(
  graphNodes: GraphNode[],
  currentEntities: EntityRecord[] | null,
  _graphMetadata: { partitions?: Record<string, PartitionData[]> } | null,
  highlightedNodeIds?: Set<string>
): EntityFlowNodesResult {
  // Compute node dimensions
  const dimensionsMap = useMemo(
    () => buildDimensionsMap(graphNodes, currentEntities || []),
    [graphNodes, currentEntities]
  );

  // Stable per-node data cache: Reuse the same `data` object reference when
  // render-relevant fields have not changed.
  const prevNodeDataRef = useRef<Map<string, { entity: GraphNode; isAgentHighlighted: boolean; isAgentDimmed: boolean }>>(new Map());

  // Build React Flow nodes
  const initialNodes: Node[] = useMemo(() => {
    const hasHighlightSelection = !!highlightedNodeIds
      && graphNodes.some((node) => highlightedNodeIds.has(node.id));

    const nextDataCache = new Map<string, { entity: GraphNode; isAgentHighlighted: boolean; isAgentDimmed: boolean }>();

    const flowNodes = graphNodes.map((node, index) => {
      const nodeDims = dimensionsMap.get(node.id) || DEFAULT_DIMENSIONS;
      const position = { x: node.x ?? index * FALLBACK_NODE_SPACING, y: node.y ?? 0 };
      const isAgentHighlighted = highlightedNodeIds?.has(node.id) ?? false;
      const isAgentDimmed = hasHighlightSelection && !isAgentHighlighted;

      const prev = prevNodeDataRef.current.get(node.id);
      let data: { entity: GraphNode; isAgentHighlighted: boolean; isAgentDimmed: boolean };
      if (
        prev
        && prev.entity.id === node.id
        && prev.entity.displayId === node.displayId
        && prev.entity.display_name === node.display_name
        && prev.entity.type === node.type
        && prev.entity.value === node.value
        && prev.entity.nodeWidth === node.nodeWidth
        && prev.entity.nodeHeight === node.nodeHeight
        && prev.isAgentHighlighted === isAgentHighlighted
        && prev.isAgentDimmed === isAgentDimmed
      ) {
        data = prev;
      } else {
        data = { entity: node, isAgentHighlighted, isAgentDimmed };
      }
      nextDataCache.set(node.id, data);

      return {
        id: node.id,
        type: 'entity-node' as const,
        position,
        data,
        width: nodeDims.width,
        height: nodeDims.height,
      };
    });

    prevNodeDataRef.current = nextDataCache;

    return flowNodes;
  }, [graphNodes, dimensionsMap, highlightedNodeIds]);

  return {
    initialNodes,
    dimensionsMap,
  };
}
