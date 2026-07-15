import * as Y from 'yjs';
import { useAppStore } from '@/stores/appStore';
import type { GraphData, GraphNode } from '@/types/graph';
import { clearAllNodePositions } from './nodePositions';

// Native Yjs Maps/Arrays for incremental sync
let sharedGraphNodes: Y.Map<GraphNode> | null = null;
let sharedGraphMetadata: Y.Map<unknown> | null = null;

// Use this variable to avoid triggering full setGraphData when we are just applying individual node updates locally
let isApplyingRemoteUpdates = false;

// Pending structural change payload, flushed after all Yjs transactions settle
let pendingStructuralPayload: GraphData | null = null;

// Store observer references for proper teardown
let nodesObserver: ((event: Y.YMapEvent<GraphNode>, transaction: Y.Transaction) => void) | null = null;
let metadataObserver: ((event: Y.YMapEvent<unknown>, transaction: Y.Transaction) => void) | null = null;
let afterAllTxHandler: ((doc: Y.Doc, transactions: Y.Transaction[]) => void) | null = null;
let currentDoc: Y.Doc | null = null;

export function setupGraphData(doc: Y.Doc) {
  sharedGraphNodes = doc.getMap('sharedGraphNodes');
  sharedGraphMetadata = doc.getMap('sharedGraphMetadata');
  currentDoc = doc;

  // Helper to re-assemble the full graph object
  const getFullGraphPayload = () => {
    if (!sharedGraphNodes || !sharedGraphMetadata) return null;

    const nodes: GraphNode[] = [];
    sharedGraphNodes.forEach((node) => {
      nodes.push(node);
    });

    return {
      nodes,
      graph: sharedGraphMetadata.get('graph') || null,
    };
  };

  // --- sharedGraphNodes observer: sync granular node updates OR full graph ---
  nodesObserver = (event, transaction) => {
    if (!sharedGraphNodes || transaction.origin === 'local') return;

    isApplyingRemoteUpdates = true;
    try {
      const graphState = useAppStore.getState().graph;

      // If the local store is completely empty, we MUST do a full load
      if (graphState.nodes.length === 0 && sharedGraphNodes.size > 0) {
        const payload = getFullGraphPayload();
        if (payload) {
          console.log('[Yjs] Received initial full graph load from remote peer');
          useAppStore.getState().graph.setGraphData(payload as GraphData);
        }
        return;
      }

      let needsFullReload = false;
      let updatedNodeCount = 0;

      event.changes.keys.forEach((change, key) => {
        if (change.action === 'add' || change.action === 'delete') {
          needsFullReload = true;
        } else if (change.action === 'update') {
          const rawNodeData = sharedGraphNodes!.get(key);
          if (rawNodeData) {
            const nodeData = { ...rawNodeData };
            delete nodeData.x;
            delete nodeData.y;
            delete nodeData.fx;
            delete nodeData.fy;
            delete nodeData.displayId;

            useAppStore.getState().graph.updateNode(key, nodeData);
            updatedNodeCount++;
          }
        }
      });

      if (needsFullReload && updatedNodeCount === 0) {
        const payload = getFullGraphPayload();
        if (payload) {
          console.log('[Yjs] Received structural graph changes from remote peer, reloading');
          useAppStore.getState().graph.setGraphData(payload as GraphData);
        }
      } else if (updatedNodeCount > 0) {
        console.log(`[Yjs] Applied ${updatedNodeCount} granular node updates from remote peer`);
      }
    } finally {
      isApplyingRemoteUpdates = false;
    }
  };
  sharedGraphNodes.observe(nodesObserver);

  // Observer for metadata: if it changes, we need a full reload.
  const handleStructuralChange = (_event: Y.YMapEvent<unknown>, transaction: Y.Transaction) => {
    if (transaction.origin === 'local') return;

    const payload = getFullGraphPayload();
    if (payload) {
      pendingStructuralPayload = payload as GraphData;
    }
  };

  metadataObserver = handleStructuralChange;
  sharedGraphMetadata.observe(handleStructuralChange);

  // Flush pending structural change after all Yjs transactions settle.
  afterAllTxHandler = () => {
    if (pendingStructuralPayload && !isApplyingRemoteUpdates) {
      console.log('[Yjs] Received structural metadata changes from remote peer, reloading');
      useAppStore.getState().graph.setGraphData(pendingStructuralPayload);
      pendingStructuralPayload = null;
    }
  };
  doc.on('afterAllTransactions', afterAllTxHandler);

}

export function teardownGraphData() {
  if (sharedGraphNodes && nodesObserver) {
    sharedGraphNodes.unobserve(nodesObserver);
  }
  if (sharedGraphMetadata && metadataObserver) {
    sharedGraphMetadata.unobserve(metadataObserver);
  }
  if (currentDoc && afterAllTxHandler) {
    currentDoc.off('afterAllTransactions', afterAllTxHandler);
  }

  sharedGraphNodes = null;
  sharedGraphMetadata = null;
  nodesObserver = null;
  metadataObserver = null;
  afterAllTxHandler = null;
  currentDoc = null;
  pendingStructuralPayload = null;
}

/**
 * Broadcast full graph data to the room via incremental Yjs structures.
 */
export function broadcastGraphData(data: GraphData): void {
  if (!sharedGraphNodes || !sharedGraphMetadata || !sharedGraphNodes.doc) return;

  sharedGraphNodes.doc.transact(() => {
    // 1. Clear existing
    sharedGraphNodes!.clear();
    sharedGraphMetadata!.clear();

    // Also clear existing node positions to prevent orphans
    clearAllNodePositions();

    // 2. Populate Nodes Map
    if (data.nodes && Array.isArray(data.nodes)) {
      data.nodes.forEach((node: GraphNode) => {
        sharedGraphNodes!.set(node.id, node);
      });
    }

    // 3. Populate Metadata
    if (data.graph) {
      sharedGraphMetadata!.set('graph', data.graph);
    }
  }, 'local');
}

/**
 * Broadcast an update to a specific node.
 * Extremely lightweight - only syncs the changed node.
 */
export function broadcastNodeUpdate(nodeId: string, updates: Partial<GraphNode>): void {
  if (!sharedGraphNodes || !sharedGraphNodes.doc) return;

  if (isApplyingRemoteUpdates) return;

  sharedGraphNodes.doc.transact(() => {
    const existingNode = sharedGraphNodes!.get(nodeId);
    if (existingNode) {
      const updatedNode = { ...existingNode, ...updates };
      sharedGraphNodes!.set(nodeId, updatedNode);
    }
  }, 'local');
}

