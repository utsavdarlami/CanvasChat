import { useCallback, useEffect, useRef, useState } from 'react';
import { useReactFlow, type Node, type OnNodeDrag } from '@xyflow/react';
import { useAppStore } from '@/stores/appStore';
import { emitNodeDragEphemeralBatch, emitNodeDragBatch, clearEphemeralDrag } from '@/services/yjsService';
import { resolveByIntersections } from '@/utils/collision';
import { COLLISION_CONFIG } from '@/utils/constants';
import { canvasToScreen } from '@/utils/nodeSyncProtocol';
import {
  findAdjacentPeer,
  findOverlappingPeers,
  getExitDirection,
  mapPositionToAdjacentDisplay,
} from '@/utils/peerArrangement';
import type { ArrangedPeer, ExitDirection } from '@/utils/peerArrangement';

const DRAG_EMIT_INTERVAL_MS = 50;
const EXIT_ANIMATION_MS = 250;
const DEBUG_TRANSFER = false;

function transferLog(message: string): void {
  if (DEBUG_TRANSFER) {
    console.log(message);
  }
}

function isTransferModifierHeld(event: unknown): boolean {
  const e = event as { ctrlKey?: boolean; metaKey?: boolean } | null | undefined;
  return !!(e?.ctrlKey || e?.metaKey);
}

interface PendingTransfer {
  nodeIds: string[];
  targetPeer: ArrangedPeer;
  sourcePeer: ArrangedPeer;
  exitDir: ExitDirection;
}

function computeExitEdgePosition(
  currentPos: { x: number; y: number },
  exitDir: ExitDirection,
  viewportWidth: number,
  viewportHeight: number,
): { x: number; y: number } {
  switch (exitDir) {
    case 'right':
      return { x: viewportWidth + 20, y: currentPos.y };
    case 'left':
      return { x: -420, y: currentPos.y };
    case 'bottom':
      return { x: currentPos.x, y: viewportHeight + 20 };
    case 'top':
      return { x: currentPos.x, y: -320 };
  }
}

function normalizeDraggedNodes(primaryNode: Node, draggedNodes: Node[] | undefined): Node[] {
  if (draggedNodes && draggedNodes.length > 0) {
    const byId = new Map<string, Node>();
    for (const draggedNode of draggedNodes) {
      byId.set(draggedNode.id, draggedNode);
    }
    if (!byId.has(primaryNode.id)) {
      byId.set(primaryNode.id, primaryNode);
    }
    return [...byId.values()];
  }
  return [primaryNode];
}

export function useNodeDrag(
  setNodes: React.Dispatch<React.SetStateAction<Node[]>>,
  setIsDragging: (dragging: boolean) => void,
  frozenViewportRef: React.MutableRefObject<import('@xyflow/react').Viewport | null>,
  animatingNodeIdsRef: React.RefObject<Set<string>>
) {
  const { getViewport, getNodes } = useReactFlow();

  const dragEmitThrottleRef = useRef(0);
  const [crossingPeerLabel, setCrossingPeerLabel] = useState<string | null>(null);
  const [transferModeActive, setTransferModeActive] = useState(false);

  const activeMirrorPeersRef = useRef<Set<string>>(new Set());
  const pendingTransferRef = useRef<PendingTransfer | null>(null);
  const isDraggingRef = useRef(false);
  const isCtrlHeldRef = useRef(false);
  const transferModeSeenDuringDragRef = useRef(false);

  const cancelActiveMirrors = useCallback((nodeId: string) => {
    if (activeMirrorPeersRef.current.size > 0) {
      const clears = [...activeMirrorPeersRef.current].map(peerId => ({
        id: nodeId,
        x: 0,
        y: 0,
        displayId: peerId,
        kind: 'mirror-clear' as const,
        space: 'screen' as const,
      }));
      emitNodeDragEphemeralBatch(clears);
      activeMirrorPeersRef.current.clear();
    }
  }, []);

  const clearPendingPreview = useCallback(() => {
    const pending = pendingTransferRef.current;
    if (!pending) return;

    const clears = pending.nodeIds.map(nodeId => ({
      id: nodeId,
      x: 0,
      y: 0,
      displayId: pending.targetPeer.id,
      kind: 'preview-clear' as const,
      space: 'screen' as const,
    }));
    emitNodeDragEphemeralBatch(clears);
  }, []);

  useEffect(() => {
    const onDown = (e: KeyboardEvent) => {
      if (e.key === 'Control' || e.key === 'Meta') isCtrlHeldRef.current = true;
    };
    const onUp = (e: KeyboardEvent) => {
      if (e.key === 'Control' || e.key === 'Meta') {
        isCtrlHeldRef.current = false;
      }
    };
    const onBlur = () => {
      isCtrlHeldRef.current = false;
    };
    window.addEventListener('keydown', onDown);
    window.addEventListener('keyup', onUp);
    window.addEventListener('blur', onBlur);
    return () => {
      window.removeEventListener('keydown', onDown);
      window.removeEventListener('keyup', onUp);
      window.removeEventListener('blur', onBlur);
    };
  }, []);

  const handleNodeDragStart: OnNodeDrag = useCallback((event) => {
    const modifierHeld = isTransferModifierHeld(event) || isCtrlHeldRef.current;
    window.getSelection()?.removeAllRanges();

    setIsDragging(true);
    isDraggingRef.current = true;
    pendingTransferRef.current = null;
    dragEmitThrottleRef.current = 0;
    isCtrlHeldRef.current = modifierHeld;
    transferModeSeenDuringDragRef.current = modifierHeld;
    if (modifierHeld) {
      setTransferModeActive(true);
      if (!frozenViewportRef.current) {
        frozenViewportRef.current = getViewport();
      }
    }
  }, [setIsDragging, getViewport, frozenViewportRef]);

  const handleNodeDrag: OnNodeDrag = useCallback((event, node, draggedNodesArg) => {
    const { session } = useAppStore.getState();
    if (!session.isConnected) return;

    const now = Date.now();
    if (now - dragEmitThrottleRef.current < DRAG_EMIT_INTERVAL_MS) return;
    dragEmitThrottleRef.current = now;

    const modifierHeld = isTransferModifierHeld(event) || isCtrlHeldRef.current;
    isCtrlHeldRef.current = modifierHeld;
    const transferLatched = modifierHeld || transferModeSeenDuringDragRef.current;

    const localDisplayId = session.localPeerId ?? '__local__';
    const draggedNodes = normalizeDraggedNodes(node, draggedNodesArg);

    const dragUpdates = draggedNodes.map(draggedNode => ({
      id: draggedNode.id,
      x: draggedNode.position.x,
      y: draggedNode.position.y,
      displayId: localDisplayId,
      kind: 'drag' as const,
      space: 'canvas' as const,
    }));
    emitNodeDragEphemeralBatch(dragUpdates);

    const { virtualDesktop: vd, localPeer } = session;

    const vp = getViewport();
    const screenPos = canvasToScreen(node.position, vp);
    const screenX = screenPos.x;
    const screenY = screenPos.y;

    if (transferLatched) {
      setTransferModeActive(true);
      if (modifierHeld) transferModeSeenDuringDragRef.current = true;
      if (!frozenViewportRef.current) {
        frozenViewportRef.current = vp;
      }

      if (vd && session.localPeerId) {
        const exitDir = getExitDirection(
          screenX,
          screenY,
          localPeer.width,
          localPeer.height,
        );

        if (exitDir) {
          const targetPeer = findAdjacentPeer(vd, session.localPeerId, exitDir);
          if (targetPeer) {
            const sourcePeer = vd.peers.find(p => p.id === session.localPeerId);
            if (sourcePeer) {
              // If target peer changed, clear old preview on previous target
              const oldPending = pendingTransferRef.current;
              if (oldPending && oldPending.targetPeer.id !== targetPeer.id) {
                clearPendingPreview();
              }

              pendingTransferRef.current = {
                nodeIds: draggedNodes.map(draggedNode => draggedNode.id),
                targetPeer,
                sourcePeer,
                exitDir,
              };

              // Batch all preview emits + mirror clears into ONE awareness update.
              // Sending mirror clears separately would overwrite the preview
              // awareness state, causing previews to be lost on the receiver.
              const batchUpdates: Array<{
                id: string; x: number; y: number;
                displayId: string; kind: 'preview' | 'mirror-clear'; space: 'screen';
              }> = [];

              for (const draggedNode of draggedNodes) {
                const draggedScreenPos = canvasToScreen(draggedNode.position, vp);
                const mappedPos = mapPositionToAdjacentDisplay(
                  draggedScreenPos.x,
                  draggedScreenPos.y,
                  sourcePeer,
                  targetPeer,
                  exitDir,
                );
                batchUpdates.push({
                  id: draggedNode.id,
                  x: mappedPos.x,
                  y: mappedPos.y,
                  displayId: targetPeer.id,
                  kind: 'preview' as const,
                  space: 'screen' as const,
                });
              }

              // Append mirror clears to the same batch
              if (activeMirrorPeersRef.current.size > 0) {
                for (const draggedNode of draggedNodes) {
                  for (const peerId of activeMirrorPeersRef.current) {
                    batchUpdates.push({
                      id: draggedNode.id,
                      x: 0,
                      y: 0,
                      displayId: peerId,
                      kind: 'mirror-clear' as const,
                      space: 'screen' as const,
                    });
                  }
                }
                activeMirrorPeersRef.current.clear();
              }

              emitNodeDragEphemeralBatch(batchUpdates);

              setCrossingPeerLabel(targetPeer.tags[0] ?? targetPeer.id.slice(0, 8));
              return;
            }
          }
        }

        if (pendingTransferRef.current) {
          clearPendingPreview();
          pendingTransferRef.current = null;
        }
        setCrossingPeerLabel(null);
      }
    } else {
      if (pendingTransferRef.current) {
        clearPendingPreview();
        pendingTransferRef.current = null;
      }
      setTransferModeActive(false);
      setCrossingPeerLabel(null);
    }

    if (!pendingTransferRef.current && vd && session.localPeerId) {
      const nodeW = node.measured?.width ?? node.width ?? 400;
      const nodeH = node.measured?.height ?? node.height ?? 300;

      const screenW = nodeW * vp.zoom;
      const screenH = nodeH * vp.zoom;

      const overlapping = findOverlappingPeers(
        vd,
        session.localPeerId,
        screenX,
        screenY,
        screenW,
        screenH,
      );

      const newMirrorPeerIds = new Set(overlapping.map(o => o.peer.id));

      // Collect all mirror updates and clears into a single batch
      const mirrorUpdates: Array<{
        id: string; x: number; y: number;
        displayId: string; kind: 'mirror' | 'mirror-clear'; space: 'screen';
      }> = [];

      for (const { peer, localX, localY } of overlapping) {
        activeMirrorPeersRef.current.add(peer.id);
        mirrorUpdates.push({
          id: node.id,
          x: localX,
          y: localY,
          displayId: peer.id,
          kind: 'mirror',
          space: 'screen',
        });
      }

      for (const prevPeerId of activeMirrorPeersRef.current) {
        if (!newMirrorPeerIds.has(prevPeerId)) {
          mirrorUpdates.push({
            id: node.id,
            x: 0,
            y: 0,
            displayId: prevPeerId,
            kind: 'mirror-clear',
            space: 'screen',
          });
          activeMirrorPeersRef.current.delete(prevPeerId);
        }
      }

      if (mirrorUpdates.length > 0) {
        emitNodeDragEphemeralBatch(mirrorUpdates);
      }
    }
  }, [getViewport, cancelActiveMirrors, clearPendingPreview, frozenViewportRef]);

  const handleNodeDragStop: OnNodeDrag = useCallback((_event, node, draggedNodesArg) => {
    dragEmitThrottleRef.current = 0;
    setIsDragging(false);
    isDraggingRef.current = false;
    setTransferModeActive(false);
    frozenViewportRef.current = null;

    clearEphemeralDrag();

    const { session, graph } = useAppStore.getState();
    const localDisplayId = session.localPeerId ?? '__local__';
    const draggedNodes = normalizeDraggedNodes(node, draggedNodesArg);
    const draggedNodeById = new Map(draggedNodes.map(draggedNode => [draggedNode.id, draggedNode]));

    // Mirrors are only created for the primary node (node.id) during drag,
    // so send mirror-clears specifically for that ID. The old loop called
    // cancelActiveMirrors for every dragged node, but activeMirrorPeersRef
    // was cleared on the first call — if the primary wasn't first in the
    // array, its mirror-clear was never sent.
    cancelActiveMirrors(node.id);

    let pending = pendingTransferRef.current;
    pendingTransferRef.current = null;

    // Fallback: if transfer mode was active during this drag but the pending
    // transfer was cleared in the final drag frames, re-evaluate from the final
    // drop position so Ctrl+drop outside the viewport still transfers reliably.
    if (
      !pending &&
      session.isConnected &&
      transferModeSeenDuringDragRef.current &&
      session.virtualDesktop &&
      session.localPeerId
    ) {
      const vp = getViewport();
      const screenPos = canvasToScreen(node.position, vp);
      const exitDir = getExitDirection(
        screenPos.x,
        screenPos.y,
        session.localPeer.width,
        session.localPeer.height,
      );

      if (exitDir) {
        const targetPeer = findAdjacentPeer(session.virtualDesktop, session.localPeerId, exitDir);
        const sourcePeer = session.virtualDesktop.peers.find(p => p.id === session.localPeerId);
        if (targetPeer && sourcePeer) {
          pending = {
            nodeIds: draggedNodes.map(draggedNode => draggedNode.id),
            targetPeer,
            sourcePeer,
            exitDir,
          };
        }
      }
    }
    transferModeSeenDuringDragRef.current = false;
    const currentFlowNodes = getNodes();
    const currentFlowNodeById = new Map(currentFlowNodes.map(flowNode => [flowNode.id, flowNode]));

    if (pending && session.isConnected) {
      const { nodeIds, targetPeer, sourcePeer, exitDir } = pending;

      const vp = getViewport();
      const canvasViewportW = sourcePeer.width / vp.zoom;
      const canvasViewportH = sourcePeer.height / vp.zoom;
      const transferNodes = nodeIds.length > 0 ? nodeIds : [node.id];
      const transferPayload: Array<{
        id: string;
        exitEdgePos: { x: number; y: number };
        sourceCanvasPos: { x: number; y: number };
        commitScreenPos: { x: number; y: number };
      }> = [];

      for (const transferNodeId of transferNodes) {
        const transferNode = draggedNodeById.get(transferNodeId) ?? currentFlowNodeById.get(transferNodeId);
        if (!transferNode) continue;

        const screenX = transferNode.position.x * vp.zoom + vp.x;
        const screenY = transferNode.position.y * vp.zoom + vp.y;
        const newPos = mapPositionToAdjacentDisplay(
          screenX,
          screenY,
          sourcePeer,
          targetPeer,
          exitDir,
        );
        const exitEdgePos = computeExitEdgePosition(
          transferNode.position,
          exitDir,
          canvasViewportW,
          canvasViewportH,
        );

        transferPayload.push({
          id: transferNode.id,
          exitEdgePos,
          sourceCanvasPos: transferNode.position,
          commitScreenPos: newPos,
        });
      }

      transferLog(
        `[NodeDrag] transfer commit: ${transferPayload.length} nodes (requested: ${transferNodes.length}), ids: [${transferPayload.map(t => t.id).join(', ')}]`,
      );

      if (transferPayload.length > 0) {
        const transferNodeIds = new Set(transferPayload.map(item => item.id));
        const payloadById = new Map(transferPayload.map(item => [item.id, item]));
        const exitTargetPeerId = targetPeer.id;

        for (const transferNodeId of transferNodeIds) {
          animatingNodeIdsRef.current?.add(transferNodeId);
        }

        setNodes(prev => prev.map(flowNode => {
          const transferNode = payloadById.get(flowNode.id);
          if (!transferNode) return flowNode;

          return {
            ...flowNode,
            position: transferNode.exitEdgePos,
            className: 'transfer-exit',
            draggable: false,
            selectable: false,
            data: {
              ...(flowNode.data as Record<string, unknown>),
              isTransientRender: true,
            },
          };
        }));

        setTimeout(() => {
          for (const transferNode of transferPayload) {
            const latestNode = useAppStore.getState().graph.nodes.find((n) => n.id === transferNode.id);
            if (latestNode?.displayId !== exitTargetPeerId) {
              graph.updateNodeDisplay(
                transferNode.id,
                exitTargetPeerId,
                transferNode.sourceCanvasPos.x,
                transferNode.sourceCanvasPos.y,
              );
            }
            animatingNodeIdsRef.current?.delete(transferNode.id);
          }
          setNodes(prev => prev.filter(flowNode => !transferNodeIds.has(flowNode.id)));

          const nodeCount = transferNodeIds.size;
          const peerLabel = targetPeer.tags[0] ?? targetPeer.id.slice(0, 8);
          const label = `Transferred ${nodeCount} entity${nodeCount > 1 ? 'ies' : ''} to ${peerLabel}`;
          const currentNodes = useAppStore.getState().graph.nodes;
          useAppStore.getState().timeline.recordSnapshot(label, 'drag', currentNodes);
        }, EXIT_ANIMATION_MS);

        emitNodeDragBatch(transferPayload.map(transferNode => ({
          id: transferNode.id,
          x: transferNode.commitScreenPos.x,
          y: transferNode.commitScreenPos.y,
          displayId: targetPeer.id,
          kind: 'commit' as const,
          space: 'screen' as const,
        })));

        setCrossingPeerLabel(null);
        return;
      }
    }

    const draggedIds = new Set(draggedNodes.map(d => d.id));
    const { resolved: resolvedNodes, adjustedIds } = resolveByIntersections(
      currentFlowNodes,
      draggedIds,
      COLLISION_CONFIG,
    );
    setNodes(resolvedNodes);
    setCrossingPeerLabel(null);

    const graphNodeById = new Map(graph.nodes.map(n => [n.id, n]));
    const prevById = new Map(currentFlowNodes.map(n => [n.id, n]));
    const resolvedById = new Map(resolvedNodes.map(n => [n.id, n]));
    const committed = new Set<string>();

    // Collect all position updates for a single batched Zustand write + Yjs transaction
    const positionUpdates: Array<{ id: string; x: number; y: number }> = [];
    const yjsUpdates: Array<{ id: string; x: number; y: number; displayId: string; kind: 'commit'; space: 'canvas' }> = [];

    const collectNodePosition = (nodeId: string, pos: { x: number; y: number }) => {
      if (committed.has(nodeId)) return;

      const graphNode = graphNodeById.get(nodeId);
      if (!graphNode || graphNode.displayId !== localDisplayId) return;

      positionUpdates.push({ id: nodeId, x: pos.x, y: pos.y });
      if (session.isConnected) {
        yjsUpdates.push({
          id: nodeId,
          x: pos.x,
          y: pos.y,
          displayId: localDisplayId,
          kind: 'commit',
          space: 'canvas',
        });
      }
      committed.add(nodeId);
    };

    for (const draggedNode of draggedNodes) {
      const draggedResolved = resolvedById.get(draggedNode.id);
      collectNodePosition(draggedNode.id, draggedResolved?.position ?? draggedNode.position);
    }

    for (const adjustedId of adjustedIds) {
      const resolvedNode = resolvedById.get(adjustedId);
      const prevNode = prevById.get(adjustedId);
      if (!resolvedNode || !prevNode) continue;

      const dx = Math.abs(resolvedNode.position.x - prevNode.position.x);
      const dy = Math.abs(resolvedNode.position.y - prevNode.position.y);
      if (dx > 0.1 || dy > 0.1) {
        collectNodePosition(adjustedId, resolvedNode.position);
      }
    }

    // Single batched Zustand update (1 set() instead of N)
    if (positionUpdates.length > 0) {
      graph.setNodePositionsBulk(positionUpdates);
    }

    // Single batched Yjs transaction (1 observer callback on remote instead of N)
    if (yjsUpdates.length > 0) {
      emitNodeDragBatch(yjsUpdates);
    }

    // Record timeline snapshot after drag completes
    if (positionUpdates.length > 0) {
      const nodeCount = positionUpdates.length;
      const nodeNames = positionUpdates.slice(0, 3).map(p => {
        const node = currentFlowNodeById.get(p.id);
        return node?.data?.name || p.id;
      });
      let label = '';
      if (nodeCount === 1) {
        label = `Moved ${nodeNames[0]}`;
      } else if (nodeCount === 2) {
        label = `Moved ${nodeNames[0]} and ${nodeNames[1]}`;
      } else if (nodeCount === 3) {
        label = `Moved ${nodeNames[0]}, ${nodeNames[1]}, and ${nodeNames[2]}`;
      } else {
        label = `Moved ${nodeCount} entities`;
      }
      
      // Get the current nodes from Zustand store directly
      const currentNodes = useAppStore.getState().graph.nodes;
      if (DEBUG_TRANSFER) {
        console.log('[Timeline] Drag snapshot - current nodes in store:', currentNodes.length);
      }
      useAppStore.getState().timeline.recordSnapshot(label, 'drag', currentNodes);
    }
  }, [setNodes, setIsDragging, cancelActiveMirrors, getViewport, getNodes, frozenViewportRef, animatingNodeIdsRef]);

  return {
    handleNodeDragStart,
    handleNodeDrag,
    handleNodeDragStop,
    crossingPeerLabel,
    transferModeActive,
  };
}
