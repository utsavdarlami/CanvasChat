import { useShallow } from 'zustand/react/shallow';
import { useAppStore } from './appStore';

export const useChatPanelStore = () =>
  useAppStore(
    useShallow((state) => ({
      messages: state.chat.messages,
      sessionId: state.chat.sessionId,
      userId: state.chat.userId,
      sessionInitialized: state.chat.sessionInitialized,
      isLoading: state.chat.isLoading,
      addMessage: state.chat.addMessage,
      updateLastAgentMessage: state.chat.updateLastAgentMessage,
      updateLastAgentThinking: state.chat.updateLastAgentThinking,
      setSessionId: state.chat.setSessionId,
      setSessionInitialized: state.chat.setSessionInitialized,
      setLoading: state.chat.setLoading,
    }))
  );

export const useResetChatSession = () =>
  useAppStore((state) => state.chat.resetSession);
