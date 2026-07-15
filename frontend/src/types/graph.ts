// Graph data types matching backend format

export interface EntityRecord {
  id?: string;
  entity_id?: string;
  name?: string;
  display_name?: string;
  x?: number;
  y?: number;
  displayId?: string;
  display_id?: string;
  type?: string;
  value?: unknown;
  created_at?: string;
  editable?: boolean;
  [key: string]: unknown;
}

export interface GraphNode extends EntityRecord {
  id: string;
  entity_id: string;
  name: string;
  x: number;
  y: number;
  fx?: number | null;  // Fixed x position (for dragging)
  fy?: number | null;  // Fixed y position (for dragging)
  displayId?: string;  // Which display/peer owns this node (multi-display)
  nodeWidth?: number;   // Override width from backend (resize/maximize)
  nodeHeight?: number;  // Override height from backend (resize/maximize)
  clusters?: ClusterInfo[];
  metadata?: Record<string, unknown>;
}

export interface ClusterInfo {
  cluster_id: string;
  cohesion_score?: number;
  metadata?: Record<string, unknown>;
}

export interface PartitionBounds {
  min_x: number;
  max_x: number;
  min_y: number;
  max_y: number;
}

export interface RegionPoint {
  x: number;
  y: number;
}

export interface Region {
  id: string;
  label: string;
  points: RegionPoint[];
  member_ids: string[];
}

export interface Partition {
  label: string;
  node_type: 'branch' | 'leaf';
  depth: number;
  bounds: PartitionBounds;
  axis?: 'X' | 'Y';                              // For branch nodes: split direction
  dimension?: string;                             // HIERARCHICAL_DETAIL, THEMATIC_PROXIMITY, etc.
  layout_type?: 'PACK' | 'FLOW' | 'CLUSTER' | 'RADIAL';  // For leaf nodes: internal arrangement hint
  entity_ids?: string[];                          // Entities contained in this partition
  num_entities?: number;
  regions?: Region[];                             // Euler diagram regions for RADIAL layouts
}

export interface GraphMetadata {
  approach?: string;
  layer_3_method?: string;
  llm_temperature?: number;
  layout_reasoning?: string;
  source?: string;
  entity_count?: number;
  metadata?: Record<string, unknown>;
}

export interface GraphData {
  nodes: GraphNode[];
  graph?: {
    metadata?: GraphMetadata;
    partitions?: Record<string, Partition[]>;
    metadata_extra?: Record<string, unknown>;
    layout_reasoning?: string;
  };
}

export type GraphContext = GraphData['graph'];

// Type aliases for convenience
export type Node = GraphNode;
export type PartitionData = Partition;
