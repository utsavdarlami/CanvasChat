import { useAppStore } from '@/stores/appStore';
import { addActionStatusMessage } from '../chatPanelHelpers';
import type { ChatActionHandler, ActionContext } from './types';

/**
 * Fallback handler: replaces the entire graph when no delta is available.
 * Used when the backend returns data.layout without a layout_delta.
 */
export const fullLayoutHandler: ChatActionHandler = {
  recordsTimeline: true,

  apply(ctx: ActionContext) {
    const { data, graph, chat } = ctx;

    if (!data.layout) return;

    console.log('[Chat] Layout update detected, refreshing visualization...');
    graph.setGraphData(data.layout);
    addActionStatusMessage(chat, data.action);

    const label = data.action?.description
      ? `Chat: ${data.action.description}`
      : 'Chat: Layout update';
    const currentNodes = useAppStore.getState().graph.nodes;
    useAppStore.getState().timeline.recordSnapshot(label, 'chat', currentNodes);
  },
};
