"""Display-aware movement and arrangement tools."""

from typing import Optional

from google.adk.tools.tool_context import ToolContext
from loguru import logger

from ..layout_operations import (
    compute_arrangement_info,
    compute_arrangement_positions,
    fit_display_camera_to_entities_if_needed,
    get_entity_dimension,
    get_node_sizes_if_available,
    get_surface_visible_bounds,
    get_surface_workspace_bounds,
    move_entity,
    resolve_display_name,
)
from ..layout_ops.regions import REGION_SLICES, slice_bounds_for_region
from ..layout_ops.spatial_summary import summarize_arrangement
from .common import tool_safe

_ARRANGEMENT_PADDING = 0.1

_REGION_SLICES = REGION_SLICES
_slice_bounds_for_region = slice_bounds_for_region


def _log_out_of_bounds(
    layout: dict,
    positions: list[tuple[float, float]],
    bounds: tuple[float, float, float, float],
    region: str,
    entity_ids: list[str],
) -> list[str]:
    """Log a warning when computed node rectangles fall outside the target region bounds.

    Checks the full node rectangle (x, y, x+w, y+h), not just the top-left point.

    Returns:
        List of entity names that overflow.
    """
    min_x, min_y, max_x, max_y = bounds
    out = []
    for eid, (px, py) in zip(entity_ids, positions):
        w = get_entity_dimension(layout, eid, "width") or 0.0
        h = get_entity_dimension(layout, eid, "height") or 0.0
        if px < min_x or (px + w) > max_x or py < min_y or (py + h) > max_y:
            name = layout.get("entity_names", {}).get(eid, eid)
            out.append(name)
    if out:
        logger.warning(
            f"{len(out)}/{len(positions)} entities placed outside "
            f"requested region '{region}': {out[:5]}"
        )
    return out


def _check_placement_overflow(
    layout: dict,
    surface_id: str,
    entity_ids: list[str],
    positions: list[tuple[float, float]],
    effective_bounds: tuple[float, float, float, float],
) -> dict | None:
    """Compute content bounding box and compare against effective bounds.

    Returns a structured dict with viewport size, content extent, overflow flags,
    and per-entity positions — or None when there are no entities.
    """
    if not entity_ids or not positions:
        return None

    eb_min_x, eb_min_y, eb_max_x, eb_max_y = effective_bounds
    viewport_w = eb_max_x - eb_min_x
    viewport_h = eb_max_y - eb_min_y

    content_min_x = float("inf")
    content_min_y = float("inf")
    content_max_x = float("-inf")
    content_max_y = float("-inf")

    pos_entries = []
    for eid, (px, py) in zip(entity_ids, positions):
        w = get_entity_dimension(layout, eid, "width") or 0.0
        h = get_entity_dimension(layout, eid, "height") or 0.0
        content_min_x = min(content_min_x, px)
        content_min_y = min(content_min_y, py)
        content_max_x = max(content_max_x, px + w)
        content_max_y = max(content_max_y, py + h)
        name = layout.get("entity_names", {}).get(eid, eid)
        pos_entries.append({"entity_id": eid, "name": name, "x": px, "y": py})

    content_w = content_max_x - content_min_x
    content_h = content_max_y - content_min_y

    overflow_x = content_min_x < eb_min_x or content_max_x > eb_max_x
    overflow_y = content_min_y < eb_min_y or content_max_y > eb_max_y

    if not overflow_x and not overflow_y:
        return None

    return {
        "viewport": {"width": round(viewport_w, 1), "height": round(viewport_h, 1)},
        "content_extent": {"width": round(content_w, 1), "height": round(content_h, 1)},
        "overflow": {"x": overflow_x, "y": overflow_y},
        "positions": pos_entries,
    }


def _resolve_display_or_error(
    layout: dict, display_name: str
) -> tuple[str | None, dict | None]:
    """Resolve display name to peer_id, returning (peer_id, None) or (None, error_dict)."""
    resolved = resolve_display_name(layout, display_name)
    if resolved:
        return resolved, None

    if display_name in layout.get("surface_assignments", {}):
        return display_name, None

    available = ", ".join(
        f"{d.get('tags', [])} ({d['peer_id']})" for d in layout.get("displays", [])
    )
    return None, {
        "status": "error",
        "message": f"Display '{display_name}' not found. Available: {available}",
    }


def _arrange_entities(
    tool_context: ToolContext,
    requested_entity_ids: list[str],
    display_name: str,
    arrangement: str,
    align: str,
    region: Optional[str],
    *,
    strict_missing: bool,
    preserve_order: bool,
    history_label: str,
    success_label: str,
    include_entity_names: bool,
) -> dict:
    """Shared arrangement pipeline for grouping and ordered list placement."""
    logger.info(
        f"CALLED: _arrange_entities(requested_entity_ids={requested_entity_ids}, display_name='{display_name}', arrangement='{arrangement}', align='{align}', region={repr(region)}, strict_missing={strict_missing}, preserve_order={preserve_order}, history_label='{history_label}', success_label='{success_label}', include_entity_names={include_entity_names})"
    )
    layout = tool_context.state.get("current_layout")

    if not requested_entity_ids:
        return {"status": "error", "message": "entity_ids cannot be empty."}

    node_positions = layout.get("node_positions", {})
    if strict_missing:
        missing = [eid for eid in requested_entity_ids if eid not in node_positions]
        if missing:
            return {"status": "error", "message": f"Entities not found: {missing}"}
        entity_ids = requested_entity_ids
    else:
        entity_ids = [eid for eid in requested_entity_ids if eid in node_positions]
        if not entity_ids:
            return {
                "status": "error",
                "message": "No valid entities found in the provided list.",
            }

    resolved, error = _resolve_display_or_error(layout, display_name)
    if error:
        return error
    assert resolved is not None

    bounds = get_surface_workspace_bounds(layout, resolved)
    if not bounds:
        return {"status": "error", "message": f"No bounds found for display {resolved}"}

    effective_bounds = bounds
    if region:
        region_bounds = get_surface_visible_bounds(layout, resolved) or bounds
        sliced = _slice_bounds_for_region(region_bounds, region)
        if sliced is None:
            return {
                "status": "error",
                "message": (
                    f"Unknown region '{region}'. "
                    f"Use one of: {', '.join(_REGION_SLICES.keys())}"
                ),
            }
        effective_bounds = sliced

    region_tag = f", region={region}" if region else ""
    node_sizes = get_node_sizes_if_available(layout, entity_ids)

    # Compute arrangement info (columns, rows, degradation warnings)
    arr_info = compute_arrangement_info(
        effective_bounds,
        len(entity_ids),
        arrangement,
        _ARRANGEMENT_PADDING,
        node_sizes=node_sizes,
        preserve_order=preserve_order,
    )

    positions = compute_arrangement_positions(
        effective_bounds,
        len(entity_ids),
        arrangement,
        _ARRANGEMENT_PADDING,
        node_sizes=node_sizes,
        align=align,
        preserve_order=preserve_order,
    )

    for eid, pos in zip(entity_ids, positions):
        layout = move_entity(layout, eid, resolved, pos)

    if region:
        _log_out_of_bounds(layout, positions, effective_bounds, region, entity_ids)

    camera_update = fit_display_camera_to_entities_if_needed(
        layout, resolved, entity_ids, region=region
    )
    if camera_update:
        layout.setdefault("_camera_updates", {})[resolved] = camera_update

    # Highlight affected entities so the user can see what was arranged
    layout["highlighted_entities"] = list(entity_ids)

    tool_context.state["current_layout"] = layout

    message = (
        f"{success_label} {len(entity_ids)} entities on {display_name} "
        f"in {arrangement} arrangement (align={align}{region_tag})"
    )
    if include_entity_names:
        names = [layout.get("entity_names", {}).get(eid, eid) for eid in entity_ids]
        message = f"{message}: {', '.join(names)}"
    else:
        message = f"{message}."

    result: dict = {"status": "success", "message": message}

    # Include arrangement info so the agent can see layout metadata
    if arr_info:
        raw_info = {
            "cols": arr_info.get("cols"),
            "rows": arr_info.get("rows"),
            "available_area": arr_info.get("available_area"),
            "packed_width": arr_info.get("packed_width"),
            "packed_height": arr_info.get("packed_height"),
            "packing_efficiency": arr_info.get("packing_efficiency"),
        }
        result["arrangement_info"] = {
            k: v for k, v in raw_info.items() if v is not None
        }
        warnings = arr_info.get("warnings", [])
        if warnings:
            result["arrangement_info"]["warnings"] = warnings
            result["message"] += f" WARNING: {'; '.join(warnings)}"

    placement = _check_placement_overflow(
        layout, resolved, entity_ids, positions, effective_bounds
    )
    if placement:
        result["placement_context"] = placement

    # Add human-readable spatial summary for the agent
    spatial = summarize_arrangement(
        layout, entity_ids, positions, display_name, arrangement
    )
    if spatial:
        result["spatial_summary"] = spatial

    return result


@tool_safe(require_layout=True)
def tool_arrange_entities(
    tool_context: ToolContext,
    entity_ids: list[str],
    display_name: str = "center",
    arrangement: str = "grid",
    align: str = "center",
    region: Optional[str] = None,
    preserve_order: bool = True,
    strict_missing: bool = False,
) -> dict:
    """
    Arrange entities in a pattern on a display. Use for bulk placement of
    multiple entities. Prefer over repeated tool_move_entity calls.

    Args:
        entity_ids: Entities to arrange.
        display_name: Target display tag ("left", "center", "right") or
            peer_id. Prefer tags from the layout context.
        arrangement: Layout pattern:
            - "grid"       — rows × columns, auto-computed from entity count
            - "horizontal" — single row, left to right
            - "vertical"   — single column, top to bottom
        align: Cross-axis alignment within the display (or region).
            For "vertical": "left", "right", or "center" (default).
            For "horizontal": "top", "bottom", or "center" (default).
            "grid" supports all directions.
        region: Sub-area of the display. One of: "top", "bottom",
            "left", "right", "top-left", "top-right", "bottom-left",
            "bottom-right", "center". Omit to use full display bounds.
        preserve_order: True (default) — keep entity_ids list order (use for
            temporal sorts or user-specified sequences). False — sort IDs for
            deterministic grouping when order doesn't matter.
        strict_missing: True — error if any IDs not found. False (default) —
            silently skip missing IDs.
    """
    logger.info(
        f"CALLED: tool_arrange_entities(entity_ids={entity_ids}, display_name='{display_name}', arrangement='{arrangement}', align='{align}', region={repr(region)}, preserve_order={preserve_order}, strict_missing={strict_missing})"
    )
    arranged_ids = entity_ids if preserve_order else sorted(set(entity_ids))
    history_label = "arrange" if preserve_order else "group"
    success_label = "Arranged" if preserve_order else "Grouped"

    return _arrange_entities(
        tool_context,
        requested_entity_ids=arranged_ids,
        display_name=display_name,
        arrangement=arrangement,
        align=align,
        region=region,
        strict_missing=strict_missing,
        preserve_order=preserve_order,
        history_label=history_label,
        success_label=success_label,
        include_entity_names=not preserve_order,
    )


_DEFAULT_GAP = 40.0  # Same as DEFAULT_NODE_GAP in constants


@tool_safe(require_layout=True)
def tool_arrange_relative(
    tool_context: ToolContext,
    target_entity_id: str,
    reference_entity_id: str,
    direction: str,
    gap: float = _DEFAULT_GAP,
) -> dict:
    """
    Move an entity relative to a reference entity on the same display.
    Automatically accounts for both entities' dimensions so the gap is
    clear space between edges.

    Args:
        target_entity_id: Entity to move.
        reference_entity_id: Entity to position relative to.
        direction: "above", "below", "left", or "right".
        gap: Clear space in canvas units between edges (default 40).
    """
    layout = tool_context.state.get("current_layout")

    if target_entity_id not in layout.get("node_positions", {}):
        return {
            "status": "error",
            "message": f"Target entity {target_entity_id} not found",
        }
    if reference_entity_id not in layout.get("node_positions", {}):
        return {
            "status": "error",
            "message": f"Reference entity {reference_entity_id} not found",
        }

    ref_x, ref_y = layout["node_positions"][reference_entity_id]

    # Look up actual dimensions (fall back to reasonable defaults)
    ref_w = get_entity_dimension(layout, reference_entity_id, "width") or 400.0
    ref_h = get_entity_dimension(layout, reference_entity_id, "height") or 300.0
    tgt_h = get_entity_dimension(layout, target_entity_id, "height") or 300.0
    tgt_w = get_entity_dimension(layout, target_entity_id, "width") or 400.0

    new_x, new_y = ref_x, ref_y
    direction = direction.lower()
    if direction == "above":
        # Place target so its bottom edge is `gap` above reference's top edge
        new_y = ref_y - tgt_h - gap
        new_x = ref_x  # align left edges
    elif direction == "below":
        # Place target so its top edge is `gap` below reference's bottom edge
        new_y = ref_y + ref_h + gap
        new_x = ref_x  # align left edges
    elif direction == "left":
        # Place target so its right edge is `gap` left of reference's left edge
        new_x = ref_x - tgt_w - gap
        new_y = ref_y  # align top edges
    elif direction == "right":
        # Place target so its left edge is `gap` right of reference's right edge
        new_x = ref_x + ref_w + gap
        new_y = ref_y  # align top edges
    else:
        return {
            "status": "error",
            "message": f"Unknown direction '{direction}'. Use 'above', 'below', 'left', or 'right'.",
        }

    ref_surface = None
    for surface_id, entity_ids in layout.get("surface_assignments", {}).items():
        if reference_entity_id in entity_ids:
            ref_surface = surface_id
            break

    if not ref_surface:
        return {
            "status": "error",
            "message": "Could not find surface for reference entity",
        }

    target_name = layout.get("entity_names", {}).get(target_entity_id, target_entity_id)
    ref_name = layout.get("entity_names", {}).get(
        reference_entity_id, reference_entity_id
    )

    updated = move_entity(layout, target_entity_id, ref_surface, (new_x, new_y))

    tool_context.state["current_layout"] = updated

    return {
        "status": "success",
        "message": f"Moved {target_name} {direction} {ref_name} on display {ref_surface} at ({new_x:.1f}, {new_y:.1f})",
    }
