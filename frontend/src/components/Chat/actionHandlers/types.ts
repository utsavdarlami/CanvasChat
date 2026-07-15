import type { ChatResponse, LayoutDelta, LayoutStage } from '@/types/api';
import type {
  ChatMessageActions,
  EmitDragBatch,
  GraphLayoutActions,
  SessionSnapshot,
} from '../chatPanelHelpers';

/**
 * Context passed to every action handler.
 * Contains everything a handler needs to apply its effect.
 */
export interface ActionContext {
  /** Full chat response from the backend */
  data: ChatResponse;
  /** Normalized layout delta (always present, arrays default to []) */
  delta: LayoutDelta;
  /** Graph store actions for state mutation */
  graph: GraphLayoutActions;
  /** Chat message actions for status/system messages */
  chat: Pick<ChatMessageActions, 'addMessage'>;
  /** Multi-display session info */
  session: SessionSnapshot;
  /** Yjs batch emitter for peer sync */
  emitDragBatch: EmitDragBatch;
  /** Resolved React Flow node IDs for highlighted entities */
  highlightedNodeIds: string[];
  /** Group stage metadata for staged animation (grouping → final) */
  layoutStages?: LayoutStage[];
}

/**
 * Contract for a chat action handler.
 *
 * To add a new action type:
 * 1. Add the type string to ChatActionType in types/api.ts
 * 2. Create a handler implementing this interface
 * 3. Register it in actionHandlers/registry.ts
 */
export interface ChatActionHandler {
  /** Apply state changes (positions, highlights, focus, etc.) */
  apply(ctx: ActionContext): void;
  /** Whether this action should record a timeline snapshot */
  recordsTimeline: boolean;
}
