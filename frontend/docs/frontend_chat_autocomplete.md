# Frontend Guide: `/api/chat/autocomplete`

This guide explains how to integrate the autocomplete endpoint into a chat input UI.

## Purpose

`POST /api/chat/autocomplete` provides quick query suggestions for the user while typing.

It is designed to:
1. Reuse the same chat session (`user_id`, `session_id`) as `/api/chat`.
2. Return suggestions only.
3. Never mutate layout state or trigger agent tools.

## Endpoint Contract

## Request

`POST /api/chat/autocomplete`

```json
{
  "partial_query": "move related",
  "user_id": "demo_user",
  "session_id": "demo_session",
  "max_suggestions": 3,
  "max_context_turns": 6
}
```

Field notes:
1. `partial_query` is required.
2. `max_suggestions` range is `1..5`.
3. `max_context_turns` range is `0..20`.

## Response

```json
{
  "suggestions": [
    { "text": "move related views to the left display", "score": 0.91 },
    { "text": "move related views to the right display", "score": 0.84 }
  ],
  "user_id": "demo_user",
  "session_id": "demo_session"
}
```

Possible empty response:

```json
{
  "suggestions": [],
  "user_id": "demo_user",
  "session_id": "demo_session"
}
```

When `suggestions` is empty, the client should skip rendering the suggestions dropdown.

## Session Requirement

Autocomplete requires an existing session.

If no session exists, the endpoint returns `400`:
```json
{
  "detail": "No active session found. Initialize the session with /api/chat first."
}
```

Practical implication:
1. First initialize a session with `/api/chat` (typically first message with `layout`).
2. Then call `/api/chat/autocomplete` using the same `user_id` and `session_id`.

## Recommended Frontend Behavior

1. Debounce calls by `150-300ms`.
2. Only call autocomplete when input length is at least `2` characters.
3. Cancel in-flight request when user types again.
4. Ignore stale responses if a newer request already started.
5. Hide suggestions when:
   - input is empty
   - response has `suggestions: []`
   - request returns non-200
6. On suggestion click:
   - set input text to suggestion
   - optionally submit directly to `/api/chat`

## TypeScript Types

```ts
export type ChatAutocompleteRequest = {
  partial_query: string;
  user_id: string;
  session_id: string;
  max_suggestions?: number;   // default 3
  max_context_turns?: number; // default 6
};

export type AutocompleteSuggestion = {
  text: string;
  score: number;
};

export type ChatAutocompleteResponse = {
  suggestions: AutocompleteSuggestion[];
  user_id: string;
  session_id: string;
};
```

## Fetch Helper (TypeScript)

```ts
export async function fetchChatAutocomplete(
  baseUrl: string,
  body: ChatAutocompleteRequest,
  signal?: AbortSignal
): Promise<ChatAutocompleteResponse> {
  const res = await fetch(`${baseUrl}/api/chat/autocomplete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });

  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Autocomplete failed (${res.status}): ${detail}`);
  }

  return res.json();
}
```

## React Hook Example

```tsx
import { useEffect, useRef, useState } from "react";

type Suggestion = { text: string; score: number };

export function useChatAutocomplete(params: {
  baseUrl: string;
  userId: string;
  sessionId: string;
  input: string;
}) {
  const { baseUrl, userId, sessionId, input } = params;
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const reqCounter = useRef(0);

  useEffect(() => {
    const trimmed = input.trim();
    if (trimmed.length < 2) {
      setSuggestions([]);
      setLoading(false);
      setError(null);
      return;
    }

    const thisReq = ++reqCounter.current;
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        setLoading(true);
        setError(null);

        const res = await fetch(`${baseUrl}/api/chat/autocomplete`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            partial_query: trimmed,
            user_id: userId,
            session_id: sessionId,
            max_suggestions: 3,
            max_context_turns: 6,
          }),
          signal: controller.signal,
        });

        if (!res.ok) {
          // Session not initialized or transient backend issue
          setSuggestions([]);
          return;
        }

        const data = (await res.json()) as { suggestions: Suggestion[] };

        // Drop stale response
        if (thisReq !== reqCounter.current) return;

        setSuggestions(Array.isArray(data.suggestions) ? data.suggestions : []);
      } catch (_err) {
        if (controller.signal.aborted) return;
        setSuggestions([]);
        setError("autocomplete_failed");
      } finally {
        if (thisReq === reqCounter.current) setLoading(false);
      }
    }, 200);

    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [baseUrl, userId, sessionId, input]);

  return { suggestions, loading, error };
}
```

## UI Rules

1. Render dropdown only when `suggestions.length > 0`.
2. Sort by backend-provided order (already ranked).
3. Show top score first.
4. Optionally display `score` as subtle confidence text.
5. Use keyboard support:
   - `ArrowDown` / `ArrowUp` to navigate
   - `Enter` to apply selected suggestion
   - `Esc` to close suggestions

## Common Failure Cases

1. `400` no active session:
   - Initialize session via `/api/chat` first.
2. `500` internal error:
   - Treat as no suggestions and continue normal chat UX.
3. Network timeout:
   - Cancel request and keep typing responsive.
4. Empty list:
   - Do not display dropdown.

## Suggested Client Flow

1. User opens chat panel.
2. First real message goes to `/api/chat` and creates/uses session.
3. While user types next messages, client calls `/api/chat/autocomplete`.
4. User picks a suggestion or continues typing.
5. Final send always goes to `/api/chat`.
