import { useShallow } from 'zustand/react/shallow';
import { useAppStore } from './appStore';

export const useSidebarUI = () =>
  useAppStore(
    useShallow((state) => ({
      leftSidebarOpen: state.ui.leftSidebarOpen,
      leftSidebarTab: state.ui.leftSidebarTab,
      leftSidebarWidth: state.ui.leftSidebarWidth,
      toggleSidebar: state.ui.toggleSidebar,
      setLeftSidebarTab: state.ui.setLeftSidebarTab,
      setSidebarWidth: state.ui.setSidebarWidth,
    }))
  );

export const useMultiDisplayModalUI = () =>
  useAppStore(
    useShallow((state) => ({
      isMultiDisplayModalOpen: state.ui.isMultiDisplayModalOpen,
      setMultiDisplayModalOpen: state.ui.setMultiDisplayModalOpen,
    }))
  );

export const useIsMultiDisplayModalOpen = () =>
  useAppStore((state) => state.ui.isMultiDisplayModalOpen);

export const useChatPanelUI = () =>
  useAppStore(
    useShallow((state) => ({
      chatPanelOpen: state.ui.chatPanelOpen,
      toggleChatPanel: state.ui.toggleChatPanel,
    }))
  );
