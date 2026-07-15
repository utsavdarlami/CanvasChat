import { StateCreator } from 'zustand';
import type { AppState } from '../appStore';
import type { ChatMessage } from '@/types/api';
import { clearChatSession } from '@/services/api';

export interface ChatState {
  // Messages
  messages: ChatMessage[];
  
  // Session
  sessionId: string | null;
  userId: string;
  sessionInitialized: boolean;
  
  // UI
  isLoading: boolean;
  
  // Actions
  addMessage: (role: ChatMessage['role'], content: string, thinking?: string[]) => void;
  updateLastAgentMessage: (content: string) => void;
  updateLastAgentThinking: (thinking: string[]) => void;
  setSessionId: (sessionId: string) => void;
  setSessionInitialized: (initialized: boolean) => void;
  setLoading: (loading: boolean) => void;
  clearMessages: () => void;
  resetSession: () => void;
}

export interface ChatSlice {
  chat: ChatState;
}

const CHAT_READY_MESSAGE =
  'Chat ready. Upload files to analyze, then ask questions about your visualization layout.';
const CHAT_RESET_MESSAGE =
  'New data uploaded. Chat session reset. Ask questions about your visualization layout.';
const CHAT_USER_ID_KEY = 'chat_user_id';
const DEFAULT_CHAT_USER_ID = 'demo_user';

const createSystemMessage = (content: string): ChatMessage => ({
  role: 'system',
  content,
  timestamp: new Date(),
});

const readUserId = (): string => {
  if (typeof localStorage !== 'undefined') {
    return localStorage.getItem(CHAT_USER_ID_KEY) ?? DEFAULT_CHAT_USER_ID;
  }
  return DEFAULT_CHAT_USER_ID;
};

const persistUserId = (userId: string): void => {
  if (typeof localStorage === 'undefined') return;
  if (localStorage.getItem(CHAT_USER_ID_KEY)) return;
  localStorage.setItem(CHAT_USER_ID_KEY, userId);
};

export const createChatSlice: StateCreator<AppState, [], [], ChatSlice> = (set, get) => ({
  chat: {
    // Initial state
    messages: [createSystemMessage(CHAT_READY_MESSAGE)],
    sessionId: null,
    userId: readUserId(),
    sessionInitialized: false,
    isLoading: false,

    // Actions
    addMessage: (role: ChatMessage['role'], content: string, thinking?: string[]) => {
      set((state) => ({
        chat: {
          ...state.chat,
          messages: [
            ...state.chat.messages,
            {
              role,
              content,
              timestamp: new Date(),
              ...(thinking?.length ? { thinking } : {}),
            },
          ],
        }
      }));
      persistUserId(readUserId());
    },

    updateLastAgentMessage: (content: string) => {
      set((state) => {
        const messages = [...state.chat.messages];
        const lastIndex = messages.length - 1;
        if (lastIndex >= 0 && messages[lastIndex].role === 'agent') {
          messages[lastIndex] = {
            ...messages[lastIndex],
            content,
          };
        }
        return { chat: { ...state.chat, messages } };
      });
    },

    updateLastAgentThinking: (thinking: string[]) => {
      set((state) => {
        const messages = [...state.chat.messages];
        const lastIndex = messages.length - 1;
        if (lastIndex >= 0 && messages[lastIndex].role === 'agent') {
          messages[lastIndex] = {
            ...messages[lastIndex],
            thinking,
          };
        }
        return { chat: { ...state.chat, messages } };
      });
    },

    setSessionId: (sessionId: string) => {
      set((state) => ({
        chat: { ...state.chat, sessionId }
      }));
    },

    setSessionInitialized: (initialized: boolean) => {
      set((state) => ({
        chat: { ...state.chat, sessionInitialized: initialized }
      }));
    },

    setLoading: (loading: boolean) => {
      set((state) => ({
        chat: { ...state.chat, isLoading: loading }
      }));
    },

    clearMessages: () => {
      set((state) => ({
        chat: {
          ...state.chat,
          messages: [createSystemMessage(CHAT_RESET_MESSAGE)],
        }
      }));
    },

    resetSession: () => {
      const { sessionId, userId } = get().chat;
      if (sessionId) {
        clearChatSession(userId, sessionId).catch((err) => {
          console.warn('[Chat] Failed to clear backend session:', err);
        });
      }
      set((state) => ({
        chat: {
          ...state.chat,
          sessionId: null,
          sessionInitialized: false,
          messages: [createSystemMessage(CHAT_READY_MESSAGE)],
        }
      }));
    },
  }
});
