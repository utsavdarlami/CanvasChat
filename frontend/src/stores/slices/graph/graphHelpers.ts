import { GraphNode, EntityRecord } from '@/types/graph';
import type { LayoutDelta } from '@/types/api';

/** Helper to apply an update to a specific node across data structures */
export function applyNodeUpdate(
  nodes: GraphNode[],
  currentEntities: EntityRecord[] | null,
  nodeId: string,
  updater: (node: GraphNode) => Partial<GraphNode>
) {
  const updatedNodes = nodes.map(node =>
    node.id === nodeId ? { ...node, ...updater(node) } : node
  );

  const updatedEntities = currentEntities
    ? currentEntities.map(e => (e.id === nodeId || e.entity_id === nodeId ? { ...e, ...updater(e as GraphNode) } : e))
    : null;

  return { updatedNodes, updatedEntities };
}

/** Reducer for updating nodes based on delta updates */
export function applyDeltaUpdatedNodes(
  delta: LayoutDelta,
  nodes: GraphNode[],
) {
  let newNodes = [...nodes];
  const affectedIds = new Set<string>();

  if (delta.updated_nodes?.length) {
    const updateMap = new Map(delta.updated_nodes.map(u => [u.entity_id, u]));

    newNodes = newNodes.map(node => {
      const update = updateMap.get(node.entity_id || node.id);
      if (!update) return node;
      affectedIds.add(node.id);
      return {
        ...node,
        x: update.x,
        y: update.y,
        ...(update.display_id ? { displayId: update.display_id } : {}),
        ...(update.width != null ? { nodeWidth: update.width } : {}),
        ...(update.height != null ? { nodeHeight: update.height } : {}),
      };
    });
  }

  return { newNodes, affectedIds };
}

/** Reducer for adding nodes based on delta updates */
export function applyDeltaAddedNodes(
  delta: LayoutDelta,
  nodes: GraphNode[],
  currentEntities: EntityRecord[] | null,
  localDisplayId: string,
  affectedIds: Set<string>
) {
  const newNodes = [...nodes];
  const newEntities = currentEntities ? [...currentEntities] : null;

  if (delta.added_nodes?.length) {
    for (const added of delta.added_nodes) {
      const newNode: GraphNode = {
        id: added.entity_id,
        entity_id: added.entity_id,
        name: added.name,
        display_name: added.display_name || added.name,
        x: added.x,
        y: added.y,
        displayId: added.display_id || localDisplayId,
        ...(added.width != null ? { nodeWidth: added.width } : {}),
        ...(added.height != null ? { nodeHeight: added.height } : {}),
        clusters: (added.clusters as unknown as GraphNode['clusters']) || [],
      };

      newNodes.push(newNode);
      if (newEntities) {
        newEntities.push({
          id: added.entity_id,
          entity_id: added.entity_id,
          name: added.name,
          display_name: added.display_name || added.name,
          x: added.x,
          y: added.y,
        });
      }
      affectedIds.add(newNode.id);
    }
  }

  return { newNodes, newEntities };
}

/** Reducer for removing nodes based on delta updates */
export function applyDeltaRemovedNodes(
  delta: LayoutDelta,
  nodes: GraphNode[],
  currentEntities: EntityRecord[] | null
) {
  let newNodes = [...nodes];
  let newEntities = currentEntities ? [...currentEntities] : null;

  if (delta.removed_nodes?.length) {
    const removedEntityIds = new Set(
      delta.removed_nodes.map((removed) =>
        typeof removed === 'string' ? removed : removed.entity_id
      )
    );

    newNodes = newNodes.filter(n => !removedEntityIds.has(n.entity_id || n.id));
    if (newEntities) {
      newEntities = newEntities.filter(e => !removedEntityIds.has(e.entity_id || e.id));
    }
  }

  return { newNodes, newEntities };
}
