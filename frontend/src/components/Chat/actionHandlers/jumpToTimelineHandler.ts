import { useAppStore } from '@/stores/appStore';
import { addActionStatusMessage } from '../chatPanelHelpers';
import type { ChatActionHandler, ActionContext } from './types';

export const jumpToTimelineHandler: ChatActionHandler = {
  recordsTimeline: false,

  apply(ctx: ActionContext) {
    const timelineIndex = ctx.data.action?.timeline_index;
    if (timelineIndex === undefined || timelineIndex === null) {
      ctx.chat.addMessage('system', 'Timeline jump failed: no index specified.');
      return;
    }

    const { timeline } = useAppStore.getState();
    if (timelineIndex < 0 || timelineIndex >= timeline.entries.length) {
      ctx.chat.addMessage(
        'system',
        `Timeline jump failed: index ${timelineIndex} out of range (0-${timeline.entries.length - 1}).`,
      );
      return;
    }

    timeline.jumpToEntry(timelineIndex);
    addActionStatusMessage(ctx.chat, ctx.data.action);
  },
};
