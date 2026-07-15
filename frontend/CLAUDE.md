# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**semantic-api-lite** - React-based visualization framework for spatial entity layouts.

A modern web application serving interactive visualizations for graph data. It leverages React Flow (XYFlow) for "Entity Panels" and integrates real-time collaboration and multi-display synchronization via Yjs.

## Architecture

### Frontend Stack
- **Core**: React 18, TypeScript, Vite.
- **Visualization**: 
  - **@xyflow/react**: For the interactive "Entity View" (nodes-only canvas).
- **State**: 
  - `zustand` for efficient global state management (`stores/`).
  - `yjs` (CRDTs) over WebSockets for cross-display state synchronization (nodes dragging, panel UI, graph data updates).

### Layout Structure
- **AppLayout**: Main shell with sidebar and content area.
- **Sidebar**: File upload, chat interface, and UI controls.
- **Main Content**: Renders `EntityFlowView` configured via `MultiDisplay` options.

### Key Components

#### Entity View (`src/components/EntityView/`)
- **EntityFlowView.tsx**: The main canvas rendering entity nodes using React Flow. Integrates `chatUpdatedNodeIds` and Yjs remote coordinate updates dynamically. No edges or overlays -- nodes only.
- **EntityNode.tsx**: Custom React Flow node wrapper around `EntityPanelContent`. Connectable via handles.
- **hooks/**: Handlers for Yjs awareness mappings (`useCrossDisplaySync`, `useNodeDrag`) pushing updates back and forth to peer displays.

#### Chat Agent (`src/components/Chat/`)
- Interacts with a backend LLM (`POST /api/chat` and `POST /api/chat/stream`) for spatial view modifications. Sends the current graph's **canvas coordinates** directly and expects layout deltas with canvas coordinates to rewrite positions in the `graphStore`.
- **Action Handler Registry** (`src/components/Chat/actionHandlers/`): Chat responses are dispatched through a handler registry pattern (inspired by tldraw-agent). Each `ChatActionType` maps to a `ChatActionHandler` that implements `apply(ctx)` and declares `recordsTimeline`.
  - `updateLayoutHandler` — structural changes (move/add/remove). Used by `update_layout`, `undo`, `redo`, `revert`.
  - `highlightHandler` — transient show_entity UI state (highlight + camera focus).
  - `fullLayoutHandler` — fallback that replaces the entire graph.
  - **To add a new action type**: (1) add to `ChatActionType` in `types/api.ts`, (2) create a handler implementing `ChatActionHandler`, (3) register in `actionHandlers/registry.ts`.

#### Multi-Display (`src/components/MultiDisplay/`)
- **PeerLayoutEditor.tsx**: An interactive mini-map that allows the user to re-orient physical peer bounds to define where "off-screen" content flows.
- **DiagnosticPanel.tsx**: A debug interface to inspect local Zustand vs remote Yjs states for consistency.

#### State Management (`src/stores/`)
- **graphStore**: Holds graph node data (`nodes`) and metadata. Reconciles local drag changes against chat updates (`chatUpdatedNodeIds`) and remote Yjs updates.
- **uiStore**: Manages UI state (sidebar visibility, active view), synchronized across peers.

## Development Commands

### Run
- **Start Dev Server**: `npm run dev` (Runs on port 5173 usually).
- **Build**: `npm run build`.

### Testing
- Load sample JSON files from `data/` via the UI.
- Test cross-peer connections using the `DiagnosticPanel` or multiple browser windows to observe `yjs` awareness synchronization.

## Implementation Details

### Coordinate System
- **Single coordinate space**: All node positions are **display-local canvas top-left** coordinates throughout the entire stack (backend, Zustand store, React Flow, Yjs CRDT).
- **No scaling pipeline**: The backend emits canvas coordinates directly. `useEntityFlowNodes` maps `GraphNode` positions to React Flow `Node` objects without transformation.
- **Chat Agent Updates**: The LLM receives canvas coordinates from the store and returns canvas coordinates in `layout_delta.updated_nodes`. These are applied directly via `applyLayoutDelta`.
- **Yjs Synchronization**: Dragging events are trapped (`onNodeDrag`, `onNodeDragStop`) and pushed to Yjs mappings so peers see live movements.

### Data Model
- **Nodes only**: The `GraphData` type contains only `nodes` (no links/edges). The `LayoutDelta` contains `updated_nodes`, `added_nodes`, `removed_nodes`, `highlighted_nodes`, and `focused_nodes`.
- **No abstract coordinates**: Historical abstract-to-canvas scaling was removed. Node positions are canvas coordinates end to end; there is no scaling step to reintroduce.

### Chat Action Flow
The backend agent runs tools that mutate layout state. The response includes an `action` with a `type` and `layout_delta`:
1. **Backend tools** forward-declare their action type via `_action_type` in their return dict (e.g. `"_action_type": "undo"`). The `tool_safe` decorator stores this in `state["_last_action_type"]`.
2. **Action detection** (`chat_logic/actions.py`) uses the forward-declared hint when available, falling back to heuristic snapshot comparison via `ActionDetector`.
3. **Frontend dispatch** (`actionHandlers/registry.ts`) routes on `action.type` to the matching `ChatActionHandler`. Transient state (highlights/focus) is applied first regardless of action type, then the handler runs.

### Pan & Zoom
- **User pan/zoom**: Pure frontend via React Flow built-in controls (scroll, pinch, drag). No backend involvement.
- **Agent `tool_show_entity`**: Sets both `highlighted_entities` + `focused_entities` → delta → `setHighlightedNodeIds` + `setFocusedNodeIds` → `EntityFlowView` useEffect calls `fitView()`/`setCenter()` to animate camera while applying amber glow.
- **Agent `tool_scale`**: Multiplies all node coordinates by a scale factor (positional transform, not viewport zoom).

## Current Test Data
- **`data/*.json`**: Sample JSON graph exports used to populate initial graphs before real-time operations occur.
