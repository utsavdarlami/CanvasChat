/**
 * Entity Helper Utilities
 *
 * Utilities for creating and managing entities in the graph.
 */

import type { GraphNode } from '@/types/graph';

/**
 * Generate a unique entity ID with timestamp and random component.
 */
function generateUniqueId(prefix: string): string {
  const timestamp = Date.now();
  const random = Math.random().toString(36).substr(2, 9);
  return `${prefix}-${timestamp}-${random}`;
}

/**
 * Calculate center position of existing nodes.
 * Returns default position if no nodes exist.
 */
function calculateCenterPosition(existingNodes: GraphNode[]): { x: number; y: number } {
  if (existingNodes.length === 0) {
    // Default to center of default viewport (abstract coordinates)
    return { x: 0.5, y: 0.5 };
  }
  
  // Calculate average position
  const sumX = existingNodes.reduce((sum, node) => sum + (node.x ?? 0), 0);
  const sumY = existingNodes.reduce((sum, node) => sum + (node.y ?? 0), 0);
  
  return {
    x: sumX / existingNodes.length,
    y: sumY / existingNodes.length,
  };
}

/**
 * Create a new write-up entity.
 *
 * @param existingNodes - Existing nodes in the graph (for position calculation)
 * @param title - Optional custom title (defaults to "New Write-up")
 * @returns A new GraphNode configured as a write-up entity
 */
export function createWriteupEntity(
  existingNodes: GraphNode[],
  title?: string
): GraphNode {
  const id = generateUniqueId('writeup');
  const name = title || 'New Write-up';
  const position = calculateCenterPosition(existingNodes);
  
  return {
    id,
    entity_id: id,
    name,
    display_name: name,
    x: position.x,
    y: position.y,
    type: 'writeup',
    value: '', // Empty content for user to fill
    // Additional metadata
    created_at: new Date().toISOString(),
    editable: true,
  };
}
