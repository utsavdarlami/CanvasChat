import type { ChatResponse, LayoutDelta } from '@/types/api';
import type {
  ChatMessageActions,
  EmitDragBatch,
  GraphLayoutActions,
  SessionSnapshot,
} from '../chatPanelHelpers';
import {
  normalizeLayoutDelta,
  getHighlightedNodeIds,
  resolveTargetNodeIds,
  resolveHighlightedNodeColors,
  hasStructuralDeltaChanges,
} from '../chatPanelHelpers';
import type { ActionContext, ChatActionHandler } from './types';

import { updateLayoutHandler } from './updateLayoutHandler';
import { highlightHandler } from './highlightHandler';
import { textHighlightHandler } from './textHighlightHandler';
import { clearTextHighlightHandler } from './clearTextHighlightHandler';
import { fullLayoutHandler } from './fullLayoutHandler';
import { jumpToTimelineHandler } from './jumpToTimelineHandler';
import { tagNodesHandler } from './tagNodesHandler';
import { clearEntityTagsHandler } from './clearEntityTagsHandler';

// ---------------------------------------------------------------------------
// Handler registry
//
// To add a new action type:
//   1. Add the type to ChatActionType in types/api.ts
//   2. Create a handler file implementing ChatActionHandler
//   3. Register it here
// ---------------------------------------------------------------------------

const handlers: Record<string, ChatActionHandler> = {
  // Structural layout changes
  update_layout: updateLayoutHandler,

  // Transient UI-only actions (status-only handler, state already applied)
  show_entity: highlightHandler,

  // Text-span highlights inside entity content
  text_highlight: textHighlightHandler,
  clear_text_highlight: clearTextHighlightHandler,

  tag_nodes: tagNodesHandler,
  clear_entity_tags: clearEntityTagsHandler,

  // Timeline navigation (jump to a previous snapshot)
  jump_to_timeline: jumpToTimelineHandler,
};

// ---------------------------------------------------------------------------
// Dispatcher
// ---------------------------------------------------------------------------

const EMPTY_DELTA: LayoutDelta = {
  updated_nodes: [],
  added_nodes: [],
  removed_nodes: [],
  highlighted_nodes: [],
  highlighted_node_colors: {},
  text_highlights: [],
  clear_text_highlight_ids: [],
};

/**
 * Build an ActionContext from the raw applyChatResponseLayout args.
 */
function buildActionContext(args: {
  data: ChatResponse;
  chat: Pick<ChatMessageActions, 'addMessage'>;
  graph: GraphLayoutActions;
  session: SessionSnapshot;
  emitDragBatch: EmitDragBatch;
}): ActionContext {
  const { data, chat, graph, session, emitDragBatch } = args;
  const delta = data.action?.layout_delta
    ? normalizeLayoutDelta(data.action.layout_delta)
    : EMPTY_DELTA;

  const highlightedNodeIds = resolveTargetNodeIds(
    getHighlightedNodeIds(data.action),
    graph.nodes,
  );

  return {
    data, delta, graph, chat, session, emitDragBatch, highlightedNodeIds,
    layoutStages: data.layout_stages,
  };
}

/**
 * Apply transient UI state (highlights / focus) regardless of action type.
 * These are always processed first so handlers don't need to repeat this.
 */
function applyTransientState(ctx: ActionContext) {
  const { highlightedNodeIds, graph, data, delta } = ctx;

  if (highlightedNodeIds.length > 0) {
    const highlightedNodeColors = resolveHighlightedNodeColors(
      delta.highlighted_node_colors,
      graph.nodes,
    );
    graph.setHighlightedNodeIds(highlightedNodeIds, highlightedNodeColors);
    // Dispatch a camera command to frame the highlighted nodes
    graph.setPendingCameraCommand({ kind: 'fitNodes', nodeIds: highlightedNodeIds });
  } else if (data.action?.type && data.action.type !== 'show_entity') {
    graph.clearHighlightedNodeIds();
  }

  if (delta.entity_tags !== undefined) {
    graph.setEntityTags(delta.entity_tags);
  }

  // Replace group overlays whenever the backend includes the key. An empty
  // array means "clear all" — treating it as a no-op strands stale rectangles
  // after tag clears or moves that drop overlays.
  if (Array.isArray(delta.group_overlays)) {
    graph.setGroupOverlays(delta.group_overlays);
  }
}

/**
 * Main entry point — replaces the old applyChatResponseLayout monolith.
 *
 * Routes the response to the correct handler based on action.type,
 * with a fallback to full-layout replacement when no delta is available.
 */
export function dispatchChatAction(args: {
  data: ChatResponse;
  chat: Pick<ChatMessageActions, 'addMessage'>;
  graph: GraphLayoutActions;
  session: SessionSnapshot;
  emitDragBatch: EmitDragBatch;
}) {
  const ctx = buildActionContext(args);

  // Always apply transient state first
  applyTransientState(ctx);

  const actionType = ctx.data.action?.type;

  // Structural changes → use the registered handler
  if (actionType && hasStructuralDeltaChanges(ctx.delta)) {
    const handler = handlers[actionType];
    if (handler) {
      handler.apply(ctx);
      return;
    }
  }

  // Non-structural action (show_entity)
  if (actionType && actionType in handlers) {
    handlers[actionType].apply(ctx);
    return;
  }

  // Fallback: full layout replacement
  if (ctx.data.layout) {
    fullLayoutHandler.apply(ctx);
  }
}
