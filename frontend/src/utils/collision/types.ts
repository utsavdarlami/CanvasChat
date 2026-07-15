import type { Node } from '@xyflow/react';

export type CollisionAlgorithmOptions = {
  maxIterations: number;
  overlapThreshold: number;
  margin: number;
};

export type CollisionAlgorithm = (
  nodes: Node[],
  options: CollisionAlgorithmOptions,
) => Node[];

export type Box = {
  x: number;
  y: number;
  width: number;
  height: number;
  moved: boolean;
  node: Node;
};
