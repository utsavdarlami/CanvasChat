"""
Calculate layout deltas for efficient client updates.

Compares two layout states and identifies what changed.
"""

from typing import Any, Dict, List
from loguru import logger

_OVERLAY_PADDING = 20.0
_FALLBACK_W = 400.0
_FALLBACK_H = 300.0


def _recalc_overlay_bounds(
    overlays: List[Dict[str, Any]],
    node_positions: Dict[str, Any],
    entity_dimensions: Dict[str, Any],
    surface_assignments: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    """Recalculate overlay bounds from final node positions.

    Drops entity_ids whose positions are gone, drops overlays with no
    remaining members, and reassigns display_id to the surface holding
    the majority of members so overlays follow cross-display moves.
    """
    entity_to_surface: Dict[str, str] = {}
    if surface_assignments:
        for surface_id, eids in surface_assignments.items():
            for eid in eids:
                entity_to_surface[eid] = surface_id

    updated: List[Dict[str, Any]] = []
    for overlay in overlays:
        entity_ids = overlay.get("entity_ids", [])
        live_ids = [eid for eid in entity_ids if eid in node_positions]
        if not live_ids:
            continue

        min_x = float("inf")
        min_y = float("inf")
        max_x = float("-inf")
        max_y = float("-inf")
        surface_counts: Dict[str, int] = {}

        for eid in live_ids:
            pos = node_positions[eid]
            x = pos[0] if isinstance(pos, (list, tuple)) else pos.get("x", 0)
            y = pos[1] if isinstance(pos, (list, tuple)) else pos.get("y", 0)
            dims = entity_dimensions.get(eid, {})
            w = dims.get("width", _FALLBACK_W) if isinstance(dims, dict) else _FALLBACK_W
            h = dims.get("height", _FALLBACK_H) if isinstance(dims, dict) else _FALLBACK_H
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x + w)
            max_y = max(max_y, y + h)
            surf = entity_to_surface.get(eid)
            if surf:
                surface_counts[surf] = surface_counts.get(surf, 0) + 1

        if min_x == float("inf"):
            continue

        new_overlay = dict(overlay)
        new_overlay["entity_ids"] = live_ids
        new_overlay["bounds"] = {
            "min_x": min_x - _OVERLAY_PADDING,
            "min_y": min_y - _OVERLAY_PADDING,
            "max_x": max_x + _OVERLAY_PADDING,
            "max_y": max_y + _OVERLAY_PADDING,
        }
        if surface_counts:
            new_overlay["display_id"] = max(surface_counts.items(), key=lambda kv: kv[1])[0]
        updated.append(new_overlay)
    return updated


def calculate_layout_delta(
    previous_layout: Dict[str, Any], current_layout: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Calculate what changed between two layouts.

    Args:
        previous_layout: Previous layout state
        current_layout: Current layout state

    Returns:
        Delta dictionary with:
        - updated_nodes: List of nodes with changed positions
        - added_nodes: List of newly added nodes
        - removed_nodes: List of removed entity IDs
        - updated_links: List of changed links (currently empty)
    """
    delta = {
        "updated_nodes": [],
        "added_nodes": [],
        "removed_nodes": [],
        "highlighted_nodes": [],
        "highlighted_node_colors": {},
        "entity_tags": {},
        "user_text_highlights": {},
    }

    try:
        prev_positions = previous_layout.get("node_positions", {})
        curr_positions = current_layout.get("node_positions", {})
        entity_names = current_layout.get("entity_names", {})
        entity_dimensions = current_layout.get("entity_dimensions", {})
        prev_entity_dimensions = previous_layout.get("entity_dimensions", {})

        delta["highlighted_nodes"] = current_layout.get("highlighted_entities", [])
        delta["highlighted_node_colors"] = dict(
            current_layout.get("highlighted_entity_colors") or {}
        )
        delta["text_highlights"] = current_layout.get("text_highlights", [])
        delta["clear_text_highlight_ids"] = current_layout.get("clear_text_highlight_ids", [])
        delta["entity_tags"] = dict(current_layout.get("entity_tags") or {})
        delta["user_text_highlights"] = dict(current_layout.get("user_text_highlights") or {})

        camera_updates = current_layout.get("_camera_updates", {})
        if camera_updates:
            delta["camera_updates"] = camera_updates

        group_overlays = current_layout.get("_group_overlays")
        if group_overlays is not None:
            # Recalculate bounds, prune dead members, follow cross-display moves.
            # Emit empty list to let the frontend clear stale overlays.
            delta["group_overlays"] = _recalc_overlay_bounds(
                group_overlays,
                curr_positions,
                entity_dimensions,
                current_layout.get("surface_assignments"),
            )

        prev_assignments = previous_layout.get("surface_assignments", {})
        curr_assignments = current_layout.get("surface_assignments", {})

        prev_entity_surface = {}
        for surface_id, entity_ids in prev_assignments.items():
            for eid in entity_ids:
                prev_entity_surface[eid] = surface_id

        curr_entity_surface = {}
        for surface_id, entity_ids in curr_assignments.items():
            for eid in entity_ids:
                curr_entity_surface[eid] = surface_id

        for entity_id, curr_pos in curr_positions.items():
            curr_surf = curr_entity_surface.get(entity_id)
            if entity_id in prev_positions:
                prev_pos = prev_positions[entity_id]
                prev_surf = prev_entity_surface.get(entity_id)
                prev_dims = prev_entity_dimensions.get(entity_id)
                curr_dims = entity_dimensions.get(entity_id)
                if prev_pos != curr_pos or prev_surf != curr_surf or prev_dims != curr_dims:
                    node_data = {
                        "entity_id": entity_id,
                        "x": curr_pos[0]
                        if isinstance(curr_pos, (list, tuple))
                        else curr_pos.get("x", 0),
                        "y": curr_pos[1]
                        if isinstance(curr_pos, (list, tuple))
                        else curr_pos.get("y", 0),
                        "name": entity_names.get(entity_id, entity_id),
                    }
                    dims = entity_dimensions.get(entity_id)
                    if isinstance(dims, dict):
                        if "width" in dims:
                            node_data["width"] = dims["width"]
                        if "height" in dims:
                            node_data["height"] = dims["height"]
                    if curr_surf is not None and curr_surf != "surface_0":
                        node_data["display_id"] = curr_surf
                    delta["updated_nodes"].append(node_data)
            else:
                node_data = {
                    "entity_id": entity_id,
                    "x": curr_pos[0]
                    if isinstance(curr_pos, (list, tuple))
                    else curr_pos.get("x", 0),
                    "y": curr_pos[1]
                    if isinstance(curr_pos, (list, tuple))
                    else curr_pos.get("y", 0),
                    "name": entity_names.get(entity_id, entity_id),
                }
                dims = entity_dimensions.get(entity_id)
                if isinstance(dims, dict):
                    if "width" in dims:
                        node_data["width"] = dims["width"]
                    if "height" in dims:
                        node_data["height"] = dims["height"]
                if curr_surf is not None and curr_surf != "surface_0":
                    node_data["display_id"] = curr_surf
                delta["added_nodes"].append(node_data)

        for entity_id in prev_positions:
            if entity_id not in curr_positions:
                delta["removed_nodes"].append(entity_id)

    except Exception as e:
        logger.warning(f"Failed to calculate layout delta: {str(e)}", exc_info=True)
        # Keep clients running by falling back to a full-layout refresh on delta failures.
        return {
            "updated_nodes": [],
            "added_nodes": [],
            "removed_nodes": [],
            "highlighted_nodes": [],
            "highlighted_node_colors": {},
            "text_highlights": [],
            "clear_text_highlight_ids": [],
            "entity_tags": {},
            "user_text_highlights": {},
        }

    return delta
