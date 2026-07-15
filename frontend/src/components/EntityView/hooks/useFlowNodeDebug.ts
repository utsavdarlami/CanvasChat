/**
 * Lightweight debug bridge: EntityFlowView writes its live React Flow
 * nodes here so the DiagnosticPanel can read them without prop-drilling
 * or adding to the main store.
 *
 * This is intentionally outside of React state to avoid re-render overhead.
 */
import type { Node } from '@xyflow/react';

let _liveNodes: Node[] = [];
let _version = 0;

/** Called by EntityFlowView after each nodes state change. */
export function setLiveFlowNodes(nodes: Node[]): void {
  _liveNodes = nodes;
  _version++;
}

/** Read the current React Flow nodes (snapshot). */
export function getLiveFlowNodes(): Node[] {
  return _liveNodes;
}

/** Monotonic counter — lets consumers detect staleness cheaply. */
export function getLiveFlowVersion(): number {
  return _version;
}
