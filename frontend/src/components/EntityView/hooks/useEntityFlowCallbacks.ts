import { useRef } from 'react';
import type { Node, OnNodeDrag, OnSelectionChangeFunc } from '@xyflow/react';

import { useAppStore } from '@/stores/appStore';
import { getEntityId } from '@/utils/entityId';
import { useCrossDisplaySync } from './useCrossDisplaySync';
import { useNodeDrag } from './useNodeDrag';

export interface EntityFlowCallbacksResult {
  handleNodeDragStart: OnNodeDrag;
  handleNodeDrag: OnNodeDrag;
  handleNodeDragStop: OnNodeDrag;
  handleSelectionChange: OnSelectionChangeFunc;
  crossingPeerLabel: string | null;
  transferModeActive: boolean;
  animatingNodeIdsRef: React.RefObject<Set<string>>;
  previewNodeIdsRef: React.RefObject<Set<string>>;
  mirrorNodeIdsRef: React.RefObject<Set<string>>;
}

export function useEntityFlowCallbacks(
  setNodes: React.Dispatch<React.SetStateAction<Node[]>>,
  setIsDragging: (dragging: boolean) => void,
  frozenViewportRef: React.MutableRefObject<import('@xyflow/react').Viewport | null>,
): EntityFlowCallbacksResult {

  // Shared refs for remote syncing and animations
  const animatingNodeIdsRef = useRef<Set<string>>(new Set());
  const previewNodeIdsRef = useRef<Set<string>>(new Set());
  const mirrorNodeIdsRef = useRef<Set<string>>(new Set());

  // 1. Selection handler
  const handleSelectionChange: OnSelectionChangeFunc = (selection) => {
    const { graph, session } = useAppStore.getState();
    const selectedNodeIds = new Set((selection.nodes || []).map((node) => String(node.id)));

    const effectiveDisplayId = session.isConnected && session.localPeerId
      ? session.localPeerId
      : null;

    const visibleNodes = effectiveDisplayId
      ? graph.nodes.filter((node) => node.displayId === effectiveDisplayId)
      : graph.nodes;

    const selectedEntityIdsOnVisibleDisplay = visibleNodes
      .filter((node) => selectedNodeIds.has(node.id))
      .map((node) => getEntityId(node));

    // Preserve selections from non-visible displays while replacing only
    // the visible display subset.
    const nextSelectedEntityIds = new Set(graph.selectedEntityIds);
    for (const node of visibleNodes) {
      nextSelectedEntityIds.delete(getEntityId(node));
    }
    for (const entityId of selectedEntityIdsOnVisibleDisplay) {
      nextSelectedEntityIds.add(entityId);
    }

    graph.setSelectedEntityIds(Array.from(nextSelectedEntityIds));
  };

  // 2. Remote Node Sync (Previews, Commits, Mirrors)
  useCrossDisplaySync(
    setNodes,
    animatingNodeIdsRef,
    previewNodeIdsRef,
    mirrorNodeIdsRef
  );

  // 3. Local Node Drag and Cross-Display Transfer Initialization
  const {
    handleNodeDragStart,
    handleNodeDrag,
    handleNodeDragStop,
    crossingPeerLabel,
    transferModeActive,
  } = useNodeDrag(
    setNodes,
    setIsDragging,
    frozenViewportRef,
    animatingNodeIdsRef
  );

  return {
    handleNodeDragStart,
    handleNodeDrag,
    handleNodeDragStop,
    handleSelectionChange,
    crossingPeerLabel,
    transferModeActive,
    animatingNodeIdsRef,
    previewNodeIdsRef,
    mirrorNodeIdsRef,
  };
}
