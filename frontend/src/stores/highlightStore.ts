import { create } from 'zustand';
import { broadcastUIState } from '@/services/yjs/uiState';

export interface TextHighlight {
  id: string;
  text: string;
  color: string;
}

export type SerializedHighlights = Record<string, { text: string; color: string }[]>;

interface HighlightState {
  /** entityId → array of highlights applied to that entity's text */
  highlights: Map<string, TextHighlight[]>;

  addHighlight: (entityId: string, text: string, color?: string, source?: 'local' | 'remote') => void;
  removeHighlight: (entityId: string, highlightId: string, source?: 'local' | 'remote') => void;
  clearHighlights: (entityId: string, source?: 'local' | 'remote') => void;
  clearAllHighlights: (source?: 'local' | 'remote') => void;
  setAllHighlights: (data: SerializedHighlights, source?: 'local' | 'remote') => void;
  getHighlights: (entityId: string) => TextHighlight[];
}

let nextId = 0;

function serializeHighlights(map: Map<string, TextHighlight[]>): string {
  const obj: SerializedHighlights = {};
  for (const [eid, hls] of map) {
    if (hls.length > 0) obj[eid] = hls.map((h) => ({ text: h.text, color: h.color }));
  }
  return JSON.stringify(obj);
}

export const useHighlightStore = create<HighlightState>((set, get) => ({
  highlights: new Map(),

  addHighlight: (entityId, text, color = '#fde68a', source = 'local') => {
    let changed = false;
    set((state) => {
      const next = new Map(state.highlights);
      const existing = next.get(entityId) ?? [];

      if (existing.some((h) => h.text === text)) return state;

      next.set(entityId, [
        ...existing,
        { id: `hl-${++nextId}`, text, color },
      ]);
      changed = true;
      return { highlights: next };
    });
    if (source === 'local' && changed) {
      broadcastUIState('textHighlights', serializeHighlights(get().highlights));
    }
  },

  removeHighlight: (entityId, highlightId, source = 'local') => {
    let changed = false;
    set((state) => {
      const next = new Map(state.highlights);
      const existing = next.get(entityId);
      if (!existing) return state;

      const filtered = existing.filter((h) => h.id !== highlightId);
      if (filtered.length === existing.length) return state;

      if (filtered.length === 0) {
        next.delete(entityId);
      } else {
        next.set(entityId, filtered);
      }
      changed = true;
      return { highlights: next };
    });
    if (source === 'local' && changed) {
      broadcastUIState('textHighlights', serializeHighlights(get().highlights));
    }
  },

  clearHighlights: (entityId, source = 'local') => {
    let changed = false;
    set((state) => {
      if (!state.highlights.has(entityId)) return state;
      const next = new Map(state.highlights);
      next.delete(entityId);
      changed = true;
      return { highlights: next };
    });
    if (source === 'local' && changed) {
      broadcastUIState('textHighlights', serializeHighlights(get().highlights));
    }
  },

  clearAllHighlights: (source = 'local') => {
    let changed = false;
    set((state) => {
      if (state.highlights.size === 0) return state;
      changed = true;
      return { highlights: new Map() };
    });
    if (source === 'local' && changed) {
      broadcastUIState('textHighlights', JSON.stringify({}));
    }
  },

  setAllHighlights: (data, source = 'local') => {
    set(() => {
      const next = new Map<string, TextHighlight[]>();
      for (const [eid, entries] of Object.entries(data)) {
        if (entries.length > 0) {
          next.set(
            eid,
            entries.map((e) => ({ id: `hl-${++nextId}`, text: e.text, color: e.color })),
          );
        }
      }
      return { highlights: next };
    });
    if (source === 'local') {
      broadcastUIState('textHighlights', JSON.stringify(data));
    }
  },

  getHighlights: (entityId) => {
    return get().highlights.get(entityId) ?? [];
  },
}));
