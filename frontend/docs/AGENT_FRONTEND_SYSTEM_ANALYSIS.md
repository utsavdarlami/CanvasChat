# Agent-Frontend System Analysis

End-to-end data flow between the backend layout agent and the frontend canvas system.

## Architecture Overview

```
User query + canvas state → Backend enriches → Agent reasons with spatial context
→ Agent calls tools → Tools mutate session state → Delta computed
→ Response + delta sent via SSE → Frontend applies delta to ReactFlow
→ Next request carries updated state
```

---

## 1. Frontend → Backend: Chat Request

**File:** `src/components/Chat/ChatPanel.tsx` (handleSend)

Each `ChatRequest` includes:

| Field | Source | Purpose |
|-------|--------|---------|
| `layout` | `prepareLayoutForChat()` — node positions from store | Current canvas coordinates |
| `display_context` | `buildDisplayContext()` — per-display viewport | Screen size, pan/zoom, visible bounds |
| `entities` | Full entity records (first request only) | Semantic content for agent |
| `selected_entity_ids` | User selection on canvas | Deictic reference resolution |
| `entity_tags` | Session state | User-assigned tags |
| `user_text_highlights` | Session state | User text selections |
| `timeline_context` | Historical snapshots | Undo/redo support |

**Optimization:** Context fingerprinting — layout/display only resent if hash changes.

---

## 2. Backend Session Processing

**Files:**
- `backend/api/endpoints/chat.py` — API routes
- `backend/api/endpoints/chat_logic/session.py` — Session management

### Endpoints

- **POST `/api/chat`** — Non-streaming, returns complete response
- **POST `/api/chat/stream`** — SSE streaming with real-time events

### Session Flow

1. `get_or_create_session()` loads/creates session with layout + entities + display_context
2. If `layout` provided → full layout refresh + merge with existing session data
3. If only `display_context` → recalculate surface assignments (multi-display topology change)
4. Display context reuse: if not provided but session has it → reuse existing
5. Selected entities enriched into query text
6. Layout snapshot captured before agent runs (for delta detection later)

---

## 3. Context Injection (Before Every LLM Call)

**File:** `backend/agent/callbacks.py` — `inject_layout_context()`

The `before_model_callback` builds `[Current Layout State]` and appends it as a system instruction before every LLM call.

### What gets injected

```
[Current Layout State]
[Display name] display (surface_id): N entities
  Screen: WxH px
  Visible canvas: (min_x, min_y) to (max_x, max_y)
  [Viewport Analysis]
    In view: X of N entities
    Screen-space entity size: ~WxH px (readable/scannable/too small)
    Density: X% (comfortable/crowded/sparse)
    Capacity: fits ~N at zoom, has M (room for X more/at limit/over capacity)
  Arrangement: stacked vertically/grid/scattered at X,Y occupying WxH
  Entities:
    entity_id "Entity Name" @ (x,y) WxH [sentiment] tags:[...] [visibility]
```

### Change detection

- MD5 fingerprint of positions + assignments + tags
- Tracks whether layout changed since last injection
- Includes active tags and user highlights sections

---

## 4. Agent Tool Execution

**Files:**
- `backend/agent/agent.py` — Agent setup with Google ADK
- `backend/agent/tools.py` — Tool facade
- `backend/agent/tool_ops/layout_tools.py` — Layout tools
- `backend/agent/tool_ops/ui_tools.py` — UI tools
- `backend/agent/layout_ops/mutations.py` — State mutations

### Available Tools

**Layout Manipulation:**
- `tool_move_entity` — Move entity to position or near reference
- `tool_resize_entity` / `tool_resize_entities` — Adjust dimensions
- `tool_adjust_position` — Fine-tune position
- `tool_arrange_entities` — Grid/horizontal/vertical arrangement
- `tool_arrange_relative` — Position relative to reference entity
- `tool_swap` — Swap two entities
- `tool_snap_edges` — Align entity edges
- `tool_maximize_to_display` — Fit entity to display
- `tool_scale` — Scale all positions uniformly

**Display/Camera:**
- `tool_camera` — Pan/zoom camera on a display
- `tool_jump_to_timeline` — Navigate frontend timeline

**Planning & Validation:**
- `tool_plan_layout` — Plan layout by clusters/field/time/declutter
- `tool_validate_layout` — Check overlaps, overflows, spacing
- `tool_inspect_layout` — Read layout (raw/summary/semantic detail)

**UI/Highlight:**
- `tool_show_entity` — Glow/highlight entity node
- `tool_highlight_text` — Highlight text spans inside entity content
- `tool_clear_text_highlights` — Remove highlights
- `tool_add_entity_tags` / `tool_remove_entity_tags` — Manage tags
- `tool_add_entity_tags_bulk` / `tool_remove_entity_tags_bulk` — Batch tagging
- `tool_move_entities_by_tag` — Bulk move by tag

**Meta:**
- `tool_think` — Agent reasoning step (no state change)
- `tool_todo` — Track multi-step tasks

### Tool execution model

Each tool reads/mutates `session.state["current_layout"]` directly:
```python
layout["node_positions"][entity_id] = target_position
return _refresh_content_bounds(layout)
```

Some tools set `session_state["_last_action_type"]` as a hint for action detection (e.g., `tool_highlight_text` → `"text_highlight"`).

---

## 5. Response Construction & Action Detection

**Files:**
- `backend/api/endpoints/chat_logic/actions.py` — Action detection
- `backend/api/models/response.py` — Response models

### Post-agent processing

1. Snapshot current layout from session
2. Compare previous ↔ current layout
3. Check forward-declared hints from tools (`_last_action_type`)
4. Run structural change detection (position, dimension, assignment diffs)
5. Structural changes take precedence over hints
6. Calculate `LayoutDelta` (updated/added/removed nodes, highlights, tags, camera_updates)
7. Export layout to graph format for client

### SSE Event Sequence

```
event: tool_call    data: {"name": "tool_move_entity", "args": {...}}
event: thinking     data: "reasoning text"
event: text         data: "partial response text"
event: done         data: {"response": "...", "action": {...}, "layout": {...}, ...}
```

### ChatResponse Structure

```python
ChatResponse(
    response=response_text,
    action=LayoutAction(type, description, affected_entities),
    layout=layout_graph,          # Full layout in graph format
    thinking=[...],               # Thinking steps from tool_think
    metadata={"tools_called": [...]},
)
```

---

## 6. Frontend Response Processing

**Files:**
- `src/services/api.ts` — SSE parsing (`streamChatMessage()`)
- `src/components/Chat/actionHandlers/registry.ts` — Action dispatch

### SSE Processing

`streamChatMessage()` parses SSE events and dispatches to callbacks:
- `onToolCall()` — real-time tool call notifications
- `onThinking()` — agent reasoning display
- `onText()` — streaming text response
- `onDone()` — final response with action, layout, tools

### Action Dispatch

1. Routes response via `action.type` to handler registry
2. Applies **transient state first** (highlights, camera) regardless of action type
3. Runs structural handler (e.g., `updateLayoutHandler`)

---

## 7. Layout Delta Application

**Files:**
- `src/stores/slices/graph/chatActions.ts` — `applyLayoutDelta()`
- `src/components/EntityView/EntityFlowView.tsx` — ReactFlow sync

### Delta application

`applyLayoutDelta()`:
1. Updates existing nodes (x, y, displayId, dimensions)
2. Removes nodes
3. Adds new nodes
4. Marks affected IDs in `chatUpdatedNodeIds` set

### ReactFlow sync

- Nodes in `chatUpdatedNodeIds` use new positions from `initialNodes`
- Other nodes preserve user's manual drag positions
- Collision resolution runs only for chat-updated nodes
- Syncs back to Zustand and broadcasts to peers via Yjs

---

## 8. Camera Command Execution

**Files:**
- `src/stores/slices/sessionSlice.ts` — Camera state
- `src/components/EntityView/EntityFlowView.tsx` — Camera effects

### Camera state

Tracked in `localPeer.camera = {x, y, zoom}`:
- **User panning/zooming:** `handleMove()` throttled at 300ms → `setLocalPeerCamera()`
- **Agent commands:** `setPendingCameraCommand()` queued → awaited in effect → `setViewport()`
- **Broadcast:** Via `updatePeerPresence()` to Yjs awareness (ephemeral)

### Camera commands from agent

Per-display camera updates from `layout_delta.camera_updates`:
```typescript
{ "yjs-peer1": { pan_x: 100, pan_y: 200, zoom: 1.5 } }
```
- Local peer → `setPendingCameraCommand({kind: 'setViewport', ...})`
- Remote peers → `broadcastUIState('cameraCommand', ...)`

### Command types

| Kind | Behavior |
|------|----------|
| `fitNodes` | Frame highlighted entities with `fitView()` |
| `setViewport` | Direct pan/zoom with `setViewport()` |
| `fitBounds` | Frame rectangle with `fitBounds()` |

All animate over 450ms.

---

## 9. Text Highlights & Entity Tags

**Files:**
- `src/stores/highlightStore.ts` — Highlight state
- `src/components/EntityView/EntityPanelContent.tsx` — Rendering
- `src/components/EntityView/highlightTextChildren.tsx` — Text marking

### Text highlight flow

1. Handler adds to `highlightStore` Map
2. Broadcast to peers via `broadcastUIState('textHighlights')`
3. Component reads highlights for entity
4. `buildHighlightComponents()` creates markdown custom components
5. `highlightTextChildren()` wraps matching text in `<mark>` elements with custom colors

### Entity tags

- Visual chips rendered on entity nodes
- Managed via `tool_add_entity_tags` / `tool_remove_entity_tags`
- Used for grouping and `tool_move_entities_by_tag` operations

---

## 10. Multi-Peer Sync (Yjs)

**Files:**
- `src/services/yjs/nodePositions.ts` — Position CRDT sync
- `src/services/yjs/uiState.ts` — UI state broadcast
- `src/services/yjs/awareness.ts` — Ephemeral presence

The frontend uses Yjs CRDTs for multi-peer synchronization:
- Node positions synced via Yjs shared types
- Cross-display transfers detected and announced
- Camera state broadcast via Yjs awareness (ephemeral, not persisted)
- Text highlights and camera commands broadcast via `broadcastUIState()`

**Note:** The agent has no awareness of other connected peers or their viewports.

---

## 11. Session State Structure

**File:** `backend/agent/agent.py`

```python
state = {
    "current_layout": {
        "node_positions": {entity_id: (x, y), ...},
        "node_dimensions": {...},
        "surface_assignments": {surface_id: [entity_ids], ...},
        "entity_names": {entity_id: "Display Name", ...},
        "entity_tags": {entity_id: ["tag1", "tag2"], ...},
        "surface_bounds": {...},
        "displays": [...],
        "user_text_highlights": {entity_id: ["text1", ...], ...},
    },
    "entities": [...],              # Semantic entity data
    "display_context": {...},       # Multi-display topology
    "timeline_context": {...},      # Frontend history
    "agent_todos": [...],           # Todo list state
    "_last_layout_fingerprint": str, # Change tracking
    "_last_action_type": str,       # Action type hints from tools
}
```

---

## Key File Reference

| Purpose | Backend | Frontend |
|---------|---------|----------|
| **API Routes** | `api/endpoints/chat.py` | `services/api.ts` |
| **Agent Setup** | `agent/agent.py` | — |
| **Agent Runner** | `api/endpoints/chat_logic/agent.py` | — |
| **Context Injection** | `agent/callbacks.py` | — |
| **Session Mgmt** | `api/endpoints/chat_logic/session.py` | — |
| **Tool Definitions** | `agent/tools.py`, `agent/tool_ops/` | — |
| **Layout Mutations** | `agent/layout_ops/mutations.py` | — |
| **Action Detection** | `api/endpoints/chat_logic/actions.py` | — |
| **Action Dispatch** | — | `Chat/actionHandlers/registry.ts` |
| **State Management** | — | `stores/graphStore.ts`, `stores/slices/` |
| **Canvas Rendering** | — | `EntityView/EntityFlowView.tsx` |
| **Highlights** | — | `stores/highlightStore.ts`, `EntityView/highlightTextChildren.tsx` |
| **Yjs Sync** | — | `services/yjs/` |
| **Request Models** | `api/models/chat.py` | `types/api.ts` |
| **Response Models** | `api/models/response.py` | `types/api.ts` |

---

## Known Gaps

1. **Frontend collision resolution** — The frontend may adjust node positions after applying the delta to resolve overlaps. The agent doesn't learn about these adjustments until the next request cycle.

2. **Camera animation delay** — Camera commands animate over 450ms. If the agent reasons about "what the user sees" immediately after a camera command, it's reasoning about a state the user hasn't visually reached yet.

3. **Multi-peer blindness** — The agent has no awareness of other connected peers or their viewports. In collaborative scenarios, the agent only knows about the requesting user's viewport.

4. **Timeline context** — The prompt's guidance on timeline operations is minimal ("don't call layout tools in the same turn after `tool_jump_to_timeline`"). The agent doesn't deeply reason about timeline state.
