export const COLOR_SCHEMES = {
  CATEGORY10: ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
               "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"],
  SET2: ["#66c2a5", "#fc8d62", "#8da0cb", "#e78ac3", "#a6d854",
         "#ffd92f", "#e5c494", "#b3b3b3"]
} as const;

/**
 * Constants for EntityFlowView position scaling and layout
 */
export const ENTITY_FLOW_CONSTANTS = {
  /** Padding around the viewport edges */
  PADDING: 100,
  /** Gap between adjacent nodes */
  NODE_SPACING: 50,
  /** Fallback spacing when no dimensions available */
  FALLBACK_NODE_SPACING: 500,
  /** Minimum viewport dimensions */
  MIN_VIEWPORT_WIDTH: 1000,
  MIN_VIEWPORT_HEIGHT: 800,
  /** Default viewport for empty graphs */
  DEFAULT_VIEWPORT_WIDTH: 2000,
  DEFAULT_VIEWPORT_HEIGHT: 1500,
  /** Default node dimensions when not computed */
  DEFAULT_NODE_WIDTH: 400,
  DEFAULT_NODE_HEIGHT: 300,
  /** Tolerance for grouping similar coordinate values */
  POSITION_TOLERANCE: 0.5
} as const;

/**
 * Collision detection configuration
 */
export const COLLISION_CONFIG = {
  /** Space between nodes after resolution */
  margin: 20,
  /** Maximum resolution passes */
  maxIterations: 50,
  /** Minimum overlap to trigger resolution */
  overlapThreshold: 0.5
} as const;

/**
 * Edge highlight style when node is selected
 */
export const EDGE_HIGHLIGHT_STYLE = {
  stroke: '#2563eb',
  strokeWidth: 4,
  strokeOpacity: 1,
} as const;
