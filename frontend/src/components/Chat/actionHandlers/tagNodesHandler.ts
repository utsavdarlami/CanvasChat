import { addActionStatusMessage } from '../chatPanelHelpers';
import type { ChatActionHandler, ActionContext } from './types';

/** Status-only; entity tags were applied in applyTransientState from layout_delta.entity_tags */
export const tagNodesHandler: ChatActionHandler = {
  recordsTimeline: false,

  apply(ctx: ActionContext) {
    addActionStatusMessage(ctx.chat, ctx.data.action);
  },
};
