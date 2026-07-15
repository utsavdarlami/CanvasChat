import { create } from 'zustand';
import { devtools } from 'zustand/middleware';
import { createGraphSlice, GraphSlice } from './slices/graphSlice';
import { createUISlice, UISlice } from './slices/uiSlice';
import { createEntitySlice, EntitySlice } from './slices/entitySlice';
import { createChatSlice, ChatSlice } from './slices/chatSlice';
import { createSessionSlice, SessionSlice } from './slices/sessionSlice';
import { createTimelineSlice, TimelineSlice } from './slices/timelineSlice';
import { createAnimationSlice, AnimationSlice } from './slices/animationSlice';

export type AppState = GraphSlice & UISlice & EntitySlice & ChatSlice & SessionSlice & TimelineSlice & AnimationSlice;

export const useAppStore = create<AppState>()(
  devtools(
    (...a) => ({
      ...createGraphSlice(...a),
      ...createUISlice(...a),
      ...createEntitySlice(...a),
      ...createChatSlice(...a),
      ...createSessionSlice(...a),
      ...createTimelineSlice(...a),
      ...createAnimationSlice(...a),
    }),
    { name: 'AppStore' }
  )
);
