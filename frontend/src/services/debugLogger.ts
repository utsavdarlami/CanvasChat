/**
 * Session-scoped debug logger.
 *
 * Captures multi-display diagnostics, chat request/response payloads,
 * and layout-update state into an in-memory buffer that can be downloaded
 * as a plain-text file.
 *
 * Disabled by default; toggle via the DiagnosticPanel "Log" button.
 * Enable state is persisted in localStorage.
 */

import type { ChatRequest, ChatResponse } from '@/types/api';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const STORAGE_KEY = 'debugLoggerEnabled';
const SEPARATOR = '='.repeat(80);
const SUB_SEPARATOR = '-'.repeat(60);

// ---------------------------------------------------------------------------
// Logger implementation
// ---------------------------------------------------------------------------

class DebugLogger {
  private buffer: string[] = [];
  private enabled: boolean;
  private chatCounter = 0;

  constructor() {
    try {
      this.enabled = localStorage.getItem(STORAGE_KEY) === 'true';
    } catch {
      this.enabled = false;
    }
  }

  // ---- Toggle ----

  isEnabled(): boolean {
    return this.enabled;
  }

  setEnabled(on: boolean): void {
    this.enabled = on;
    try {
      localStorage.setItem(STORAGE_KEY, String(on));
    } catch {
      // localStorage unavailable — ignore
    }
  }

  // ---- Session lifecycle ----

  startSession(metadata: {
    mode: string;
    files: string[];
    nodeCount: number;
  }): void {
    if (!this.enabled) return;

    // Reset buffer for the new analysis session
    this.buffer = [];
    this.chatCounter = 0;

    this.buffer.push(SEPARATOR);
    this.buffer.push(`SESSION START: ${new Date().toISOString()}`);
    this.buffer.push(`Mode: ${metadata.mode}`);
    this.buffer.push(`Files: ${metadata.files.join(', ')}`);
    this.buffer.push(`Nodes: ${metadata.nodeCount}`);
    this.buffer.push(SEPARATOR);
    this.buffer.push('');
  }

  // ---- Chat lifecycle ----

  logPreChat(diagnosticText: string, requestPayload: ChatRequest): void {
    if (!this.enabled) return;

    this.chatCounter++;
    const ts = new Date().toISOString();

    this.buffer.push(`${SUB_SEPARATOR}`);
    this.buffer.push(`CHAT #${this.chatCounter} PRE-SEND [${ts}]`);
    this.buffer.push(`${SUB_SEPARATOR}`);
    this.buffer.push('');

    this.buffer.push('=== Multi-Display Diagnostics (pre-chat) ===');
    this.buffer.push(diagnosticText);
    this.buffer.push('');

    this.buffer.push('=== Request Payload ===');
    try {
      this.buffer.push(JSON.stringify(requestPayload, null, 2));
    } catch {
      this.buffer.push('[Failed to serialize request payload]');
    }
    this.buffer.push('');
  }

  logPostChat(
    responsePayload: ChatResponse,
    deltaSummary: string,
    diagnosticText: string,
  ): void {
    if (!this.enabled) return;

    const ts = new Date().toISOString();

    this.buffer.push(`${SUB_SEPARATOR}`);
    this.buffer.push(`CHAT #${this.chatCounter} POST-RESPONSE [${ts}]`);
    this.buffer.push(`${SUB_SEPARATOR}`);
    this.buffer.push('');

    this.buffer.push('=== Response Payload ===');
    try {
      this.buffer.push(JSON.stringify(responsePayload, null, 2));
    } catch {
      this.buffer.push('[Failed to serialize response payload]');
    }
    this.buffer.push('');

    if (deltaSummary) {
      this.buffer.push('=== Layout Delta Summary ===');
      this.buffer.push(deltaSummary);
      this.buffer.push('');
    }

    this.buffer.push('=== Multi-Display Diagnostics (post-update) ===');
    this.buffer.push(diagnosticText);
    this.buffer.push('');
  }

  // ---- Manual entry ----

  log(label: string, data?: unknown): void {
    if (!this.enabled) return;

    const ts = new Date().toISOString();
    this.buffer.push(`[${ts}] ${label}`);
    if (data !== undefined) {
      try {
        this.buffer.push(typeof data === 'string' ? data : JSON.stringify(data, null, 2));
      } catch {
        this.buffer.push(String(data));
      }
    }
    this.buffer.push('');
  }

  // ---- Output ----

  getLogText(): string {
    return this.buffer.join('\n');
  }

  downloadLog(): void {
    const text = this.getLogText();
    if (!text) return;

    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const filename = `debug-session-${timestamp}.txt`;

    const blob = new Blob([text], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    URL.revokeObjectURL(url);
  }

  clear(): void {
    this.buffer = [];
    this.chatCounter = 0;
  }
}

// Singleton export
export const debugLogger = new DebugLogger();
