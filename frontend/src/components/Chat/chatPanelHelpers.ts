import type { MutableRefObject } from 'react';
import type {
  ChatMessage,
  ChatRequest,
  ChatResponse,
  DisplayContext,
  LayoutDelta,
  TimelineContextEntry,
} from '@/types/api';
import { useAppStore } from '@/stores/appStore';
import { getEntityId } from '@/utils/entityId';
import type {
  EntityRecord,
  GraphContext,
  GraphData,
  GraphNode,
} from '@/types/graph';
import type { NodeUpdate, Peer } from '@/types/session';
import type { VirtualDesktop } from '@/utils/peerArrangement';
import { getNodeDimensions } from '@/components/EntityView/entityNodeUtils';

const DEFAULT_COORDINATE = 0;
const DEFAULT_PAN = 0;
const DEFAULT_ZOOM = 1;
const SESSION_ID_PREFIX = 'session_';
const UNASSIGNED_DISPLAY_ID = '__unassigned__';
const DISPLAY_LABEL_SUFFIX = ' display';
const PEER_ID_PREVIEW_LENGTH = 12;
const CHAT_TRANSFER_ORIGIN = 'chat-transfer';
const LOCAL_ONLY_TRANSFER_ORIGIN = 'local';
const CHAT_TRANSFER_LOCAL_ECHO_LIMIT = 12;
const CHAT_TRANSFER_DETAIL_MESSAGE_LIMIT = 8;

export const CHAT_TEXT = {
  panelTitle: 'Layout Chat',
  expandTitle: 'Expand chat',
  collapseTitle: 'Collapse chat',
  placeholder: 'Ask to modify the layout...',
  thinking: 'Thinking...',
  missingGraphData: 'Please upload files first before chatting.',
  missingAgentMessage: 'Received response without message content.',
  sessionExpired: 'Session expired. Please try again.',
  layoutUpdated: 'Layout updated.',
  entityShown: 'Entity shown.',
  actionApplied: 'Action applied.',
} as const;

export interface ContextFingerprintRefs {
  sessionRef: MutableRefObject<string | null>;
  layoutRef: MutableRefObject<string | null>;
  displayRef: MutableRefObject<string | null>;
  timelineRef: MutableRefObject<string | null>;
}

export interface SessionSnapshot {
  isConnected: boolean;
  localPeerId: string | null;
  virtualDesktop: VirtualDesktop | null;
  localPeer: Omit<Peer, 'id'>;
  peers: Map<string, Peer>;
}

export interface GraphPayloadContext {
  nodes: GraphNode[];
  graphMetadata: GraphContext | null;
  currentEntities: EntityRecord[] | null;
  entityTags: Record<string, string[]>;
}

export interface GraphLayoutActions {
  nodes: GraphNode[];
  applyLayoutDelta: (delta: LayoutDelta) => void;
  setGraphData: (data: GraphData) => void;
  setHighlightedNodeIds: (nodeIds: string[], nodeColors?: Record<string, string>) => void;
  clearHighlightedNodeIds: () => void;
  setEntityTags: (tags: Record<string, string[]>) => void;
  setGroupOverlays: (overlays: import('@/types/api').GroupOverlay[], source?: 'local' | 'remote') => void;
  clearGroupOverlays: (source?: 'local' | 'remote') => void;
  setPendingCameraCommand: (cmd: import('@/stores/slices/graphSlice').CameraCommand | null) => void;
}

export interface ChatMessageActions {
  addMessage: (role: ChatMessage['role'], content: string, thinking?: string[]) => void;
  setSessionInitialized: (initialized: boolean) => void;
  setSessionId: (sessionId: string) => void;
}

interface NormalizedCamera {
  panX: number;
  panY: number;
  zoom: number;
}

interface DetectedTransfer {
  entityId: string;
  name: string;
  fromDisplayId: string;
  toDisplayId: string;
  x: number;
  y: number;
}

export type EmitDragBatch = (updates: NodeUpdate[], options?: { origin?: string }) => void;

function prepareLayoutForChat(
  nodes: GraphNode[],
  graphMetadata: GraphContext | null,
  currentEntities: EntityRecord[],
) {
  return {
    nodes: nodes.map((node) => {
      const dims = getNodeDimensions(node, currentEntities);
      const layoutNode: Record<string, unknown> = {
        entity_id: getEntityId(node),
        name: node.name || node.display_name || '',
        x: node.x !== undefined ? node.x : DEFAULT_COORDINATE,
        y: node.y !== undefined ? node.y : DEFAULT_COORDINATE,
        width: dims.width,
        height: dims.height,
      };

      if (node.clusters) {
        layoutNode.clusters = node.clusters;
      }

      if (node.displayId) {
        layoutNode.display_id = node.displayId;
      }

      return layoutNode;
    }),
    graph: graphMetadata || {},
  };
}

function normalizeCamera(camera?: Peer['camera']): NormalizedCamera {
  return {
    panX: camera?.x ?? DEFAULT_PAN,
    panY: camera?.y ?? DEFAULT_PAN,
    zoom: camera?.zoom && camera.zoom > 0 ? camera.zoom : DEFAULT_ZOOM,
  };
}

function computeVisibleCanvas(width: number, height: number, camera: NormalizedCamera) {
  const minX = (DEFAULT_COORDINATE - camera.panX) / camera.zoom;
  const minY = (DEFAULT_COORDINATE - camera.panY) / camera.zoom;
  const maxX = (width - camera.panX) / camera.zoom;
  const maxY = (height - camera.panY) / camera.zoom;

  return {
    minX,
    minY,
    maxX,
    maxY,
    width: maxX - minX,
    height: maxY - minY,
  };
}

function buildPeerNodeMap(nodes: GraphNode[]): Map<string, string[]> {
  const peerNodeMap = new Map<string, string[]>();

  for (const node of nodes) {
    if (!node.displayId) continue;

    const nodeIds = peerNodeMap.get(node.displayId) || [];
    nodeIds.push(getEntityId(node));
    peerNodeMap.set(node.displayId, nodeIds);
  }

  for (const ids of peerNodeMap.values()) {
    ids.sort();
  }

  return peerNodeMap;
}

function buildDisplayContext(session: SessionSnapshot, nodes: GraphNode[]): DisplayContext | undefined {
  const peerNodeMap = buildPeerNodeMap(nodes);

  // Not connected to a room: build solo display context from localPeer
  // so the backend still knows screen dimensions, camera, and visible canvas.
  if (!session.isConnected || !session.localPeerId) {
    const camera = normalizeCamera(session.localPeer.camera);
    const width = session.localPeer.width || 0;
    const height = session.localPeer.height || 0;
    if (width <= 0 || height <= 0) return undefined;
    const visibleCanvas = computeVisibleCanvas(width, height, camera);
    const allNodeIds = nodes.map((n) => getEntityId(n));

    return {
      is_multi_display: false,
      local_peer_id: 'local',
      virtual_desktop: {
        total_width: width,
        total_height: height,
        displays: [{
          peer_id: 'local',
          tags: [],
          x: 0,
          y: 0,
          width,
          height,
          node_ids: allNodeIds,
          camera: {
            pan_x: camera.panX,
            pan_y: camera.panY,
            zoom: camera.zoom,
          },
          visible_canvas: {
            min_x: visibleCanvas.minX,
            min_y: visibleCanvas.minY,
            max_x: visibleCanvas.maxX,
            max_y: visibleCanvas.maxY,
            width: visibleCanvas.width,
            height: visibleCanvas.height,
          },
        }],
      },
    };
  }

  // Multi-display: use virtualDesktop peers
  if (session.virtualDesktop) {
    return {
      is_multi_display: true,
      local_peer_id: session.localPeerId,
      virtual_desktop: {
        total_width: session.virtualDesktop.totalWidth,
        total_height: session.virtualDesktop.totalHeight,
        displays: session.virtualDesktop.peers.map((peer) => {
          const cameraSource = peer.id === session.localPeerId
            ? session.localPeer.camera
            : session.peers.get(peer.id)?.camera;
          const camera = normalizeCamera(cameraSource);
          const visibleCanvas = computeVisibleCanvas(peer.width, peer.height, camera);

          return {
            peer_id: peer.id,
            tags: peer.tags || [],
            x: peer.x,
            y: peer.y,
            width: peer.width,
            height: peer.height,
            node_ids: peerNodeMap.get(peer.id) || [],
            camera: {
              pan_x: camera.panX,
              pan_y: camera.panY,
              zoom: camera.zoom,
            },
            visible_canvas: {
              min_x: visibleCanvas.minX,
              min_y: visibleCanvas.minY,
              max_x: visibleCanvas.maxX,
              max_y: visibleCanvas.maxY,
              width: visibleCanvas.width,
              height: visibleCanvas.height,
            },
          };
        }),
      },
    };
  }

  // Single display: build context from localPeer so backend knows the real
  // peer ID and viewport bounds instead of falling back to "surface_0".
  const camera = normalizeCamera(session.localPeer.camera);
  const width = session.localPeer.width || 0;
  const height = session.localPeer.height || 0;
  const visibleCanvas = computeVisibleCanvas(width, height, camera);

  return {
    is_multi_display: false,
    local_peer_id: session.localPeerId,
    virtual_desktop: {
      total_width: width,
      total_height: height,
      displays: [{
        peer_id: session.localPeerId,
        tags: [],
        x: 0,
        y: 0,
        width,
        height,
        node_ids: peerNodeMap.get(session.localPeerId) || [],
        camera: {
          pan_x: camera.panX,
          pan_y: camera.panY,
          zoom: camera.zoom,
        },
        visible_canvas: {
          min_x: visibleCanvas.minX,
          min_y: visibleCanvas.minY,
          max_x: visibleCanvas.maxX,
          max_y: visibleCanvas.maxY,
          width: visibleCanvas.width,
          height: visibleCanvas.height,
        },
      }],
    },
  };
}

function getDisplayTag(peerId: string, virtualDesktop: VirtualDesktop | null): string {
  if (!virtualDesktop) return peerId;

  const peer = virtualDesktop.peers.find((entry) => entry.id === peerId);
  if (peer?.tags?.length) {
    return `${peer.tags.join(', ')}${DISPLAY_LABEL_SUFFIX}`;
  }

  return peerId.length > PEER_ID_PREVIEW_LENGTH
    ? `${peerId.slice(0, PEER_ID_PREVIEW_LENGTH)}...`
    : peerId;
}

export function normalizeLayoutDelta(delta: LayoutDelta): LayoutDelta {
  return {
    ...delta,
    updated_nodes: delta.updated_nodes ?? [],
    added_nodes: delta.added_nodes ?? [],
    removed_nodes: delta.removed_nodes ?? [],
    highlighted_nodes: delta.highlighted_nodes ?? [],
    highlighted_node_colors: delta.highlighted_node_colors ?? {},
    text_highlights: delta.text_highlights ?? [],
    clear_text_highlight_ids: delta.clear_text_highlight_ids ?? [],
    ...(delta.entity_tags !== undefined ? { entity_tags: delta.entity_tags } : {}),
  };
}

export function summarizeDeltaChanges(delta: LayoutDelta): string {
  const parts: string[] = [];
  if (delta.updated_nodes.length) parts.push(`${delta.updated_nodes.length} moved`);
  if (delta.added_nodes.length) parts.push(`${delta.added_nodes.length} added`);
  if (delta.removed_nodes.length) parts.push(`${delta.removed_nodes.length} removed`);
  if (delta.highlighted_nodes?.length) parts.push(`${delta.highlighted_nodes.length} highlighted`);
  return parts.join(', ');
}

export function hasStructuralDeltaChanges(delta: LayoutDelta | undefined): delta is LayoutDelta {
  if (!delta) return false;

  const normalized = normalizeLayoutDelta(delta);
  return (
    normalized.updated_nodes.length > 0 ||
    normalized.added_nodes.length > 0 ||
    normalized.removed_nodes.length > 0
  );
}

export function resolveDisplayTransfers(
  delta: LayoutDelta,
  nodes: GraphNode[],
  virtualDesktop: VirtualDesktop | null,
): { delta: LayoutDelta; transfers: DetectedTransfer[] } {
  const normalizedDelta = normalizeLayoutDelta(delta);
  if (!normalizedDelta.updated_nodes.length || !virtualDesktop) {
    return { delta: normalizedDelta, transfers: [] };
  }

  const currentNodeMap = new Map(nodes.map((node) => [getEntityId(node), node]));
  const transfers: DetectedTransfer[] = [];

  const updatedNodes = normalizedDelta.updated_nodes.map((update) => {
    if (!update.display_id) return update;

    const currentNode = currentNodeMap.get(update.entity_id);
    if (!currentNode || currentNode.displayId === update.display_id) {
      return update;
    }

    // Chat layout deltas are in display-local canvas coordinates already.
    // Do not reproject through virtual desktop offsets or camera transform;
    // doing so pushes nodes off-screen on the target display.
    const convertedUpdate = update;

    transfers.push({
      entityId: update.entity_id,
      name: update.name || currentNode.name || update.entity_id,
      fromDisplayId: currentNode.displayId || UNASSIGNED_DISPLAY_ID,
      toDisplayId: update.display_id,
      x: convertedUpdate.x,
      y: convertedUpdate.y,
    });

    return convertedUpdate;
  });

  return {
    delta: {
      ...normalizedDelta,
      updated_nodes: updatedNodes,
    },
    transfers,
  };
}

export function announceTransfers(
  transfers: DetectedTransfer[],
  chat: Pick<ChatMessageActions, 'addMessage'>,
  virtualDesktop: VirtualDesktop | null,
  isConnected: boolean,
  emitDragBatch: EmitDragBatch,
) {
  const yjsUpdates: NodeUpdate[] = [];
  if (transfers.length > CHAT_TRANSFER_DETAIL_MESSAGE_LIMIT) {
    const destinationCounts = new Map<string, number>();
    for (const transfer of transfers) {
      const key = transfer.toDisplayId;
      destinationCounts.set(key, (destinationCounts.get(key) ?? 0) + 1);
    }
    const summary = [...destinationCounts.entries()]
      .map(([displayId, count]) => `${count} to ${getDisplayTag(displayId, virtualDesktop)}`)
      .join(', ');
    chat.addMessage('system', `Transferred ${transfers.length} entities (${summary})`);
  }

  for (const transfer of transfers) {
    if (transfers.length <= CHAT_TRANSFER_DETAIL_MESSAGE_LIMIT) {
      const fromTag = getDisplayTag(transfer.fromDisplayId, virtualDesktop);
      const toTag = getDisplayTag(transfer.toDisplayId, virtualDesktop);
      chat.addMessage('system', `Transferred "${transfer.name}" from ${fromTag} to ${toTag}`);
    }

    if (isConnected) {
      yjsUpdates.push({
        id: transfer.entityId,
        x: transfer.x,
        y: transfer.y,
        displayId: transfer.toDisplayId,
        kind: 'commit',
        space: 'canvas',
      });
    }
  }
  if (yjsUpdates.length > 0) {
    // For small transfer sets, keep local echo enabled so source/target
    // commit animations run on the initiating peer.
    // For large transfer sets, suppress local echo to avoid O(k) local
    // callback storms that can freeze the UI.
    const origin = yjsUpdates.length > CHAT_TRANSFER_LOCAL_ECHO_LIMIT
      ? LOCAL_ONLY_TRANSFER_ORIGIN
      : CHAT_TRANSFER_ORIGIN;
    emitDragBatch(yjsUpdates, { origin });
  }
}

export function getHighlightedNodeIds(action: ChatResponse['action']): string[] {
  if (!action?.layout_delta && !action?.affected_entities) return [];

  const fromDelta = action.layout_delta?.highlighted_nodes ?? [];
  const fromAffected = action.type === 'show_entity'
    ? (action.affected_entities ?? [])
    : [];

  return Array.from(new Set([...fromDelta, ...fromAffected]));
}

export function resolveTargetNodeIds(nodeIds: string[], nodes: GraphNode[]): string[] {
  if (nodeIds.length === 0) return [];
  const nodeIdByEntityId = new Map(nodes.map((node) => [getEntityId(node), node.id]));

  return Array.from(new Set(nodeIds.map((id) => nodeIdByEntityId.get(id) ?? id)));
}

export function resolveHighlightedNodeColors(
  colorsByEntityId: Record<string, string> | undefined,
  nodes: GraphNode[],
): Record<string, string> {
  if (!colorsByEntityId) return {};
  const nodeIdByEntityId = new Map(nodes.map((node) => [getEntityId(node), node.id]));

  const resolved: Record<string, string> = {};
  for (const [entityId, color] of Object.entries(colorsByEntityId)) {
    if (typeof color !== 'string') continue;
    const trimmed = color.trim();
    if (!trimmed) continue;
    const nodeId = nodeIdByEntityId.get(entityId) ?? entityId;
    resolved[nodeId] = trimmed;
  }
  return resolved;
}

export function addActionStatusMessage(
  chat: Pick<ChatMessageActions, 'addMessage'>,
  action: ChatResponse['action'],
) {
  const statusPrefix = action?.type === 'show_entity'
    ? CHAT_TEXT.entityShown
    : action?.type
      ? CHAT_TEXT.actionApplied
      : CHAT_TEXT.layoutUpdated;

  if (action?.description) {
    chat.addMessage('system', `${statusPrefix}: ${action.description}`);
    if (action.affected_entities?.length) {
      console.log('[Chat] Affected entities:', action.affected_entities);
    }
    return;
  }

  chat.addMessage('system', statusPrefix);
}

export function syncSessionFingerprint(sessionId: string, refs: ContextFingerprintRefs): boolean {
  const isNewSessionContext = refs.sessionRef.current !== sessionId;
  if (!isNewSessionContext) return false;

  refs.sessionRef.current = sessionId;
  refs.layoutRef.current = null;
  refs.displayRef.current = null;
  refs.timelineRef.current = null;
  return true;
}

export function syncPayloadContext(args: {
  payload: ChatRequest;
  graph: Pick<GraphPayloadContext, 'nodes' | 'graphMetadata' | 'currentEntities'>;
  session: SessionSnapshot;
  forceContextSend: boolean;
  refs: ContextFingerprintRefs;
}) {
  const { payload, graph, session, forceContextSend, refs } = args;
  if (graph.nodes.length === 0) return;

  const layoutSnapshot = prepareLayoutForChat(
    graph.nodes, graph.graphMetadata, graph.currentEntities || [],
  );
  const layoutFingerprint = JSON.stringify(layoutSnapshot);
  if (forceContextSend || layoutFingerprint !== refs.layoutRef.current) {
    payload.layout = layoutSnapshot;
    refs.layoutRef.current = layoutFingerprint;
  }

  const displayContextSnapshot = buildDisplayContext(session, graph.nodes);
  if (!displayContextSnapshot) return;

  const displayFingerprint = JSON.stringify(displayContextSnapshot);
  if (forceContextSend || displayFingerprint !== refs.displayRef.current) {
    payload.display_context = displayContextSnapshot;
    refs.displayRef.current = displayFingerprint;
  }

  // Timeline context fingerprinting
  const timelineState = useAppStore.getState().timeline;
  if (timelineState.entries.length > 0) {
    const timelineSnapshot = {
      entries: timelineState.entries.map((e, i) => ({
        index: i,
        label: e.label,
        source: e.source,
        timestamp: e.timestamp,
      } as TimelineContextEntry)),
      current_index: timelineState.currentIndex,
    };
    const timelineFingerprint = JSON.stringify(timelineSnapshot);
    if (forceContextSend || timelineFingerprint !== refs.timelineRef.current) {
      payload.timeline_context = timelineSnapshot;
      refs.timelineRef.current = timelineFingerprint;
    }
  }
}

export function addInitialSemanticContext(
  payload: ChatRequest,
  graph: Pick<GraphPayloadContext, 'currentEntities'>,
  isFirstRequest: boolean,
) {
  if (!isFirstRequest) return;

  if (graph.currentEntities) {
    payload.entities = graph.currentEntities;
  }
}

export function getSessionId(
  existingSessionId: string | null,
  isFirstRequest: boolean,
  chat: Pick<ChatMessageActions, 'setSessionId'>,
): string {
  if (isFirstRequest) {
    const freshSessionId = `${SESSION_ID_PREFIX}${Date.now()}`;
    chat.setSessionId(freshSessionId);
    return freshSessionId;
  }

  if (existingSessionId) {
    return existingSessionId;
  }

  const recoveredSessionId = `${SESSION_ID_PREFIX}${Date.now()}`;
  chat.setSessionId(recoveredSessionId);
  return recoveredSessionId;
}

export function handleChatError(
  error: unknown,
  chat: Pick<ChatMessageActions, 'addMessage' | 'setSessionInitialized'>,
) {
  const errorMessage = error instanceof Error ? error.message : String(error);
  if (errorMessage === 'SESSION_EXPIRED') {
    chat.setSessionInitialized(false);
    chat.addMessage('system', CHAT_TEXT.sessionExpired);
    return;
  }

  chat.addMessage('system', `Error: ${errorMessage}`);
  console.error('[Chat] API error:', error);
}

/**
 * Apply a chat response to the layout.
 *
 * Delegates to the action handler registry — see actionHandlers/registry.ts.
 * To add a new action type, create a handler and register it there.
 */
export { dispatchChatAction as applyChatResponseLayout } from './actionHandlers/registry';
