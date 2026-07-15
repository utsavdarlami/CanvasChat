import { StateCreator } from 'zustand';
import type { AppState } from '../appStore';

export interface UIState {
  // Sidebars
  leftSidebarOpen: boolean;
  rightSidebarOpen: boolean;
  leftSidebarWidth: number;
  rightSidebarWidth: number;
  leftSidebarTab: 'current' | 'timeline' | 'chat';

  // Multi-Display Modal
  isMultiDisplayModalOpen: boolean;

  // Chat Panel
  chatPanelOpen: boolean;

  // Actions
  toggleSidebar: (side: 'left' | 'right') => void;
  setSidebarWidth: (side: 'left' | 'right', width: number) => void;
  setLeftSidebarTab: (tab: 'current' | 'timeline' | 'chat') => void;
  setMultiDisplayModalOpen: (open: boolean) => void;
  toggleChatPanel: () => void;
}

export interface UISlice {
  ui: UIState;
}

const MIN_SIDEBAR_WIDTH = 200;
const MAX_SIDEBAR_WIDTH = 600;
const DEFAULT_LEFT_SIDEBAR_WIDTH = 280;
const DEFAULT_RIGHT_SIDEBAR_WIDTH = 400;

export const createUISlice: StateCreator<AppState, [], [], UISlice> = (set) => ({
  ui: {
    // Initial state
    leftSidebarOpen: true,
    rightSidebarOpen: false,
    leftSidebarWidth: DEFAULT_LEFT_SIDEBAR_WIDTH,
    rightSidebarWidth: DEFAULT_RIGHT_SIDEBAR_WIDTH,
    leftSidebarTab: 'current',
    isMultiDisplayModalOpen: false,
    chatPanelOpen: false,

    // Actions
    toggleSidebar: (side: 'left' | 'right') => {
      set((state) => ({
        ui: {
          ...state.ui,
          leftSidebarOpen: side === 'left' ? !state.ui.leftSidebarOpen : state.ui.leftSidebarOpen,
          rightSidebarOpen: side === 'right' ? !state.ui.rightSidebarOpen : state.ui.rightSidebarOpen,
        }
      }));
    },

    setSidebarWidth: (side: 'left' | 'right', width: number) => {
      const clampedWidth = Math.max(MIN_SIDEBAR_WIDTH, Math.min(MAX_SIDEBAR_WIDTH, width));
      
      set((state) => ({
        ui: {
          ...state.ui,
          leftSidebarWidth: side === 'left' ? clampedWidth : state.ui.leftSidebarWidth,
          rightSidebarWidth: side === 'right' ? clampedWidth : state.ui.rightSidebarWidth,
        }
      }));
    },

    setLeftSidebarTab: (tab: 'current' | 'timeline' | 'chat') => {
      set((state) => ({
        ui: {
          ...state.ui,
          leftSidebarTab: tab,
          leftSidebarOpen: true,
        }
      }));
    },

    setMultiDisplayModalOpen: (open: boolean) => {
      set((state) => ({
        ui: { ...state.ui, isMultiDisplayModalOpen: open },
      }));
    },

    toggleChatPanel: () => {
      set((state) => ({
        ui: { ...state.ui, chatPanelOpen: !state.ui.chatPanelOpen },
      }));
    },
  }
});
