import { addActionStatusMessage } from '../chatPanelHelpers';
import type { ChatActionHandler, ActionContext } from './types';

/**
 * Handles show_entity actions — transient entity highlight + camera focus.
 * The highlight and focus state is applied earlier in the dispatch pipeline,
 * so this handler only posts the status message.
 */
export const highlightHandler: ChatActionHandler = {
  recordsTimeline: false,

  apply(ctx: ActionContext) {
    addActionStatusMessage(ctx.chat, ctx.data.action);
  },
};
