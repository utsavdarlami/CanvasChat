"""Position search helpers for collision-avoiding placement using rectpack."""

from typing import Any, Dict, Optional

from loguru import logger
from rectpack.maxrects import MaxRectsBssf
from rectpack.geometry import Rectangle

from .constants import (
    DEFAULT_MIN_NODE_DISTANCE,
)
from .dimensions import get_entity_dimension


def find_available_position(
    layout: Dict[str, Any],
    surface_id: str,
    entity_id: str,
    reference_position: Optional[tuple] = None,
    min_distance: float = DEFAULT_MIN_NODE_DISTANCE,
) -> tuple:
    """
    Find the nearest non-overlapping position on a surface for a specific entity.

    Uses 2D bin-packing (MaxRects) to find the optimal empty pocket that fits the
    entity's bounding box, closest to the reference position.
    """
    surface_entities = layout.get("surface_assignments", {}).get(surface_id, [])

    # Get bounds
    bounds = layout.get("surface_content_bounds", layout.get("surface_bounds", {})).get(
        surface_id
    )
    if not bounds:
        raise ValueError(f"No bounds found for surface {surface_id}")

    min_x, min_y, max_x, max_y = bounds
    avail_w = max_x - min_x
    avail_h = max_y - min_y

    # Resolve reference position
    if reference_position is None:
        reference_position = (min_x + avail_w / 2, min_y + avail_h / 2)

    # Get target entity dimensions
    target_w = get_entity_dimension(layout, entity_id, "width") or 0.0
    target_h = get_entity_dimension(layout, entity_id, "height") or 0.0

    # Add gap
    target_w += min_distance
    target_h += min_distance

    # Attempt to find position within strict bounds
    pos = _find_empty_pocket(
        layout,
        surface_entities,
        entity_id,
        min_distance,
        min_x,
        min_y,
        avail_w,
        avail_h,
        target_w,
        target_h,
        reference_position,
    )

    if pos is not None:
        return pos

    # Fallback: Surface is too crowded, expand bounds artificially to guarantee a spot
    logger.info(
        f"Surface {surface_id} too crowded. Expanding bounds to find position for {entity_id}."
    )
    EXPAND = 10000.0
    pos = _find_empty_pocket(
        layout,
        surface_entities,
        entity_id,
        min_distance,
        min_x - EXPAND,
        min_y - EXPAND,
        avail_w + EXPAND * 2,
        avail_h + EXPAND * 2,
        target_w,
        target_h,
        reference_position,
    )

    if pos is not None:
        return pos

    raise ValueError(
        f"Could not find available position on surface {surface_id} even after expanding bounds."
    )


def _find_empty_pocket(
    layout,
    surface_entities,
    target_entity_id,
    gap,
    min_x,
    min_y,
    avail_w,
    avail_h,
    target_w,
    target_h,
    reference_position,
):
    """
    Core function that calculates free rectangles and finds the one closest to the reference position.
    """
    # Initialize algorithm
    algo = MaxRectsBssf(avail_w, avail_h, rot=False)

    # Add existing entities as obstacles
    node_positions = layout.get("node_positions", {})
    for eid in surface_entities:
        if eid == target_entity_id:
            continue
        if eid not in node_positions:
            continue

        ex, ey = node_positions[eid]
        ew = get_entity_dimension(layout, eid, "width") or 0.0
        eh = get_entity_dimension(layout, eid, "height") or 0.0

        # Normalize to bin coordinates (0,0 origin)
        norm_x = ex - min_x
        norm_y = ey - min_y

        # Add gap to obstacle bounding box to guarantee spacing
        r = Rectangle(norm_x, norm_y, ew + gap, eh + gap)
        algo._split(r)
        algo._remove_duplicates()

    valid_spaces = []
    for m in algo._max_rects:
        if target_w <= m.width and target_h <= m.height:
            valid_spaces.append(m)

    if not valid_spaces:
        return None

    # Normalize reference position
    ref_x, ref_y = reference_position
    norm_ref_x = ref_x - min_x
    norm_ref_y = ref_y - min_y

    best_dist = float("inf")
    best_pos = None

    for m in valid_spaces:
        ideal_x = norm_ref_x - target_w / 2
        ideal_y = norm_ref_y - target_h / 2

        # Clamp to ensure the new rectangle is fully inside the free space
        px = max(m.x, min(ideal_x, m.x + m.width - target_w))
        py = max(m.y, min(ideal_y, m.y + m.height - target_h))

        dist = (px + target_w / 2 - norm_ref_x) ** 2 + (
            py + target_h / 2 - norm_ref_y
        ) ** 2
        if dist < best_dist:
            best_dist = dist
            best_pos = (px, py)

    if best_pos is None:
        return None

    # Denormalize
    return (best_pos[0] + min_x, best_pos[1] + min_y)
