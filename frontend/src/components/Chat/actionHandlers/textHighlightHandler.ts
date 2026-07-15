import { useHighlightStore } from '@/stores/highlightStore';
import { addActionStatusMessage } from '../chatPanelHelpers';
import type { ChatActionHandler, ActionContext } from './types';

/**
 * Applies text-span highlights inside entity nodes.
 *
 * The backend sends text_highlights entries in the layout delta.
 * Each entry maps an entity_id to an array of exact text snippets.
 * This handler pushes them into the shared highlightStore so that
 * EntityPanelContent renders <mark> elements via highlightTextChildren.
 */
export const textHighlightHandler: ChatActionHandler = {
  recordsTimeline: false,

  apply(ctx: ActionContext) {
    const entries = ctx.delta.text_highlights ?? [];
    const store = useHighlightStore.getState();

    for (const entry of entries) {
      for (const text of entry.texts) {
        store.addHighlight(entry.entity_id, text, entry.color);
      }
    }

    addActionStatusMessage(ctx.chat, ctx.data.action);
  },
};
