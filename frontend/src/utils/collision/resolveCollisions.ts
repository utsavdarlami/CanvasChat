import type { Node } from '@xyflow/react';
import type { CollisionAlgorithmOptions, Box } from './types';

function getBoxesFromNodes(nodes: Node[], margin: number = 0): Box[] {
  const boxes: Box[] = new Array(nodes.length);

  for (let i = 0; i < nodes.length; i++) {
    const node = nodes[i];
    boxes[i] = {
      x: node.position.x - margin,
      y: node.position.y - margin,
      width: (node.width ?? node.measured?.width ?? 0) + margin * 2,
      height: (node.height ?? node.measured?.height ?? 0) + margin * 2,
      node,
      moved: false,
    };
  }

  return boxes;
}

export const resolveCollisions = (
  nodes: Node[],
  { maxIterations = 50, overlapThreshold = 0.5, margin = 0 }: Partial<CollisionAlgorithmOptions> = {},
): Node[] => {
  const boxes = getBoxesFromNodes(nodes, margin);

  let numIterations = 0;

  for (let iter = 0; iter <= maxIterations; iter++) {
    let moved = false;

    for (let i = 0; i < boxes.length; i++) {
      for (let j = i + 1; j < boxes.length; j++) {
        const A = boxes[i];
        const B = boxes[j];

        // Calculate center positions
        const centerAX = A.x + A.width * 0.5;
        const centerAY = A.y + A.height * 0.5;
        const centerBX = B.x + B.width * 0.5;
        const centerBY = B.y + B.height * 0.5;

        // Calculate distance between centers
        const dx = centerAX - centerBX;
        const dy = centerAY - centerBY;

        // Calculate overlap along each axis
        const px = (A.width + B.width) * 0.5 - Math.abs(dx);
        const py = (A.height + B.height) * 0.5 - Math.abs(dy);

        // Check if there's significant overlap
        if (px > overlapThreshold && py > overlapThreshold) {
          A.moved = B.moved = moved = true;

          // Context-aware resolution: preserve timeline layouts
          const ALIGNMENT_THRESHOLD = 10;
          const isHorizontallyAligned = Math.abs(centerAY - centerBY) < ALIGNMENT_THRESHOLD;
          const isVerticallyAligned = Math.abs(centerAX - centerBX) < ALIGNMENT_THRESHOLD;

          if (isHorizontallyAligned) {
            // Force X-axis separation for horizontally aligned nodes (timeline layouts)
            const sx = dx > 0 ? 1 : -1;
            const moveAmount = (px / 2) * sx;
            A.x += moveAmount;
            B.x -= moveAmount;
          } else if (isVerticallyAligned) {
            // Force Y-axis separation for vertically aligned nodes
            const sy = dy > 0 ? 1 : -1;
            const moveAmount = (py / 2) * sy;
            A.y += moveAmount;
            B.y -= moveAmount;
          } else {
            // Default: resolve along the smallest overlap axis
            if (px < py) {
              // Move along x-axis
              const sx = dx > 0 ? 1 : -1;
              const moveAmount = (px / 2) * sx;
              A.x += moveAmount;
              B.x -= moveAmount;
            } else {
              // Move along y-axis
              const sy = dy > 0 ? 1 : -1;
              const moveAmount = (py / 2) * sy;
              A.y += moveAmount;
              B.y -= moveAmount;
            }
          }
        }
      }
    }
    numIterations++;

    // Early exit if no overlaps were found
    if (!moved) {
      break;
    }
  }

  const newNodes = boxes.map((box) => {
    if (box.moved) {
      return {
        ...box.node,
        position: {
          x: box.x + margin,
          y: box.y + margin,
        },
      };
    }
    return box.node;
  });

  return newNodes;
};
