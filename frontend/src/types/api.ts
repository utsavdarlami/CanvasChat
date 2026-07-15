// API request/response types

import type { GraphData, EntityRecord } from './graph';

export interface VisualizationResponse extends GraphData {
  error?: string;
}

export { GraphData };

export interface ChatMessage {
  role: 'user' | 'agent' | 'system';
  content: string;
  timestamp: Date;
  thinking?: string[];
}

export interface DisplayContext {
  is_multi_display: boolean;
  local_peer_id: string;
  virtual_desktop: {
    total_width: number;
    total_height: number;
    displays: Array<{
      peer_id: string;
      tags: string[];
      x: number;
      y: number;
      width: number;
      height: number;
      node_ids: string[];
      camera?: {
        pan_x: number;
        pan_y: number;
        zoom: number;
      };
      visible_canvas?: {
        min_x: number;
        min_y: number;
        max_x: number;
        max_y: number;
        width: number;
        height: number;
      };
    }>;
  };
}

export interface TimelineContextEntry {
  index: number;
  label: string;
  source: 'drag' | 'chat';
  timestamp: number;
}

export interface ChatRequest {
  query: string;
  user_id: string;
  session_id: string;
  layout?: GraphData | Record<string, unknown>;
  entities?: EntityRecord[];
  selected_entity_ids?: string[];
  display_context?: DisplayContext;
  timeline_context?: {
    entries: TimelineContextEntry[];
    current_index: number;
  };
  user_text_highlights?: Record<string, string[]>;
  entity_tags?: Record<string, string[]>;
}

export interface ChatAutocompleteRequest {
  partial_query: string;
  user_id: string;
  session_id: string;
  max_suggestions?: number;
  max_context_turns?: number;
}

export interface AutocompleteSuggestion {
  text: string;
  score: number;
}

export interface ChatAutocompleteResponse {
  suggestions: AutocompleteSuggestion[];
  user_id: string;
  session_id: string;
}

export interface LayoutDeltaNode {
  entity_id: string;
  x: number;
  y: number;
  name?: string;
  display_id?: string;
  width?: number;
  height?: number;
}

export interface AddedNode {
  entity_id: string;
  name: string;
  display_name?: string;
  x: number;
  y: number;
  display_id?: string;
  width?: number;
  height?: number;
  clusters?: Array<Record<string, unknown>>;
  metadata?: Record<string, unknown>;
}

export interface RemovedNodeObject {
  entity_id: string;
  name?: string;
}
export type RemovedNode = RemovedNodeObject | string;

export interface TextHighlightEntry {
  entity_id: string;
  texts: string[];
  color?: string;
}

export interface GroupOverlay {
  label: string;
  entity_ids: string[];
  bounds: { min_x: number; min_y: number; max_x: number; max_y: number };
  color_index: number;
  display_id?: string;
}

export interface LayoutDelta {
  updated_nodes: LayoutDeltaNode[];
  added_nodes: AddedNode[];
  removed_nodes: RemovedNode[];
  highlighted_nodes?: string[];
  highlighted_node_colors?: Record<string, string>;
  text_highlights?: TextHighlightEntry[];
  clear_text_highlight_ids?: string[];
  /** Per-entity tag labels (entity_id → tags), authoritative from chat session layout */
  entity_tags?: Record<string, string[]>;
  user_text_highlights?: Record<string, string[]>;
  /** Per-display camera adjustments when arrangement overflows viewport. Maps display peer_id → {pan_x, pan_y, zoom}. */
  camera_updates?: Record<string, { pan_x: number; pan_y: number; zoom: number }>;
  /** Visual group overlays with bounds and labels, emitted by grouping actions. */
  group_overlays?: GroupOverlay[];
}

export type ChatActionType =
  | 'update_layout'
  | 'show_entity'
  | 'jump_to_timeline'
  | 'text_highlight'
  | 'clear_text_highlight'
  | 'tag_nodes'
  | 'clear_entity_tags';

export interface ChatAction {
  type?: ChatActionType;
  description: string;
  affected_entities?: string[];
  layout_delta?: LayoutDelta;
  timeline_index?: number;
}

export interface LayoutStage {
  label: string;
  entity_ids: string[];
  center: [number, number];
}

export interface ChatResponse {
  response: string;
  user_id: string;
  session_id: string;
  layout?: GraphData;
  action?: ChatAction;
  layout_stages?: LayoutStage[];
  thinking?: string[];
  metadata?: Record<string, unknown>;
}

export const API_CONFIG = {
  BASE_URL: import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000',
  ENDPOINTS: {
    CHAT: '/api/chat',
    CHAT_AUTOCOMPLETE: '/api/chat/autocomplete',
    CHAT_SESSION: '/api/chat/session',
  }
} as const;
