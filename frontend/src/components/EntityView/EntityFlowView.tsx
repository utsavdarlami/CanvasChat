/**
 * EntityFlowView - Main React Flow canvas for entity graph visualization.
 *
 * Renders entities as interactive nodes on a canvas.
 * Supports partition and region overlays for hierarchical grouping visualization.
 *
 * Multi-display: Uses display-local viewport model. Each peer has its own
 * independent coordinate space. Only nodes assigned to this peer (via displayId)
 * are rendered. React Flow zoom/pan work freely within each display.
 *
 * Ctrl+drag enables cross-display node transfer: viewport freezes,
 * and dragging a node past the viewport boundary transfers it to the
 * adjacent display.
 *
 * Coordinates are canvas-only: backend returns canvas coords, frontend uses
 * them directly. No abstract-to-canvas scaling pipeline.
 */
import React, { startTransition, useEffect, useLayoutEffect, useRef, useState, useCallback } from 'react';
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  Controls,
  useNodesState,
  useReactFlow,
  type Node as FlowNode,
  type Viewport,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { setUserInteracting } from './vegaSpecCache';
import { setWorkerInteracting } from './vegaWorkerService';
import { GroupOverlayLayer } from './GroupOverlayLayer';
import { ExportImageButton } from './ExportImageButton';


import { useAppStore } from '@/stores/appStore';
import { useEntityFlowGraph } from '@/stores/graphStore';
import { useEntityFlowSession } from '@/stores/sessionStore';
import { EntityNode } from './EntityNode';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { useLocalDisplayNodes } from './hooks/useLocalDisplayNodes';
import { useEntityFlowNodes } from './hooks/useEntityFlowNodes';
import { useEntityFlowCallbacks } from './hooks/useEntityFlowCallbacks';
import { useCtrlKey } from './hooks/useCtrlKey';
import { setLiveFlowNodes } from './hooks/useFlowNodeDebug';
import { updatePeerPresence } from '@/services/yjs/awareness';
import { emitNodeDragBatch } from '@/services/yjsService';
import { resolveCollisions, resolveByIntersections } from '@/utils/collision';
import { COLLISION_CONFIG } from '@/utils/constants';
import { captureSnapshot } from '@/utils/captureSnapshot';


// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Custom node types for React Flow */
const nodeTypes = {
  'entity-node': EntityNode,
};

const CAMERA_FOCUS_DURATION_MS = 450;
const CAMERA_FOCUS_PADDING = 0.2;
const CAMERA_FOCUS_MIN_ZOOM = 0.05;
const CAMERA_FOCUS_MAX_ZOOM = 4;
const CAMERA_PAN_EPSILON = 0.5;
const CAMERA_ZOOM_EPSILON = 0.001;

// Stable object refs — inline objects here would create new refs on every render
const DEFAULT_VIEWPORT: Viewport = { x: 0, y: 0, zoom: 1 };
const FIT_VIEW_OPTIONS = { padding: 0.2, maxZoom: 2, minZoom: 0.1 };

type NodePositionAdjustment = {
  id: string;
  x: number;
  y: number;
};

function resolveChatCollisionAdjustments(
  mergedNodes: FlowNode[],
  chatUpdatedNodeIds: Set<string>,
): {
  resolvedNodes: FlowNode[];
  adjustments: NodePositionAdjustment[];
} {
  if (chatUpdatedNodeIds.size > mergedNodes.length * 0.5) {
    console.warn(
      '[EntityFlowView] Large chat update set for collision resolution',
      { updated: chatUpdatedNodeIds.size, total: mergedNodes.length },
    );
  }

  const { resolved: resolvedNodes, adjustedIds } = resolveByIntersections(
    mergedNodes,
    chatUpdatedNodeIds,
    COLLISION_CONFIG,
  );

  if (adjustedIds.size === 0) {
    return { resolvedNodes, adjustments: [] };
  }

  const resolvedById = new Map(resolvedNodes.map((node) => [node.id, node]));
  const adjustments: NodePositionAdjustment[] = [];

  for (const adjustedId of adjustedIds) {
    const resolvedNode = resolvedById.get(adjustedId);
    if (!resolvedNode) continue;
    adjustments.push({
      id: resolvedNode.id,
      x: resolvedNode.position.x,
      y: resolvedNode.position.y,
    });
  }

  return { resolvedNodes, adjustments };
}

// ---------------------------------------------------------------------------
// Inner Component (must be inside ReactFlowProvider for useReactFlow access)
// ---------------------------------------------------------------------------

const EntityFlowViewInner: React.FC = () => {
  const {
    nodes: graphNodes,
    currentEntities,
    graphMetadata,
    chatUpdatedNodeIds,
    highlightedNodeIds,
    pendingCameraCommand,
    setNodePositionsBulk,
    clearChatUpdatedNodeIds,
    clearHighlightedNodeIds,
    setPendingCameraCommand,
  } = useEntityFlowGraph();

  const clearGroupOverlays = useAppStore((s) => s.graph.clearGroupOverlays);
  const groupOverlaysCount = useAppStore((s) => s.graph.groupOverlays.length);

  const {
    isConnected,
    localPeerId,
    updateLocalPeerDimensions,
  } = useEntityFlowSession();


  const containerRef = useRef<HTMLDivElement>(null);

  // -- Ctrl key + drag state for cross-display transfer mode ----------------
  const isCtrlHeld = useCtrlKey();
  const [isDragging, setIsDragging] = useState(false);
  const [isSelecting, setIsSelecting] = useState(false);
  const isPanningRef = useRef(false);
  const moveStartViewportRef = useRef<Viewport | null>(null);
  const { setViewport, getViewport, setCenter, fitView, fitBounds, getNodes } = useReactFlow();

  // Pause chart render queue while user is interacting (drag or pan)
  const setIsDraggingWrapped = useCallback((dragging: boolean) => {
    setIsDragging(dragging);
    const interacting = dragging || isPanningRef.current;
    setUserInteracting(interacting);
    setWorkerInteracting(interacting);
  }, []);
  const handleMoveStart = useCallback((_event: unknown, viewport: Viewport) => {
    moveStartViewportRef.current = viewport;
    isPanningRef.current = true;
    setUserInteracting(true);
    setWorkerInteracting(true);
  }, []);
  const handleMoveEnd = useCallback((_event: unknown, viewport: Viewport) => {
    const startViewport = moveStartViewportRef.current;
    moveStartViewportRef.current = null;

    isPanningRef.current = false;
    const interacting = isDragging;
    setUserInteracting(interacting);
    setWorkerInteracting(interacting);

    if (isDragging) return;
    if (!startViewport) return;
    const panX = Math.abs(viewport.x - startViewport.x);
    const panY = Math.abs(viewport.y - startViewport.y);
    const zoomDelta = viewport.zoom - startViewport.zoom;

    const didPan = panX > CAMERA_PAN_EPSILON || panY > CAMERA_PAN_EPSILON;
    const didZoom = Math.abs(zoomDelta) > CAMERA_ZOOM_EPSILON;

    if (!didPan && !didZoom) return;

    let movementLabel = 'camera_move';
    if (didPan && didZoom) movementLabel = zoomDelta < 0 ? 'pan_zoom_out' : 'pan_zoom_in';
    else if (didPan) movementLabel = 'pan';
    else movementLabel = zoomDelta < 0 ? 'zoom_out' : 'zoom_in';

    captureSnapshot(movementLabel);
  }, [isDragging]);
  const frozenViewportRef = useRef<Viewport | null>(null);
  const isCrossDisplayMode =
    isConnected && isDragging && (isCtrlHeld || frozenViewportRef.current !== null);
  const clearNativeSelection = useCallback(() => {
    window.getSelection()?.removeAllRanges();
  }, []);
  const handleSelectionStart = useCallback(() => {
    setIsSelecting(true);
    clearNativeSelection();
  }, [clearNativeSelection]);
  const handleSelectionEnd = useCallback(() => {
    setIsSelecting(false);
  }, []);

  // Hard reset interaction gate on unmount so queued chart renders cannot remain paused.
  useEffect(() => () => {
    setUserInteracting(false);
    setWorkerInteracting(false);
  }, []);

  // Safety net: if focus/visibility changes mid-drag or mid-pan, clear interaction state.
  useEffect(() => {
    const resetInteractionState = () => {
      isPanningRef.current = false;
      moveStartViewportRef.current = null;
      frozenViewportRef.current = null;
      setIsDragging(false);
      setIsSelecting(false);
      setUserInteracting(false);
      setWorkerInteracting(false);
    };

    const onVisibilityChange = () => {
      if (document.hidden) {
        resetInteractionState();
      }
    };

    window.addEventListener('blur', resetInteractionState);
    document.addEventListener('visibilitychange', onVisibilityChange);
    return () => {
      window.removeEventListener('blur', resetInteractionState);
      document.removeEventListener('visibilitychange', onVisibilityChange);
    };
  }, []);

  // Freeze/unfreeze based on cross-display mode changes
  useEffect(() => {
    if (isCrossDisplayMode) {
      if (!frozenViewportRef.current) {
        frozenViewportRef.current = getViewport();
      }
    } else {
      frozenViewportRef.current = null;
    }
  }, [isCrossDisplayMode, getViewport]);

  // -- Camera tracking: throttled onMove → store + awareness ----------------
  const cameraThrottleRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleMove = useCallback((_event: any, viewport: Viewport) => {
    const frozen = frozenViewportRef.current;
    if (frozen) {
      const dx = Math.abs(viewport.x - frozen.x);
      const dy = Math.abs(viewport.y - frozen.y);
      const dz = Math.abs(viewport.zoom - frozen.zoom);
      if (dx > 0.5 || dy > 0.5 || dz > 0.001) {
        setViewport(frozen, { duration: 0 });
      }
      return;
    }

    if (cameraThrottleRef.current) return;
    cameraThrottleRef.current = setTimeout(() => {
      cameraThrottleRef.current = null;
      const session = useAppStore.getState().session;
      session.setLocalPeerCamera(viewport.x, viewport.y, viewport.zoom);
      if (session.isConnected) {
        updatePeerPresence({
          ...session.localPeer,
          camera: { x: viewport.x, y: viewport.y, zoom: viewport.zoom },
        });
      }
    }, 300);
  }, [setViewport]);

  // Cleanup throttle timer on unmount
  useEffect(() => {
    return () => {
      if (cameraThrottleRef.current) {
        clearTimeout(cameraThrottleRef.current);
      }
    };
  }, []);

  // Keep peer viewport dimensions aligned with the actual rendered flow area.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    let lastW = -1;
    let lastH = -1;
    const pushSize = (width: number, height: number) => {
      const w = Math.round(width);
      const h = Math.round(height);
      if (w <= 0 || h <= 0) return;
      if (w === lastW && h === lastH) return;
      lastW = w;
      lastH = h;
      updateLocalPeerDimensions(w, h);
    };

    pushSize(el.clientWidth, el.clientHeight);

    if (typeof ResizeObserver !== 'undefined') {
      const observer = new ResizeObserver((entries) => {
        const entry = entries[0];
        if (!entry) return;
        pushSize(entry.contentRect.width, entry.contentRect.height);
      });
      observer.observe(el);
      return () => observer.disconnect();
    }

    const onResize = () => pushSize(el.clientWidth, el.clientHeight);
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, [updateLocalPeerDimensions]);

  // -- Filter nodes to this display ----------------------------------
  const { localNodes } = useLocalDisplayNodes(
    graphNodes,
    localPeerId,
    isConnected
  );

  // -- Nodes (canvas coords used directly) ----------------------------
  const {
    initialNodes,
  } = useEntityFlowNodes(
    localNodes,
    currentEntities,
    graphMetadata,
    highlightedNodeIds,
  );

  const hasSeededYjsRef = useRef(false);
  const prevNodeIdsKeyRef = useRef<string>('');

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);

  // Late-binding Yjs seed fallback: only fires if the merge-effect reset branch
  // ran without `localPeerId` available. By the time `localPeerId` arrives,
  // RF's live `nodes` have been collision-resolved by the reset branch, so
  // sourcing from `nodes` here emits resolved positions.
  useEffect(() => {
    if (hasSeededYjsRef.current || nodes.length === 0 || !localPeerId) return;
    hasSeededYjsRef.current = true;

    const seedUpdates = nodes.map(node => ({
      id: node.id,
      x: node.position.x,
      y: node.position.y,
      displayId: localPeerId,
      kind: 'commit' as const,
      space: 'canvas' as const,
    }));
    if (seedUpdates.length > 0) {
      emitNodeDragBatch(seedUpdates);
    }
  }, [nodes, localPeerId]);

  // -- Callbacks --
  const {
    handleNodeDragStart,
    handleNodeDrag,
    handleNodeDragStop,
    handleSelectionChange,
    crossingPeerLabel,
    transferModeActive,
    animatingNodeIdsRef,
    previewNodeIdsRef,
    mirrorNodeIdsRef,
  } = useEntityFlowCallbacks(
    setNodes,
    setIsDraggingWrapped,
    frozenViewportRef,
  );

  // Sync nodes when graph store data changes. useLayoutEffect ensures the
  // collision-resolved `setNodes(seeded)` commits before the browser paints,
  // so the user never sees a frame of raw (potentially overlapping) positions.
  const prevNodeIdsRef = useRef<Set<string>>(new Set());

  useLayoutEffect(() => {
    const incomingIds = new Set(initialNodes.map(n => n.id));
    const prevIds = prevNodeIdsRef.current;
    const shouldResolveChatCollisions = chatUpdatedNodeIds.size > 0;

    const isFullReset = prevIds.size > 0
      && incomingIds.size > 0
      && [...incomingIds].every(id => !prevIds.has(id));

    prevNodeIdsRef.current = incomingIds;

    if (isFullReset || prevIds.size === 0) {
      const seeded = resolveCollisions(initialNodes, COLLISION_CONFIG);
      startTransition(() => {
        setNodes(seeded);
      });

      // Seed Yjs with the same `seeded` array we just committed to RF, gated
      // on entity ID set so a data reload re-seeds. If localPeerId isn't ready
      // yet, the late-binding fallback effect handles it once it arrives.
      const idKey = initialNodes.map(n => n.id).sort().join(',');
      if (idKey !== prevNodeIdsKeyRef.current) {
        prevNodeIdsKeyRef.current = idKey;
        hasSeededYjsRef.current = false;
      }
      if (!hasSeededYjsRef.current && localPeerId && seeded.length > 0) {
        hasSeededYjsRef.current = true;
        emitNodeDragBatch(seeded.map(node => ({
          id: node.id,
          x: node.position.x,
          y: node.position.y,
          displayId: localPeerId,
          kind: 'commit' as const,
          space: 'canvas' as const,
        })));
      }

      if (shouldResolveChatCollisions) clearChatUpdatedNodeIds();
      return;
    }

    let collisionAdjustedNodes: NodePositionAdjustment[] = [];
    const currentNodesSync = getNodes();

    const currentMap = new Map(currentNodesSync.map(n => [n.id, n]));
    const animating = animatingNodeIdsRef.current;
    const previewing = previewNodeIdsRef.current;
    const mirroring = mirrorNodeIdsRef.current;

    const mergedForCollision: FlowNode[] = [];
    for (const incoming of initialNodes) {
      const existing = currentMap.get(incoming.id);
      const isTransientNode = animating.has(incoming.id)
        || previewing.has(incoming.id)
        || mirroring.has(incoming.id);
      if (isTransientNode && existing) {
        mergedForCollision.push(existing);
      } else if (chatUpdatedNodeIds.has(incoming.id)) {
        mergedForCollision.push(incoming);
      } else if (existing) {
        mergedForCollision.push({
          ...incoming,
          position: existing.position,
        });
      } else {
        mergedForCollision.push(incoming);
      }
    }

    if (shouldResolveChatCollisions) {
      const { adjustments } = resolveChatCollisionAdjustments(
        mergedForCollision,
        chatUpdatedNodeIds,
      );
      collisionAdjustedNodes = adjustments;
    }

    // Cross-display transfers need synchronous updates for correct drop behavior.
    // Only defer with startTransition when no transient nodes are active.
    const hasTransientNodes = animating.size > 0 || previewing.size > 0 || mirroring.size > 0;

    const applyMerge = () => {
      setNodes((currentNodes: FlowNode[]) => {
        const currentMap = new Map(currentNodes.map(n => [n.id, n]));
        const merged: FlowNode[] = [];
        for (const incoming of initialNodes) {
          const existing = currentMap.get(incoming.id);
          const isTransientNode = animating.has(incoming.id)
            || previewing.has(incoming.id)
            || mirroring.has(incoming.id);
          if (isTransientNode && existing) {
            merged.push(existing);
          } else if (chatUpdatedNodeIds.has(incoming.id)) {
            merged.push(incoming);
          } else if (existing) {
            merged.push({
              ...incoming,
              position: existing.position,
            });
          } else {
            merged.push(incoming);
          }
        }

        // Also preserve transient nodes not in initialNodes
        for (const current of currentNodes) {
          const isTransientNode = animating.has(current.id)
            || previewing.has(current.id)
            || mirroring.has(current.id);
          if (!incomingIds.has(current.id) && isTransientNode) {
            merged.push(current);
          }
        }

        if (!shouldResolveChatCollisions) {
          return merged;
        }

        const adjustmentsMap = new Map(collisionAdjustedNodes.map(a => [a.id, a]));
        const resolvedNodes = merged.map(node => {
          const adjustment = adjustmentsMap.get(node.id);
          if (adjustment) {
            return { ...node, position: { x: adjustment.x, y: adjustment.y } };
          }
          return node;
        });

        return resolvedNodes;
      });
    };

    if (hasTransientNodes || shouldResolveChatCollisions) {
      applyMerge();
    } else {
      startTransition(applyMerge);
    }

    if (shouldResolveChatCollisions) {
      clearChatUpdatedNodeIds();
    }

    if (!shouldResolveChatCollisions || collisionAdjustedNodes.length === 0) {
      return;
    }

    const localDisplayId = localPeerId ?? '__local__';
    const storeNodes = useAppStore.getState().graph.nodes;
    const graphNodeById = new Map(storeNodes.map((node) => [node.id, node]));

    const positionUpdates: Array<{ id: string; x: number; y: number }> = [];
    const yjsUpdates: Array<{ id: string; x: number; y: number; displayId: string; kind: 'commit'; space: 'canvas' }> = [];

    for (const adjusted of collisionAdjustedNodes) {
      const graphNode = graphNodeById.get(adjusted.id);
      if (!graphNode) continue;
      if (isConnected && graphNode.displayId && graphNode.displayId !== localDisplayId) continue;

      positionUpdates.push({ id: adjusted.id, x: adjusted.x, y: adjusted.y });
      if (isConnected) {
        yjsUpdates.push({
          id: adjusted.id,
          x: adjusted.x,
          y: adjusted.y,
          displayId: localDisplayId,
          kind: 'commit',
          space: 'canvas',
        });
      }
    }

    if (positionUpdates.length > 0) {
      setNodePositionsBulk(positionUpdates);
    }

    if (yjsUpdates.length > 0) {
      emitNodeDragBatch(yjsUpdates);
    }

  }, [
    initialNodes,
    setNodes,
    getNodes,
    chatUpdatedNodeIds,
    clearChatUpdatedNodeIds,
    isConnected,
    localPeerId,
    setNodePositionsBulk,
  ]);

  // Unified camera command effect — single entry point for all camera movements.
  useEffect(() => {
    if (!pendingCameraCommand || isCrossDisplayMode) return;

    const cmd = pendingCameraCommand;
    setPendingCameraCommand(null);

    const runCamera = async () => {
      try {
        if (cmd.kind === 'setViewport') {
          const { pan_x, pan_y, zoom } = cmd;
          setViewport(
            { x: pan_x, y: pan_y, zoom },
            { duration: CAMERA_FOCUS_DURATION_MS },
          );

          // Keep session store and peer awareness in sync
          const session = useAppStore.getState().session;
          session.setLocalPeerCamera(pan_x, pan_y, zoom);
          if (session.isConnected) {
            updatePeerPresence({
              ...session.localPeer,
              camera: { x: pan_x, y: pan_y, zoom },
            });
          }
          return;
        }

        if (cmd.kind === 'fitBounds') {
          await fitBounds(cmd.bounds, {
            duration: CAMERA_FOCUS_DURATION_MS,
            padding: cmd.padding ?? CAMERA_FOCUS_PADDING,
          });
          return;
        }

        // kind === 'fitNodes' — read nodes imperatively to avoid re-running on every node change
        const currentNodes = getNodes();
        const targets = currentNodes.filter((node) => cmd.nodeIds.includes(node.id));
        if (targets.length === 0) return;

        if (targets.length === 1) {
          const target = targets[0];
          const width = target.measured?.width ?? target.width ?? 0;
          const height = target.measured?.height ?? target.height ?? 0;
          const centerX = target.position.x + width / 2;
          const centerY = target.position.y + height / 2;
          const currentZoom = getViewport().zoom;

          await setCenter(centerX, centerY, {
            zoom: currentZoom,
            duration: CAMERA_FOCUS_DURATION_MS,
          });
          return;
        }

        await fitView({
          nodes: targets.map((node) => ({ id: node.id })),
          duration: CAMERA_FOCUS_DURATION_MS,
          padding: CAMERA_FOCUS_PADDING,
          minZoom: CAMERA_FOCUS_MIN_ZOOM,
          maxZoom: CAMERA_FOCUS_MAX_ZOOM,
        });
      } catch (error) {
        console.error('[EntityFlowView] Failed to apply camera command:', error);
      }
    };

    void runCamera();
  }, [pendingCameraCommand, setPendingCameraCommand, isCrossDisplayMode, getViewport, getNodes, setCenter, fitView, fitBounds, setViewport]);

  // Clear highlights and group overlays on intentional user interaction
  // Pan/zoom (wheel, canvas drag) should NOT dismiss — users need to inspect overlays.
  // Only clear on: Escape key, or clicking on a node.
  useEffect(() => {
    if (highlightedNodeIds.size === 0 && groupOverlaysCount === 0) return;

    const clearAll = () => {
      clearHighlightedNodeIds();
      clearGroupOverlays();
    };

    const handleKeydown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') clearAll();
    };

    const handlePointerdown = (e: PointerEvent) => {
      // Only clear when clicking on a node, not the canvas background or other UI
      const target = e.target as HTMLElement | null;
      if (target?.closest('.react-flow__node')) clearAll();
    };

    window.addEventListener('keydown', handleKeydown, true);
    window.addEventListener('pointerdown', handlePointerdown, true);

    return () => {
      window.removeEventListener('keydown', handleKeydown, true);
      window.removeEventListener('pointerdown', handlePointerdown, true);
    };
  }, [highlightedNodeIds, clearHighlightedNodeIds, groupOverlaysCount, clearGroupOverlays]);

  // Push live React Flow nodes to the debug bridge for DiagnosticPanel
  useEffect(() => { setLiveFlowNodes(nodes); }, [nodes]);

  // -- Render -------------------------------------------------------------
  return (
    <div ref={containerRef} style={{ width: '100%', height: '100%', position: 'relative' }}>
      {/* Cross-display transfer mode indicator */}
      {isCrossDisplayMode && (
        <div style={{
          position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
          border: '2px solid rgba(59,130,246,0.5)',
          borderRadius: 4,
          pointerEvents: 'none', zIndex: 5,
        }} />
      )}
      {crossingPeerLabel && (
        <div style={{
          position: 'absolute', top: 12, left: '50%', transform: 'translateX(-50%)',
          background: 'rgba(59,130,246,0.9)', color: '#fff', borderRadius: 6,
          padding: '4px 12px', fontSize: 13, pointerEvents: 'none', zIndex: 10,
        }}>
          Moving to <strong>{crossingPeerLabel}</strong>
        </div>
      )}
      {transferModeActive && !crossingPeerLabel && (
        <div style={{
          position: 'absolute', top: 12, left: '50%', transform: 'translateX(-50%)',
          background: 'rgba(59,130,246,0.6)', color: '#fff', borderRadius: 6,
          padding: '4px 12px', fontSize: 12, pointerEvents: 'none', zIndex: 10,
        }}>
          Transfer mode (Ctrl+drag)
        </div>
      )}
      <ReactFlow
        className={[
          isDragging ? 'dragging' : '',
          isSelecting ? 'selecting' : '',
        ].filter(Boolean).join(' ') || undefined}
        nodes={nodes}
        onNodesChange={onNodesChange}
        onPaneClick={clearNativeSelection}
        onSelectionStart={handleSelectionStart}
        onSelectionEnd={handleSelectionEnd}
        onNodeDragStart={handleNodeDragStart}
        onNodeDrag={handleNodeDrag}
        onNodeDragStop={(event, node, nodeList) => {
          handleNodeDragStop(event, node, nodeList);
          captureSnapshot('user_drag');
        }}
        onSelectionChange={handleSelectionChange}
        onMove={handleMove}
        onMoveStart={handleMoveStart}
        onMoveEnd={handleMoveEnd}
        nodeTypes={nodeTypes}
        defaultViewport={DEFAULT_VIEWPORT}
        fitView={!isConnected}
        fitViewOptions={FIT_VIEW_OPTIONS}
        minZoom={0.05}
        maxZoom={4}
        panOnDrag={!isCrossDisplayMode}
        zoomOnScroll={!isCrossDisplayMode}
        zoomOnPinch={!isCrossDisplayMode}
        zoomOnDoubleClick={!isCrossDisplayMode}
        panOnScroll={false}
        autoPanOnNodeDrag={!isCrossDisplayMode}
        preventScrolling={true}
      >
        <Background />
        <GroupOverlayLayer />
        <Controls />
        <ExportImageButton />
      </ReactFlow>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Outer Component (provides ReactFlowProvider context)
// ---------------------------------------------------------------------------

export const EntityFlowView: React.FC = () => {
  return (
    <ErrorBoundary
      fallback={
        <div style={{
          width: '100%', height: '100%',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: '#f5f5f5',
        }}>
          <div style={{ textAlign: 'center', padding: '2rem' }}>
            <h2>Entity View Error</h2>
            <p>Failed to render the entity graph view.</p>
            <p style={{ fontSize: '0.9em', color: '#666' }}>
              Check the console for more details.
            </p>
          </div>
        </div>
      }
    >
      <ReactFlowProvider>
        <EntityFlowViewInner />
      </ReactFlowProvider>
    </ErrorBoundary>
  );
};
