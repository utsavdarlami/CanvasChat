import * as Y from 'yjs';
import type { GraphNode } from '@/types/graph';

export interface TimelineEntry {
  id: string;
  timestamp: number;
  label: string;
  source: 'drag' | 'chat';
  snapshot: GraphNode[];
}

let sharedTimeline: Y.Map<TimelineEntry> | null = null;
let timelineObserver: ((event: Y.YMapEvent<TimelineEntry>, transaction: Y.Transaction) => void) | null = null;
let onRemoteEntryCallback: ((entry: TimelineEntry) => void) | null = null;
let onRemoteClearCallback: (() => void) | null = null;

export function setupTimeline(doc: Y.Doc) {
  sharedTimeline = doc.getMap('sharedTimeline');

  timelineObserver = (event, transaction) => {
    if (!sharedTimeline || transaction.origin === 'local') return;

    let hasDeletes = false;
    event.keysChanged.forEach((id) => {
      const entry = sharedTimeline!.get(id);
      if (entry && onRemoteEntryCallback) {
        onRemoteEntryCallback(entry);
      } else if (!entry) {
        hasDeletes = true;
      }
    });

    // If all entries were deleted, notify the store to clear
    if (hasDeletes && sharedTimeline.size === 0 && onRemoteClearCallback) {
      onRemoteClearCallback();
    }
  };
  sharedTimeline.observe(timelineObserver);
}

export function teardownTimeline() {
  if (sharedTimeline && timelineObserver) {
    sharedTimeline.unobserve(timelineObserver);
  }
  sharedTimeline = null;
  timelineObserver = null;
  onRemoteEntryCallback = null;
  onRemoteClearCallback = null;
}

export function setOnRemoteEntry(callback: (entry: TimelineEntry) => void) {
  onRemoteEntryCallback = callback;
}

export function setOnRemoteClear(callback: () => void) {
  onRemoteClearCallback = callback;
}

export function broadcastTimelineEntry(entry: TimelineEntry): void {
  if (!sharedTimeline || !sharedTimeline.doc) return;

  sharedTimeline.doc.transact(() => {
    sharedTimeline!.set(entry.id, entry);
  }, 'local');
}

export function clearRemoteTimeline(): void {
  if (!sharedTimeline || !sharedTimeline.doc) return;

  sharedTimeline.doc.transact(() => {
    const keys = Array.from(sharedTimeline!.keys());
    keys.forEach((key) => {
      sharedTimeline!.delete(key);
    });
  }, 'local');
}

export function getAllRemoteEntries(): TimelineEntry[] {
  if (!sharedTimeline) return [];

  const entries: TimelineEntry[] = [];
  sharedTimeline.forEach((entry) => {
    entries.push(entry);
  });
  return entries.sort((a, b) => a.timestamp - b.timestamp);
}
