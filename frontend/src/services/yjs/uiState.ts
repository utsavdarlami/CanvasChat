import * as Y from 'yjs';
import { useAppStore } from '@/stores/appStore';
import { useHighlightStore, type SerializedHighlights } from '@/stores/highlightStore';

type UIStateValue = string | string[] | null;

let sharedUIState: Y.Map<UIStateValue> | null = null;
let uiStateObserver: ((event: Y.YMapEvent<UIStateValue>, transaction: Y.Transaction) => void) | null = null;

export function setupUIState(doc: Y.Doc) {
  sharedUIState = doc.getMap('sharedUIState');

  // --- sharedUIState observer: sync cross-display UI state ---
  // Use source='remote' when applying observer updates so store actions skip
  // re-broadcasting and avoid write-back loops.
  uiStateObserver = (event, transaction) => {
    if (!sharedUIState || transaction.origin === 'local') return;

    let shouldApplyHighlightState = false;

    event.keysChanged.forEach((key) => {
      const val = sharedUIState!.get(key);
      
      if (key === 'activePanelId') {
        const currentActive = useAppStore.getState().entity.activePanelId;
        if (currentActive !== val) {
          if (val === null) {
            useAppStore.getState().entity.closeAllPanels('remote');
          } else {
            useAppStore.getState().entity.setActivePanel(val as string, 'remote');
          }
        }
      }

      if (key === 'highlightedNodeIds' || key === 'highlightedNodeColors') {
        shouldApplyHighlightState = true;
      }

      if (key === 'selectedEntityIds') {
        const entityIds = Array.isArray(val) ? val as string[] : [];
        const graph = useAppStore.getState().graph;
        if (entityIds.length > 0) {
          graph.setSelectedEntityIds(entityIds, 'remote');
        } else {
          graph.clearSelectedEntityIds('remote');
        }
      }

      if (key === 'entityTags') {
        if (typeof val !== 'string') return;
        try {
          const parsed = JSON.parse(val) as unknown;
          if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
            useAppStore.getState().graph.setEntityTags(parsed as Record<string, string[]>, 'remote');
          }
        } catch {
          /* ignore malformed payload */
        }
      }

      if (key === 'textHighlights') {
        if (typeof val !== 'string') return;
        try {
          const parsed = JSON.parse(val) as unknown;
          if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
            useHighlightStore.getState().setAllHighlights(parsed as SerializedHighlights, 'remote');
          }
        } catch {
          /* ignore malformed payload */
        }
      }

      if (key === 'groupOverlays') {
        if (typeof val !== 'string') return;
        try {
          const parsed = JSON.parse(val) as unknown;
          if (Array.isArray(parsed) && parsed.length > 0) {
            useAppStore.getState().graph.setGroupOverlays(parsed as import('@/types/api').GroupOverlay[], 'remote');
          } else {
            useAppStore.getState().graph.clearGroupOverlays('remote');
          }
        } catch {
          /* ignore malformed payload */
        }
      }

      if (key === 'cameraCommand') {
        if (typeof val !== 'string') return;
        try {
          const cmd = JSON.parse(val) as { target_peer_id?: string; pan_x?: number; pan_y?: number; zoom?: number };
          const localPeerId = useAppStore.getState().session.localPeerId;
          if (
            cmd.target_peer_id === localPeerId
            && typeof cmd.pan_x === 'number'
            && typeof cmd.pan_y === 'number'
            && typeof cmd.zoom === 'number'
          ) {
            useAppStore.getState().graph.setPendingCameraCommand(
              { kind: 'setViewport', pan_x: cmd.pan_x, pan_y: cmd.pan_y, zoom: cmd.zoom },
            );
          }
        } catch {
          /* ignore malformed payload */
        }
      }

      if (key === 'timelineIndex') {
        if (typeof val !== 'string') return;
        try {
          const newIndex = parseInt(val, 10);
          if (!isNaN(newIndex)) {
            useAppStore.getState().timeline.setRemoteCurrentIndex(newIndex);
          }
        } catch {
          /* ignore malformed payload */
        }
      }

      if (key === 'groupAnimation') {
        if (typeof val !== 'string') return;
        try {
          const parsed = JSON.parse(val) as { type: string; stages?: unknown[] };
          if (parsed.type === 'gather_start' && Array.isArray(parsed.stages)) {
            useAppStore.getState().animation.setGatherTargets(
              parsed.stages as import('@/types/api').LayoutStage[],
              'remote',
            );
          } else if (parsed.type === 'gather_end') {
            useAppStore.getState().animation.clearGatherTargets('remote');
          }
        } catch {
          /* ignore malformed payload */
        }
      }
    });

    if (shouldApplyHighlightState) {
      const graph = useAppStore.getState().graph;
      const rawIds = sharedUIState.get('highlightedNodeIds');
      const nodeIds = Array.isArray(rawIds) ? rawIds as string[] : [];

      const rawColors = sharedUIState.get('highlightedNodeColors');
      let nodeColors: Record<string, string> = {};
      if (typeof rawColors === 'string') {
        try {
          const parsed = JSON.parse(rawColors) as unknown;
          if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
            nodeColors = Object.fromEntries(
              Object.entries(parsed).filter(
                ([, value]) => typeof value === 'string' && value.trim().length > 0,
              ),
            ) as Record<string, string>;
          }
        } catch {
          /* ignore malformed payload */
        }
      }

      if (nodeIds.length > 0) {
        graph.setHighlightedNodeIds(nodeIds, nodeColors, 'remote');
      } else {
        graph.clearHighlightedNodeIds('remote');
      }
    }
  };
  sharedUIState.observe(uiStateObserver);
}

export function teardownUIState() {
  if (sharedUIState && uiStateObserver) {
    sharedUIState.unobserve(uiStateObserver);
  }
  sharedUIState = null;
  uiStateObserver = null;
}

/**
 * Broadcast UI state to the room (like active entity, highlighted/focused nodes).
 */
export function broadcastUIState(
  key: 'activePanelId' | 'highlightedNodeIds' | 'highlightedNodeColors' | 'selectedEntityIds' | 'entityTags' | 'textHighlights' | 'groupOverlays' | 'cameraCommand' | 'timelineIndex' | 'groupAnimation',
  value: UIStateValue,
): void {
  if (!sharedUIState || !sharedUIState.doc) return;
  
  sharedUIState.doc.transact(() => {
    sharedUIState!.set(key, value);
  }, 'local');
}
