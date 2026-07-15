import { useEffect, useRef, useState } from 'react';
// import { fetchChatAutocomplete } from '@/services/api';
import type { AutocompleteSuggestion } from '@/types/api';

interface UseChatAutocompleteParams {
  input: string;
  userId: string;
  sessionId: string | null;
  sessionInitialized: boolean;
  enabled?: boolean;
  debounceMs?: number;
  minQueryLength?: number;
  maxSuggestions?: number;
  maxContextTurns?: number;
}

const DEFAULT_DEBOUNCE_MS = 200;
const DEFAULT_MIN_QUERY_LENGTH = 2;
const DEFAULT_MAX_SUGGESTIONS = 3;
const DEFAULT_MAX_CONTEXT_TURNS = 6;

export function useChatAutocomplete(params: UseChatAutocompleteParams) {
  const {
    input,
    userId,
    sessionId,
    sessionInitialized,
    enabled = true,
    debounceMs = DEFAULT_DEBOUNCE_MS,
    minQueryLength = DEFAULT_MIN_QUERY_LENGTH,
    maxSuggestions = DEFAULT_MAX_SUGGESTIONS,
    maxContextTurns = DEFAULT_MAX_CONTEXT_TURNS,
  } = params;

  const [suggestions, setSuggestions] = useState<AutocompleteSuggestion[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const requestCounter = useRef(0);

  useEffect(() => {
    const trimmed = input.trim();
    const canRequest = enabled
      && sessionInitialized
      && !!sessionId
      && trimmed.length >= minQueryLength;

    if (!canRequest || !sessionId) {
      setSuggestions([]);
      setIsLoading(false);
      return;
    }

    const thisRequestId = ++requestCounter.current;
    const controller = new AbortController();

    const timer = window.setTimeout(async () => {
      try {
        setIsLoading(true);

        // const data = await fetchChatAutocomplete(
        //   {
        //     partial_query: trimmed,
        //     user_id: userId,
        //     session_id: sessionId,
        //     max_suggestions: maxSuggestions,
        //     max_context_turns: maxContextTurns,
        //   },
        //   controller.signal,
        // );

        if (thisRequestId !== requestCounter.current) return;
        // setSuggestions(Array.isArray(data.suggestions) ? data.suggestions : []);
      } catch {
        if (controller.signal.aborted) return;
        if (thisRequestId !== requestCounter.current) return;
        setSuggestions([]);
      } finally {
        if (thisRequestId === requestCounter.current) {
          setIsLoading(false);
        }
      }
    }, debounceMs);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [
    debounceMs,
    enabled,
    input,
    maxContextTurns,
    maxSuggestions,
    minQueryLength,
    sessionId,
    sessionInitialized,
    userId,
  ]);

  return { suggestions, isLoading };
}
