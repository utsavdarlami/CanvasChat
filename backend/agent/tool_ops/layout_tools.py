"""Core layout read/write/export tools."""

from typing import List, Optional

from google.adk.tools.tool_context import ToolContext

from ..layout_operations import (
    find_available_position,
    gather_entity_content,
    gather_layout_snapshot,
    get_surface_visible_bounds,
    infer_arrangement,
    move_entity,
    resize_entity,
    resolve_display_name,
    scale_layout,
    swap_entities,
)
from .common import tool_safe

_MAX_CONTENT_READ_PER_CALL = 20

_MOVE_REGION_FACTORS = {
    "top-left": (0.0, 0.0),
    "top": (0.5, 0.0),
    "top-right": (1.0, 0.0),
    "left": (0.0, 0.5),
    "center": (0.5, 0.5),
    "right": (1.0, 0.5),
    "bottom-left": (0.0, 1.0),
    "bottom": (0.5, 1.0),
    "bottom-right": (1.0, 1.0),
}


def _get_reference_position(
    layout: dict, reference_entity_id: Optional[str]
) -> Optional[tuple]:
    """Get position of reference entity if provided."""
    if not reference_entity_id:
        return None
    if reference_entity_id not in layout.get("node_positions", {}):
        return None
    return layout["node_positions"][reference_entity_id]


def _resolve_surface(layout: dict, target_surface: str) -> str:
    """Resolve display aliases/tags to canonical surface id when available."""
    resolved = resolve_display_name(layout, target_surface)
    return resolved if resolved else target_surface


def _get_region_position(
    layout: dict, target_surface: str, region: str
) -> tuple[Optional[tuple[float, float]], Optional[str]]:
    """Map a region label to a display-local anchor position."""
    bounds = get_surface_visible_bounds(layout, target_surface)
    if not bounds:
        return None, f"No bounds found for surface {target_surface}"

    factors = _MOVE_REGION_FACTORS.get(region.lower())
    if not factors:
        return (
            None,
            f"Unknown region '{region}'. Use one of: {', '.join(_MOVE_REGION_FACTORS.keys())}",
        )

    min_x, min_y, max_x, max_y = bounds
    return (
        min_x + (max_x - min_x) * factors[0],
        min_y + (max_y - min_y) * factors[1],
    ), None


@tool_safe(require_layout=True)
def tool_get_entity_semantics(
    tool_context: ToolContext,
    display_id: Optional[str] = None,
    entity_ids: Optional[List[str]] = None,
) -> dict:
    """
    Return per-view semantic content joined with spatial position, plus cluster
    memberships. Each display's views are sorted in reading order and carry a
    geometric fingerprint of the arrangement.

    USE WHEN you need semantic fields NOT in the injected [Current Layout State]
    (`item_type`, `granularity`, `domain`, `location`, `temporal_focus`,
    `key_themes`, cluster memberships), or whenever you need to reason about
    what a spatial arrangement means (e.g., replicating an organizing principle
    from one display to another).

    Scoping: pass `display_id` to limit the snapshot to a single display when
    reasoning about that display's arrangement; pass `entity_ids` to limit to a
    specific selection (e.g., user-selected nodes). When both are given,
    `entity_ids` takes precedence. Omit both only when you truly need the full
    cross-layout picture — response size scales with view count.

    Returns a snapshot with:
      - `displays`: per-display list; each view has `position` plus semantic
        fields, sorted top-to-bottom then left-to-right, with a `geometry`
        field (`entity_count`, `row_bands`, `col_bands`, `bbox_width`,
        `bbox_height`) summarizing arrangement shape
      - `clusters`: cross-display cluster memberships (when in scope)
    """
    layout = tool_context.state.get("current_layout")
    entities = tool_context.state.get("entities")
    return {
        "status": "success",
        "snapshot": gather_layout_snapshot(
            layout,
            entities=entities,
            display_id=display_id,
            entity_ids=entity_ids,
        ),
    }


@tool_safe(require_layout=True)
def tool_read_entity_content(
    tool_context: ToolContext,
    entity_ids: List[str],
) -> dict:
    """
    Return the raw `value` and `summary` for the requested entities.

    USE WHEN the answer depends on content that entity metadata cannot
    express: facts present in the text but not captured in `key_themes`,
    or exact substrings needed for `tool_highlight_text`. Do NOT use to
    browse the dataset or to answer questions already served by
    `tool_get_entity_semantics`.

    Narrow first. Pick candidate IDs from the injected layout state, a
    user selection, or a `tool_get_entity_semantics` filter; pass only
    those IDs here. The call is capped at 20 IDs per invocation.

    Returns:
      - `entries`: list of per-entity records in the order requested,
        each containing `entity_id`, `name`, `value`, `summary`, and any
        available classification fields.
      - `missing`: IDs that could not be resolved.
    """
    if not entity_ids:
        return {
            "status": "error",
            "message": "entity_ids is required. Narrow with tool_get_entity_semantics first.",
        }

    if len(entity_ids) > _MAX_CONTENT_READ_PER_CALL:
        return {
            "status": "error",
            "message": (
                f"Too many entity_ids ({len(entity_ids)}). "
                f"Cap is {_MAX_CONTENT_READ_PER_CALL} per call — "
                "narrow further or split into multiple calls."
            ),
        }

    layout = tool_context.state.get("current_layout")
    entities = tool_context.state.get("entities")
    content = gather_entity_content(layout, entities, entity_ids)
    return {"status": "success", **content}


@tool_safe(require_layout=True)
def tool_infer_arrangement(
    tool_context: ToolContext,
    display_id: Optional[str] = None,
    entity_ids: Optional[List[str]] = None,
) -> dict:
    """
    Identify which semantic field best explains the row and column
    structure of views on each display, with per-band rationale.

    USE WHEN you need to name the organizing principle of an existing
    arrangement (e.g., "rows = year, columns = domain"), self-check
    whether a rearrangement you just performed actually produced the
    intended structure, or compare organizing principles across displays
    before replicating one elsewhere.

    Heuristic: for each semantic field (scalars plus individual themes),
    scores how often views in the same row/column band share that field's
    modal value. The highest-scoring field per axis wins, subject to a
    homogeneity floor. If no field clears the floor the axis is reported
    as `null`.

    Scoping: pass `display_id` to limit inference to a single display, or
    `entity_ids` to limit to a specific selection (entities spanning
    multiple displays are grouped per-display — axes are always
    display-local). `entity_ids` takes precedence over `display_id`.

    Returns a list under `per_display`, one entry per display in scope:
      - `row_axis`, `col_axis`: each `null` or `{field, score, rationale}`
        where `field` is a semantic field name or `theme:<name>`, and
        `rationale` enumerates each band's modal value and match count
      - `bands`: `{row, col}` band counts
      - `unexplained_views`: names of views that fail every claimed axis
      - `note`: present only when no axis clears the floor
    """
    layout = tool_context.state.get("current_layout")
    entities = tool_context.state.get("entities")
    return {
        "status": "success",
        "per_display": infer_arrangement(
            layout,
            entities=entities,
            display_id=display_id,
            entity_ids=entity_ids,
        ),
    }


@tool_safe(require_layout=True)
def tool_move_entity(
    tool_context: ToolContext,
    entity_id: str,
    target_surface: str,
    x: Optional[float] = None,
    y: Optional[float] = None,
    reference_entity_id: Optional[str] = None,
    region: Optional[str] = None,
    preview_only: bool = False,
) -> dict:
    """
    Move a single entity to a target display using one of several placement
    modes. Use tool_arrange_entities for bulk moves.

    Args:
        entity_id: ID of entity to move.
        target_surface: Target display — prefer tags ("left", "right",
            "center"). peer_id also accepted.
        x: X coordinate (must provide y together). Mutually exclusive with
            reference_entity_id and region.
        y: Y coordinate (must provide x together).
        reference_entity_id: Entity to position near.
        region: Display region anchor ("top-left", "center", etc.).
        preview_only: If True, returns target position without moving.
    """
    layout = tool_context.state.get("current_layout")

    if entity_id not in layout.get("node_positions", {}):
        return {"status": "error", "message": f"Entity {entity_id} not found"}

    target_surface = _resolve_surface(layout, target_surface)

    if (x is None) != (y is None):
        return {
            "status": "error",
            "message": "x and y must be provided together.",
        }

    explicit_xy = x is not None and y is not None
    mode_count = sum(
        [1 if explicit_xy else 0, 1 if reference_entity_id else 0, 1 if region else 0]
    )
    if mode_count > 1:
        return {
            "status": "error",
            "message": "Use only one placement mode: explicit coordinates, reference_entity_id, or region.",
        }

    entity_name = layout.get("entity_names", {}).get(entity_id, entity_id)

    if explicit_xy:
        target_pos: tuple[float, float] = (x, y)
    elif region:
        region_pos, region_error = _get_region_position(layout, target_surface, region)
        if region_error:
            return {"status": "error", "message": region_error}
        assert region_pos is not None
        target_pos = region_pos
    elif reference_entity_id:
        reference_position = _get_reference_position(layout, reference_entity_id)
        if reference_position is None:
            return {
                "status": "error",
                "message": f"Reference entity {reference_entity_id} not found",
            }
        try:
            target_pos = find_available_position(
                layout, target_surface, entity_id, reference_position
            )
        except ValueError as e:
            return {"status": "error", "message": str(e)}
    else:
        try:
            target_pos = find_available_position(
                layout, target_surface, entity_id, None
            )
        except ValueError as e:
            return {"status": "error", "message": str(e)}

    if preview_only:
        return {
            "status": "success",
            "message": (
                f"Previewed target position for {entity_name} on {target_surface} "
                f"at ({target_pos[0]:.1f}, {target_pos[1]:.1f})"
            ),
            "position": {"x": target_pos[0], "y": target_pos[1]},
            "target_surface": target_surface,
        }

    updated = move_entity(layout, entity_id, target_surface, target_pos)

    tool_context.state["current_layout"] = updated

    return {
        "status": "success",
        "message": (
            f"Moved {entity_name} to {target_surface} "
            f"at ({target_pos[0]:.1f}, {target_pos[1]:.1f})"
        ),
        "position": {"x": target_pos[0], "y": target_pos[1]},
        "target_surface": target_surface,
    }


@tool_safe(require_layout=True)
def tool_scale(tool_context: ToolContext, scale_factor: float) -> dict:
    """
    Scale the entire layout by a factor. Use when the layout feels too
    cramped or too spread out overall.

    Args:
        scale_factor: Multiplier (e.g., 1.5 = 50% larger, 0.5 = 50% smaller).
    """
    layout = tool_context.state.get("current_layout")

    updated = scale_layout(layout, scale_factor)

    tool_context.state["current_layout"] = updated

    return {"status": "success", "message": f"Scaled layout by {scale_factor}x"}


@tool_safe(require_layout=True)
def tool_resize_entities(
    tool_context: ToolContext,
    entity_ids: list[str],
    width: float,
    height: float,
) -> dict:
    """
    Resize multiple entities to the same width and height in a single call.
    Typical sizes: ~400×300 (standard), ~600×450 (primary/emphasis),
    ~300×200 (secondary/compact).

    Args:
        entity_ids: List of entity IDs to resize.
        width: New width in canvas units.
        height: New height in canvas units.
    """
    layout = tool_context.state.get("current_layout")
    node_positions = layout.get("node_positions", {})

    resized = []
    skipped = []
    for eid in entity_ids:
        if eid not in node_positions:
            skipped.append(eid)
            continue
        layout = resize_entity(layout, eid, width, height)
        resized.append(eid)

    tool_context.state["current_layout"] = layout

    msg = f"Resized {len(resized)} entities to {width}x{height}"
    if skipped:
        msg += f" (skipped {len(skipped)} not found)"
    return {"status": "success", "message": msg}


@tool_safe(require_layout=True)
def tool_swap(tool_context: ToolContext, entity_id_1: str, entity_id_2: str) -> dict:
    """
    Swap the positions of two entities.

    Args:
        entity_id_1: First entity ID.
        entity_id_2: Second entity ID.
    """
    layout = tool_context.state.get("current_layout")

    updated = swap_entities(layout, entity_id_1, entity_id_2)

    tool_context.state["current_layout"] = updated

    return {
        "status": "success",
        "message": f"Swapped positions of {entity_id_1} and {entity_id_2}",
    }


@tool_safe(require_layout=True)
def tool_snap_edges(
    tool_context: ToolContext,
    entity_ids: list[str],
    axis: Optional[str] = "both",
) -> dict:
    """
    Align entities so their x and/or y coordinates match the first entity
    in the list. The first entity acts as the reference anchor — all others
    snap to its position. Use to fix minor misalignments after manual
    placement.

    Args:
        entity_ids: List of entity IDs. The FIRST ID is the anchor;
            all others align to its x/y coordinate.
        axis: "x" (align left edges), "y" (align top edges), or "both".
    """
    layout = tool_context.state.get("current_layout")

    if not entity_ids:
        return {"status": "error", "message": "No entity IDs provided"}

    node_positions = layout.get("node_positions", {})
    valid_ids = [eid for eid in entity_ids if eid in node_positions]

    if not valid_ids:
        return {
            "status": "error",
            "message": "None of the provided entities were found",
        }

    reference_id = valid_ids[0]
    ref_x, ref_y = node_positions[reference_id]

    for eid in valid_ids[1:]:
        curr_x, curr_y = node_positions[eid]
        new_x = ref_x if axis in ["x", "both"] else curr_x
        new_y = ref_y if axis in ["y", "both"] else curr_y
        node_positions[eid] = [new_x, new_y]

    tool_context.state["current_layout"] = layout

    return {
        "status": "success",
        "message": f"Aligned {len(valid_ids)} entities along {axis} axis to match {reference_id}",
    }


@tool_safe(require_layout=True)
def tool_maximize_to_display(
    tool_context: ToolContext, entity_id: str, display_id: Optional[str] = None
) -> dict:
    """
    Scale and position a single entity to fill the entire usable area of
    a display. Use when the user wants to focus on one view full-screen.

    Args:
        entity_id: Entity ID to maximize.
        display_id: Target display ID (defaults to entity's current display).
    """
    layout = tool_context.state.get("current_layout")

    if entity_id not in layout.get("node_positions", {}):
        return {"status": "error", "message": f"Entity {entity_id} not found"}

    displays = layout.get("displays", [])
    if not displays:
        return {
            "status": "error",
            "message": "No display information available in layout",
        }

    assignments = layout.get("display_assignments", {})
    if not display_id:
        display_id = assignments.get(
            entity_id, displays[0].get("peer_id", displays[0].get("id"))
        )

    target_display = None
    for d in displays:
        if (
            d.get("peer_id") == display_id
            or d.get("id") == display_id
            or display_id in d.get("tags", [])
        ):
            target_display = d
            break

    if not target_display:
        target_display = displays[0]

    # Maximization anchors the entity at display origin; frontend handles viewport fit.
    layout.setdefault("node_positions", {})[entity_id] = [0, 0]

    width = target_display.get("width", 1920)
    height = target_display.get("height", 1080)

    if "node_sizes" not in layout:
        layout["node_sizes"] = {}
    layout["node_sizes"][entity_id] = [width, height]

    if "entity_dimensions" not in layout:
        layout["entity_dimensions"] = {}
    layout["entity_dimensions"][entity_id] = {"width": width, "height": height}

    assignments[entity_id] = target_display.get("peer_id", target_display.get("id"))
    layout["display_assignments"] = assignments

    tool_context.state["current_layout"] = layout

    return {
        "status": "success",
        "message": f"Maximized {entity_id} to {width}x{height} on display {target_display.get('peer_id', 'unknown')}",
    }
