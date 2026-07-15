// Entity types for detail panels

import type { GraphNode } from './graph';

export interface Entity extends GraphNode {
  // All GraphNode properties plus panel-specific data
}

export interface EntityPanelData {
  entityId: string;
  entity: Entity;
  isFloating: boolean;
  isMaximized: boolean;
  position?: {
    x: number;
    y: number;
    width: number;
    height: number;
  };
}

export interface EntityRelationship {
  targetId: string;
  targetName: string;
  relationshipType: string;
  direction: 'incoming' | 'outgoing';
  strength?: string;
  confidence?: number;
}
