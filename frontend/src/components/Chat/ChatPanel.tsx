import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Virtuoso, type VirtuosoHandle } from 'react-virtuoso';
import { useChatPanelStore } from '@/stores/chatStore';
import { useChatSessionContext } from '@/stores/sessionStore';
import { useAppStore } from '@/stores/appStore';
import { useHighlightStore } from '@/stores/highlightStore';
import { sendChatMessage, streamChatMessage } from '@/services/api';
import { emitNodeDragBatch } from '@/services/yjsService';
import { debugLogger } from '@/services/debugLogger';
import { buildDiagnosticText } from '@/utils/buildDiagnosticText';
import { getNodePositionsSnapshot } from '@/services/yjs/nodePositions';
import { getLiveFlowNodes, getLiveFlowVersion } from '@/components/EntityView/hooks/useFlowNodeDebug';
import type { ChatRequest, ChatResponse } from '@/types/api';
import { useChatAutocomplete } from './hooks/useChatAutocomplete';
import {
  CHAT_TEXT,
  addInitialSemanticContext,
  applyChatResponseLayout,
  getSessionId,
  handleChatError,
  summarizeDeltaChanges,
  syncPayloadContext,
  syncSessionFingerprint,
  type ContextFingerprintRefs,
  type SessionSnapshot,
} from './chatPanelHelpers';
import { ChatMessageMarkdown } from './ChatMessageMarkdown';
import { SendIcon } from './icons';
import './ChatPanel.css';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Capture a diagnostic text snapshot from the current store/Yjs/Flow state. */
function captureDiagnosticSnapshot(): string {
  const { session } = useAppStore.getState();
  const { nodes: graphNodes } = useAppStore.getState().graph;
  return buildDiagnosticText({
    peers: session.peers,
    localPeerId: session.localPeerId,
    localPeer: session.localPeer,
    virtualDesktop: session.virtualDesktop,
    graphNodes,
    yjsSnapshot: getNodePositionsSnapshot(),
    flowNodes: getLiveFlowNodes(),
    flowVersion: getLiveFlowVersion(),
  });
}

// ---------------------------------------------------------------------------
// ThinkingSection — collapsible agent reasoning
// ---------------------------------------------------------------------------

const ThinkingSection: React.FC<{ content: string | string[] }> = ({ content }) => {
  if (!content) return null;
  if (Array.isArray(content) && content.length === 0) return null;
  
  const contentStr = Array.isArray(content) ? content.join('\n\n') : content;
  
  return (
    <details className="chat-thinking-section">
      <summary className="chat-thinking-summary">
        Reasoning
      </summary>
      <div className="chat-thinking-step">
        <ChatMessageMarkdown content={contentStr} />
      </div>
    </details>
  );
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export const ChatPanel: React.FC = () => {
  const chat = useChatPanelStore();
  const { isConnected, localPeerId, virtualDesktop, peers, localPeer } = useChatSessionContext();

  const [inputValue, setInputValue] = useState('');
  const [activeSuggestionIndex, setActiveSuggestionIndex] = useState(-1);
  const [suggestionsDismissed, setSuggestionsDismissed] = useState(false);
  const virtuosoRef = useRef<VirtuosoHandle>(null);
  const isAtBottomRef = useRef(true);
  const inputAreaRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const lastContextSessionRef = useRef<string | null>(null);
  const lastLayoutFingerprintRef = useRef<string | null>(null);
  const lastDisplayContextFingerprintRef = useRef<string | null>(null);
  const lastTimelineFingerprintRef = useRef<string | null>(null);
  
  // Streaming state refs
  const streamingTextRef = useRef('');
  const streamingThinkingRef = useRef<string>('');
  const streamingToolsRef = useRef<{ name: string; args: unknown }[]>([]);
  
  const { suggestions } = useChatAutocomplete({
    input: inputValue,
    userId: chat.userId,
    sessionId: chat.sessionId,
    sessionInitialized: chat.sessionInitialized,
    enabled: !chat.isLoading,
  });
  const showSuggestions = !suggestionsDismissed && suggestions.length > 0;

  const contextFingerprintRefs: ContextFingerprintRefs = {
    sessionRef: lastContextSessionRef,
    layoutRef: lastLayoutFingerprintRef,
    displayRef: lastDisplayContextFingerprintRef,
    timelineRef: lastTimelineFingerprintRef,
  };

  // Virtuoso tracks "is user near the bottom?" itself via atBottomStateChange.
  // We mirror it into a ref so `followOutput` can decide whether to auto-scroll.
  const followOutput = useCallback(() => (isAtBottomRef.current ? 'smooth' as const : false), []);

  const resizeInput = useCallback(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;

    const minLines = 2;
    const maxLines = 9;
    const computed = window.getComputedStyle(textarea);
    const lineHeight = Number.parseFloat(computed.lineHeight) || 20;
    const padding =
      Number.parseFloat(computed.paddingTop) + Number.parseFloat(computed.paddingBottom);
    const minHeight = lineHeight * minLines + padding;
    const maxHeight = lineHeight * maxLines + padding;

    textarea.style.height = 'auto';
    const nextHeight = Math.min(Math.max(textarea.scrollHeight, minHeight), maxHeight);
    textarea.style.height = `${nextHeight}px`;
    textarea.style.overflowY = textarea.scrollHeight > maxHeight ? 'auto' : 'hidden';
  }, []);

  useEffect(() => {
    resizeInput();
  }, [inputValue, resizeInput]);

  useEffect(() => {
    if (chat.messages.length === 0) return;
    if (!isAtBottomRef.current) return;

    // When returning to the Chat tab, force a post-mount scroll so Virtuoso
    // measures and renders the existing conversation reliably.
    let firstRaf = 0;
    let secondRaf = 0;
    firstRaf = requestAnimationFrame(() => {
      secondRaf = requestAnimationFrame(() => {
        virtuosoRef.current?.scrollToIndex({
          index: chat.messages.length - 1,
          align: 'end',
          behavior: 'auto',
        });
      });
    });

    return () => {
      cancelAnimationFrame(firstRaf);
      cancelAnimationFrame(secondRaf);
    };
  }, [chat.messages.length]);

  // Reset stale suggestion index when suggestions shrink — computed during render
  // to avoid an extra effect-driven re-render cascade.
  if (activeSuggestionIndex >= suggestions.length && activeSuggestionIndex !== -1) {
    setActiveSuggestionIndex(-1);
  }
  const clampedSuggestionIndex = activeSuggestionIndex >= suggestions.length ? -1 : activeSuggestionIndex;

  useEffect(() => {
    if (!showSuggestions) return;

    const handleOutsideClick = (event: MouseEvent) => {
      if (inputAreaRef.current?.contains(event.target as Node)) return;
      setSuggestionsDismissed(true);
      setActiveSuggestionIndex(-1);
    };

    document.addEventListener('mousedown', handleOutsideClick);
    return () => {
      document.removeEventListener('mousedown', handleOutsideClick);
    };
  }, [showSuggestions]);

  const applySuggestion = useCallback((suggestion: string) => {
    setInputValue(suggestion);
    setSuggestionsDismissed(true);
    setActiveSuggestionIndex(-1);
  }, []);

  const handleSend = async () => {
    const message = inputValue.trim();
    if (!message) return;

    setSuggestionsDismissed(true);
    setActiveSuggestionIndex(-1);

    // Read graph snapshot at call time — no need to subscribe to graph changes
    const graph = useAppStore.getState().graph;

    // Read user highlights and convert Map<string, TextHighlight[]> to Record<string, string[]>
    const highlightMap = useHighlightStore.getState().highlights;
    const userTextHighlights: Record<string, string[]> = {};
    for (const [entityId, highlights] of highlightMap) {
      if (highlights.length > 0) {
        userTextHighlights[entityId] = highlights.map((h) => h.text);
      }
    }

    chat.addMessage('user', message);
    setInputValue('');
    chat.setLoading(true);

    const isFirstRequest = !chat.sessionInitialized;
    if (isFirstRequest && graph.nodes.length === 0) {
      chat.addMessage('system', CHAT_TEXT.missingGraphData);
      chat.setLoading(false);
      return;
    }

    const sessionId = getSessionId(chat.sessionId, isFirstRequest, chat);
    const isNewSessionContext = syncSessionFingerprint(sessionId, contextFingerprintRefs);

    const payload: ChatRequest = {
      query: message,
      user_id: chat.userId,
      session_id: sessionId,
    };

    const sessionSnapshot: SessionSnapshot = {
      isConnected,
      localPeerId,
      virtualDesktop,
      localPeer,
      peers,
    };

    syncPayloadContext({
      payload,
      graph,
      session: sessionSnapshot,
      forceContextSend: isFirstRequest || isNewSessionContext,
      refs: contextFingerprintRefs,
    });
    addInitialSemanticContext(payload, graph, isFirstRequest);

    payload.selected_entity_ids = Array.from(graph.selectedEntityIds);
    if (Object.keys(userTextHighlights).length > 0) {
      payload.user_text_highlights = userTextHighlights;
    }
    if (Object.keys(graph.entityTags).length > 0) {
      payload.entity_tags = graph.entityTags;
    }

    // --- Debug: pre-chat snapshot ---
    if (debugLogger.isEnabled()) {
      const preDiag = captureDiagnosticSnapshot();
      debugLogger.logPreChat(preDiag, payload);
    }

    // Reset streaming state
    streamingTextRef.current = '';
    streamingThinkingRef.current = '';
    streamingToolsRef.current = [];

    // Create initial agent message for streaming updates
    chat.addMessage('agent', '');

    const finalizeResponse = (data: ChatResponse) => {
      if (isFirstRequest) {
        chat.setSessionInitialized(true);
      }

      if (data.response) {
        chat.updateLastAgentMessage(data.response);
      } else {
        chat.addMessage('system', CHAT_TEXT.missingAgentMessage);
      }

      if (data.thinking) {
        chat.updateLastAgentThinking(data.thinking);
      }

      applyChatResponseLayout({
        data,
        chat,
        graph,
        session: sessionSnapshot,
        emitDragBatch: emitNodeDragBatch,
      });

      // --- Debug: post-chat snapshot (after Yjs propagation) ---
      if (debugLogger.isEnabled()) {
        const delta = data.action?.layout_delta;
        const deltaSummary = delta ? summarizeDeltaChanges({
          updated_nodes: delta.updated_nodes ?? [],
          added_nodes: delta.added_nodes ?? [],
          removed_nodes: delta.removed_nodes ?? [],
          highlighted_nodes: delta.highlighted_nodes ?? [],
        }) : '';

        const postDiagDelayMs = data.action?.type === 'show_entity' ? 900 : 200;

        setTimeout(() => {
          const postDiag = captureDiagnosticSnapshot();
          debugLogger.logPostChat(data, deltaSummary, postDiag);
        }, postDiagDelayMs);
      }
    };

    try {
      // Use streaming endpoint
      await streamChatMessage(payload, {
        onToolCall: (name, args) => {
          console.log('[ChatPanel] Tool call:', name, args);
          streamingToolsRef.current.push({ name, args });
        },
        onThinking: (reasoning) => {
          console.log('[ChatPanel] Thinking:', reasoning);
          streamingThinkingRef.current = reasoning;
          chat.updateLastAgentThinking([reasoning]);
        },
        onText: (text) => {
          streamingTextRef.current = text;
          chat.updateLastAgentMessage(text);
        },
        onDone: (data) => {
          console.log('[ChatPanel] Done:', data);

          // Build a full ChatResponse from the enriched done event
          const responseData: ChatResponse = {
            response: data.response,
            user_id: data.user_id ?? chat.userId,
            session_id: data.session_id ?? sessionId,
            thinking: data.thinking,
            action: data.action as ChatResponse['action'],
            layout: data.layout as ChatResponse['layout'],
            layout_stages: data.layout_stages as ChatResponse['layout_stages'],
            metadata: {
              tools_called: Array.isArray(data.tools)
                ? data.tools
                : streamingToolsRef.current,
            },
          };

          finalizeResponse(responseData);
        },
      });
    } catch (error: unknown) {
      // If streaming fails, fall back to non-streaming
      console.warn('[ChatPanel] Streaming failed, falling back to non-streaming:', error);
      
      try {
        const data: ChatResponse = await sendChatMessage(payload);

        finalizeResponse(data);
      } catch (fallbackError: unknown) {
        handleChatError(fallbackError, chat);
      }
    } finally {
      chat.setLoading(false);
    }
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Escape') {
      if (showSuggestions) {
        event.preventDefault();
        setSuggestionsDismissed(true);
        setActiveSuggestionIndex(-1);
      }
      return;
    }

    if (event.key === 'ArrowDown' && suggestions.length > 0) {
      event.preventDefault();
      setSuggestionsDismissed(false);
      setActiveSuggestionIndex((prev) => (
        prev < 0 || prev >= suggestions.length - 1 ? 0 : prev + 1
      ));
      return;
    }

    if (event.key === 'ArrowUp' && suggestions.length > 0) {
      event.preventDefault();
      setSuggestionsDismissed(false);
      setActiveSuggestionIndex((prev) => (
        prev <= 0 ? suggestions.length - 1 : prev - 1
      ));
      return;
    }

    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      if (showSuggestions && clampedSuggestionIndex >= 0) {
        applySuggestion(suggestions[clampedSuggestionIndex].text);
        return;
      }
      handleSend();
    }
  };

  const virtuosoComponents = useMemo(() => ({
    Header: () => <div className="chat-messages-edge-spacer" />,
    Footer: () => (
      <>
        {chat.isLoading && (
          <div className="chat-message-row">
            <div className="chat-message system">{CHAT_TEXT.thinking}</div>
          </div>
        )}
        <div className="chat-messages-edge-spacer" />
      </>
    ),
  }), [chat.isLoading]);

  return (
    <div className="chat-panel">
      <Virtuoso
        ref={virtuosoRef}
        className="chat-messages"
        data={chat.messages}
        followOutput={followOutput}
        atBottomStateChange={(atBottom) => { isAtBottomRef.current = atBottom; }}
        atBottomThreshold={50}
        components={virtuosoComponents}
        computeItemKey={(index) => index}
        itemContent={(_index, msg) => (
          <div className="chat-message-row">
            {msg.role === 'agent' && msg.thinking ? (
              <ThinkingSection content={msg.thinking} />
            ) : null}
            <div className={`chat-message ${msg.role}`}>
              {msg.role === 'user' ? msg.content : <ChatMessageMarkdown content={msg.content} />}
            </div>
          </div>
        )}
      />

      <div className="chat-input-area" ref={inputAreaRef}>
        <div className="chat-input-stack">
          <textarea
            ref={textareaRef}
            className="chat-input"
            placeholder={CHAT_TEXT.placeholder}
            value={inputValue}
            onChange={(event) => {
              setInputValue(event.target.value);
              setSuggestionsDismissed(false);
              setActiveSuggestionIndex(-1);
            }}
            onKeyDown={handleKeyDown}
            disabled={chat.isLoading}
            rows={2}
            aria-autocomplete="list"
            aria-expanded={showSuggestions}
            aria-controls="chat-autocomplete-list"
          />
          {showSuggestions && (
            <ul
              id="chat-autocomplete-list"
              className="chat-autocomplete-list"
              role="listbox"
              aria-label="Chat suggestions"
            >
              {suggestions.map((suggestion, index) => {
                const isActive = index === clampedSuggestionIndex;
                return (
                  <li key={`${suggestion.text}-${index}`} className="chat-autocomplete-row">
                    <button
                      type="button"
                      className={`chat-autocomplete-item ${isActive ? 'active' : ''}`}
                      role="option"
                      aria-selected={isActive}
                      onMouseDown={(event) => event.preventDefault()}
                      onClick={() => applySuggestion(suggestion.text)}
                    >
                      {suggestion.text}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
        <button
          className="chat-send-btn"
          onClick={handleSend}
          disabled={chat.isLoading || !inputValue.trim()}
          aria-label="Send message"
        >
          <SendIcon />
        </button>
      </div>
    </div>
  );
};
