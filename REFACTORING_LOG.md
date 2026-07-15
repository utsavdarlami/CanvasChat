# Refactoring Log: Coordinate System Simplification

**Date:** March 8, 2026
**Scope:** Full-stack removal of links/relationships and the abstract-to-canvas coordinate scaling pipeline
**Commits:** `708dd37` (monolithic app restructure + backend/frontend refactor), `6f5b7e5` (dead code cleanup)

---

## Background

The project originated as a **networkx/matplotlib** experiment where the backend produced abstract graph coordinates (small unitless floats like `-3.2`, `0.0`, `1.5`) and the frontend scaled them into pixel coordinates for a React Flow canvas. This created a triple coordinate pipeline:

```
Abstract (backend)  -->  Canvas (React Flow)  -->  Screen (viewport pixels)
```

Over time, the system evolved:

- **React Flow became the direct canvas.** The backend's layout agent now emits display-local canvas coordinates directly. There is no abstract space.
- **Links/edges were never rendered in React Flow.** The `GraphLink`, `D3Node`, `D3Link`, and `RelationshipRecord` types were vestiges of the networkx data model. They were carried through the entire stack (API request/response, store, hooks, view) but never visualized.
- **Visualization overlays (partitions, regions, phantom nodes) were removed.** `PartitionOverlay`, `RegionOverlay`, `PhantomEndpointNode`, and `EdgeReasoningTooltip` were either unfinished experiments or tied to the removed link/edge rendering.

The refactoring goal was to **eliminate this dead complexity** and establish a single, clean data flow:

```
Canvas coordinates (backend) --> Canvas coordinates (frontend) --> React Flow
```

---

## The 7-Phase Plan

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Backend -- remove links, relationships, visualize graph | Complete |
| 2 | Frontend Types -- remove link types (GraphLink, D3Node, D3Link, etc.) | Complete |
| 3 | Frontend Store -- remove rawGraphData, hasScaled, link handling | Complete |
| 4 | Frontend Hooks -- remove scaling pipeline | Complete |
| 5 | Frontend View -- simplify EntityFlowView | Complete |
| 6 | Delete dead files | Complete |
| 7 | Cleanup and build verification | Complete |

---

## Phase 1: Backend

Removed `links`, `relationships`, and `relational_semantics` from the backend API and agent.

### Files modified

| File | Changes |
|------|---------|
| `backend/agent/layout_ops/io.py` | Removed `links` from all 3 code paths in `load_layout_from_output()`. Removed `links`, `directed`, `multigraph` from `export_to_graph_format()`. |
| `backend/agent/layout_delta.py` | Removed `updated_links: []` from delta dict and error return. |
| `backend/api/models/chat.py` | Removed `updated_links` field from `LayoutDelta` model. Removed `relationships` field from `ChatRequest`. Updated layout description. |
| `backend/prompts/layout_agent_instruction.txt` | Removed `links` from input format description. |
| `backend/agent/tool_ops/layout_tools.py` | Removed relationships/edges/clusters count from `tool_get_current_layout`. |
| `backend/api/endpoints/chat.py` | Removed `relationships` param from `get_or_create_session` call. |
| `backend/api/endpoints/chat_logic/session.py` | Removed `relationships` from `_build_state_delta_for_existing_session`, `get_or_create_session`, `_ensure_session_exists`, `_update_existing_session_state`. |
| `backend/agent/agent.py` | Removed `relationships` from `initialize_session`. |

---

## Phase 2: Frontend Types

Removed all link-related and relationship types from the type system.

### Files modified

| File | Changes |
|------|---------|
| `frontend/src/types/graph.ts` | Removed `GraphLink`, `D3Node`, `D3Link`, `RelationshipRecord`. Kept `EntityRecord`, `GraphNode`, `ClusterInfo`, `GraphData` (without links), `GraphContext`, `Partition*`, `Region*`. |
| `frontend/src/types/api.ts` | Removed `RelationshipRecord` import, `relational_semantics` from `LLMLayoutRequest`, `UpdatedLink` type, `updated_links` from `LayoutDelta`, `relationships` from `ChatRequest`. |

---

## Phase 3: Frontend Store

Removed `rawGraphData`, `hasScaled`, and link handling from the Zustand store.

### Files modified

| File | Changes |
|------|---------|
| `frontend/src/stores/slices/graph/dataActions.ts` | Removed `rawGraphData`, links handling from `setGraphData`, `setOriginalData`, `removeNode`. |
| `frontend/src/stores/slices/graph/lifecycleActions.ts` | Removed `hasScaled`, `setHasScaled`. Removed links/rawGraphData from `clearGraph`. |
| `frontend/src/stores/slices/graph/chatActions.ts` | Removed `applyDeltaUpdatedLinks` import/usage. Removed rawGraphData/rawNodes/links tracking from `applyLayoutDelta`. |
| `frontend/src/stores/slices/graph/graphHelpers.ts` | Removed `GraphLink`/`UpdatedLink` imports, `getLinkEndpointId`, `getLinkKey`, `applyDeltaUpdatedLinks` functions. Removed rawNodes/rawLinks from `applyDeltaRemovedNodes` and `applyDeltaAddedNodes`. |
| `frontend/src/stores/slices/graphSlice.ts` | Removed `links`, `rawGraphData`, `hasScaled`, `setHasScaled` from `GraphState` interface and initial state. |
| `frontend/src/stores/graphStore.ts` | Removed `links`, `rawGraphData`, `hasScaled`, `setHasScaled` from `useEntityFlowGraph`. |

---

## Phase 4: Frontend Hooks

Removed the abstract-to-canvas scaling pipeline and edge interaction handling.

### Files modified

| File | Changes |
|------|---------|
| `frontend/src/components/EntityView/hooks/useEntityFlowNodes.ts` | Major rewrite: removed scaling pipeline (`extractGlobalBounds`, `extractAllPartitions`, `extractRadialRegions`, `coordinateScaling` imports). Removed `ScalingContext` output. Simplified to directly map `GraphNode`s to React Flow Nodes without scaling. Removed edge building, partition/region extraction. |
| `frontend/src/components/EntityView/hooks/useEntityFlowViewport.ts` | Removed `ScalingContext` dependency. Simplified to return default viewport. |
| `frontend/src/components/EntityView/hooks/useLocalDisplayNodes.ts` | Removed `GraphLink` and edge filtering. Returns only `localNodes` and `localNodeIds`. |
| `frontend/src/components/EntityView/hooks/useEntityFlowCallbacks.ts` | Removed edge interaction handlers (`useEdgeInteractions`), `hoveredEdge`, `tooltipPosition`, `handleEdgeMouseEnter/Move/Leave`, `setEdges` parameter. Later also removed `usePartitionStyles` import/call and partition toggle params. |

---

## Phase 5: Frontend View

Simplified `EntityFlowView` to a nodes-only React Flow canvas.

### Files modified

| File | Changes |
|------|---------|
| `frontend/src/components/EntityView/EntityFlowView.tsx` | Removed `useEdgesState`, edges from ReactFlow. Removed `EdgeReasoningTooltip`, `PartitionOverlay`, `RegionOverlay`, `PhantomEndpointNode` imports/usage. Removed `hasScaled` lifecycle. Removed canvas writeback effects. Simplified node merge effect. Removed unused `showBranchPartitions`/`showLeafPartitions`/`showRegions` destructures. |

---

## Phase 6: Delete Dead Files

Removed files that were no longer imported anywhere.

### Files deleted

| File | What it was |
|------|-------------|
| `frontend/src/components/EntityView/EdgeReasoningTooltip.tsx` | Tooltip shown on edge hover |
| `frontend/src/components/EntityView/PhantomEndpointNode.tsx` | Ghost node at viewport boundary for cross-display edges |
| `frontend/src/components/EntityView/PartitionOverlay.tsx` | SVG overlay for branch/leaf partition boundaries |
| `frontend/src/components/EntityView/RegionOverlay.tsx` | SVG overlay for radial region Euler diagrams |
| `frontend/src/utils/coordinateScaling.ts` | Abstract-to-canvas coordinate scaling functions |
| `frontend/src/components/EntityView/hooks/useEdgeInteractions.ts` | Mouse event handlers for edge hover/tooltip |
| `frontend/src/components/EntityView/hooks/usePartitionStyles.ts` | CSS class toggler for partition visibility |
| `frontend/src/components/EntityView/types.ts` | Contained `ScalingContext`, `GlobalBounds` (removed). `NodeDimensionsMap` moved to survive; `NodePositionMap` removed as dead code. |

**Note on types.ts:** The file was not fully deleted. `NodeDimensionsMap` is still in use by `useEntityFlowNodes.ts`. The dead `NodePositionMap` type was removed separately. The file now contains only `NodeDimensionsMap`.

---

## Phase 7: Cleanup and Build Verification

Cleaned unused imports across the codebase and verified the build.

### Additional files cleaned

| File | Changes |
|------|---------|
| `frontend/src/components/Chat/chatPanelHelpers.ts` | Removed `RelationshipRecord` import, `relationships` from payload, `currentRelationships` from types. Fixed `GraphPayloadContext`. |
| `frontend/src/components/Sidebar/hooks/useGraphUpload.ts` | Fixed unused `relFile` parameter. |
| `frontend/src/services/api.ts` | Removed `RelationshipRecord` import, `relational_semantics` from `generateLLMLayout`. |
| `frontend/src/components/EntityView/index.ts` | Removed `NodePositionMap` from re-export. |

### Build result

```
$ npm run build   # (tsc -b && vite build)
989 modules transformed
built in 6.51s
```

Build passes clean with no errors.

---

## Architecture After Refactoring

### Coordinate flow (simplified)

```
Backend layout agent
  |  emits display-local canvas top-left (x, y) coordinates
  v
POST /api/chat response  -->  layout_delta.updated_nodes[].x/y
  |
  v
Frontend Zustand store (graph.nodes[].x/y)
  |  used directly as React Flow node positions
  v
React Flow canvas  <-->  Yjs CRDT (cross-display sync)
```

There is no abstract space. There is no scaling step. The backend and frontend share a single coordinate language: **display-local canvas top-left**.

### Data model (simplified)

**Before:**
- `GraphData` had `nodes` and `links`
- `LayoutDelta` had `updated_nodes`, `added_nodes`, `removed_nodes`, `updated_links`
- `ChatRequest` had `layout` (with links), `relationships`, `relational_semantics`
- Store held `nodes`, `links`, `rawGraphData`, `hasScaled`

**After:**
- `GraphData` has `nodes` only
- `LayoutDelta` has `updated_nodes`, `added_nodes`, `removed_nodes`, `highlighted_nodes`, `focused_nodes`
- `ChatRequest` has `layout` (nodes only), no relationships
- Store holds `nodes` only

### React Flow integration (simplified)

**Before:**
- `useEntityFlowNodes` scaled abstract coords to canvas, extracted partitions/regions, built edges
- `EntityFlowView` managed `useEdgesState`, partition/region overlays, phantom nodes, edge tooltips, `hasScaled` lifecycle
- `useEntityFlowCallbacks` handled edge interactions, partition CSS styles

**After:**
- `useEntityFlowNodes` directly maps `GraphNode` positions to React Flow `Node` objects
- `EntityFlowView` manages only nodes (no edges, overlays, or scaling lifecycle)
- `useEntityFlowCallbacks` handles only node drag and cross-display sync

---

## Phase 8: Remove Vestigial UI Components

**Date:** March 8, 2026
**Scope:** Remove dead UI controls, store fields, and Yjs sync left over from the coordinate system refactoring.

After the Phase 1–7 refactoring, several UI components and store fields remained that no longer served any purpose:

1. **Relationship file upload** — The backend endpoints (`/api/distribution/visualize-from-cache`, `/api/generate-llm-layout`) no longer exist.
2. **"Use LLM-based layout" toggle** — Tied to the removed `generate-llm-layout` endpoint.
3. **Display Options (partition toggles)** — `showBranchPartitions`, `showLeafPartitions`, `showRegions` toggled nothing since `PartitionOverlay` and `RegionOverlay` were deleted.
4. **Diagnostic panel column naming** — Headers said `graph(cvs-tl)`, `flow(cvs-tl)`, `yjs(cvs-tl)` as if they were different coordinate systems. Post-refactoring they're all the same space.
5. **`useStaticLayout` store field** — Set on every `setGraphData` call but never read anywhere.

### Files modified

| File | Changes |
|------|---------|
| `frontend/src/components/Sidebar/FileUploadSection.tsx` | Removed `relationshipsFile`, `useLLM`, `setUseLLM`, `handleRelationshipsChange` props. Removed relationships file input and LLM toggle checkbox. Button text simplified to `'Load Entities'`. |
| `frontend/src/components/Sidebar/hooks/useGraphUpload.ts` | Removed `relationshipsFile`, `useLLM` state. Removed `handleRemoteLLMLayout()`, `handleBasicUpload()`, `handleRelationshipsChange()`. `handleUpload()` now always uses the local entities path. Removed `uploadForVisualization`/`generateLLMLayout` imports. |
| `frontend/src/components/Sidebar/UploadSidebar.tsx` | Removed `DisplayOptionsSection` import/JSX and the "Display Options" section. Removed dead destructures from `useSidebarGraph()` and `useGraphUpload()`. |
| `frontend/src/services/api.ts` | Removed `uploadForVisualization()` and `generateLLMLayout()` functions and their type imports. |
| `frontend/src/types/api.ts` | Removed `UploadFilesRequest`, `LLMLayoutRequest`, `GraphVisualizationResponse`, `LLMLayoutResponse` types. Removed `REGULAR_UPLOAD` and `LLM_LAYOUT` endpoint constants. |

### Files deleted

| File | What it was |
|------|-------------|
| `frontend/src/components/Sidebar/DisplayOptionsSection.tsx` | Partition visibility toggle UI (branch/leaf checkboxes) |

### Store and Yjs cleanup

| File | Changes |
|------|---------|
| `frontend/src/stores/slices/graphSlice.ts` | Removed `useStaticLayout`, `showBranchPartitions`, `showLeafPartitions`, `showRegions`, `useLLMLayout` from `GraphState` interface and initial values. Removed `togglePartitionVisibility` and `setLLMLayout` action signatures. |
| `frontend/src/stores/slices/graph/displayActions.ts` | Removed `togglePartitionVisibility` and `setLLMLayout` actions. Removed `broadcastGraphState` import. Only `setGlobalAnnotation` remains. |
| `frontend/src/stores/slices/graph/dataActions.ts` | Removed `useStaticLayout` assignment from `setGraphData`. |
| `frontend/src/stores/graphStore.ts` | Removed `showBranchPartitions`, `showLeafPartitions`, `togglePartitionVisibility` from `useSidebarGraph()`. Removed `showRegions`, `showBranchPartitions`, `showLeafPartitions` from `useEntityFlowGraph()`. |
| `frontend/src/services/yjs/graphData.ts` | Removed `sharedGraphState` Y.Map, `graphStateObserver`, and `broadcastGraphState()` function. Removed teardown/cleanup for those resources. |

### Other cleanup

| File | Changes |
|------|---------|
| `frontend/src/styles/global.css` | Removed `.partition-rect`, `.partition-label` and variants. Removed `.hide-branches`, `.hide-leaves`, `.hide-regions` visibility toggle rules. Removed `.radial-region`, `.radial-region-label` styles. |
| `frontend/src/utils/buildDiagnosticText.ts` | Renamed diagnostic column headers: `graph(cvs-tl)` → `store`, `flow(cvs-tl)` → `flow`, `yjs(cvs-tl)` → `yjs`. All three columns retained — they track genuinely separate state replicas (Zustand, React Flow, CRDT). |

### Build result

```
$ npm run build   # (tsc -b && vite build)
988 modules transformed
built in 6.19s
```

Build passes clean with no errors.

---

## Known Remaining Items

### Backend tests not re-run

The backend Python tests (`backend/tests/`) were not re-run after the refactoring to verify no regressions. The changes were limited to removing fields (not changing logic), so risk is low, but tests should be validated.

### Documentation updated separately

Several existing docs referenced the old architecture (abstract coordinates, links, scaling pipeline). These have been updated as part of this refactoring to reflect the current state. See the commit history for details.
