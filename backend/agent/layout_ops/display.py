"""Display/surface resolution and construction helpers."""

from typing import Any, Dict, Optional

from .dimensions import _parse_positive_float


def get_surface_workspace_bounds(
    layout: Dict[str, Any], surface_id: str
) -> Optional[tuple[float, float, float, float]]:
    """Return the stable display-local workspace bounds for a surface."""
    bounds = layout.get("surface_bounds", {}).get(surface_id)
    if bounds is not None:
        return bounds
    return layout.get("surface_content_bounds", {}).get(surface_id)


def get_surface_viewport_dims(
    layout: Dict[str, Any], surface_id: str
) -> Optional[tuple[float, float]]:
    """Return actual display viewport dimensions (width, height).

    Unlike visible_canvas bounds (which change with camera zoom/pan),
    these are the stable physical display dimensions used for spacing
    budget calculations.
    """
    # First check surface_bounds which stores (0, 0, width, height)
    bounds = layout.get("surface_bounds", {}).get(surface_id)
    if bounds is not None:
        return (bounds[2], bounds[3])

    # Fall back to display metadata
    for display in layout.get("displays", []):
        if display.get("peer_id") == surface_id:
            w = float(display.get("width", 0) or 0)
            h = float(display.get("height", 0) or 0)
            if w > 0 and h > 0:
                return (w, h)
    return None


def get_surface_visible_bounds(
    layout: Dict[str, Any], surface_id: str
) -> Optional[tuple[float, float, float, float]]:
    """Return the current visible canvas bounds for a surface when available."""
    visible = layout.get("surface_visible_bounds", {}).get(surface_id)
    if visible is not None:
        return visible

    for display in layout.get("displays", []):
        if display.get("peer_id") != surface_id:
            continue
        visible_canvas = display.get("visible_canvas")
        if visible_canvas:
            return (
                visible_canvas.get("min_x", 0.0),
                visible_canvas.get("min_y", 0.0),
                visible_canvas.get("max_x", visible_canvas.get("width", 0.0)),
                visible_canvas.get("max_y", visible_canvas.get("height", 0.0)),
            )
        break

    return get_surface_workspace_bounds(layout, surface_id)


def resolve_display_name(layout: Dict[str, Any], display_name: str) -> Optional[str]:
    """
    Resolve a user-friendly display reference to a peer_id.

    Matches against display tags (e.g., "left", "right") and peer_id values.
    Case-insensitive matching.

    Args:
        layout: Current layout state (must contain 'displays' if multi-display)
        display_name: User reference like "left", "right display", or a peer_id

    Returns:
        Resolved peer_id or None if not found
    """
    displays = layout.get("displays", [])
    if not displays:
        return None

    name_lower = display_name.lower().replace(" display", "").strip()

    for display in displays:
        if display.get("peer_id") == display_name:
            return display["peer_id"]

        tags = [t.lower() for t in display.get("tags", [])]
        if name_lower in tags:
            return display["peer_id"]

    return None


def _single_surface_fallback(node_positions: Dict[str, tuple]) -> tuple:
    """Build a single surface_0 fallback when no multi-display context is available.

    Returns:
        (
            surface_assignments,
            surface_bounds,
            surface_visible_bounds,
            surface_content_bounds,
            displays_metadata,
        )
    """
    surface_assignments = {"surface_0": list(node_positions.keys())}

    if node_positions:
        xs = [pos[0] for pos in node_positions.values()]
        ys = [pos[1] for pos in node_positions.values()]
        padding = 2.0
        surface_bounds = {
            "surface_0": (
                min(xs) - padding,
                min(ys) - padding,
                max(xs) + padding,
                max(ys) + padding,
            )
        }
    else:
        surface_bounds = {"surface_0": (0, 0, 0, 0)}

    surface_visible_bounds = dict(surface_bounds)
    surface_content_bounds = dict(surface_bounds)

    return (
        surface_assignments,
        surface_bounds,
        surface_visible_bounds,
        surface_content_bounds,
        [],
    )


def _build_display_surfaces(
    node_positions: Dict[str, tuple],
    entity_display_ids: Dict[str, str],
    display_context: Optional[Dict[str, Any]],
    entity_dimensions: Optional[Dict[str, Any]] = None,
) -> tuple:
    """
    Build surface assignments and bounds from display context or fallback to single surface.

    Returns:
        (
            surface_assignments,
            surface_bounds,
            surface_visible_bounds,
            surface_content_bounds,
            displays_metadata,
        )
        - surface_bounds: stable display-local workspace bounds
        - surface_visible_bounds: current visible canvas bounds (camera-dependent)
        - surface_content_bounds: workspace bounds expanded to include current content
    """
    if not display_context:
        return _single_surface_fallback(node_positions)

    raw_displays = display_context.get("virtual_desktop", {}).get("displays", [])
    if not raw_displays:
        return _single_surface_fallback(node_positions)

    surface_assignments = {}
    surface_bounds = {}
    surface_visible_bounds = {}
    displays = []

    for disp in raw_displays:
        peer_id = disp["peer_id"]

        width = float(disp.get("width", 0.0) or 0.0)
        height = float(disp.get("height", 0.0) or 0.0)
        surface_bounds[peer_id] = (0.0, 0.0, width, height)

        visible_canvas = disp.get("visible_canvas")
        if visible_canvas:
            surface_visible_bounds[peer_id] = (
                visible_canvas.get("min_x", 0),
                visible_canvas.get("min_y", 0),
                visible_canvas.get("max_x", visible_canvas.get("width", 0)),
                visible_canvas.get("max_y", visible_canvas.get("height", 0)),
            )
        else:
            surface_visible_bounds[peer_id] = surface_bounds[peer_id]

        assigned = list(disp.get("node_ids", []))

        for eid, did in entity_display_ids.items():
            if did == peer_id and eid not in assigned:
                assigned.append(eid)

        surface_assignments[peer_id] = assigned

        displays.append(
            {
                "peer_id": peer_id,
                "tags": disp.get("tags", []),
                "x": disp.get("x", 0),
                "y": disp.get("y", 0),
                "width": width,
                "height": height,
                "camera": disp.get("camera"),
                "visible_canvas": disp.get("visible_canvas"),
            }
        )

    all_assigned = set()
    for ids in surface_assignments.values():
        all_assigned.update(ids)

    unassigned = [eid for eid in node_positions if eid not in all_assigned]
    if unassigned:
        first_peer = raw_displays[0]["peer_id"]
        surface_assignments[first_peer].extend(unassigned)

    # Keep viewport bounds pure for region tools, but expand separate content
    # bounds so collision/spiral logic can reach nodes outside the workspace.
    surface_content_bounds = _expand_bounds_to_content(
        dict(surface_bounds),
        surface_assignments,
        node_positions,
        entity_dimensions=entity_dimensions,
    )

    return (
        surface_assignments,
        surface_bounds,
        surface_visible_bounds,
        surface_content_bounds,
        displays,
    )


def _expand_bounds_to_content(
    surface_bounds: Dict[str, tuple],
    surface_assignments: Dict[str, list],
    node_positions: Dict[str, tuple],
    entity_dimensions: Optional[Dict[str, Any]] = None,
) -> Dict[str, tuple]:
    """Union each display's bounds with the bounding box of its assigned nodes."""

    def _dimension(entity_id: str, axis: str) -> float:
        if not entity_dimensions:
            return 0.0
        dims = entity_dimensions.get(entity_id)
        if isinstance(dims, dict):
            return _parse_positive_float(dims.get(axis)) or 0.0
        if isinstance(dims, (list, tuple)) and len(dims) == 2:
            idx = 0 if axis == "width" else 1
            return _parse_positive_float(dims[idx]) or 0.0
        return 0.0

    for peer_id, eids in surface_assignments.items():
        positions = [node_positions[eid] for eid in eids if eid in node_positions]
        if not positions:
            continue

        content_min_x = min(p[0] for p in positions)
        content_min_y = min(p[1] for p in positions)
        content_max_x = max(
            node_positions[eid][0] + _dimension(eid, "width")
            for eid in eids
            if eid in node_positions
        )
        content_max_y = max(
            node_positions[eid][1] + _dimension(eid, "height")
            for eid in eids
            if eid in node_positions
        )

        cur = surface_bounds.get(peer_id)
        if cur is None:
            surface_bounds[peer_id] = (
                content_min_x,
                content_min_y,
                content_max_x,
                content_max_y,
            )
        else:
            surface_bounds[peer_id] = (
                min(cur[0], content_min_x),
                min(cur[1], content_min_y),
                max(cur[2], content_max_x),
                max(cur[3], content_max_y),
            )

    return surface_bounds


def recalculate_surface_content_bounds(layout: Dict[str, Any]) -> Dict[str, tuple]:
    """Recompute content bounds from current workspace bounds and entity rectangles."""
    return _expand_bounds_to_content(
        dict(layout.get("surface_bounds", {})),
        layout.get("surface_assignments", {}),
        layout.get("node_positions", {}),
        entity_dimensions=layout.get("entity_dimensions", {}),
    )
