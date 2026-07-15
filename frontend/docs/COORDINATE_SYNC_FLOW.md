# Coordinate Sync Flow — End-to-End Reference

Date: March 2, 2026
Status: Reference document

This document traces the full lifecycle of node coordinates as they flow between
the React/TypeScript frontend and the Python backend agent. It is the single
authoritative reference for how coordinates are produced, transmitted, and
consumed across the system.

For focused coverage of individual pieces, see:

- [Frontend coordinate system](./coordinate-system.md)
- [Backend chat coordinate contract](./BACKEND_CHAT_COORDINATE_CONTRACT.md)
- [Display-local viewport model](./DISPLAY_LOCAL_VIEWPORT_MODEL.md)

---

## 1. The Two Coordinate Spaces

| Space | Definition | Origin | Owner | Typical values |
|-------|-----------|--------|-------|----------------|
| **Canvas** | React Flow's infinite-plane coordinates, display-local, top-left anchored | `(0, 0)` at React Flow default viewport origin | Frontend (per-display) | `0`–`5000+` depending on zoom/content |
| **Screen** | Pixel coordinates within a display's viewport container | Top-left of the React Flow container element | Frontend (derived from canvas + camera) | `0`–`1920` (viewport width) |

A fourth space exists for topology only:

| Space | Definition | Used for |
|-------|-----------|----------|
| **Virtual desktop** | Global pixel grid spanning all physical displays | Display adjacency, cross-display transfer routing. Never used for node placement. |

### Key invariant

> After initial scaling, the **authoritative coordinate space** for all node
> positions is **display-local canvas**. Every store (Zustand graph-store,
> React Flow internal state, Yjs CRDT for commits) holds canvas top-left
> coordinates. Screen coordinates appear only transiently at cross-display
> transfer boundaries.

---

## 2. Frontend → Backend Flow

When the user sends a chat message, the frontend assembles a `ChatRequest` and
POSTs it to `/api/chat`.

### 2.1 Preparing node positions

`chatPanelHelpers.ts:prepareLayoutForChat()` (line 105) builds the `layout`
payload:

```
layout.nodes[] = graph-store nodes mapped to:
  {
    entity_id,
    name,
    x: node.x,           // display-local canvas top-left
    y: node.y,           // display-local canvas top-left
    width, height,       // measured DOM dimensions
    display_id,          // owning peer ID
    clusters             // semantic cluster tags
  }
```

Coordinates come directly from `graph-store` — no conversion applied.

### 2.2 Building the display context

`chatPanelHelpers.ts:buildDisplayContext()` (line 192) constructs
`display_context` from the Yjs session state:

```
display_context = {
  is_multi_display: true,
  local_peer_id: <this peer's ID>,
  virtual_desktop: {
    total_width, total_height,
    displays: [
      {
        peer_id,
        tags: ["left"],
        x, y, width, height,          // virtual desktop topology
        node_ids: [entity IDs on this display],
        camera: { pan_x, pan_y, zoom },
        visible_canvas: { min_x, min_y, max_x, max_y, width, height }
      },
      ...
    ]
  }
}
```

### 2.3 Computing visible_canvas

`chatPanelHelpers.ts:computeVisibleCanvas()` (line 158) derives the visible
canvas rectangle from the camera:

```
min_x = (0 - pan_x) / zoom
min_y = (0 - pan_y) / zoom
max_x = (screen_width - pan_x) / zoom
max_y = (screen_height - pan_y) / zoom
```

This tells the backend exactly which region of the canvas the user can see on
each display.

### 2.4 Fingerprinting and deduplication

`chatPanelHelpers.ts:syncPayloadContext()` (line 427) fingerprints both `layout`
and `display_context` as JSON strings. Unchanged payloads are omitted from
subsequent requests to reduce bandwidth.

### 2.5 Wire format summary

```
POST /api/chat
{
  query: "move the outlier to the right display",
  layout: {
    nodes: [ { entity_id, x, y, display_id, width, height, ... } ],
    graph: { metadata }
  },
  display_context: {
    is_multi_display: true,
    virtual_desktop: { displays: [...] }
  }
}
```

---

## 3. Backend Internal Flow

### 3.1 Receiving the request

`api/endpoints/chat.py` (line 37) deserializes the request into Pydantic models
defined in `api/models/chat.py`:

- `ChatRequest.layout` — raw dict with nodes/links/graph
- `ChatRequest.display_context` — `DisplayContext` model with `VirtualDesktop`
  containing `DisplayInfo` entries

The display context is converted to a plain dict via `model_dump()` and passed
into the session initializer.

### 3.2 Loading and normalizing layout

`agent/layout_ops/io.py:load_layout_from_output()` (line 9) normalizes the
incoming layout into the agent's internal format:

```python
{
  "node_positions":      { entity_id: (x, y) },       # canvas coords as-is
  "surface_assignments": { peer_id: [entity_ids] },    # from display_context
  "surface_bounds":      { peer_id: (min_x, min_y, max_x, max_y) },
  "entity_names":        { entity_id: name },
  "entity_dimensions":   { entity_id: { width, height } },
  "displays":            [ { peer_id, tags, x, y, w, h, camera, visible_canvas } ]
}
```

### 3.3 Building display surfaces

`agent/layout_ops/display.py:_build_display_surfaces()` (line 59) constructs
surface bounds from the display context:

- **When `visible_canvas` is present** (normal case): uses `min_x/min_y/max_x/max_y`
  directly as surface bounds. This means all positioning operations work within
  the canvas region the user can actually see.
- **Fallback** (no `visible_canvas`): uses topology `x, y, x+width, y+height`.
  This is less accurate but functional.
- **No multi-display**: single `surface_0` with bounds derived from node extent.

Nodes are assigned to surfaces by matching `display_id` to `peer_id`.

### 3.4 Positioning operations

`agent/layout_ops/positioning.py:find_available_position()` (line 13) searches
for non-overlapping positions within surface bounds using a spiral search
outward from a reference point. All coordinates are in the canvas space
inherited from the frontend's `visible_canvas`.

### 3.5 Arrangement operations

`agent/layout_ops/arrangement.py:compute_arrangement_positions()` (line 35)
computes evenly-spaced positions within surface bounds for horizontal, vertical,
or grid arrangements. When node dimensions are available, uses dimension-aware
placement with configurable gaps.

### 3.6 Camera fit

`agent/layout_ops/arrangement.py:fit_display_camera_to_entities_if_needed()`
(line 179) checks whether arranged entities overflow the visible viewport. If
so, it computes a new camera (pan + zoom) to fit the content:

```python
fit_zoom = min(screen_w / content_w, screen_h / content_h)
pan_x = (screen_w / 2) - (center_x * fit_zoom)
pan_y = (screen_h / 2) - (center_y * fit_zoom)
```

The updated camera is attached to the display metadata in the response.

### 3.7 Exporting the response

`agent/layout_ops/io.py:export_to_graph_format()` (line 122) converts the
internal layout back to graph format. Node `x, y` values are written directly
from `node_positions` — still display-local canvas coordinates.

The chat endpoint compares before/after layout states to produce a `LayoutDelta`
containing only changed nodes, which is attached to the `ChatResponse`.

---

## 4. Backend → Frontend Flow

The backend returns a `ChatResponse` with an optional `action.layout_delta`:

```json
{
  "action": {
    "type": "update_layout",
    "description": "Moved outlier to right display center",
    "layout_delta": {
      "updated_nodes": [
        {
          "entity_id": "entity-...",
          "display_id": "yjs-1542366968",
          "x": 817.5,
          "y": 448.5
        }
      ],
      "added_nodes": [],
      "removed_nodes": [],
      "highlighted_nodes": [],
      "focused_nodes": []
    }
  }
}
```

All `x, y` values in `updated_nodes` are **display-local canvas coordinates**
for the target display. No reprojection is needed on the frontend.

---

## 5. Frontend Application Flow

### 5.1 Entry point

`chatPanelHelpers.ts:applyChatResponseLayout()` (line 507) orchestrates delta
application.

### 5.2 Display transfer resolution

`chatPanelHelpers.ts:resolveDisplayTransfers()` (line 287) detects nodes whose
`display_id` changed between the current graph state and the delta. For each
transfer:

1. The update's `x, y` are used **as-is** (display-local canvas coords).
2. No coordinate conversion is applied. The comment at line 308 explicitly
   states: *"Chat layout deltas are in display-local canvas coordinates already.
   Do not reproject through virtual desktop offsets or camera transform."*
3. The transfer is recorded for Yjs broadcast and chat announcement.

### 5.3 Applying the delta to graph store

`chatActions.ts:applyLayoutDelta()` (line 22) applies the delta to Zustand
state:

1. `applyDeltaUpdatedNodes` — patches `x, y, displayId` on existing nodes
2. `applyDeltaRemovedNodes` — removes nodes
3. `applyDeltaAddedNodes` — inserts new nodes with the local display ID

### 5.4 Yjs broadcast for same-display moves

After applying the delta, `applyChatResponseLayout()` broadcasts position
updates to remote peers via `emitDragBatch()`. Two separate broadcasts happen:

- **Cross-display transfers** (`announceTransfers`, line 548): emitted with
  `origin: 'chat-transfer'` so the initiating peer also receives the callback
  for animation.
- **Same-display moves** (line 556): emitted for nodes that moved within their
  current display, since these only touched Zustand and need to reach the Yjs
  CRDT.

Both use `space: 'canvas'` — the coordinates are canvas top-left.

### 5.5 Remote node update handling

`useCrossDisplaySync.ts:handleRemoteNodeUpdate()` (line 126) processes incoming
Yjs updates on each display:

1. Resolves coordinate space: if `space === 'screen'`, converts to canvas via
   `screenToCanvas()`; otherwise uses coordinates directly.
2. Routes by `kind`:
   - `mirror` / `mirror-clear`: drag shadow on adjacent display
   - `preview` / `preview-clear`: ghost node for pending transfer
   - `drag`: live position update during drag
   - `commit`: final position — triggers entry/exit animations and ownership
     transfer in graph store

---

## 6. Cross-Display Transfer Flow

### 6.1 User drag (Ctrl+drag via Yjs)

```
Source display                              Target display
─────────────                               ──────────────
1. User Ctrl+drags node
2. handleNodeDrag detects exit
   → getExitDirection(screenX, screenY)
3. findAdjacentPeer(desktop, peerId, dir)
4. mapPositionToAdjacentDisplay()
   → globalX = sourcePeer.x + nodeX        5. handleRemoteNodeUpdate(update)
   → localX  = globalX - targetPeer.x         kind='preview': show ghost
   → clamped to [INSET, targetW - INSET]
5. emitNodeDrag({ x, y, displayId,
     kind: 'preview', space: 'screen' })
                    ↓ Yjs CRDT ↓
                                            6. screenToCanvas({ x, y }, viewport)
                                               → canvas position for ghost
─── on drop ───
6. emitNodeDrag({ ..., kind: 'commit' })
                    ↓ Yjs CRDT ↓
                                            7. handleRemoteNodeUpdate(update)
                                               kind='commit':
                                               → entry animation from edge
                                               → graph.updateNodeDisplay()
                                               → collision resolution
7. Exit animation on source
8. graph.updateNodeDisplay() (deferred
   until after EXIT_ANIMATION_MS)
```

### 6.2 Agent command (chat transfer via HTTP + Yjs)

```
Frontend                    Backend                     Target display
────────                    ───────                     ──────────────
1. POST /api/chat
   layout + display_context
                            2. Agent decides to move
                               node to right display
                            3. Returns layout_delta with
                               display_id + canvas (x,y)
4. applyChatResponseLayout()
5. resolveDisplayTransfers()
   → detects display_id change
   → no coordinate conversion
6. announceTransfers()
   → emitDragBatch([{
       id, x, y,
       displayId: target,
       kind: 'commit',
       space: 'canvas'
     }], { origin: 'chat-transfer' })
                    ↓ Yjs CRDT ↓
                                            7. handleRemoteNodeUpdate()
                                               kind='commit', space='canvas'
                                               → entry animation
                                               → updateNodeDisplay()
7. applyLayoutDelta()
   → Zustand store updated
8. Source display: exit animation
   via handleRemoteNodeUpdate
   (receives own broadcast
   because origin='chat-transfer')
```

---

## 7. Transformation Formulas

### Canvas ↔ Screen

```
screen_x = canvas_x * zoom + pan_x
screen_y = canvas_y * zoom + pan_y

canvas_x = (screen_x - pan_x) / zoom
canvas_y = (screen_y - pan_y) / zoom
```

**Source**: `nodeSyncProtocol.ts:canvasToScreen()` (line 31),
`screenToCanvas()` (line 44)

### Visible canvas from camera

```
visible_min_x = (0 - pan_x) / zoom
visible_min_y = (0 - pan_y) / zoom
visible_max_x = (screen_width - pan_x) / zoom
visible_max_y = (screen_height - pan_y) / zoom
```

**Source**: `chatPanelHelpers.ts:computeVisibleCanvas()` (line 158),
`agent/layout_ops/arrangement.py:_get_display_visible_bounds()` (line 252)

### Camera fit (backend)

```
fit_zoom = min(screen_w / content_w, screen_h / content_h)
fit_zoom = clamp(fit_zoom, MIN_CAMERA_ZOOM, MAX_CAMERA_ZOOM)

pan_x = (screen_w / 2) - (center_x * fit_zoom)
pan_y = (screen_h / 2) - (center_y * fit_zoom)
```

**Source**: `agent/layout_ops/arrangement.py:_compute_fit_camera()` (line 297)

### Cross-display coordinate mapping (drag transfer)

```
global_x = source_peer.x + node_x    (source-local → virtual desktop)
global_y = source_peer.y + node_y

local_x = global_x - target_peer.x   (virtual desktop → target-local)
local_y = global_y - target_peer.y

clamped to [INSET, target_width - INSET]
```

**Source**: `peerArrangement.ts:mapPositionToAdjacentDisplay()` (line 192)

### Initial Load

Node positions in uploaded JSON or backend responses are already canvas
top-left coordinates. No abstract-to-canvas scaling step exists. Positions
are stored directly into the graph store and used by React Flow as-is.

---

## 8. Historical Bug: Peer-Offset Double-Subtraction

### The bug

When the backend returned a cross-display move with `x=817.5` targeting the
right display (topology offset `x=1670`), the frontend applied a legacy
reprojection step that subtracted the peer offset:

```
displayed_x = 817.5 - 1670 = -852.5   (off-screen)
```

The node appeared at a negative canvas coordinate on the right display, far
off-screen. Users had to manually "fit view" to recover.

### Root cause

The frontend treated `layout_delta.updated_nodes[].x/y` as virtual-desktop
global coordinates and converted them to display-local by subtracting the peer
offset. But the backend already emitted display-local canvas coordinates.
Subtracting the offset a second time violated the invariant.

### The fix

`chatPanelHelpers.ts:resolveDisplayTransfers()` was corrected to pass through
delta coordinates without conversion. The explicit comment at line 308 now
reads:

> *"Chat layout deltas are in display-local canvas coordinates already. Do not
> reproject through virtual desktop offsets or camera transform; doing so pushes
> nodes off-screen on the target display."*

### Violated invariant

> Layout delta coordinates from the backend are always display-local canvas
> coordinates. They must never be transformed through virtual desktop offsets
> or camera projections before being applied to the graph store.

---

## 9. Non-Negotiable Rules

These rules are derived from the coordinate contract and codified in the backend
agent prompt (`prompts/layout_agent_instruction.txt`).

### For the backend

1. All `layout_delta.updated_nodes[].x/y` are **display-local canvas
   top-left** coordinates.
2. Never treat `virtual_desktop.displays[].x/y` as node coordinates.
3. Never add/subtract display topology offsets when emitting node positions.
4. For cross-display transfers, emit final `x, y` already local to the target
   display's canvas.
5. Use `visible_canvas` bounds for region-based positioning (center, top-right,
   etc.).
6. Include `display_id` on every node whose display ownership changes.

### For the frontend

1. Apply `layout_delta` coordinates directly to graph store — no reprojection.
2. Screen coordinates exist only transiently at Ctrl+drag transfer boundaries.
3. Yjs commit broadcasts from chat use `space: 'canvas'`.
4. The virtual desktop is a topology map for adjacency routing, not a
   coordinate system for node placement.
## 10. Shared State (Yjs Synchronization)

The multi-display system relies on several shared Yjs CRDT maps to keep clients synchronized in real time. These maps initialize in `src/services/yjs/core.ts` during `joinRoom`, register observers that hydrate the relevant Zustand slices, and expose helper broadcasters used by the UI.

- `sharedGraphData`: holds the full `GraphData` payload (stringified for atomic updates). Upload sidebar broadcasts immediately after local load so all peers can render.
- `sharedGraphState`: mirrors graph visibility toggles (`showBranchPartitions`, `showLeafPartitions`, `showRegions`). Slice actions broadcast automatically, so any toggle stays in sync room-wide.
- `sharedUIState`: propagates interaction state (`activePanelId`, `highlightedNodeIds`, `focusedNodeIds`) so panel focus and chat-driven emphasis stay in sync across displays.
- `nodePositions`: high-frequency node position map, drives drag physics and cross-display transfers.
- `peerLayouts`: persistent peer layout topology (x, y, width, height, tags). Any peer can reposition any other peer by writing directly to this map.
