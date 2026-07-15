import { useEffect, useRef } from 'react';
import { useReactFlow, type Node } from '@xyflow/react';
import { useAppStore } from '@/stores/appStore';
import { setNodeMovedCallback, setEphemeralDragCallback, emitNodeDragBatch } from '@/services/yjsService';
import type { NodeUpdate } from '@/types/session';
import type { ExitDirection } from '@/utils/peerArrangement';
import { canvasToScreen, resolveNodeUpdateKind, resolveNodeUpdateSpace, screenToCanvas } from '@/utils/nodeSyncProtocol';
import { resolveByIntersections } from '@/utils/collision';
import { COLLISION_CONFIG } from '@/utils/constants';
import { getNodeDimensions } from '../entityNodeUtils';

const ENTRY_ANIMATION_MS = 300;
const COMMIT_ANIMATION_MS = 200;
const EXIT_ANIMATION_MS = 250;
const DEBUG_TRANSFER = false;

function transferLog(message: string): void {
  if (DEBUG_TRANSFER) {
    console.log(message);
  }
}

function hasClassName(node: Node, className: string): boolean {
  const current = node.className;
  if (!current) return false;
  return typeof current === 'string' ? current.includes(className) : false;
}

function inferEntryDirection(
  x: number,
  y: number,
  viewportWidth: number,
  viewportHeight: number,
): ExitDirection {
  const distances = {
    left: Math.abs(x),
    right: Math.abs(x - viewportWidth),
    top: Math.abs(y),
    bottom: Math.abs(y - viewportHeight),
  };

  const minDist = Math.min(distances.left, distances.right, distances.top, distances.bottom);
  if (distances.left === minDist) return 'left';
  if (distances.right === minDist) return 'right';
  if (distances.top === minDist) return 'top';
  return 'bottom';
}

function computeEntryEdgePosition(
  entryDir: ExitDirection,
  finalY: number,
  finalX: number,
  viewportWidth: number,
  viewportHeight: number,
): { x: number; y: number } {
  switch (entryDir) {
    case 'left':
      return { x: -420, y: finalY };
    case 'right':
      return { x: viewportWidth + 20, y: finalY };
    case 'top':
      return { x: finalX, y: -320 };
    case 'bottom':
      return { x: finalX, y: viewportHeight + 20 };
  }
}

export function useCrossDisplaySync(
  setNodes: React.Dispatch<React.SetStateAction<Node[]>>,
  animatingNodeIdsRef: React.RefObject<Set<string>>,
  previewNodeIdsRef: React.RefObject<Set<string>>,
  mirrorNodeIdsRef: React.RefObject<Set<string>>,
) {
  const { getViewport, getNodes } = useReactFlow();
  const collisionFrameRef = useRef<number | null>(null);
  const collisionScheduledRef = useRef(false);
  const pendingArrivalIdsRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    /**
     * After a transferred node's entry animation completes, resolve any
     * collisions against the receiver's existing nodes and broadcast the
     * adjusted positions to keep all peers in sync.
     */
    function resolveAndBroadcastCollisions(arrivedIds: Set<string>): void {
      if (arrivedIds.size === 0) return;
      const { session, graph } = useAppStore.getState();
      const localDisplayId = session.localPeerId ?? '__local__';

      // Use functional updater to avoid race conditions when multiple
      // entry animations complete in the same React batch. A VALUE-based
      // setNodes(resolvedNodes) would overwrite pending state from other
      // animation callbacks.
      setNodes(currentNodes => {
        const { resolved: resolvedNodes, adjustedIds } = resolveByIntersections(
          currentNodes,
          arrivedIds,
          COLLISION_CONFIG,
        );

        if (adjustedIds.size === 0) return currentNodes;

        const resolvedById = new Map(resolvedNodes.map(n => [n.id, n]));
        const positionUpdates: Array<{ id: string; x: number; y: number }> = [];
        const yjsUpdates: Array<{
          id: string; x: number; y: number;
          displayId: string; kind: 'commit'; space: 'canvas';
        }> = [];

        for (const adjustedId of adjustedIds) {
          const resolved = resolvedById.get(adjustedId);
          if (!resolved) continue;
          positionUpdates.push({
            id: resolved.id,
            x: resolved.position.x,
            y: resolved.position.y,
          });
          if (session.isConnected) {
            yjsUpdates.push({
              id: resolved.id,
              x: resolved.position.x,
              y: resolved.position.y,
              displayId: localDisplayId,
              kind: 'commit',
              space: 'canvas',
            });
          }
        }

        // Schedule store and Yjs updates outside the updater
        if (positionUpdates.length > 0) {
          queueMicrotask(() => graph.setNodePositionsBulk(positionUpdates));
        }
        if (yjsUpdates.length > 0) {
          queueMicrotask(() => emitNodeDragBatch(yjsUpdates));
        }

        return resolvedNodes;
      });
    }

    const scheduleCollisionResolution = (arrivedId: string): void => {
      pendingArrivalIdsRef.current.add(arrivedId);
      if (collisionScheduledRef.current) return;
      collisionScheduledRef.current = true;
      collisionFrameRef.current = requestAnimationFrame(() => {
        collisionFrameRef.current = null;
        collisionScheduledRef.current = false;
        const arrivals = pendingArrivalIdsRef.current;
        pendingArrivalIdsRef.current = new Set();
        resolveAndBroadcastCollisions(arrivals);
      });
    };

    const handleRemoteNodeUpdate = (update: NodeUpdate) => {
      const { session, graph } = useAppStore.getState();
      const localDisplayId = session.localPeerId ?? '__local__';
      const kind = resolveNodeUpdateKind(update);
      const space = resolveNodeUpdateSpace(update, kind);
      const viewport = getViewport();

      if (kind === 'commit') {
        transferLog(
          `[CrossDisplaySync] commit received: node=${update.id}, targetDisplay=${update.displayId}, isLocal=${update.displayId === localDisplayId}, graphHasNode=${graph.nodes.some(n => n.id === update.id)}`,
        );
      }

      const canvasPos = space === 'screen'
        ? screenToCanvas({ x: update.x, y: update.y }, viewport)
        : { x: update.x, y: update.y };
      const screenPos = space === 'screen'
        ? { x: update.x, y: update.y }
        : canvasToScreen({ x: update.x, y: update.y }, viewport);

      // ===================================================================
      // BRANCH 0: Clear transient nodes
      // ===================================================================
      if (kind === 'mirror-clear') {
        setNodes(prev => {
          const shouldClear = mirrorNodeIdsRef.current?.has(update.id) ?? false;
          if (!shouldClear) return prev;
          mirrorNodeIdsRef.current?.delete(update.id);
          return prev.filter(n => !(n.id === update.id && hasClassName(n, 'drag-mirror')));
        });
        return;
      }

      if (kind === 'preview-clear') {
        if (update.displayId !== localDisplayId) return;
        setNodes(prev => {
          const shouldClear = previewNodeIdsRef.current?.has(update.id) ?? false;
          if (!shouldClear) return prev;
          previewNodeIdsRef.current?.delete(update.id);
          return prev.filter(n => !(n.id === update.id && hasClassName(n, 'transfer-preview')));
        });
        return;
      }

      // ===================================================================
      // BRANCH 0: Drag mirror
      // ===================================================================
      if (kind === 'mirror') {
        if (update.displayId === localDisplayId) {
          setNodes(prev => {
            const existingIdx = prev.findIndex(n => n.id === update.id);
            if (existingIdx >= 0) {
              return prev.map(n =>
                n.id === update.id
                  ? {
                      ...n,
                      position: canvasPos,
                      className: 'drag-mirror',
                      data: {
                        ...(n.data as Record<string, unknown>),
                        isTransientRender: true,
                      },
                    }
                  : n
              );
            } else {
              const graphNode = graph.nodes.find(n => n.id === update.id);
              if (!graphNode) return prev;

              const entities = graph.currentEntities || [];
              const dims = getNodeDimensions(graphNode, entities);

              mirrorNodeIdsRef.current?.add(update.id);

              const shadowNode: Node = {
                id: update.id,
                type: 'entity-node' as const,
                position: canvasPos,
                className: 'drag-mirror',
                data: { entity: graphNode, isTransientRender: true },
                width: dims.width,
                height: dims.height,
                draggable: false,
                selectable: false,
              };

              return [...prev, shadowNode];
            }
          });
        } else {
          // This mirror update targets a different display; ignore it locally.
        }
        return;
      }

      if (mirrorNodeIdsRef.current?.has(update.id) && update.displayId !== localDisplayId) {
        setNodes(prev => {
          mirrorNodeIdsRef.current?.delete(update.id);
          return prev.filter(n => !(n.id === update.id && hasClassName(n, 'drag-mirror')));
        });
        return;
      }

      if (mirrorNodeIdsRef.current?.has(update.id) && update.displayId === localDisplayId) {
        mirrorNodeIdsRef.current?.delete(update.id);
      }

      // ===================================================================
      // BRANCH 1: Node assigned to this display
      // ===================================================================
      if (update.displayId === localDisplayId) {
        if (kind === 'drag') {
          setNodes(prev => prev.map(n =>
            n.id === update.id
              ? { ...n, position: canvasPos }
              : n
          ));
          return;
        }

        // -- 1a: Live preview (ghost node) --
        if (kind === 'preview') {
          const previewPos = canvasPos;

          setNodes(prev => {
            const existingIdx = prev.findIndex(n => n.id === update.id);
            if (existingIdx >= 0) {
              return prev.map(n =>
                n.id === update.id
                  ? {
                      ...n,
                      position: previewPos,
                      className: 'transfer-preview',
                      data: {
                        ...(n.data as Record<string, unknown>),
                        isTransientRender: true,
                      },
                    }
                  : n
              );
            } else {
              const graphNode = graph.nodes.find(n => n.id === update.id);
              if (!graphNode) return prev;

              const entities = graph.currentEntities || [];
              const dims = getNodeDimensions(graphNode, entities);

              previewNodeIdsRef.current?.add(update.id);

              const ghostNode: Node = {
                id: update.id,
                type: 'entity-node' as const,
                position: previewPos,
                className: 'transfer-preview',
                data: { entity: graphNode, isTransientRender: true },
                width: dims.width,
                height: dims.height,
                draggable: false,
                selectable: false,
              };

              return [...prev, ghostNode];
            }
          });
          return;
        }

        if (kind !== 'commit') return;

        // Keep graph-store ownership/position sync outside setNodes updater.
        // Calling store actions inside setState updater can trigger React's
        // "Cannot update a component while rendering a different component" warning.
        const existingFlowNode = getNodes().find((n) => n.id === update.id);
        const wasPreviewBeforeCommit = !!existingFlowNode
          && (previewNodeIdsRef.current?.has(update.id) ?? false);
        const canCreateNodeFromGraph = !existingFlowNode
          && graph.nodes.some((n) => n.id === update.id);

        transferLog(
          `[CrossDisplaySync] commit processing: node=${update.id}, existsInFlow=${!!existingFlowNode}, wasPreview=${wasPreviewBeforeCommit}, canCreate=${canCreateNodeFromGraph}, flowNodeClass=${existingFlowNode?.className ?? 'none'}`,
        );

        // Always update graph store for commits destined to this display.
        // Without this, nodes that exist in flow as mirrors (or other
        // transient states) keep the sender's displayId in the store.
        // On the next render cycle useLocalDisplayNodes filters them out
        // and the node disappears.
        graph.updateNodeDisplay(update.id, localDisplayId, canvasPos.x, canvasPos.y);
        if (space === 'screen' && session.isConnected) {
          queueMicrotask(() => {
            emitNodeDragBatch([{
              id: update.id,
              x: canvasPos.x,
              y: canvasPos.y,
              displayId: localDisplayId,
              kind: 'commit',
              space: 'canvas',
            }]);
          });
        }

        // -- 1b: Committed transfer --
        setNodes(prev => {
          const existingIdx = prev.findIndex(n => n.id === update.id);
          if (existingIdx >= 0) {
            const wasPreview = previewNodeIdsRef.current?.has(update.id);
            const existingClass = prev[existingIdx]?.className;
            transferLog(
              `[CrossDisplaySync] commit setNodes: node=${update.id}, exists=true, wasPreview=${wasPreview}, existingClass=${existingClass ?? 'none'}, prevCount=${prev.length}`,
            );

            if (wasPreview) {
              const commitPos = canvasPos;

              previewNodeIdsRef.current?.delete(update.id);
              animatingNodeIdsRef.current?.add(update.id);

              const commitNodeId = update.id;
              setTimeout(() => {
                setNodes(curr => curr.map(n =>
                  n.id === commitNodeId
                      ? {
                          ...n,
                          className: undefined,
                          draggable: true,
                          selectable: true,
                          data: {
                            ...(n.data as Record<string, unknown>),
                            isTransientRender: false,
                          },
                        }
                      : n
                ));
                animatingNodeIdsRef.current?.delete(commitNodeId);
                scheduleCollisionResolution(commitNodeId);
              }, COMMIT_ANIMATION_MS);

              return prev.map(n =>
                n.id === update.id
                  ? {
                      ...n,
                      position: commitPos,
                      className: 'transfer-commit',
                      draggable: false,
                      selectable: false,
                      data: {
                        ...(n.data as Record<string, unknown>),
                        isTransientRender: true,
                      },
                    }
                  : n
              );
            }

            // Node exists but wasn't a preview — could be a stale mirror
            // or a regular node. Reset className/draggable to ensure the
            // node is fully interactive after the commit.
            const existingNode = prev[existingIdx];
            const wasMirror = hasClassName(existingNode, 'drag-mirror');
            if (wasMirror) {
              mirrorNodeIdsRef.current?.delete(update.id);
            }
            return prev.map(n =>
              n.id === update.id
                ? {
                    ...n,
                    position: canvasPos,
                    className: undefined,
                    draggable: true,
                    selectable: true,
                    data: {
                      ...(n.data as Record<string, unknown>),
                      isTransientRender: false,
                    },
                  }
                : n
            );
          } else {
            const graphNode = graph.nodes.find(n => n.id === update.id);
            transferLog(
              `[CrossDisplaySync] commit setNodes: node=${update.id}, exists=false, graphNodeFound=${!!graphNode}, prevCount=${prev.length}`,
            );
            if (!graphNode) return prev;

            const entities = graph.currentEntities || [];
            const dims = getNodeDimensions(graphNode, entities);

            const { localPeer } = session;
            const entryDir = inferEntryDirection(
              screenPos.x,
              screenPos.y,
              localPeer.width,
              localPeer.height,
            );

            const canvasViewportW = localPeer.width / viewport.zoom;
            const canvasViewportH = localPeer.height / viewport.zoom;
            const entryEdgePos = computeEntryEdgePosition(
              entryDir,
              canvasPos.y,
              canvasPos.x,
              canvasViewportW,
              canvasViewportH,
            );

            animatingNodeIdsRef.current?.add(update.id);

            const newNode: Node = {
              id: update.id,
              type: 'entity-node' as const,
              position: entryEdgePos,
              className: 'transfer-enter-start',
              data: { entity: graphNode, isTransientRender: true },
              width: dims.width,
              height: dims.height,
              draggable: false,
              selectable: false,
            };

            const entryNodeId = update.id;
            const finalPos = canvasPos;
            requestAnimationFrame(() => {
              requestAnimationFrame(() => {
                setNodes(curr => curr.map(n =>
                  n.id === entryNodeId
                    ? {
                        ...n,
                        position: finalPos,
                        className: 'transfer-enter',
                        data: {
                          ...(n.data as Record<string, unknown>),
                          isTransientRender: true,
                        },
                      }
                    : n
                ));

                setTimeout(() => {
                  setNodes(curr => curr.map(n =>
                    n.id === entryNodeId
                      ? {
                          ...n,
                          className: undefined,
                          draggable: true,
                          selectable: true,
                          data: {
                            ...(n.data as Record<string, unknown>),
                            isTransientRender: false,
                          },
                        }
                      : n
                  ));
                  animatingNodeIdsRef.current?.delete(entryNodeId);
                  scheduleCollisionResolution(entryNodeId);
                }, ENTRY_ANIMATION_MS);
              });
            });

            return [...prev, newNode];
          }
        });
        return;
      }

      if (kind !== 'commit') return;

      // Keep ownership/position in the graph store in sync even when this
      // node is not currently rendered on this display.
      const currentGraphNode = graph.nodes.find((n) => n.id === update.id);
      const graphX = currentGraphNode?.x ?? update.x;
      const graphY = currentGraphNode?.y ?? update.y;
      graph.updateNodeDisplay(
        update.id,
        update.displayId,
        space === 'screen' ? graphX : update.x,
        space === 'screen' ? graphY : update.y,
      );

      // ===================================================================
      // BRANCH 2: Node assigned to a DIFFERENT display
      // ===================================================================
      setNodes(prev => {
        const existingNode = prev.find(n => n.id === update.id);
        if (!existingNode) return prev;

        previewNodeIdsRef.current?.delete(update.id);
        mirrorNodeIdsRef.current?.delete(update.id);

        // Ghost/mirror nodes can be removed immediately.
        if (
          hasClassName(existingNode, 'transfer-preview')
          || hasClassName(existingNode, 'drag-mirror')
        ) {
          animatingNodeIdsRef.current?.delete(update.id);
          return prev.filter(n => n.id !== update.id);
        }

        // If already exiting, keep current state and let existing timeout finish.
        if (hasClassName(existingNode, 'transfer-exit')) {
          return prev;
        }

        // Animate sender-side disappearance for chat/remote transfer commits.
        animatingNodeIdsRef.current?.add(update.id);
        const exitNodeId = update.id;
        setTimeout(() => {
          setNodes(curr => curr.filter(n => n.id !== exitNodeId));
          animatingNodeIdsRef.current?.delete(exitNodeId);
        }, EXIT_ANIMATION_MS);

        return prev.map(n =>
          n.id === update.id
            ? {
                ...n,
                className: 'transfer-exit',
                draggable: false,
                selectable: false,
                data: {
                  ...(n.data as Record<string, unknown>),
                  isTransientRender: true,
                },
              }
            : n
        );
      });
    };

    setNodeMovedCallback(handleRemoteNodeUpdate);
    setEphemeralDragCallback(handleRemoteNodeUpdate);

    return () => {
      if (collisionFrameRef.current != null) {
        cancelAnimationFrame(collisionFrameRef.current);
        collisionFrameRef.current = null;
      }
      collisionScheduledRef.current = false;
      pendingArrivalIdsRef.current.clear();
      setNodeMovedCallback(null);
      setEphemeralDragCallback(null);
    };
  }, [setNodes, getViewport, getNodes, animatingNodeIdsRef, previewNodeIdsRef, mirrorNodeIdsRef]);
}
