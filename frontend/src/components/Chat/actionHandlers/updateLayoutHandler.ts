import type { NodeUpdate } from '@/types/session';
import { useAppStore } from '@/stores/appStore';
import {
  summarizeDeltaChanges,
  resolveDisplayTransfers,
  announceTransfers,
  addActionStatusMessage,
} from '../chatPanelHelpers';
import type { ChatActionHandler, ActionContext } from './types';
import { getEntityId } from '@/utils/entityId';
import { broadcastUIState } from '@/services/yjs/uiState';
import { GATHER_PHASE_DELAY_MS } from '@/stores/slices/animationSlice';

/**
 * Apply the final layout delta and Yjs sync (phase 2 of staged animation,
 * or the only phase when no stages are present).
 */
function applyFinalLayout(ctx: ActionContext) {
  const { delta, graph, chat, session, emitDragBatch, data } = ctx;

  const { delta: transferredDelta, transfers } = resolveDisplayTransfers(
    delta,
    graph.nodes,
    session.virtualDesktop,
  );

  console.log('[Chat] Applying layout delta:', summarizeDeltaChanges(transferredDelta));

  announceTransfers(transfers, chat, session.virtualDesktop, session.isConnected, emitDragBatch);
  graph.applyLayoutDelta(transferredDelta);

  // Broadcast same-display moves to remote peers.
  if (session.isConnected && transferredDelta.updated_nodes.length) {
    const transferredIds = new Set(transfers.map((t) => t.entityId));
    const currentNodeMap = new Map(graph.nodes.map((n) => [getEntityId(n), n]));

    const yjsUpdates: NodeUpdate[] = [];
    for (const update of transferredDelta.updated_nodes) {
      if (transferredIds.has(update.entity_id)) continue;

      const currentNode = currentNodeMap.get(update.entity_id);
      const displayId = update.display_id
        || currentNode?.displayId
        || session.localPeerId
        || '__local__';

      yjsUpdates.push({
        id: update.entity_id,
        x: update.x,
        y: update.y,
        displayId,
        kind: 'commit',
        space: 'canvas',
      });
    }
    if (yjsUpdates.length > 0) {
      emitDragBatch(yjsUpdates);
    }
  }

  // Apply per-display camera adjustments from the layout agent.
  const cameraUpdates = delta.camera_updates;
  if (cameraUpdates) {
    const localId = session.localPeerId ?? 'local';
    for (const [peerId, camera] of Object.entries(cameraUpdates)) {
      if (peerId === localId) {
        graph.setPendingCameraCommand({ kind: 'setViewport', pan_x: camera.pan_x, pan_y: camera.pan_y, zoom: camera.zoom });
      } else if (session.isConnected) {
        broadcastUIState('cameraCommand', JSON.stringify({
          target_peer_id: peerId,
          pan_x: camera.pan_x,
          pan_y: camera.pan_y,
          zoom: camera.zoom,
        }));
      }
    }
  }

  addActionStatusMessage(chat, data.action);

  const label = data.action?.description
    ? `Chat: ${data.action.description}`
    : 'Chat: Layout update';
  const currentNodes = useAppStore.getState().graph.nodes;
  useAppStore.getState().timeline.recordSnapshot(label, 'chat', currentNodes);
}

/**
 * Handles structural layout changes: moved, added, or removed nodes.
 *
 * When layout_stages are present, animates in two phases:
 *   Phase 1: CSS-only animation to group centers (no store/Yjs position changes)
 *   Phase 2: Apply final positions to store + Yjs (CSS transitions to final)
 *
 * The animation is synchronized across displays via Yjs events, but positions
 * are only committed once (in Phase 2) to avoid drift bugs.
 *
 * Used by action type: update_layout.
 */
export const updateLayoutHandler: ChatActionHandler = {
  recordsTimeline: true,

  apply(ctx: ActionContext) {
    const { layoutStages, session } = ctx;
    const animation = useAppStore.getState().animation;

    // No stages → apply final layout immediately (existing behavior)
    if (!layoutStages?.length) {
      applyFinalLayout(ctx);
      return;
    }

    // Phase 1: CSS-only animation to group centers
    // Store/Yjs positions are NOT modified - only visual CSS transforms
    console.log('[Chat] Layout stage animation: CSS gather to group centers');

    // Set local animation state (triggers CSS transforms)
    animation.setGatherTargets(layoutStages, 'local');

    // Broadcast animation event to remote peers (they'll run their own CSS animation)
    if (session.isConnected) {
      broadcastUIState('groupAnimation', JSON.stringify({
        type: 'gather_start',
        stages: layoutStages,
      }));
    }

    // Phase 2: After CSS animation completes, apply final positions
    setTimeout(() => {
      console.log('[Chat] Layout stage animation: applying final positions');

      // Clear animation state (removes CSS transforms)
      animation.clearGatherTargets('local');

      // Broadcast animation end to remote peers
      if (session.isConnected) {
        broadcastUIState('groupAnimation', JSON.stringify({
          type: 'gather_end',
        }));
      }

      // Now apply the actual final positions to store + Yjs
      applyFinalLayout(ctx);
    }, GATHER_PHASE_DELAY_MS);
  },
};
