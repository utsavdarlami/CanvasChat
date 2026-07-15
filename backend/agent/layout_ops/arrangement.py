"""Node arrangement and camera-fit helpers."""

import math
from typing import Any, Dict, Optional

from loguru import logger
from rectpack.geometry import Rectangle
from rectpack.maxrects import MaxRectsBssf

from .constants import (
    CAMERA_FIT_MARGIN,
    DEFAULT_NODE_GAP,
    MAX_CAMERA_ZOOM,
    MIN_CAMERA_ZOOM,
)
from .dimensions import _parse_positive_float, get_entity_dimension

# When the tallest node is this many times taller than the shortest,
# switch from row-based flow-wrap to MaxRects bin packing for tighter layouts.
_MAXRECTS_HEIGHT_VARIANCE_THRESHOLD = 2.5


def _aspect_aware_cols(
    count: int,
    avail_w: float = 0.0,
    avail_h: float = 0.0,
    node_w: float = 0.0,
    node_h: float = 0.0,
) -> int:
    """Compute grid column count that matches layout shape to available space.

    Instead of ``ceil(sqrt(n))`` (which always produces square-ish grids),
    this considers the aspect ratio of the available area and the node
    dimensions so the resulting grid fills wide/landscape displays better.

    Falls back to ``ceil(sqrt(n))`` when dimensions are missing or invalid.
    """
    if count <= 0:
        return 1

    # Fall back to square grid when we don't have usable dimensions
    if avail_w <= 0 or avail_h <= 0 or node_w <= 0 or node_h <= 0:
        return math.ceil(math.sqrt(count))

    # Ideal cols so grid aspect ≈ space aspect:
    #   grid_w / grid_h ≈ avail_w / avail_h
    #   (cols * node_w) / (rows * node_h) ≈ avail_w / avail_h
    #   cols² / n ≈ (avail_w / avail_h) * (node_h / node_w)
    space_aspect = avail_w / avail_h
    node_aspect = node_w / node_h
    ideal_cols = math.sqrt(count * space_aspect / node_aspect)
    cols = max(1, min(count, round(ideal_cols)))
    return cols


def get_node_sizes_if_available(
    layout: Dict[str, Any],
    entity_ids: list[str],
) -> Optional[list[tuple[float, float]]]:
    """
    Build per-node (width, height) list for arrangement.

    Returns None when any requested entity is missing explicit width/height.
    This preserves legacy behavior for clients that do not send dimensions.
    """
    sizes: list[tuple[float, float]] = []
    for entity_id in entity_ids:
        width = get_entity_dimension(layout, entity_id, "width")
        height = get_entity_dimension(layout, entity_id, "height")
        if width is None or height is None:
            return None
        sizes.append((width, height))
    return sizes


def compute_arrangement_positions(
    bounds: tuple[float, float, float, float],
    count: int,
    arrangement: str,
    padding: float = 0.1,
    node_sizes: Optional[list[tuple[float, float]]] = None,
    gap: float = DEFAULT_NODE_GAP,
    align: str = "center",
    preserve_order: bool = False,
) -> list[tuple[float, float]]:
    """
    Compute evenly-spaced positions within display bounds for a given arrangement.

    Args:
        bounds: (min_x, min_y, max_x, max_y) of the target area
        count: Number of positions to generate
        arrangement: "horizontal", "vertical", or "grid"
        padding: Fraction of edge padding (default 0.1 = 10%)
        node_sizes: Optional per-node (width, height) tuples in display order.
        gap: Minimum spacing between neighboring nodes.
        align: Cross-axis alignment. For vertical arrangements use "left",
            "right", or "center" (default). For horizontal arrangements use
            "top", "bottom", or "center". Grid supports all four directions.
        preserve_order: Whether to preserve original node order vs dense pack (grid)

    Returns:
        List of (x, y) positions
    """
    logger.info(
        f"CALLED: compute_arrangement_positions(bounds={bounds}, count={count}, arrangement='{arrangement}', padding={padding}, node_sizes={node_sizes}, gap={gap}, align='{align}', preserve_order={preserve_order})"
    )
    if count <= 0:
        return []

    if node_sizes and len(node_sizes) == count:
        return _compute_dimension_aware_positions(
            bounds=bounds,
            arrangement=arrangement,
            node_sizes=node_sizes,
            padding=padding,
            gap=gap,
            align=align,
            preserve_order=preserve_order,
        )

    return _compute_evenly_spaced_positions(
        bounds, count, arrangement, padding, align=align
    )


def _compute_evenly_spaced_positions(
    bounds: tuple[float, float, float, float],
    count: int,
    arrangement: str,
    padding: float,
    *,
    align: str = "center",
) -> list[tuple[float, float]]:
    """Legacy even-spacing fallback used when node dimensions are unknown."""
    logger.info("CALLED: _compute_evenly_spaced_positions (fallback layout)")
    min_x, min_y, max_x, max_y = bounds
    w = max_x - min_x
    h = max_y - min_y

    positions = []
    if arrangement == "horizontal":
        if align == "top":
            cy = min_y + h * padding
        elif align == "bottom":
            cy = min_y + h * (1.0 - padding)
        else:
            cy = min_y + h * 0.5
        for i in range(count):
            px = min_x + w * (padding + (1 - 2 * padding) * i / max(count - 1, 1))
            positions.append((px, cy))
    elif arrangement == "vertical":
        if align == "left":
            cx = min_x + w * padding
        elif align == "right":
            cx = min_x + w * (1.0 - padding)
        else:
            cx = min_x + w * 0.5
        for i in range(count):
            py = min_y + h * (padding + (1 - 2 * padding) * i / max(count - 1, 1))
            positions.append((cx, py))
    else:
        avail_w = w * (1 - 2 * padding)
        avail_h = h * (1 - 2 * padding)
        # Use a default node size estimate for the legacy path (no node_sizes)
        cols = _aspect_aware_cols(count, avail_w, avail_h, 400.0, 300.0)
        rows = math.ceil(count / cols)
        for i in range(count):
            row = i // cols
            col = i % cols
            px = min_x + w * (padding + (1 - 2 * padding) * col / max(cols - 1, 1))
            py = min_y + h * (padding + (1 - 2 * padding) * row / max(rows - 1, 1))
            positions.append((px, py))
    return positions


def _flow_wrap_grid(
    node_sizes: list[tuple[float, float]],
    avail_w: float,
    avail_h: float,
    gap: float,
    preserve_order: bool = False,
    force_cols: Optional[int] = None,
) -> list[tuple[float, float]]:
    """Flow-wrap nodes into a grid with clean, aligned rows.

    When *preserve_order* is False, nodes are sorted by height descending
    so that similarly-sized nodes share rows, producing even row heights
    and a visually clean layout.

    When *force_cols* is set, uses that exact column count and skips
    aspect-aware computation.  Use to force a single row (cols=count)
    or single column (cols=1) regardless of available width.

    Returns positions relative to (0, 0) in the same order as *node_sizes*.
    """
    count = len(node_sizes)
    if count == 0:
        return []

    # Build sort order: preserve original or sort by height descending
    sort_indices = list(range(count))
    if not preserve_order:
        sort_indices.sort(key=lambda i: node_sizes[i][1], reverse=True)

    sorted_widths = [max(node_sizes[i][0], 1.0) for i in sort_indices]
    sorted_heights = [max(node_sizes[i][1], 1.0) for i in sort_indices]

    if force_cols is not None and force_cols > 0:
        cols = max(1, min(count, force_cols))
    else:
        max_node_w = max(sorted_widths)
        max_node_h = max(sorted_heights)
        cols = _aspect_aware_cols(count, avail_w, avail_h, max_node_w, max_node_h)

    sorted_packed: list[tuple[float, float]] = []
    x_cursor = 0.0
    y_cursor = 0.0
    current_row_h = 0.0

    for i in range(count):
        if i > 0 and i % cols == 0:
            x_cursor = 0.0
            y_cursor += current_row_h + gap
            current_row_h = 0.0

        sorted_packed.append((x_cursor, y_cursor))
        x_cursor += sorted_widths[i] + gap
        current_row_h = max(current_row_h, sorted_heights[i])

    # Map back to original order
    packed: list[tuple[float, float] | None] = [None] * count
    for sorted_idx, orig_idx in enumerate(sort_indices):
        packed[orig_idx] = sorted_packed[sorted_idx]

    return packed  # type: ignore[return-value]


def _should_use_maxrects(node_sizes: list[tuple[float, float]]) -> bool:
    """Whether height variance warrants MaxRects over row-based packing."""
    if len(node_sizes) < 3:
        return False
    heights = [max(s[1], 1.0) for s in node_sizes]
    return max(heights) / min(heights) > _MAXRECTS_HEIGHT_VARIANCE_THRESHOLD


def _maxrects_grid(
    node_sizes: list[tuple[float, float]],
    avail_w: float,
    gap: float,
) -> list[tuple[float, float]]:
    """Pack variable-height nodes using MaxRects BSSF bin packing.

    Unlike ``_flow_wrap_grid`` which uses fixed-height rows (wasting space
    when a tall node inflates the entire row), this fills empty pockets
    next to tall nodes with shorter ones.

    Returns positions relative to (0, 0) in the same order as *node_sizes*.
    """
    count = len(node_sizes)
    if count == 0:
        return []

    widths = [max(s[0], 1.0) for s in node_sizes]
    heights = [max(s[1], 1.0) for s in node_sizes]

    # Sort by height descending — tall items first leaves pockets for short ones.
    sort_indices = sorted(range(count), key=lambda i: heights[i], reverse=True)

    padded_w = [widths[i] + gap for i in sort_indices]
    padded_h = [heights[i] + gap for i in sort_indices]

    # Estimate bin height generously: total area / width × safety margin.
    total_area = sum(pw * ph for pw, ph in zip(padded_w, padded_h))
    bin_h = max(total_area / max(avail_w, 1.0) * 2.0, max(padded_h))

    algo = MaxRectsBssf(avail_w, bin_h, rot=False)

    sorted_packed: list[tuple[float, float]] = []
    for i in range(count):
        pw, ph = padded_w[i], padded_h[i]

        # Find best free rect (Best Short Side Fit).
        best_rect: Rectangle | None = None
        best_score = float("inf")
        for m in algo._max_rects:
            if pw <= m.width and ph <= m.height:
                score = min(m.width - pw, m.height - ph)
                if score < best_score:
                    best_score = score
                    best_rect = m

        if best_rect is not None:
            pos = (best_rect.x, best_rect.y)
            placed = Rectangle(best_rect.x, best_rect.y, pw, ph)
            algo._split(placed)
            algo._remove_duplicates()
        else:
            # Overflow fallback — extend below current content.
            pos = (0.0, bin_h)
            bin_h += ph

        sorted_packed.append(pos)

    # Map back to original order.
    packed: list[tuple[float, float] | None] = [None] * count
    for sorted_idx, orig_idx in enumerate(sort_indices):
        packed[orig_idx] = sorted_packed[sorted_idx]

    return packed  # type: ignore[return-value]


def _pack_grid(
    node_sizes: list[tuple[float, float]],
    avail_w: float,
    avail_h: float,
    gap: float,
    preserve_order: bool = False,
    force_cols: Optional[int] = None,
) -> list[tuple[float, float]]:
    """Pack nodes in a grid, choosing the best algorithm automatically.

    Uses MaxRects bin packing when node heights vary significantly
    (tallest / shortest > 2.5×), producing tighter layouts by filling
    pockets next to tall nodes.  Falls back to row-based flow-wrap for
    uniform heights or when reading order must be preserved.

    When *force_cols* is set, always uses row-based flow-wrap with the
    exact column count (MaxRects is skipped because it ignores columns).
    """
    if force_cols is not None:
        return _flow_wrap_grid(
            node_sizes, avail_w, avail_h, gap, preserve_order, force_cols,
        )
    if not preserve_order and _should_use_maxrects(node_sizes):
        return _maxrects_grid(node_sizes, avail_w, gap)
    return _flow_wrap_grid(node_sizes, avail_w, avail_h, gap, preserve_order)


def _compute_dimension_aware_positions(
    bounds: tuple[float, float, float, float],
    arrangement: str,
    node_sizes: list[tuple[float, float]],
    padding: float,
    gap: float,
    align: str = "center",
    preserve_order: bool = False,
) -> list[tuple[float, float]]:
    """Dimension-aware node placement that preserves requested order."""
    logger.info(
        f"CALLED: _compute_dimension_aware_positions(bounds={bounds}, arrangement='{arrangement}', node_sizes={node_sizes}, padding={padding}, gap={gap}, align='{align}', preserve_order={preserve_order})"
    )
    min_x, min_y, max_x, max_y = bounds
    w = max_x - min_x
    h = max_y - min_y

    content_min_x = min_x + (w * padding)
    content_max_x = max_x - (w * padding)
    content_min_y = min_y + (h * padding)
    content_max_y = max_y - (h * padding)
    avail_w = max(content_max_x - content_min_x, 0.0)
    avail_h = max(content_max_y - content_min_y, 0.0)

    widths = [max(size[0], 1.0) for size in node_sizes]
    heights = [max(size[1], 1.0) for size in node_sizes]
    count = len(node_sizes)

    if arrangement == "horizontal":
        total_w = sum(widths) + gap * max(count - 1, 0)
        row_h = max(heights)

        start_x = content_min_x + max((avail_w - total_w) * 0.5, 0.0)
        if align == "top":
            y = content_min_y
        elif align == "bottom":
            y = content_max_y - row_h
        else:
            y = content_min_y + max((avail_h - row_h) * 0.5, 0.0)

        positions = []
        x_cursor = start_x
        for item_w in widths:
            positions.append((x_cursor, y))
            x_cursor += item_w + gap
        return positions

    if arrangement == "vertical":
        col_w = max(widths)
        total_h = sum(heights) + gap * max(count - 1, 0)

        if align == "left":
            x = content_min_x
        elif align == "right":
            x = content_max_x - col_w
        else:
            x = content_min_x + max((avail_w - col_w) * 0.5, 0.0)
        start_y = content_min_y + max((avail_h - total_h) * 0.5, 0.0)

        positions = []
        y_cursor = start_y
        for item_h in heights:
            positions.append((x, y_cursor))
            y_cursor += item_h + gap
        return positions

    # Grid arrangement — MaxRects when heights vary, flow-wrap otherwise
    packed = _pack_grid(node_sizes, avail_w, avail_h, gap, preserve_order)

    # Bounding box of packed result (visual extent, not gap-padded)
    pack_w = max(packed[i][0] + widths[i] for i in range(count))
    pack_h = max(packed[i][1] + heights[i] for i in range(count))

    # Apply alignment (same pattern as horizontal/vertical)
    if align == "left":
        offset_x = content_min_x
    elif align == "right":
        offset_x = content_max_x - pack_w
    else:
        offset_x = content_min_x + max((avail_w - pack_w) * 0.5, 0.0)

    if align == "top":
        offset_y = content_min_y
    elif align == "bottom":
        offset_y = content_max_y - pack_h
    else:
        offset_y = content_min_y + max((avail_h - pack_h) * 0.5, 0.0)

    return [(offset_x + px, offset_y + py) for px, py in packed]


def compute_arrangement_info(
    bounds: tuple[float, float, float, float],
    count: int,
    arrangement: str,
    padding: float = 0.1,
    node_sizes: Optional[list[tuple[float, float]]] = None,
    gap: float = DEFAULT_NODE_GAP,
    preserve_order: bool = False,
) -> Dict[str, Any]:
    """Compute metadata about how an arrangement will lay out without placing.

    Returns a dict with arrangement details and any degradation warnings.
    """
    info: Dict[str, Any] = {
        "arrangement": arrangement,
        "count": count,
        "warnings": [],
    }

    if count <= 0:
        return info

    min_x, min_y, max_x, max_y = bounds
    w = max_x - min_x
    h = max_y - min_y
    avail_w = max(w * (1 - 2 * padding), 0.0)
    avail_h = max(h * (1 - 2 * padding), 0.0)

    info["available_area"] = {"width": round(avail_w, 1), "height": round(avail_h, 1)}

    if not node_sizes or len(node_sizes) != count:
        # Can't compute detailed info without dimensions
        if arrangement == "grid":
            cols = _aspect_aware_cols(count, avail_w, avail_h, 400.0, 300.0)
            rows = math.ceil(count / cols)
            info["cols"] = cols
            info["rows"] = rows
        return info

    if arrangement == "grid":
        packed = _pack_grid(node_sizes, avail_w, avail_h, gap, preserve_order)

        if packed and len(packed) == count:
            widths = [max(s[0], 1.0) for s in node_sizes]
            heights = [max(s[1], 1.0) for s in node_sizes]
            pack_w = max(packed[i][0] + widths[i] for i in range(count))
            pack_h = max(packed[i][1] + heights[i] for i in range(count))
            total_item_area = sum(w * h for w, h in zip(widths, heights))
            pack_area = pack_w * pack_h

            info["packed_width"] = round(pack_w, 1)
            info["packed_height"] = round(pack_h, 1)
            if pack_area > 0:
                info["packing_efficiency"] = round(total_item_area / pack_area, 3)

            if pack_w > avail_w or pack_h > avail_h:
                info["warnings"].append(
                    f"Packed content ({pack_w:.0f}×{pack_h:.0f}px) exceeds "
                    f"available area ({avail_w:.0f}×{avail_h:.0f}px) — "
                    f"entities will overflow. "
                    f"Camera will auto-fit to show all content."
                )

    elif arrangement == "horizontal":
        total_w = sum(s[0] for s in node_sizes) + gap * max(count - 1, 0)
        if total_w > avail_w:
            info["warnings"].append(
                f"Horizontal row width ({total_w:.0f}px) exceeds available width "
                f"({avail_w:.0f}px) — entities will overflow."
            )

    elif arrangement == "vertical":
        total_h = sum(s[1] for s in node_sizes) + gap * max(count - 1, 0)
        if total_h > avail_h:
            info["warnings"].append(
                f"Vertical stack height ({total_h:.0f}px) exceeds available height "
                f"({avail_h:.0f}px) — entities will overflow."
            )

    # Aspect mismatch warning — flag when layout shape differs greatly
    # from the available space shape (e.g. tall-narrow layout on wide display).
    layout_w = info.get("packed_width", 0)
    layout_h = info.get("packed_height", 0)
    if layout_w > 0 and layout_h > 0 and avail_w > 0 and avail_h > 0:
        layout_aspect = layout_w / layout_h
        space_aspect = avail_w / avail_h
        ratio = max(layout_aspect, space_aspect) / max(
            min(layout_aspect, space_aspect), 0.01
        )
        if ratio > 2.0:
            info["warnings"].append(
                f"Layout shape ({layout_w:.0f}×{layout_h:.0f}px, "
                f"aspect {layout_aspect:.1f}:1) poorly matches available space "
                f"({avail_w:.0f}×{avail_h:.0f}px, aspect {space_aspect:.1f}:1). "
                f"Consider using {'more columns' if layout_h > layout_w else 'more rows'} "
                f"or a different arrangement to fill the display better."
            )

    return info


def fit_display_camera_to_entities_if_needed(
    layout: Dict[str, Any],
    surface_id: str,
    entity_ids: list[str],
    region: Optional[str] = None,
    force: bool = False,
) -> Optional[Dict[str, float]]:
    """
    Adjust a display camera to fit the provided entities when they overflow the visible viewport.

    When *region* is provided, the camera pans so that content appears in that
    region of the physical screen instead of dead-center.

    The zoom level is computed from **all** entities on the display (not just the
    ones being arranged) so that existing content is never pushed off-screen.

    When *force* is True, always reframe the camera regardless of whether
    content already fits.  Use this after major reorganizations (e.g.
    ``tool_plan_semantic_layout``) where the user should always see the
    full result.

    Returns the updated camera dict when a change was applied; otherwise None.
    """
    if not entity_ids:
        return None

    display = next(
        (d for d in layout.get("displays", []) if d.get("peer_id") == surface_id),
        None,
    )
    if display is None:
        return None

    arranged_bounds = compute_entities_bounds(layout, entity_ids)
    if arranged_bounds is None:
        return None

    # Zoom must cover ALL entities on this display so nothing gets pushed off-screen.
    all_entity_ids = layout.get("surface_assignments", {}).get(surface_id, [])

    # When the arranged entities ARE the only content on the display (first
    # placement), always reframe — the existing camera is likely stale /
    # zoomed to an arbitrary area.  Otherwise, skip when content already fits.
    # When force=True, always reframe (used after plan_semantic_layout).
    is_first_placement = set(all_entity_ids) == set(entity_ids)
    if not force and not is_first_placement:
        visible_bounds = get_display_visible_bounds(display)
        if visible_bounds and _bounds_contained(
            inner=arranged_bounds, outer=visible_bounds
        ):
            return None
    if all_entity_ids:
        all_bounds = compute_entities_bounds(layout, all_entity_ids)
    else:
        all_bounds = None
    zoom_bounds = all_bounds or arranged_bounds

    target_camera = compute_fit_camera(
        display, zoom_bounds, region=region, anchor_bounds=arranged_bounds
    )
    if target_camera is None:
        return None

    display["camera"] = target_camera

    # Recompute visible_canvas so subsequent calls to
    # get_display_visible_bounds use the updated camera, not stale data.
    screen_w = _parse_positive_float(display.get("width"))
    screen_h = _parse_positive_float(display.get("height"))
    if screen_w is not None and screen_h is not None:
        z = target_camera["zoom"]
        px, py = target_camera["pan_x"], target_camera["pan_y"]
        vc_min_x = -px / z
        vc_min_y = -py / z
        vc_max_x = (screen_w - px) / z
        vc_max_y = (screen_h - py) / z
        display["visible_canvas"] = {
            "min_x": vc_min_x,
            "min_y": vc_min_y,
            "max_x": vc_max_x,
            "max_y": vc_max_y,
            "width": vc_max_x - vc_min_x,
            "height": vc_max_y - vc_min_y,
        }

    return target_camera


def compute_entities_bounds(
    layout: Dict[str, Any],
    entity_ids: list[str],
) -> Optional[tuple[float, float, float, float]]:
    """Compute content bounds for a set of entities using stored width/height."""
    node_positions = layout.get("node_positions", {})

    min_x: Optional[float] = None
    min_y: Optional[float] = None
    max_x: Optional[float] = None
    max_y: Optional[float] = None

    for entity_id in entity_ids:
        pos = node_positions.get(entity_id)
        if not isinstance(pos, (list, tuple)) or len(pos) != 2:
            continue

        x, y = float(pos[0]), float(pos[1])
        width = get_entity_dimension(layout, entity_id, "width") or 0.0
        height = get_entity_dimension(layout, entity_id, "height") or 0.0

        left = x
        top = y
        right = x + width
        bottom = y + height

        min_x = left if min_x is None else min(min_x, left)
        min_y = top if min_y is None else min(min_y, top)
        max_x = right if max_x is None else max(max_x, right)
        max_y = bottom if max_y is None else max(max_y, bottom)

    if min_x is None or min_y is None or max_x is None or max_y is None:
        return None

    return (min_x, min_y, max_x, max_y)


def get_display_visible_bounds(
    display: Dict[str, Any],
) -> Optional[tuple[float, float, float, float]]:
    """
    Resolve current visible canvas bounds for a display.

    Prefers explicit `visible_canvas`, falling back to camera + screen dimensions.
    """
    visible = display.get("visible_canvas")
    if isinstance(visible, dict):
        min_x = float(visible.get("min_x", 0.0))
        min_y = float(visible.get("min_y", 0.0))
        max_x = float(visible.get("max_x", min_x + visible.get("width", 0.0)))
        max_y = float(visible.get("max_y", min_y + visible.get("height", 0.0)))
        return (min_x, min_y, max_x, max_y)

    camera = display.get("camera") or {}
    zoom = _parse_positive_float(camera.get("zoom")) or 1.0
    pan_x = float(camera.get("pan_x", 0.0))
    pan_y = float(camera.get("pan_y", 0.0))
    screen_w = _parse_positive_float(display.get("width"))
    screen_h = _parse_positive_float(display.get("height"))
    if screen_w is None or screen_h is None:
        return None

    min_x = (0.0 - pan_x) / zoom
    min_y = (0.0 - pan_y) / zoom
    max_x = (screen_w - pan_x) / zoom
    max_y = (screen_h - pan_y) / zoom
    return (min_x, min_y, max_x, max_y)


def _bounds_contained(
    inner: tuple[float, float, float, float],
    outer: tuple[float, float, float, float],
) -> bool:
    """Return True when the inner bounds are fully inside the outer bounds."""
    return (
        inner[0] >= outer[0]
        and inner[1] >= outer[1]
        and inner[2] <= outer[2]
        and inner[3] <= outer[3]
    )


def compute_fit_camera(
    display: Dict[str, Any],
    content_bounds: tuple[float, float, float, float],
    region: Optional[str] = None,
    anchor_bounds: Optional[tuple[float, float, float, float]] = None,
) -> Optional[Dict[str, float]]:
    """Compute pan/zoom values to fit content bounds within display screen pixels.

    *content_bounds* drives the **zoom** — everything inside must be visible.

    When *region* is given, the camera pans so that the *anchor_bounds* (the
    entities that were just arranged) appear in that region of the physical
    viewport.  If *anchor_bounds* is ``None`` it falls back to *content_bounds*.

    When *region* is ``None`` or ``"center"`` the camera simply centers on
    *content_bounds* (original behaviour).
    """
    screen_w = _parse_positive_float(display.get("width"))
    screen_h = _parse_positive_float(display.get("height"))
    if screen_w is None or screen_h is None:
        return None

    min_x, min_y, max_x, max_y = content_bounds
    content_w = max((max_x - min_x) + (CAMERA_FIT_MARGIN * 2), 1.0)
    content_h = max((max_y - min_y) + (CAMERA_FIT_MARGIN * 2), 1.0)

    fit_zoom = min(screen_w / content_w, screen_h / content_h)
    fit_zoom = max(MIN_CAMERA_ZOOM, min(MAX_CAMERA_ZOOM, fit_zoom))

    # Use anchor_bounds (the just-arranged entities) for region panning,
    # falling back to the full content_bounds when not provided.
    a_min_x, a_min_y, a_max_x, a_max_y = anchor_bounds or content_bounds

    # --- Region-aware panning ---
    h_region = _extract_h_region(region)
    if h_region == "left":
        # Anchor arranged content's left edge to the left edge of the screen
        pan_x = CAMERA_FIT_MARGIN - (a_min_x * fit_zoom)
    elif h_region == "right":
        # Anchor arranged content's right edge to the right edge of the screen
        pan_x = screen_w - ((a_max_x + CAMERA_FIT_MARGIN) * fit_zoom)
    else:
        center_x = (min_x + max_x) * 0.5
        pan_x = (screen_w * 0.5) - (center_x * fit_zoom)

    v_region = _extract_v_region(region)
    if v_region == "top":
        pan_y = CAMERA_FIT_MARGIN - (a_min_y * fit_zoom)
    elif v_region == "bottom":
        pan_y = screen_h - ((a_max_y + CAMERA_FIT_MARGIN) * fit_zoom)
    else:
        center_y = (min_y + max_y) * 0.5
        pan_y = (screen_h * 0.5) - (center_y * fit_zoom)

    # --- Clamp: ensure all content remains visible ---
    # After region-biased panning, check that the full content_bounds
    # hasn't been pushed outside the viewport and correct if needed.
    visible_min_x = -pan_x / fit_zoom
    visible_max_x = (screen_w - pan_x) / fit_zoom
    visible_min_y = -pan_y / fit_zoom
    visible_max_y = (screen_h - pan_y) / fit_zoom

    margin_canvas = CAMERA_FIT_MARGIN
    if min_x - margin_canvas < visible_min_x:
        pan_x = -(min_x - margin_canvas) * fit_zoom
    elif max_x + margin_canvas > visible_max_x:
        pan_x = screen_w - (max_x + margin_canvas) * fit_zoom

    if min_y - margin_canvas < visible_min_y:
        pan_y = -(min_y - margin_canvas) * fit_zoom
    elif max_y + margin_canvas > visible_max_y:
        pan_y = screen_h - (max_y + margin_canvas) * fit_zoom

    return {"pan_x": pan_x, "pan_y": pan_y, "zoom": fit_zoom}


def _extract_h_region(region: Optional[str]) -> Optional[str]:
    """Extract horizontal component from a region name."""
    if not region:
        return None
    r = region.lower()
    if r in ("left", "top-left", "bottom-left"):
        return "left"
    if r in ("right", "top-right", "bottom-right"):
        return "right"
    return None


def _extract_v_region(region: Optional[str]) -> Optional[str]:
    """Extract vertical component from a region name."""
    if not region:
        return None
    r = region.lower()
    if r in ("top", "top-left", "top-right"):
        return "top"
    if r in ("bottom", "bottom-left", "bottom-right"):
        return "bottom"
    return None
