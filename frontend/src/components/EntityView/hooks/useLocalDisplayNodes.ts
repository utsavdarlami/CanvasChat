/**
 * useLocalDisplayNodes - Filters graph nodes to only those
 * belonging to the local display (peer).
 *
 * In multi-display mode, each peer only renders nodes whose displayId
 * matches its own localPeerId.
 *
 * In single-display mode (not connected), all nodes are shown.
 */
import { useMemo } from 'react';
import type { GraphNode } from '@/types/graph';

export interface LocalDisplayNodesResult {
  /** Nodes belonging to this display */
  localNodes: GraphNode[];
  /** Set of node IDs on this display (for quick lookup) */
  localNodeIds: Set<string>;
}

export function useLocalDisplayNodes(
  allNodes: GraphNode[],
  localPeerId: string | null,
  isConnected: boolean
): LocalDisplayNodesResult {
  // Determine the effective display ID for filtering
  const effectiveDisplayId = isConnected && localPeerId
    ? localPeerId
    : null; // null means show all (single display mode)

  const localNodes = useMemo(() => {
    if (!effectiveDisplayId) return allNodes;
    return allNodes.filter(
      n => n.displayId === effectiveDisplayId
    );
  }, [allNodes, effectiveDisplayId]);

  const localNodeIds = useMemo(
    () => new Set(localNodes.map(n => n.id)),
    [localNodes]
  );

  return { localNodes, localNodeIds };
}
