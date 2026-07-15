/**
 * Geometry utilities for graph visualization
 * 
 * Provides convex hull calculation and related geometric operations
 * for region boundary computation.
 */

export interface Point {
  x: number;
  y: number;
}

/**
 * Compute a simple convex hull using angular sorting from centroid.
 * For small point sets typical in region visualization.
 * 
 * @param points - Array of 2D points to compute hull from
 * @returns Points sorted in angular order forming the hull boundary
 */
export function computeConvexHull(points: Point[]): Point[] {
  if (points.length < 3) return points;
  
  // Calculate centroid
  const centroid = {
    x: points.reduce((sum, p) => sum + p.x, 0) / points.length,
    y: points.reduce((sum, p) => sum + p.y, 0) / points.length,
  };
  
  // Sort points by angle from centroid
  const sorted = [...points].sort((a, b) => {
    const angleA = Math.atan2(a.y - centroid.y, a.x - centroid.x);
    const angleB = Math.atan2(b.y - centroid.y, b.x - centroid.x);
    return angleA - angleB;
  });
  
  return sorted;
}

/**
 * Expand a hull outward from its centroid by a fixed distance.
 * Creates visual margin around grouped nodes.
 * 
 * @param hull - Points forming the original hull boundary
 * @param expandDistance - Distance in pixels to expand outward
 * @returns Expanded hull points
 */
export function expandHull(hull: Point[], expandDistance: number): Point[] {
  if (hull.length === 0) return hull;
  
  // Calculate centroid
  const cx = hull.reduce((sum, p) => sum + p.x, 0) / hull.length;
  const cy = hull.reduce((sum, p) => sum + p.y, 0) / hull.length;
  
  return hull.map(point => {
    const dx = point.x - cx;
    const dy = point.y - cy;
    const dist = Math.sqrt(dx * dx + dy * dy);
    
    // Avoid division by zero for points at centroid
    if (dist === 0) return point;
    
    return {
      x: point.x + (dx / dist) * expandDistance,
      y: point.y + (dy / dist) * expandDistance,
    };
  });
}

/**
 * Convert points array to SVG path string.
 * Creates a closed polygon path.
 * 
 * @param points - Array of points forming the polygon
 * @returns SVG path data string (e.g., "M 0 0 L 10 10 L 20 0 Z")
 */
export function pointsToPath(points: Point[]): string {
  if (points.length < 3) return '';
  
  const pathParts = points.map((p, i) => 
    i === 0 ? `M ${p.x} ${p.y}` : `L ${p.x} ${p.y}`
  );
  pathParts.push('Z');
  
  return pathParts.join(' ');
}

/**
 * Calculate the centroid (geometric center) of a set of points.
 * 
 * @param points - Array of 2D points
 * @returns The centroid point
 */
export function calculateCentroid(points: Point[]): Point {
  if (points.length === 0) return { x: 0, y: 0 };
  
  return {
    x: points.reduce((sum, p) => sum + p.x, 0) / points.length,
    y: points.reduce((sum, p) => sum + p.y, 0) / points.length,
  };
}
