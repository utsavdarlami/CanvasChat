# Display-Local Viewport Model with Ctrl+Drag Cross-Display Transfer

**Date:** Feb 23, 2026  
**Status:** Implemented

> **Note:** The "Before" sections in this document describe a deprecated architecture (single shared global coordinate space with camera offsets) that has been completely removed from the codebase. It is preserved here solely to explain the problems it caused and why the display-local viewport model was adopted.

---

## Problem Statement

The previous multi-display approach used a **single shared global coordinate space** with camera offsets. Each peer ran its own React Flow instance with ALL nodes, and the camera was shifted by `(-peer.x, -peer.y)` so each peer saw its region. Enabling React Flow's native zoom/pan made this brittle because each peer zooming independently caused the shared coordinate space to diverge -- nodes placed for one peer's zoom level appeared wrong on another.

## Solution: Display-Local Viewport Model

Switched from a **shared-global-viewport-offset model** to a **display-local-viewport model** where:

- Each display (peer) has its **own independent coordinate space** `(0,0)` to `(localWidth, localHeight)`
- Each display only renders nodes **assigned to it** via `displayId`
- React Flow's native zoom, pan, and drag work freely within each display
- **Ctrl+drag** enables cross-display node transfer with frozen viewport

---

## Architecture

### Before (Global Viewport Offset)

```
Peer A viewport ─────────┐    Peer B viewport ─────────┐
│ camera at (-0, 0)       │    │ camera at (-1920, 0)    │
│ renders ALL nodes       │    │ renders ALL nodes       │
│ shared coordinate space │    │ shared coordinate space │
└─────────────────────────┘    └─────────────────────────┘
         Global space: 0 ─────────────────────────── 3840
```

### After (Display-Local)

```
Peer A viewport ──────────┐    Peer B viewport ──────────┐
│ camera at (0, 0)         │    │ camera at (0, 0)         │
│ renders OWN nodes only   │    │ renders OWN nodes only   │
│ local space: 0──1920     │    │ local space: 0──1920     │
│ zoom/pan independent     │    │ zoom/pan independent     │
└──────────────────────────┘    └──────────────────────────┘
                    ← Ctrl+drag transfers nodes →
```

### Node Ownership via `displayId`

Every `GraphNode` has a `displayId` field:
- On graph load: `displayId = localPeerId` (or `'__local__'` if not connected yet)
- On connection: `'__local__'` nodes are claimed by the connecting peer
- On Ctrl+drag transfer: `displayId` changes to the target peer's ID

### Interaction Modes

| Ctrl held | Node dragging | Pan/Zoom | Node drag behavior |
|-----------|---------------|----------|--------------------|
| No        | No            | Enabled  | N/A                |
| No        | Yes           | Enabled  | Normal within-display drag |
| Yes       | No            | Enabled  | User can freely pan/zoom |
| Yes       | Yes           | **Frozen** | Cross-display transfer mode |

### Cross-Display Transfer Flow

1. User holds Ctrl and starts dragging a node
2. Viewport freezes (pan/zoom disabled)
3. Visual indicator shows "Transfer mode (Ctrl+drag)"
4. Node is dragged past the viewport boundary
5. `getExitDirection()` determines which edge was crossed (left/right/top/bottom)
6. `findAdjacentPeer()` locates the neighboring display in that direction
7. `mapPositionToAdjacentDisplay()` computes entry coordinates in the target display
8. Node's `displayId` updates, coordinates remap, change broadcasts via Yjs
9. Node disappears from source display, appears on target display

### Cross-Display Indication

The system is nodes-only (no edges/links). When nodes are distributed across
displays, each display renders only the nodes assigned to it. Users rely on the
diagnostic panel and display badges to understand cross-display node ownership.

---

## Implementation Details

### Files Modified

| File | Changes |
|------|---------|
| `src/types/session.ts` | `displayId` is now **required** on `NodeUpdate` (was optional). Comments updated to reflect display-local coordinates. |
| `src/stores/slices/graphSlice.ts` | `setGraphData()` assigns `displayId = localPeerId` (or `'__local__'`) to all loaded nodes. Added `updateNodeDisplay()` and `claimLocalNodes()` actions. |
| `src/services/yjs/core.ts` | Calls `claimLocalNodes(localPeerId)` on connection to reassign `'__local__'` nodes. |
| `src/services/yjs/nodePositions.ts` | CRDT map now stores `{ x, y, displayId }`. Observer and emitter both pass `displayId` through. |
| `src/utils/peerArrangement.ts` | Added explicit type exports (`ArrangedPeer`, `VirtualDesktop`, `ExitDirection`). Added `getExitDirection()`, `findAdjacentPeer()`, and `mapPositionToAdjacentDisplay()` utilities. |
| `src/components/EntityView/EntityFlowView.tsx` | Orchestrator now uses display-local model: always uses `localPeer.width/height`, integrates `useLocalDisplayNodes` filtering, `useCtrlKey` state, reactive pan/zoom props based on `isCrossDisplayMode`. Visual feedback for transfer mode. |
| `src/components/EntityView/hooks/useEntityFlowNodes.ts` | Accepts `localNodeIds` param. Converts graph nodes to React Flow nodes with canvas top-left positions. |
| `src/components/EntityView/hooks/useEntityFlowViewport.ts` | Simplified: no peer offset, `defaultViewport` is always `{x:0, y:0, zoom:1}`. Frozen scaling context logic retained for stability. |
| `src/components/EntityView/hooks/useEntityFlowCallbacks.ts` | Added `handleNodeDragStart`, `setIsDragging` prop, Ctrl-key ref tracking, full cross-display transfer logic in `handleNodeDragStop`, smart remote node-moved subscription that adds/removes nodes based on `displayId`. |

### Files Created

| File | Purpose |
|------|---------|
| `src/components/EntityView/hooks/useCtrlKey.ts` | Hook tracking Ctrl/Meta key state with blur cleanup. Returns reactive boolean. |
| `src/components/EntityView/hooks/useLocalDisplayNodes.ts` | Filters `graphNodes` by `displayId` matching `localPeerId`. Returns only nodes owned by the local display. |

---

## Key Utilities Added

### `peerArrangement.ts`

- **`getExitDirection(x, y, width, height)`** -- Determines which viewport edge a node has crossed (returns `'left' | 'right' | 'top' | 'bottom' | null`).

- **`findAdjacentPeer(desktop, sourcePeerId, direction)`** -- Finds the nearest peer in the given direction that has perpendicular overlap with the source peer on the virtual desktop.

- **`mapPositionToAdjacentDisplay(nodeX, nodeY, sourcePeer, targetPeer, direction)`** -- Maps a node's position from source display local coords to target display local coords, placing it at the entry edge with proportional perpendicular positioning.

### `graphSlice.ts`

- **`updateNodeDisplay(nodeId, displayId, x, y)`** -- Updates a node's display assignment and position in a single action.

- **`claimLocalNodes(peerId)`** -- Reassigns all `displayId === '__local__'` nodes to the given peer ID (called on connection).

---

## Behavior by Mode

### Single Display (not connected)
Zero change to existing behavior. All nodes render, React Flow zoom/pan/drag work normally. Nodes get `displayId = '__local__'`.

### Multi-Display (connected)
Each peer renders only its own nodes (filtered by `displayId`). React Flow zoom/pan/drag work freely per-display.

### Ctrl+Drag Transfer (connected)
Viewport freezes while Ctrl is held AND a node drag is in progress. Dragging past the viewport boundary transfers the node to the adjacent display. Coordinates remap to the target display's edge. The change broadcasts via Yjs CRDT.

---

## Bug Fixes (Feb 23, 2026)

### Bug: Nodes appeared on BOTH displays after loading

**Symptom:** When entities were loaded on one peer, all nodes appeared on both displays instead of only the uploading peer's display.

**Root Cause:** Two issues working together:

1. `UploadSidebar.tsx` called `broadcastGraphData(graphData)` with the **raw** graph data (no `displayId` on nodes). The receiving peer's `setGraphData` then stamped every node with its own `displayId`, so both peers claimed ownership of all nodes.

2. The originating peer's own Yjs observer also fired on its own broadcast (no echo suppression), causing a redundant re-processing.

**Fix (2 files):**

| File | Change |
|------|--------|
| `src/components/Sidebar/UploadSidebar.tsx` | After `setGraphData` stamps nodes with the local peer's `displayId`, reads the stamped nodes back from the store and broadcasts those (with `displayId` intact) instead of the raw data. Remote peers preserve node ownership via the `n.displayId ?? displayId` fallback. |
| `src/services/yjs/graphData.ts` | Added `suppressLocalEcho` flag (same pattern as `nodePositions.ts`). Set before writing to the shared Yjs map, cleared on the next microtask via `queueMicrotask`. Prevents the originating peer from re-processing its own broadcast. |

### Bug: Canvas panned/scrolled during Ctrl+drag transfer

**Symptom:** When Ctrl+dragging a node toward a viewport boundary, the React Flow background panned automatically, shifting the canvas.

**Root Cause:** React Flow's `autoPanOnNodeDrag` feature (default: `true`) auto-pans the viewport when a node is dragged near the container edge. This is independent of the `panOnDrag` prop and was never disabled during cross-display transfer mode.

**Fix (1 file):**

| File | Change |
|------|--------|
| `src/components/EntityView/EntityFlowView.tsx` | Added `autoPanOnNodeDrag={!isCrossDisplayMode}` to the `<ReactFlow>` component. Disables auto-panning during Ctrl+drag transfer mode while keeping it active for normal within-display dragging. |

### Bug: Viewport freeze glitches during Ctrl+drag (timing gap)

**Symptom:** Even with `panOnDrag` and `autoPanOnNodeDrag` disabled via `isCrossDisplayMode`, the canvas would occasionally pan or zoom for a frame or two when starting a Ctrl+drag. The glitch was intermittent and more visible with fast mouse movements near the viewport edge.

**Root Cause:** `isCrossDisplayMode` is computed from two React state values (`isCtrlHeld` from `useCtrlKey` + `isDragging` from `handleNodeDragStart`). React Flow's props (`panOnDrag={!isCrossDisplayMode}`, `autoPanOnNodeDrag={!isCrossDisplayMode}`) only take effect after a re-render. Between the state update in `handleNodeDragStart` and the render that propagates the new props, React Flow's internal drag handler runs with the OLD prop values — allowing auto-pan and pan-on-drag to slip through for one or more frames.

**Fix (2 files):**

| File | Change |
|------|--------|
| `src/components/EntityView/EntityFlowView.tsx` | Added `frozenViewportRef` (a ref, not state). When `isCrossDisplayMode` becomes true, captures the current viewport. In the `onMove` handler, if `frozenViewportRef` is set, immediately snaps the viewport back with `setViewport(frozen, { duration: 0 })`. This is synchronous and independent of the React render cycle. Cleared when `isCrossDisplayMode` becomes false. |
| `src/components/EntityView/hooks/useEntityFlowCallbacks.ts` | Accepts `frozenViewportRef` parameter. `handleNodeDragStart` sets `frozenViewportRef` synchronously if Ctrl is already held (before React Flow's next auto-pan frame). `handleNodeDrag` captures the viewport if Ctrl is pressed mid-drag. `handleNodeDragStop` clears the ref to unfreeze. |

The state-driven props (`panOnDrag={!isCrossDisplayMode}` etc.) remain as the primary freeze mechanism. The ref-based `frozenViewportRef` + `onMove` snap-back acts as a synchronous safety net that closes the timing gap.

### Enhancement: displayId badge on entity nodes

**Purpose:** Visual debugging aid — each entity node now shows its `displayId` in a small badge at the top-right corner.

| File | Change |
|------|--------|
| `src/components/EntityView/EntityNode.tsx` | Added a monospace badge showing the node's `displayId` (truncated to last 6 chars of peer ID, or `local` for `'__local__'`). Hover tooltip shows the full ID. Styled as a subtle blue label that doesn't compete with node content. |

---

## Coordinate Space Fix (Feb 23, 2026)

### The Three Coordinate Spaces

The multi-display system operates across three distinct coordinate spaces. Mixing them was the root cause of several bugs.

| Space | Origin | Used By | Example Values |
|-------|--------|---------|----------------|
| **Canvas** | React Flow infinite plane | `node.position`, React Flow internals | Affected by zoom/pan, can be 0–5000+ |
| **Screen/Pixel** | Top-left of React Flow container | Virtual desktop topology, peer `x/y/width/height` | 0–1920 (viewport width) |

### Conversion Formulas

```
canvas → screen:   screenX = canvasX * zoom + panX
screen → canvas:   canvasX = (screenX - panX) / zoom

Where { x: panX, y: panY, zoom } = getViewport()
```

### Bugs Fixed

#### 1. Exit direction detection used wrong coordinate space

**Symptom:** At zoom ≠ 1, cross-display transfer triggered at wrong screen positions (too early when zoomed out, too late when zoomed in).

**Root cause:** `getExitDirection()` in `handleNodeDrag` compared canvas coords (`node.position.x`) against pixel viewport dimensions (`localPeer.width`). These are different spaces.

**Fix** (`useEntityFlowCallbacks.ts`): Convert `node.position` to screen coords via `screenX = node.position.x * vp.zoom + vp.x` before calling `getExitDirection` and `mapPositionToAdjacentDisplay`.

#### 2. Ghost node pinned to edge on target display

**Symptom:** During Ctrl+drag transfer, the ghost on the target display was stuck along the x-axis — it could only move vertically, not track the actual overshoot into the target.

**Root cause:** `mapPositionToAdjacentDisplay()` hardcoded the transfer-axis to the entry edge (`newX = 0` for right exit, `newX = targetPeer.width` for left, etc.) instead of computing the actual overshoot position.

**Fix** (`peerArrangement.ts`): Replaced per-direction switch with unified global→local coordinate conversion. Both axes now use `globalX = sourcePeer.x + nodeX; localX = globalX - targetPeer.x`. A 20px inset clamp prevents edge-landing.

#### 3. Node reappears on source after zoomed-out drop

**Symptom:** When zoomed out on the source display, dropping a Ctrl+dragged node caused it to reappear far away on the source canvas instead of appearing on the target.

**Root cause:** `graph.updateNodeDisplay()` was called immediately on drop, before the 250ms exit animation completed. This changed `displayId` in the graph store, triggering the merge effect in `EntityFlowView` to re-process the node — potentially re-adding it at a stale position before the exit animation removed it.

**Fix** (`useEntityFlowCallbacks.ts`): Moved `graph.updateNodeDisplay()` inside the `setTimeout` callback (after `EXIT_ANIMATION_MS`). The Yjs broadcast fires immediately (so the target gets the node right away), but the sender's local graph store update is deferred until after the exit animation completes.

#### 4. Receiver ignored its own zoom/pan

**Symptom:** Transferred nodes appeared at wrong positions on the target display when it had been zoomed or panned.

**Root cause:** Cross-display transfers broadcast pixel-space coords (from `mapPositionToAdjacentDisplay`). The receiver used them directly as React Flow canvas positions without converting to its own canvas space.

**Fix** (`useEntityFlowCallbacks.ts`): Added `canvasX = (pixelX - panX) / zoom` conversion on the receiver side for preview, commit, and entry-animation branches. Same-display drag sync (already canvas coords) left unchanged.

#### 5. Exit animation targeted wrong edge when zoomed

**Symptom:** Exit slide animation didn't reach the visible viewport edge at non-1x zoom.

**Root cause:** `computeExitEdgePosition` received pixel viewport dims but its output is used as a React Flow canvas position.

**Fix** (`useEntityFlowCallbacks.ts`): Convert viewport dims to canvas space (`canvasViewportW = sourcePeer.width / vp.zoom`) before passing to `computeExitEdgePosition`.

### Protocol: Coordinate Space per Broadcast Type

| Broadcast Type | Coord Space | Why |
|---------------|-------------|-----|
| Normal drag sync (`emitNodeDrag` in `handleNodeDrag`) | Canvas | Same display consumes it, needs canvas coords |
| Preview/commit (`emitNodeDrag` with `preview`/transfer) | Pixel | Cross-display, receiver converts to its own canvas |
| Mirror overlap | Pixel | Virtual desktop overlap test needs pixel coords |

---

## Diagnostic Panel

### Location
`src/components/MultiDisplay/DiagnosticPanel.tsx`

### Data Sources (3-column comparison per node)

The diagnostic panel shows three position sources side by side for each node, making coordinate mismatches immediately visible:

| Column | Source | Coord Space | Module |
|--------|--------|-------------|--------|
| `graph-store` | Zustand `graphSlice.nodes[].x/y` | Canvas | `useGraphStore()` |
| `react-flow` | Live React Flow node state | Canvas (what's rendered) | `useFlowNodeDebug.ts` bridge |
| `yjs-crdt` | Yjs shared map snapshot | Canvas (what's broadcast) | `getNodePositionsSnapshot()` |

### Flags

| Flag | Meaning |
|------|---------|
| `DRIFT` | graph-store and react-flow positions diverge by >5px |
| `P` | Yjs `preview: true` — live ghost from cross-display drag |
| `M` | Yjs `mirror: true` — boundary shadow |
| `T:exit` / `T:enter` / `T:commit` | Active CSS transfer animation class |
| `!drag` | Node not draggable (mid-animation) |
| `yjs:XXXXXX` | Yjs displayId ≠ graph store displayId (ownership desync) |

### Orphan Detection

Two sections at the bottom catch leaked state:
- **Orphan React Flow Nodes**: In React Flow but not in graph store (leaked ghosts/mirrors)
- **Orphan Yjs Entries**: In Yjs CRDT but not in graph store (stale sync entries)

### Debug Bridge

`src/components/EntityView/hooks/useFlowNodeDebug.ts` — module-level ref (not React state) to avoid re-render overhead:
- `setLiveFlowNodes(nodes)` — called by `EntityFlowView` on each nodes state change
- `getLiveFlowNodes()` — read by DiagnosticPanel on 500ms interval
- `getLiveFlowVersion()` — monotonic counter for staleness detection

---

## Virtual Desktop — Why It's Still Needed

The virtual desktop is a **topology map**, not a rendering coordinate system. It does not participate in per-display rendering. Each display has its own independent React Flow canvas.

It is used exclusively for cross-display operations:
- `findAdjacentPeer()` — determines which display is left/right/above/below
- `mapPositionToAdjacentDisplay()` — converts coordinates between displays via global intermediate space
- `findOverlappingPeers()` / `doesNodeOverlapPeer()` — drag mirror boundary detection

---

## Virtual Desktop Position Desync Fix (Feb 23, 2026)

### Bug: Virtual desktop showed all peers at (0,0) despite PeerLayoutEditor configuration

**Symptom:** After arranging peers side-by-side in the PeerLayoutEditor mini-map, the virtual desktop still reported both peers at `(0,0)`. Cross-display transfers silently failed because `findAdjacentPeer()` returned `null` (overlapping peers have negative distances). Nodes stayed on the source display after Ctrl+drag.

**Root Cause:** Three compounding issues in `sessionSlice.ts`:

1. **`setLocalPeerConfig` didn't sync to peers map or recompute layout.** The PeerLayoutEditor calls `setLocalPeerConfig(x, y, ...)` during drag, which updated `session.localPeer.x/y` but never updated the corresponding entry in `session.peers` map. Since `recomputeLayout()` reads from `peers.values()`, the virtual desktop always used the connection-time position `(0,0)`.

2. **`syncRoomState` clobbered local peer position.** Every awareness change (including camera updates at 300ms intervals) triggered `syncRoomState`, which rebuilt the entire `peers` map from awareness data. For the local peer, this overwrote the locally-set position with potentially stale awareness state.

3. **`recomputeLayout` had no fallback.** It trusted `peers.values()` entirely, with no mechanism to prefer the authoritative `localPeer` data for the local peer's position.

**Fix (1 file, 3 changes):**

| Location | Change |
|----------|--------|
| `sessionSlice.ts` — `setLocalPeerConfig` | Now also updates the `peers` map entry for the local peer and calls `recomputeLayout()`. Virtual desktop immediately reflects mini-map drags. |
| `sessionSlice.ts` — `syncRoomState` | For the local peer's entry, preserves `localPeer.x/y/width/height/tags` instead of using awareness data. Prevents stale awareness round-trips from clobbering locally-set positions. |
| `sessionSlice.ts` — `recomputeLayout` | Safety net: overlays `localPeer` position/dimensions onto the local peer's entry in the peer list before passing to `computeManualDesktop()`. |

**Diagnostic fix:** `DiagnosticPanel.tsx` now shows the authoritative `localPeer` position for the local peer instead of the potentially stale `peers` map entry.

---

## Known Remaining Issues

- **Echo suppression timing:** `nodePositions.ts` uses `requestAnimationFrame` for echo suppression, which is timing-fragile. Consider using `doc.transact()` + `transaction.local` instead.
- **Mirror cancel semantics:** Cancellation works by accident (displayId mismatch triggers removal path). Could use an explicit cancel flag.
- **No explicit transfer cancel flag:** Cancellation is implicit via displayId change.

---

## Future Considerations

- **Peer disconnect handling:** Orphaned nodes (whose `displayId` matches a disconnected peer) currently remain in the graph store. A future enhancement could redistribute them automatically.
- **Phantom node direction accuracy:** Currently uses a heuristic (first other peer's relative position). Could be improved to look up the actual target peer by the remote node's `displayId`.
- **Multi-node transfer:** Currently transfers one node at a time. Could support dragging a selection across displays.
