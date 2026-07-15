import type {
  ChatAutocompleteRequest,
  ChatAutocompleteResponse,
  ChatRequest,
  ChatResponse,
} from '@/types/api';

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL !== undefined
    ? import.meta.env.VITE_API_BASE_URL
    : 'http://127.0.0.1:8000';

/**
 * Event types from streaming SSE endpoint
 */
export type StreamEventType = 'tool_call' | 'thinking' | 'text' | 'done';

export interface StreamEvent {
  type: StreamEventType;
  data: unknown;
}

/**
 * Callback types for streaming
 */
export type StreamToolCallCallback = (name: string, args: Record<string, unknown>) => void;
export type StreamThinkingCallback = (reasoning: string) => void;
export type StreamTextCallback = (text: string) => void;
export type StreamDoneCallback = (data: {
  response: string;
  user_id?: string;
  session_id?: string;
  tools: unknown[];
  thinking: string[];
  action?: unknown;
  layout?: unknown;
  layout_stages?: Array<{
    label: string;
    entity_ids: string[];
    center: [number, number];
  }>;
}) => void;

/**
 * Stream chat message for real-time updates
 */
export async function streamChatMessage(
  payload: ChatRequest,
  callbacks: {
    onToolCall?: StreamToolCallCallback;
    onThinking?: StreamThinkingCallback;
    onText?: StreamTextCallback;
    onDone?: StreamDoneCallback;
  }
): Promise<void> {
  const apiUrl = `${API_BASE_URL}/api/chat/stream`;
  
  console.log('[Chat] Streaming request payload:', payload);

  const response = await fetch(apiUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    let errorData: { detail?: string } | null = null;
    try {
      errorData = (await response.json()) as { detail?: string };
    } catch {
      errorData = { detail: 'Server error: ' + response.statusText };
    }
    throw new Error(errorData?.detail || `HTTP error! status: ${response.status}`);
  }

  if (!response.body) {
    throw new Error('No response body');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  const dispatchEvent = (eventType: StreamEventType, data: unknown) => {
    switch (eventType) {
      case 'tool_call': {
        const payload = data as { name?: unknown; args?: unknown };
        const name = typeof payload?.name === 'string' ? payload.name : '';
        const args = (payload?.args && typeof payload.args === 'object' && !Array.isArray(payload.args))
          ? (payload.args as Record<string, unknown>)
          : {};
        callbacks.onToolCall?.(name, args);
        break;
      }
      case 'thinking':
        if (typeof data === 'string') {
          callbacks.onThinking?.(data);
        }
        break;
      case 'text':
        if (typeof data === 'string') {
          callbacks.onText?.(data);
        }
        break;
      case 'done':
        if (data && typeof data === 'object') {
          callbacks.onDone?.(data as Parameters<NonNullable<typeof callbacks.onDone>>[0]);
        }
        break;
    }
  };

  const parseEventBlock = (block: string) => {
    if (!block.trim()) return;

    let eventType: StreamEventType | null = null;
    const dataLines: string[] = [];

    for (const rawLine of block.split('\n')) {
      const line = rawLine.trimEnd();
      if (!line || line.startsWith(':')) continue;

      if (line.startsWith('event:')) {
        eventType = line.slice('event:'.length).trim() as StreamEventType;
        continue;
      }

      if (line.startsWith('data:')) {
        dataLines.push(line.slice('data:'.length).trimStart());
      }
    }

    if (!eventType || dataLines.length === 0) return;

    try {
      const data = JSON.parse(dataLines.join('\n'));
      dispatchEvent(eventType, data);
    } catch (e) {
      console.warn('[Chat Stream] Failed to parse SSE event payload:', e);
    }
  };

  while (true) {
    const { done, value } = await reader.read();

    if (done) {
      buffer += decoder.decode();
      break;
    }

    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n');

    let splitIndex = buffer.indexOf('\n\n');
    while (splitIndex !== -1) {
      const block = buffer.slice(0, splitIndex);
      buffer = buffer.slice(splitIndex + 2);
      parseEventBlock(block);
      splitIndex = buffer.indexOf('\n\n');
    }
  }

  if (buffer.trim()) {
    parseEventBlock(buffer);
  }
}

/**
 * Send chat message for layout modifications
 */
export async function sendChatMessage(
  payload: ChatRequest
): Promise<ChatResponse> {
  const apiUrl = `${API_BASE_URL}/api/chat`;
  
  console.log('[Chat] Request payload:', payload);

  const response = await fetch(apiUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    let errorData: { detail?: string } | null = null;
    try {
      errorData = (await response.json()) as { detail?: string };
    } catch {
      errorData = { detail: 'Server error: ' + response.statusText };
    }

    if (response.status === 400 && errorData?.detail?.includes('No active session')) {
      throw new Error('SESSION_EXPIRED');
    }
    throw new Error(errorData?.detail || `HTTP error! status: ${response.status}`);
  }

  const data: ChatResponse = await response.json();
  console.log('[Chat] Response:', data);
  return data;
}

/**
 * Fetch chat autocomplete suggestions for an existing session
 */
export async function fetchChatAutocomplete(
  payload: ChatAutocompleteRequest,
  signal?: AbortSignal,
): Promise<ChatAutocompleteResponse> {
  const apiUrl = `${API_BASE_URL}/api/chat/autocomplete`;

  const response = await fetch(apiUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(payload),
    signal,
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const data = (await response.json()) as { detail?: string };
      detail = data.detail || detail;
    } catch {
      // Ignore parsing errors; fallback to statusText
    }
    throw new Error(`AUTOCOMPLETE_FAILED:${response.status}:${detail}`);
  }

  return response.json();
}

/**
 * Clear chat session
 */
export async function clearChatSession(userId: string, sessionId: string): Promise<void> {
  const params = new URLSearchParams({
    user_id: userId,
    session_id: sessionId,
  });
  const apiUrl = `${API_BASE_URL}/api/chat/session?${params.toString()}`;
  
  const response = await fetch(apiUrl, {
    method: 'DELETE',
    headers: {
      'Content-Type': 'application/json'
    }
  });

  if (!response.ok) {
    throw new Error(`Failed to clear chat session: ${response.statusText}`);
  }
}

/**
 * Upload image files to the backend static directory.
 * Returns a map of filename -> served URL path.
 */
export async function uploadImageFiles(
  files: File[],
): Promise<Map<string, string>> {
  const apiUrl = `${API_BASE_URL}/api/upload-files`;

  const formData = new FormData();
  for (const file of files) {
    formData.append('files', file);
  }

  const response = await fetch(apiUrl, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const data = (await response.json()) as { detail?: string };
      detail = data.detail || detail;
    } catch {
      // fallback to statusText
    }
    throw new Error(`Image upload failed: ${detail}`);
  }

  const data = (await response.json()) as {
    uploaded: Array<{ filename: string; url: string }>;
  };

  const urlMap = new Map<string, string>();
  for (const entry of data.uploaded) {
    urlMap.set(entry.filename, `${API_BASE_URL}${entry.url}`);
  }
  return urlMap;
}

/**
 * Read file as JSON
 */
export function readFileAsJSON<T = unknown>(file: File): Promise<T> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    
    reader.onload = (e) => {
      try {
        const jsonData = JSON.parse(e.target?.result as string);
        resolve(jsonData);
      } catch (error) {
        reject(new Error(`Failed to parse ${file.name}: ${error}`));
      }
    };
    
    reader.onerror = () => {
      reject(new Error(`Failed to read ${file.name}`));
    };
    
    reader.readAsText(file);
  });
}

/**
 * Format file size for display
 */
export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
