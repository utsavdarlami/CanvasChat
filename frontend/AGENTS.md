# AGENTS.md

This file provides context and instructions for AI agents (and human developers) working on the `semantic-api-lite` repository.

## 1. Project Overview

**semantic-api-lite** is a React-based web application (using Vite) for visualizing spatial entity layouts across multiple displays. It utilizes **React Flow (XYFlow)** for interactive entity views and **Yjs** for real-time state synchronization.

### Architecture
- **Framework**: React + Vite + TypeScript.
- **State Management**: Zustand stores (`src/stores/`).
- **Real-time Sync**: Yjs (CRDT) over WebSockets for cross-display state (node positions, UI state, active panels).
- **Graph Visualization**: 
  - `EntityFlowView`: Interactive nodes-only canvas using `@xyflow/react` (no edges/links).
- **Data Flow**: Users load JSON graph data, which is parsed and stored in Zustand. All node positions are **display-local canvas top-left** coordinates used directly by React Flow. Graph positions and UI state are broadcasted to connected peers via Yjs.

## 2. Environment & Commands

### Setup
1.  Install dependencies: `npm install`
2.  Start development server: `npm run dev`

### External API Endpoints
The frontend communicates with an external API (default: `http://127.0.0.1:8000`).
- `POST /api/distribution/visualize-from-cache`: Visualization data.
- `POST /api/chat`: Layout modification agent (request-response). Returns layout deltas with canvas coordinates.
- `POST /api/chat/stream`: Streaming chat via SSE. Events: `tool_call`, `thinking`, `text`, `done`.
- `POST /api/chat/autocomplete`: Query suggestions (wired but currently disabled on frontend).
- `DELETE /api/chat/session`: Clear/reset a chat session.
- `POST /api/extract-semantics`: Extract semantics for a single entity (visual or text).

### Testing
- Run the dev server and load sample data from `data/`.
- Verify graph rendering in the "Entity View" tab.
- Test multi-display synchronization by opening the app in multiple browser windows and using the Multi-Display modal to assign peer spaces.

## 3. Code Style Guidelines

### TypeScript/React (`src/**/*.tsx`)
- **Components**: Functional components with Hooks.
- **State**: Use `zustand` stores for global state (`useGraphStore`, `useUIStore`). Yjs state should sync with Zustand.
- **Styling**: CSS Modules or global CSS (`src/styles/`). `classcat` is available for class merging.
- **Formatting**: 2-space indentation (standard for the project).
- **Naming**: `PascalCase` for components, `camelCase` for functions/variables.

## 4. Agent Operational Rules

1.  **File Operations**:
    - Always use **absolute paths**.
    - Resolve paths relative to `/home/felladog/Desktop/LabUAH/semantic-api-lite`.
    - **Primary Source**: Work entirely in `src/`.

2.  **Safety**:
    - Check `CLAUDE.md` for architectural context.
    - Verify component imports (especially from `@xyflow/react` and `yjs`).

3.  **Refactoring**:
    - When modifying `EntityFlowView`, remember it uses **React Flow**, and all node coordinates are canvas top-left — used directly by React Flow with no conversion.
    - Be aware of **Yjs sync hooks** (like `useCrossDisplaySync` or `emitNodeDrag`) and **Chat Agent updates** (`chatUpdatedNodeIds`). Ensure that new layout updates correctly propagate to the global `graphStore` or Yjs maps without causing infinite loops.
    - When adding new chat action types, follow the handler registry pattern in `src/components/Chat/actionHandlers/`. Do **not** add if/else branches to `chatPanelHelpers.ts` — create a handler and register it.

4.  **Dependencies**:
    - Use `npm install` for new packages.
    - `libs/xyflow` is available for reference/documentation, but the app uses the installed npm package (`@xyflow/react`).

5.  **Documentation**:
    - Update `MIGRATION_PLAN.md` when completing tasks.
    - Log major architectural changes in `docs/`.

## 5. Chat Action Handler Pattern

Chat responses from the backend are dispatched through a **handler registry** (`src/components/Chat/actionHandlers/`). This pattern is inspired by `tldraw-agent`'s action util registry.

### How it works
1. Backend tools return `_action_type` in their result dict (e.g. `"highlight"`, `"undo"`).
2. The `tool_safe` decorator stores this in session state as `_last_action_type`.
3. The chat endpoint uses this hint (falling back to heuristic detection) to set `action.type`.
4. The frontend `dispatchChatAction()` routes to the matching `ChatActionHandler`.

### Adding a new action type
| Step | File | What to do |
|------|------|------------|
| 1 | `backend/api/models/chat.py` | Add type string to `LayoutAction.type` Literal |
| 2 | Backend tool file | Return `"_action_type": "your_type"` in the tool result |
| 3 | `frontend/src/types/api.ts` | Add `'your_type'` to `ChatActionType` union |
| 4 | `frontend/src/components/Chat/actionHandlers/yourTypeHandler.ts` | Implement `ChatActionHandler` |
| 5 | `frontend/src/components/Chat/actionHandlers/registry.ts` | Register: `your_type: yourTypeHandler` |

### Handler interface
```typescript
interface ChatActionHandler {
  apply(ctx: ActionContext): void;  // Apply state changes
  recordsTimeline: boolean;         // Whether to snapshot for timeline
}
```

## 6. Directory Structure Key
- `src/`: Main application source.
  - `components/`: React components.
    - `Chat/`: Chat agent interface for layout modifications.
      - `actionHandlers/`: Action handler registry (types, handlers, registry).
    - `EntityView/`: **EntityFlowView** (React Flow graph), EntityNode.
    - `MultiDisplay/`: Peer layout management and diagnostic panels for Yjs.
    - `Sidebar/`: UI controls.
  - `services/`: API and Yjs integration.
    - `yjs/`: Yjs awareness, node position syncing, and CRDT configurations.
  - `stores/`: Zustand state stores.
  - `utils/`: Helper functions.
  - `types/`: TypeScript definitions.
- `docs/`: Project documentation.
- `data/`: Sample JSON data.
