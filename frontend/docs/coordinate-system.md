# Unified Coordinate System — Frontend

## Single Source of Truth: Canvas Top-Left

All coordinate stores use **React Flow canvas top-left** coordinates:

| Store         | Format         | Description                                  |
|---------------|----------------|----------------------------------------------|
| graph-store   | canvas top-left | `node.x`, `node.y` in Zustand                |
| react-flow    | canvas top-left | `node.position.x/y` (React Flow's internal)  |
| yjs-crdt      | canvas top-left | Synced positions across peers                 |

**Canvas top-left** means the (x, y) position of a node's top-left corner in
React Flow's coordinate space (before zoom/pan transformation).

## Lifecycle

### 1. Initial Load

When a graph JSON is uploaded or received from the backend, node positions are
already **canvas top-left** coordinates. `useEntityFlowNodes` reads `node.x`
and `node.y` directly from the graph store and passes them to React Flow as
`node.position`. No scaling or coordinate conversion is applied.

On first render, `EntityFlowView` seeds Yjs via `emitNodeDrag` so that
connected peers receive the initial positions.

### 2. Drag Updates

When a user drags a node, `handleNodeDragStop` writes
`node.position.x, node.position.y` (canvas top-left) directly to graph-store.
No conversion needed — React Flow positions are already canvas top-left.

### 3. Chat Agent Updates

The chat API receives canvas top-left coords (from graph-store) and returns
canvas top-left coords in `layout_delta.updated_nodes`. These are stored
directly via `applyLayoutDelta`. The coordinate bounds sent to the backend
correspond to the viewport dimensions.

### 4. Cross-Display Transfers

Cross-display transfers are the **only** place where screen-space coordinates
are used, at the transfer boundary:

```
Sender display:
  canvas top-left → screen coords (via viewport zoom/pan)
  ↓ (yjs broadcast)
Receiver display:
  screen coords → canvas top-left (via receiver's viewport zoom/pan)
  → stored to graph-store as canvas top-left
```

The conversion happens in:
- `useNodeDrag.ts`: `mapPositionToAdjacentDisplay()` produces screen-space
  coords for the target display
- `useCrossDisplaySync.ts`: `screenToCanvas()` converts received
  screen coords back to canvas top-left on the receiving display

## Diagnostics

The `DiagnosticPanel` shows three columns — all in canvas top-left coords:
- **store**: from Zustand graph-store
- **flow**: from React Flow's live state
- **yjs**: from the Yjs CRDT map

A **DRIFT** flag means the graph-store and react-flow positions differ by >5px,
which indicates a real bug in the coordinate pipeline.

## Key Invariant

After graph load, for any node on the local display:

```
graph-store (x, y) ≈ react-flow position (x, y) ≈ yjs (x, y)
```

All three should be within a few pixels of each other (differences can arise
from collision resolution or animation timing, but should converge).
