import type { Node } from '@xyflow/react';
import type { CollisionAlgorithmOptions } from './types';

const ALIGNMENT_THRESHOLD = 10;

type InflatedBox = {
  x: number;
  y: number;
  width: number;
  height: number;
};

function inflatedBox(node: Node, margin: number): InflatedBox {
  const width = (node.width ?? node.measured?.width ?? 0) + margin * 2;
  const height = (node.height ?? node.measured?.height ?? 0) + margin * 2;
  return {
    x: node.position.x - margin,
    y: node.position.y - margin,
    width,
    height,
  };
}

/**
 * Asymmetric push: driver stays pinned, target absorbs the full minimum
 * translation along the smallest-overlap axis. Returns the new position
 * for `target`, or null if the overlap is below threshold.
 */
function pushTargetAwayFromDriver(
  driver: Node,
  target: Node,
  margin: number,
  overlapThreshold: number,
): { x: number; y: number } | null {
  const A = inflatedBox(driver, margin);
  const B = inflatedBox(target, margin);

  const centerAX = A.x + A.width * 0.5;
  const centerAY = A.y + A.height * 0.5;
  const centerBX = B.x + B.width * 0.5;
  const centerBY = B.y + B.height * 0.5;

  // Vector from driver to target: positive dx means target is to the right.
  const dx = centerBX - centerAX;
  const dy = centerBY - centerAY;

  const px = (A.width + B.width) * 0.5 - Math.abs(dx);
  const py = (A.height + B.height) * 0.5 - Math.abs(dy);

  if (px <= overlapThreshold || py <= overlapThreshold) return null;

  const isHorizontallyAligned = Math.abs(centerBY - centerAY) < ALIGNMENT_THRESHOLD;
  const isVerticallyAligned = Math.abs(centerBX - centerAX) < ALIGNMENT_THRESHOLD;

  let nextX = target.position.x;
  let nextY = target.position.y;

  if (isHorizontallyAligned) {
    nextX += (dx >= 0 ? 1 : -1) * px;
  } else if (isVerticallyAligned) {
    nextY += (dy >= 0 ? 1 : -1) * py;
  } else if (px < py) {
    nextX += (dx >= 0 ? 1 : -1) * px;
  } else {
    nextY += (dy >= 0 ? 1 : -1) * py;
  }

  return { x: nextX, y: nextY };
}

export interface ResolveByIntersectionsResult {
  resolved: Node[];
  adjustedIds: Set<string>;
}

/**
 * Driver-based collision resolution.
 *
 * Drivers (`movedIds`) are the nodes that just moved (drag, chat update,
 * cross-display arrival). They stay pinned. Any node intersecting a driver
 * is pushed asymmetrically and re-queued so cascading conflicts resolve.
 *
 * Complexity is bounded by the actual cascade: O(driverCount × n) for the
 * first pass, falling off as the queue drains. Compare with the all-pairs
 * `resolveCollisions` which is O(maxIterations × n²/2) regardless of how
 * many nodes actually moved.
 */
export function resolveByIntersections(
  workingNodes: Node[],
  movedIds: Set<string>,
  options: CollisionAlgorithmOptions,
): ResolveByIntersectionsResult {
  const { margin, maxIterations, overlapThreshold } = options;

  if (movedIds.size === 0 || workingNodes.length < 2) {
    return { resolved: workingNodes, adjustedIds: new Set() };
  }

  const byId = new Map<string, Node>();
  for (const node of workingNodes) {
    byId.set(node.id, node);
  }

  const queue: string[] = [...movedIds];
  const adjustedIds = new Set<string>();
  let pushes = 0;

  while (queue.length > 0 && pushes < maxIterations) {
    const driverId = queue.shift()!;
    const driver = byId.get(driverId);
    if (!driver) continue;

    const driverBox = inflatedBox(driver, margin);
    const driverCenterX = driverBox.x + driverBox.width * 0.5;
    const driverCenterY = driverBox.y + driverBox.height * 0.5;
    const driverHalfW = driverBox.width * 0.5;
    const driverHalfH = driverBox.height * 0.5;

    for (const candidate of byId.values()) {
      if (candidate.id === driverId) continue;

      const candBox = inflatedBox(candidate, margin);
      const candCenterX = candBox.x + candBox.width * 0.5;
      const candCenterY = candBox.y + candBox.height * 0.5;

      const dx = Math.abs(driverCenterX - candCenterX);
      const dy = Math.abs(driverCenterY - candCenterY);

      const overlapX = driverHalfW + candBox.width * 0.5 - dx;
      const overlapY = driverHalfH + candBox.height * 0.5 - dy;

      if (overlapX <= overlapThreshold || overlapY <= overlapThreshold) continue;

      const next = pushTargetAwayFromDriver(driver, candidate, margin, overlapThreshold);
      if (!next) continue;

      const updated: Node = { ...candidate, position: next };
      byId.set(candidate.id, updated);
      adjustedIds.add(candidate.id);
      queue.push(candidate.id);

      pushes++;
      if (pushes >= maxIterations) break;
    }
  }

  if (adjustedIds.size === 0) {
    return { resolved: workingNodes, adjustedIds };
  }

  const resolved: Node[] = new Array(workingNodes.length);
  for (let i = 0; i < workingNodes.length; i++) {
    const original = workingNodes[i];
    resolved[i] = adjustedIds.has(original.id)
      ? (byId.get(original.id) as Node)
      : original;
  }

  return { resolved, adjustedIds };
}
