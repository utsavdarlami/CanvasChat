/**
 * Random Distribution Utilities
 *
 * Generate random or grid-based positions for entities without coordinates.
 */

import { ENTITY_FLOW_CONSTANTS } from './constants';
import type { EntityRecord } from '@/types/graph';

const { NODE_SPACING, PADDING } = ENTITY_FLOW_CONSTANTS;

/** Options for grid distribution that account for actual node dimensions. */
export interface GridDistributionOptions {
  /** Width of each node (default: ENTITY_FLOW_CONSTANTS.DEFAULT_NODE_WIDTH) */
  nodeWidth?: number;
  /** Height of each node (default: ENTITY_FLOW_CONSTANTS.DEFAULT_NODE_HEIGHT) */
  nodeHeight?: number;
  /** Gap between nodes (default: NODE_SPACING) */
  gap?: number;
  /** Number of columns (auto-calculated from count if omitted) */
  cols?: number;
}

/**
 * Generate random positions for entities within viewport bounds.
 * Ensures minimum spacing between entities to reduce overlaps.
 */
export function generateRandomPositions(
  entities: EntityRecord[],
  viewportWidth: number = 2000,
  viewportHeight: number = 1500
): Array<{ x: number; y: number }> {
  const positions: Array<{ x: number; y: number }> = [];
  const minSpacing = NODE_SPACING * 1.5; // Extra spacing for random distribution
  
  // Calculate usable area (with padding)
  const minX = PADDING;
  const maxX = viewportWidth - PADDING;
  const minY = PADDING;
  const maxY = viewportHeight - PADDING;
  
  for (let i = 0; i < entities.length; i++) {
    let attempts = 0;
    let position: { x: number; y: number };
    let valid = false;
    
    // Try to find a position that doesn't overlap with existing ones
    while (!valid && attempts < 50) {
      position = {
        x: minX + Math.random() * (maxX - minX),
        y: minY + Math.random() * (maxY - minY),
      };
      
      // Check distance from all existing positions
      valid = positions.every(pos => {
        const dx = pos.x - position!.x;
        const dy = pos.y - position!.y;
        const distance = Math.sqrt(dx * dx + dy * dy);
        return distance >= minSpacing;
      });
      
      attempts++;
      
      if (valid || attempts >= 50) {
        positions.push(position!);
        break;
      }
    }
  }
  
  return positions;
}

/**
 * Distribute entities in a grid pattern.
 *
 * The viewport is computed *from* the node dimensions and count so that every
 * cell is guaranteed to be large enough to hold a node with comfortable gaps.
 * This ensures nodes are readable at 1:1 zoom regardless of dataset size.
 */
export function distributeEntitiesOnGrid(
  entities: EntityRecord[],
  options: GridDistributionOptions = {},
): Array<{ x: number; y: number }> {
  if (entities.length === 0) return [];

  const nodeW = options.nodeWidth ?? ENTITY_FLOW_CONSTANTS.DEFAULT_NODE_WIDTH;
  const nodeH = options.nodeHeight ?? ENTITY_FLOW_CONSTANTS.DEFAULT_NODE_HEIGHT;
  const gap = options.gap ?? NODE_SPACING;

  // Auto-calculate columns if not provided
  const numCols = options.cols ?? Math.ceil(Math.sqrt(entities.length));

  // Cell = node + gap on each side so nodes never touch
  const cellWidth = nodeW + gap;
  const cellHeight = nodeH + gap;

  const positions: Array<{ x: number; y: number }> = [];

  entities.forEach((_, index) => {
    const col = index % numCols;
    const row = Math.floor(index / numCols);

    // Position is the top-left of the node, with padding offset
    const x = PADDING + col * cellWidth;
    const y = PADDING + row * cellHeight;

    positions.push({ x, y });
  });

  return positions;
}

/**
 * Assign positions to entities, using existing coordinates if available,
 * or generating new ones using the specified strategy.
 */
export function assignPositions(
  entities: EntityRecord[],
  strategy: 'random' | 'grid' = 'grid',
  viewportWidth?: number,
  viewportHeight?: number,
  gridOptions?: GridDistributionOptions,
): EntityRecord[] {
  // Separate entities with and without coordinates
  const withCoords = entities.filter(e => e.x !== undefined && e.y !== undefined);
  const withoutCoords = entities.filter(e => e.x === undefined || e.y === undefined);

  if (withoutCoords.length === 0) {
    return entities; // All have coordinates already
  }

  // Generate positions for entities without coordinates
  const newPositions = strategy === 'random'
    ? generateRandomPositions(withoutCoords, viewportWidth, viewportHeight)
    : distributeEntitiesOnGrid(withoutCoords, gridOptions);

  // Assign new positions to entities without coordinates
  const updatedWithoutCoords = withoutCoords.map((entity, index) => ({
    ...entity,
    x: newPositions[index].x,
    y: newPositions[index].y,
  }));

  // Combine and return all entities
  return [...withCoords, ...updatedWithoutCoords];
}
