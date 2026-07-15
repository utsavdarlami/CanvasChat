# Backend Chat Agent Coordinate Contract

Date: February 26, 2026  
Scope: `/api/chat` request/response contract for multi-display layout edits

## Why This Doc Exists

A recent chat session exposed a coordinate-space mismatch that made a moved node appear off-screen on the right display. This document uses that session as a concrete example and defines the expected frontend/backend contract.

## Session Sample (Condensed)

### Request 1 (user asks outlier)
- Query: `"which view do feel is outlier here"`
- Frontend sent:
  - `layout.nodes[]` with `x,y,display_id`
  - `display_context.virtual_desktop.displays[]` with `x,y,width,height,camera,visible_canvas`
  - full semantic `entities[]`
- Backend response (correctly identified):
  - semantic outlier: `trimmer_spec.txt`
  - offered to move/group

### Request 2 (user says “yes do that”)
- Backend action moved `trimmer_spec.txt` to right display center:
  - `display_id: "yjs-1542366968"`
  - `x: 817.5, y: 448.5`

### Observed Runtime Symptom
- Diagnostics on right display showed:
  - `trimmer_spec.txt` at `x=-852.5, y=419.5` (off-screen)
- After manual `fit view`, right camera updated and node became visible.

## Root Cause Summary

The frontend had a legacy reprojection step for chat cross-display updates. It incorrectly treated chat `layout_delta` coordinates like virtual-desktop/global coordinates and applied peer-offset/camera conversion again.

Given returned `x=817.5` and right peer offset `x=1670`, that conversion produced `817.5 - 1670 = -852.5`, matching diagnostics.

Frontend has now been corrected to treat chat `layout_delta.updated_nodes[].x/y` as display-local canvas coordinates directly.

## Canonical Coordinate Contract

## 1) Coordinate Spaces
- **Canvas space (authoritative for layout)**:
  - display-local React Flow canvas top-left coordinates
  - used for node `x,y` in chat layout payloads and layout deltas
- **Screen space (derived, camera-dependent)**:
  - viewport pixel space after pan/zoom
  - formula: `screen_x = canvas_x * zoom + pan_x`, `screen_y = canvas_y * zoom + pan_y`
- **Virtual desktop topology space**:
  - `virtual_desktop.displays[].x/y/width/height`
  - used for adjacency and display arrangement context only
  - **not** a direct node placement coordinate system
  - `virtual_desktop.displays[].tags` are user-defined labels to give displays meaning
    (for example `left`, `right`, `wall`, `overview`), not coordinate values

## 2) What Frontend Sends to Backend (`/api/chat`)

### Required behavioral meaning
- `layout.nodes[].x/y`: display-local canvas coordinates.
- `layout.nodes[].display_id`: owning display/peer for that node.
- `display_context.virtual_desktop.displays[]`:
  - `x/y/width/height`: display topology bounds
  - `tags`: user semantic labels for display intent selection
  - `camera`: current pan/zoom (may be default `0,0,1` early in session)
  - `visible_canvas`: currently visible canvas rectangle for that display.

### Backend should use
- `visible_canvas` for region-based moves (`top-right`, `center`, etc.).
- topology (`display x/y`) only for choosing target display and adjacency intent.

## 3) What Frontend Expects from Backend (`/api/chat` response)

For layout changes, backend should return:
- `action.type: "update_layout"`
- `action.layout_delta.updated_nodes[]` with:
  - `entity_id`
  - `display_id` (when ownership/display changes)
  - `x,y` in **target display local canvas space**

Optional:
- `action.description`
- `history` metadata

For transient, non-structural UI guidance, backend may return:
- `action.type: "highlight"`
- `action.layout_delta.highlighted_nodes[]` with node/entity IDs to emphasize
- `action.layout_delta.updated_nodes/added_nodes/removed_nodes` empty

Frontend behavior for `highlight`:
- apply a one-shot visual highlight to listed nodes
- do **not** mutate layout coordinates/history
- clear highlight on next user interaction
- if a highlighted target may be off-screen, also provide `focused_nodes` (or emit `focus_camera`) so the user can see it immediately
- ignore `layout` payload refresh when `action.type` is `highlight`

For camera guidance, backend may return:
- `action.type: "focus_camera"`
- `action.layout_delta.focused_nodes[]` with node/entity IDs to center in viewport

Frontend behavior for `focus_camera`:
- animate camera with React Flow viewport helpers (`setCenter` for single node, `fitView` for multiple)
- do **not** mutate layout coordinates/history
- keep focus intent active until superseded by another action
- ignore `layout` payload refresh when `action.type` is `focus_camera`

## 4) Non-Negotiable Rules for Backend Agent

1. Never treat `virtual_desktop.displays[].x/y` as node coordinates.
2. Never add/subtract display offsets when emitting `layout_delta.updated_nodes[].x/y`.
3. For cross-display transfer, emit final `x,y` already local to target display.
4. Prefer semantic tools (`move_to_region`, `arrange_relative`, `group`) over manual pixel arithmetic.
5. If user intent says “make visible on right display center”, ensure returned `x,y` is inside that display’s `visible_canvas`.
6. Include `display_id` for each moved node when display ownership changes.

## Backend Agent Prompt Fixes (Recommended)

Add/keep these explicit statements:
- “All tool and layout-delta node `x,y` are display-local canvas top-left coordinates unless explicitly stated otherwise.”
- “`screen_x/screen_y` are viewport-local pixels; do not confuse with virtual desktop offsets.”
- “`virtual_desktop.displays[].x/y` are topology offsets, not node placement coordinates.”
- “When moving across displays, output `x,y` in target display-local canvas coordinates.”

Remove/avoid:
- references to `surface_assignments` as the primary ownership source if runtime contract uses `display_id` on nodes.
- mandatory “always load layout first” behavior for turns where session already has layout state.

## Validation Checklist

Run these checks after backend changes:

1. Start with two displays (`left`, `right`) and 5 nodes.
2. Ask: “which view is outlier”, then: “yes do that”.
3. Verify response `layout_delta` sets moved outlier to right `display_id`.
4. Verify right diagnostics immediately show node with non-negative in-view canvas coordinates (no forced `fit view` needed).
5. Verify moved node remains visible when camera is default `(0,0,1)`.
6. Verify relative/grouping tools place nodes within `visible_canvas` bounds when requested.

## Example of Correct Cross-Display Delta Shape

```json
{
  "action": {
    "type": "update_layout",
    "description": "Moved outlier to right display center",
    "layout_delta": {
      "updated_nodes": [
        {
          "entity_id": "entity-1769204937393-ee58c9b9",
          "name": "trimmer_spec.txt",
          "display_id": "yjs-1542366968",
          "x": 817.5,
          "y": 448.5
        }
      ],
      "added_nodes": [],
      "removed_nodes": []
    }
  }
}
```

Interpretation: `x=817.5,y=448.5` is already local canvas position for the right display and should be applied directly.

## Example of Correct Highlight Action Shape

```json
{
  "action": {
    "type": "highlight",
    "description": "highlighted 1 entities",
    "affected_entities": ["entity-1769204937393-ee58c9b9"],
    "layout_delta": {
      "updated_nodes": [],
      "added_nodes": [],
      "removed_nodes": [],
      "highlighted_nodes": ["entity-1769204937393-ee58c9b9"],
      "focused_nodes": []
    }
  }
}
```

## Example of Correct Focus Action Shape

```json
{
  "action": {
    "type": "focus_camera",
    "description": "focused camera on 1 entities",
    "affected_entities": ["entity-1769204937393-ee58c9b9"],
    "layout_delta": {
      "updated_nodes": [],
      "added_nodes": [],
      "removed_nodes": [],
      "highlighted_nodes": [],
      "focused_nodes": ["entity-1769204937393-ee58c9b9"]
    }
  }
}
```
