import { useHighlightStore } from '@/stores/highlightStore';
import { addActionStatusMessage } from '../chatPanelHelpers';
import type { ChatActionHandler, ActionContext } from './types';

/**
 * Clears text-span highlights from entity nodes.
 *
 * Supports targeted removal (specific entity IDs) or global removal
 * (when the list contains '__all__' or is empty).
 */
export const clearTextHighlightHandler: ChatActionHandler = {
  recordsTimeline: false,

  apply(ctx: ActionContext) {
    const ids = ctx.delta.clear_text_highlight_ids ?? [];
    const store = useHighlightStore.getState();

    if (ids.length === 0 || ids.includes('__all__')) {
      store.clearAllHighlights();
    } else {
      for (const entityId of ids) {
        store.clearHighlights(entityId);
      }
    }

    addActionStatusMessage(ctx.chat, ctx.data.action);
  },
};
