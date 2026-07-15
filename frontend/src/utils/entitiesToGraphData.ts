/**
 * Entities-to-GraphData Converter
 *
 * Converts entities JSON to GraphData format for frontend-only visualization.
 */

import type { GraphData, GraphNode, EntityRecord } from '@/types/graph';
import { distributeEntitiesOnGrid } from './randomDistribution';
import { DEFAULT_TEXT_NODE_WIDTH, DEFAULT_TEXT_NODE_HEIGHT } from '@/components/EntityView/entityNodeUtils';

/**
 * Convert entities data to GraphData format.
 *
 * Handles entities-only mode (no backend call) by:
 * - Extracting entities from analyzed_entities array
 * - Validating required fields (id, name, type, value)
 * - Generating grid positions for all entities (no custom coordinates)
 * - Creating GraphNode objects with all entity fields preserved
 * - Returning GraphData ready for visualization
 *
 * @param entitiesData - Raw entities data from JSON file (Format 2: { analyzed_entities: [...] })
 * @returns GraphData ready for visualization
 */
export function convertEntitiesToGraphData(
  entitiesData: { analyzed_entities?: EntityRecord[] } | EntityRecord[],
): GraphData {
  // Extract entities array (Format 2: { analyzed_entities: [...] })
  const entities = Array.isArray(entitiesData)
    ? entitiesData
    : entitiesData.analyzed_entities || [];

  if (!Array.isArray(entities)) {
    throw new Error('Invalid entities data: analyzed_entities must be an array');
  }

  if (entities.length === 0) {
    console.warn('[entitiesToGraphData] No entities found in analyzed_entities');
    return {
      nodes: [],
      graph: {
        metadata: {
          approach: 'frontend_only',
          source: 'entities_only_upload'
        }
      }
    };
  }

  // Generate grid positions sized to actual node dimensions so nodes are
  // readable at 1:1 zoom regardless of dataset size.
  const positions = distributeEntitiesOnGrid(entities, {
    nodeWidth: DEFAULT_TEXT_NODE_WIDTH,
    nodeHeight: DEFAULT_TEXT_NODE_HEIGHT,
  });

  // Convert to GraphNode format
  const nodes: GraphNode[] = entities.map((entity, index) => {
    // Preserve all entity fields for proper rendering
    const node: GraphNode = {
      ...entity,
      id: entity.id || `entity-${index}`,
      entity_id: entity.id || `entity-${index}`,
      name: entity.name || entity.display_name || `Entity ${index}`,
      display_name: entity.display_name || entity.name || `Entity ${index}`,
      x: positions[index].x,
      y: positions[index].y,
    };

    return node;
  });

  return {
    nodes,
    graph: {
      metadata: {
        approach: 'frontend_only',
        source: 'entities_only_upload',
        entity_count: nodes.length,
      }
    }
  };
}

/**
 * Validate entities data structure
 */
export function validateEntitiesData(
  data: { analyzed_entities?: EntityRecord[] } | EntityRecord[] | null
): { valid: boolean; error?: string } {
  if (!data) {
    return { valid: false, error: 'No data provided' };
  }

  if (Array.isArray(data)) {
    if (data.length === 0) {
      return { valid: false, error: 'Empty entities array' };
    }
  } else {
    if (!data.analyzed_entities) {
      return { valid: false, error: 'Missing "analyzed_entities" field' };
    }

    if (!Array.isArray(data.analyzed_entities)) {
      return { valid: false, error: '"analyzed_entities" must be an array' };
    }

    if (data.analyzed_entities.length === 0) {
      return { valid: false, error: 'Empty "analyzed_entities" array' };
    }
  }

  // Check that entities have required fields
  const invalidEntities: string[] = [];

  const entities = Array.isArray(data) ? data : data.analyzed_entities || [];

  entities.forEach((entity, index) => {
    const issues: string[] = [];

    if (!entity.id && !entity.name) {
      issues.push('id or name');
    }

    if (!entity.type) {
      issues.push('type');
    }

    if (entity.value === undefined || entity.value === null) {
      issues.push('value');
    }

    if (issues.length > 0) {
      invalidEntities.push(`Entity at index ${index} missing: ${issues.join(', ')}`);
    }
  });

  if (invalidEntities.length > 0) {
    return {
      valid: false,
      error: `Invalid entities:\n${invalidEntities.join('\n')}\n\nRequired fields: id (or name), type, value`
    };
  }

  return { valid: true };
}
