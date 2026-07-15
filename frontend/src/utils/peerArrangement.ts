import type { Peer } from '@/types/session';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ArrangedPeer {
  id: string;
  x: number;      // arranged X offset on the virtual desktop
  y: number;      // arranged Y offset (0 for top-aligned)
  width: number;
  height: number;
  tags: string[];
}

export interface VirtualDesktop {
  totalWidth: number;
  totalHeight: number;
  peers: ArrangedPeer[];
}

export type ExitDirection = 'left' | 'right' | 'top' | 'bottom';

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

/**
 * Find which peer's region contains a given point on the virtual desktop.
 */
export function findPeerAtPoint(
  desktop: VirtualDesktop,
  x: number,
  y: number,
): ArrangedPeer | null {
  for (const peer of desktop.peers) {
    if (
      x >= peer.x && x < peer.x + peer.width &&
      y >= peer.y && y < peer.y + peer.height
    ) {
      return peer;
    }
  }
  return null;
}

/**
 * Computes the virtual desktop bounds from manual peer positions.
 * Normalizes coordinates so the top-leftmost peer is at (0, 0),
 * ensuring the graph fits exactly within the bounding box.
 */
export function computeManualDesktop(peers: Array<Pick<Peer, 'id' | 'x' | 'y' | 'width' | 'height' | 'tags'>>): VirtualDesktop | null {
  if (peers.length < 2) return null;

  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;

  for (const peer of peers) {
    minX = Math.min(minX, peer.x);
    minY = Math.min(minY, peer.y);
    maxX = Math.max(maxX, peer.x + peer.width);
    maxY = Math.max(maxY, peer.y + peer.height);
  }

  const arranged: ArrangedPeer[] = peers.map(peer => ({
    id: peer.id,
    x: peer.x - minX,
    y: peer.y - minY,
    width: peer.width,
    height: peer.height,
    tags: peer.tags,
  }));

  return {
    totalWidth: maxX - minX,
    totalHeight: maxY - minY,
    peers: arranged,
  };
}

/**
 * Determine the exit direction when a node leaves the local viewport.
 * Returns null if the position is still within bounds.
 */
export function getExitDirection(
  x: number,
  y: number,
  viewportWidth: number,
  viewportHeight: number,
): ExitDirection | null {
  // Determine the most dominant exit direction
  const overflows = {
    left: x < 0 ? -x : 0,
    right: x > viewportWidth ? x - viewportWidth : 0,
    top: y < 0 ? -y : 0,
    bottom: y > viewportHeight ? y - viewportHeight : 0,
  };

  const maxOverflow = Math.max(overflows.left, overflows.right, overflows.top, overflows.bottom);
  if (maxOverflow <= 0) return null;

  if (overflows.left === maxOverflow) return 'left';
  if (overflows.right === maxOverflow) return 'right';
  if (overflows.top === maxOverflow) return 'top';
  return 'bottom';
}

/**
 * Find the adjacent peer in a given direction from the source peer
 * on the virtual desktop.
 *
 * Adjacency is determined by finding the nearest peer whose rectangle
 * overlaps on the perpendicular axis and is positioned in the correct
 * direction on the parallel axis.
 */
export function findAdjacentPeer(
  desktop: VirtualDesktop,
  sourcePeerId: string,
  direction: ExitDirection,
): ArrangedPeer | null {
  const source = desktop.peers.find(p => p.id === sourcePeerId);
  if (!source) return null;

  let bestPeer: ArrangedPeer | null = null;
  let bestDistance = Infinity;

  for (const candidate of desktop.peers) {
    if (candidate.id === sourcePeerId) continue;

    let distance: number;
    let hasPerpendicularOverlap: boolean;

    switch (direction) {
      case 'right':
        // Candidate must be to the right
        distance = candidate.x - (source.x + source.width);
        if (distance < 0) continue;
        // Must overlap vertically
        hasPerpendicularOverlap =
          candidate.y < source.y + source.height &&
          candidate.y + candidate.height > source.y;
        break;

      case 'left':
        // Candidate must be to the left
        distance = source.x - (candidate.x + candidate.width);
        if (distance < 0) continue;
        hasPerpendicularOverlap =
          candidate.y < source.y + source.height &&
          candidate.y + candidate.height > source.y;
        break;

      case 'bottom':
        // Candidate must be below
        distance = candidate.y - (source.y + source.height);
        if (distance < 0) continue;
        hasPerpendicularOverlap =
          candidate.x < source.x + source.width &&
          candidate.x + candidate.width > source.x;
        break;

      case 'top':
        // Candidate must be above
        distance = source.y - (candidate.y + candidate.height);
        if (distance < 0) continue;
        hasPerpendicularOverlap =
          candidate.x < source.x + source.width &&
          candidate.x + candidate.width > source.x;
        break;
    }

    if (hasPerpendicularOverlap && distance < bestDistance) {
      bestDistance = distance;
      bestPeer = candidate;
    }
  }

  return bestPeer;
}

/**
 * Map a node's position from one display's local coordinate space
 * to an adjacent display's local coordinate space.
 *
 * The node enters at the corresponding edge of the target display.
 * The perpendicular axis position is mapped proportionally, accounting
 * for relative vertical/horizontal alignment between the two peers
 * on the virtual desktop.
 */
export function mapPositionToAdjacentDisplay(
  nodeX: number,
  nodeY: number,
  sourcePeer: ArrangedPeer,
  targetPeer: ArrangedPeer,
  _direction: ExitDirection,
): { x: number; y: number } {
  // Convert to global (virtual desktop) coordinates, then to target-local.
  // Both axes are computed from the global position so the node tracks
  // the actual overshoot instead of being pinned to the entry edge.
  const globalX = sourcePeer.x + nodeX;
  const globalY = sourcePeer.y + nodeY;
  const localX = globalX - targetPeer.x;
  const localY = globalY - targetPeer.y;

  // Clamp to keep the node within the target's viewport bounds.
  // A small inset (20px) prevents the node from landing exactly on the
  // edge which can look glitchy and be hard to grab.
  const INSET = 20;
  return {
    x: clamp(localX, INSET, targetPeer.width - INSET),
    y: clamp(localY, INSET, targetPeer.height - INSET),
  };
}

function clamp(val: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, val));
}

// ---------------------------------------------------------------------------
// Drag mirror: boundary overlap detection
// ---------------------------------------------------------------------------

/**
 * Check if a node's bounding box (in source peer's local coordinates)
 * overlaps with a target peer's viewport on the virtual desktop.
 */
export function doesNodeOverlapPeer(
  nodeX: number,
  nodeY: number,
  nodeWidth: number,
  nodeHeight: number,
  sourcePeer: ArrangedPeer,
  targetPeer: ArrangedPeer,
): boolean {
  // Convert node bounds to global (virtual desktop) coordinates
  const globalLeft = sourcePeer.x + nodeX;
  const globalTop = sourcePeer.y + nodeY;
  const globalRight = globalLeft + nodeWidth;
  const globalBottom = globalTop + nodeHeight;

  // Check AABB overlap with target peer's rectangle
  return (
    globalRight > targetPeer.x &&
    globalLeft < targetPeer.x + targetPeer.width &&
    globalBottom > targetPeer.y &&
    globalTop < targetPeer.y + targetPeer.height
  );
}

/**
 * Find all peers on the virtual desktop whose viewport is overlapped
 * by a node's bounding box (in source peer's local coordinates).
 * Returns the overlapping peers along with the node's position mapped
 * to each peer's local coordinate space.
 */
export function findOverlappingPeers(
  desktop: VirtualDesktop,
  sourcePeerId: string,
  nodeX: number,
  nodeY: number,
  nodeWidth: number,
  nodeHeight: number,
): Array<{ peer: ArrangedPeer; localX: number; localY: number }> {
  const sourcePeer = desktop.peers.find(p => p.id === sourcePeerId);
  if (!sourcePeer) return [];

  const results: Array<{ peer: ArrangedPeer; localX: number; localY: number }> = [];

  for (const candidate of desktop.peers) {
    if (candidate.id === sourcePeerId) continue;

    if (doesNodeOverlapPeer(nodeX, nodeY, nodeWidth, nodeHeight, sourcePeer, candidate)) {
      // Map node position from source's local coords to candidate's local coords
      const globalX = sourcePeer.x + nodeX;
      const globalY = sourcePeer.y + nodeY;
      const localX = globalX - candidate.x;
      const localY = globalY - candidate.y;
      results.push({ peer: candidate, localX, localY });
    }
  }

  return results;
}
