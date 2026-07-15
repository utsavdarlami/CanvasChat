"""Before-model callbacks for the layout agent."""

import hashlib
import json
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from loguru import logger

from .layout_ops.dimensions import get_entity_dimension
from .layout_ops.display_profile import _compute_adjacency
from .layout_ops.snapshot import _build_display_labels

# ---------------------------------------------------------------------------
# Constants for viewport analysis
# ---------------------------------------------------------------------------

# Screen-space pixel thresholds for readability judgement
_READABLE_MIN_W = 350  # full content legible
_SCANNABLE_MIN_W = 200  # titles/headings readable, body small
# Below _SCANNABLE_MIN_W → "too small" (thumbnail only)

# Default entity dimensions when not measured
_DEFAULT_ENTITY_W = 400
_DEFAULT_ENTITY_H = 300

# Gap budget per entity for capacity estimates (px in flow coords)
_GAP_BUDGET = 50


def _estimate_readability_for_display(
    display: Dict[str, Any],
    entity_count: int,
    avg_node_w: float = _DEFAULT_ENTITY_W,
    avg_node_h: float = _DEFAULT_ENTITY_H,
) -> Optional[Dict[str, Any]]:
    """Estimate zoom-to-fit readability if *entity_count* nodes were on *display*.

    Uses aspect-aware grid estimation to predict the content bounds, then
    computes the zoom level needed to fit everything and the resulting
    screen-space entity size.

    Returns ``None`` when display dimensions are missing, otherwise a dict::

        {
            "zoom": float,
            "screen_entity_w": float,
            "readability": "readable" | "scannable" | "too small to read",
        }
    """
    screen_w = display.get("width") or 0
    screen_h = display.get("height") or 0
    if screen_w <= 0 or screen_h <= 0 or entity_count <= 0:
        return None

    gap = 40  # same default used by arrangement helpers
    # Aspect-aware column count (mirrors _aspect_aware_cols logic)
    space_aspect = screen_w / screen_h
    node_aspect = avg_node_w / avg_node_h if avg_node_h > 0 else 1.0
    ideal_cols = math.sqrt(entity_count * space_aspect / node_aspect)
    cols = max(1, min(entity_count, round(ideal_cols)))
    rows = math.ceil(entity_count / cols)

    content_w = cols * avg_node_w + (cols - 1) * gap
    content_h = rows * avg_node_h + (rows - 1) * gap
    # 90% margin (same as zoom-to-fit in _compute_viewport_analysis)
    fit_zoom = min(screen_w / content_w, screen_h / content_h) * 0.9
    fit_zoom = max(0.05, min(fit_zoom, 4.0))

    screen_entity_w = avg_node_w * fit_zoom

    if screen_entity_w >= _READABLE_MIN_W:
        readability = "readable"
    elif screen_entity_w >= _SCANNABLE_MIN_W:
        readability = "scannable"
    else:
        readability = "too small to read"

    return {
        "zoom": fit_zoom,
        "screen_entity_w": screen_entity_w,
        "readability": readability,
    }


def _layout_fingerprint(layout: Dict[str, Any]) -> str:
    """Quick hash of position-relevant layout data for change detection."""
    positions = layout.get("node_positions", {})
    assignments = layout.get("surface_assignments", {})
    tags = layout.get("entity_tags", {})
    return hashlib.md5(
        json.dumps({"p": positions, "a": assignments, "t": tags}, sort_keys=True).encode()
    ).hexdigest()


async def inject_layout_context(
    callback_context: CallbackContext,
    llm_request: LlmRequest,
) -> Optional[LlmResponse]:
    """Inject spatial layout context before every LLM call.

    Gives the agent full spatial awareness: display geometry, camera state,
    entity positions/dimensions, and arrangement descriptions — so the agent
    can reason about spatial feasibility before calling tools.
    """
    layout = callback_context.state.get("current_layout")
    if not layout:
        return None

    # Track user-message count so tools can snapshot it.
    user_msg_count = sum(
        1 for c in (llm_request.contents or []) if c.role == "user"
    )
    callback_context.state["_user_msg_count"] = user_msg_count

    # Clear the "just created" flag when a new user turn starts so the
    # Active Grouping warning fires on subsequent turns but stays
    # suppressed for continuation LLM calls within the same invocation.
    if callback_context.state.get("_active_grouping_just_created"):
        created_at = callback_context.state.get(
            "_grouping_created_at_user_count", 0
        )
        if user_msg_count > created_at:
            callback_context.state["_active_grouping_just_created"] = False
            callback_context.state["_grouping_created_at_user_count"] = 0

    # Track whether layout changed since last injection
    layout_key = _layout_fingerprint(layout)
    last_key = callback_context.state.get("_last_layout_fingerprint")
    layout_changed = layout_key != last_key
    if layout_changed:
        callback_context.state["_last_layout_fingerprint"] = layout_key

    summary = _build_compact_context(layout, callback_context.state)
    current = llm_request.config.system_instruction or ""
    logger.info(f"Instruction size: {len(current)} chars")
    if summary:
        llm_request.append_instructions([summary])
        change_status = "changed" if layout_changed else "unchanged"
        logger.info(
            f"Injected layout context ({len(summary)} chars, layout {change_status})"
        )

    # When an active grouping exists, prepend a note to the last user message
    # so the agent sees it right next to the user's request and can't miss it.
    _inject_grouping_user_note(callback_context.state, llm_request)

    logger.info(f"Total instruction size: {len(llm_request.config.system_instruction)} chars")
    return None


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------


def _build_compact_context(
    layout: Dict[str, Any],
    state: Any,
) -> Optional[str]:
    """Build a spatial-awareness summary for the LLM.

    Includes per-display: geometry, camera, visible canvas, entity positions
    and dimensions — everything the agent needs to reason about layout
    feasibility before calling tools.
    """
    surface_assignments = layout.get("surface_assignments", {})
    if not surface_assignments:
        return None

    entity_names = layout.get("entity_names", {})
    entity_tags = layout.get("entity_tags", {})
    display_labels = _build_display_labels(layout)
    sentiment_lookup = _build_sentiment_lookup(state.get("entities"))
    displays_by_id = _index_displays(layout)

    layout_section = _build_spatial_layout_section(
        layout,
        surface_assignments,
        entity_names,
        entity_tags,
        display_labels,
        sentiment_lookup,
        displays_by_id,
    )
    active_tags_section = _build_active_tags_lines(entity_tags)
    user_highlights_section = _build_user_highlights_lines(
        layout.get("user_text_highlights", {}), entity_names
    )

    active_grouping_section = _build_active_grouping_lines(state)

    # Put active grouping FIRST so the agent sees it before the spatial data
    return (
        f"{active_grouping_section}\n{layout_section}\n{active_tags_section}\n"
        f"{user_highlights_section}"
    ).strip()


# ---------------------------------------------------------------------------
# Display indexing
# ---------------------------------------------------------------------------


def _index_displays(layout: Dict[str, Any]) -> Dict[str, Dict]:
    """Build peer_id → display info lookup."""
    return {d["peer_id"]: d for d in layout.get("displays", []) if "peer_id" in d}


# ---------------------------------------------------------------------------
# Display header with geometry
# ---------------------------------------------------------------------------


def _format_display_header(
    surface_id: str,
    label: str,
    display: Optional[Dict],
    entity_count: int,
    surface_bounds: Optional[Tuple],
    all_displays: Optional[List[Dict]] = None,
    display_labels: Optional[Dict[str, str]] = None,
) -> List[str]:
    """Format display header lines with geometry, camera, and canvas info."""
    tags = display.get("tags", []) if display else []
    tag_str = f" [{', '.join(tags)}]" if tags else ""
    lines = [f"\n{label} display ({surface_id}){tag_str}: {entity_count} entities"]

    if not display:
        return lines

    # Screen dimensions
    screen_w = display.get("width")
    screen_h = display.get("height")
    if screen_w and screen_h:
        lines.append(f"  Screen: {screen_w:.0f}×{screen_h:.0f}px")

    # Physical adjacency derived from virtual-desktop coordinates.
    # This is tag-independent: it reflects where the displays actually sit
    # relative to each other, so the agent can reason about continuation
    # and overflow even when the user hasn't tagged displays.
    if all_displays:
        adjacency = _compute_adjacency(display, all_displays)
        if adjacency:
            parts = []
            for direction in ("left", "right", "above", "below"):
                peer = adjacency.get(direction)
                if not peer:
                    continue
                peer_label = (display_labels or {}).get(peer, peer)
                parts.append(f"{direction}={peer_label}")
            if parts:
                lines.append(f"  Adjacent: {', '.join(parts)}")

    if surface_bounds:
        lines.append(
            "  Workspace: "
            f"({surface_bounds[0]:.0f},{surface_bounds[1]:.0f}) to "
            f"({surface_bounds[2]:.0f},{surface_bounds[3]:.0f})"
        )

    # Camera state
    camera = display.get("camera")
    if camera:
        zoom = camera.get("zoom", 1.0)
        lines[-1] += f" | Zoom: {zoom:.2f}×"

    # Visible canvas — the actual working area the user sees
    vc = display.get("visible_canvas")
    if isinstance(vc, dict):
        vc_w = vc.get("width", 0)
        vc_h = vc.get("height", 0)
        vc_min_x = vc.get("min_x", 0)
        vc_min_y = vc.get("min_y", 0)
        vc_max_x = vc.get("max_x", 0)
        vc_max_y = vc.get("max_y", 0)
        lines.append(
            f"  Visible canvas: ({vc_min_x:.0f},{vc_min_y:.0f}) to "
            f"({vc_max_x:.0f},{vc_max_y:.0f}) — {vc_w:.0f}×{vc_h:.0f} canvas units"
        )

    return lines


# ---------------------------------------------------------------------------
# Entity position lines
# ---------------------------------------------------------------------------


def _format_entity_line(
    layout: Dict[str, Any],
    eid: str,
    entity_names: Dict[str, str],
    entity_tags: Dict[str, List[str]],
    sentiment_lookup: Dict[str, str],
    visible_canvas: Optional[Dict] = None,
) -> str:
    """Format a single entity line with position, dimensions, and visibility."""
    name = entity_names.get(eid, eid)
    sentiment = sentiment_lookup.get(eid)
    tags = entity_tags.get(eid, [])
    tags_str = f" tags:[{','.join(tags)}]" if tags else ""
    sentiment_str = f" ({sentiment})" if sentiment else ""

    # Position
    pos = layout.get("node_positions", {}).get(eid)
    if isinstance(pos, (list, tuple)) and len(pos) == 2:
        pos_str = f" @ ({pos[0]:.0f},{pos[1]:.0f})"
    else:
        pos_str = ""

    # Dimensions
    w = get_entity_dimension(layout, eid, "width") or _DEFAULT_ENTITY_W
    h = get_entity_dimension(layout, eid, "height") or _DEFAULT_ENTITY_H
    dim_str = f" {w:.0f}×{h:.0f}"

    # Visibility status relative to viewport
    vis_str = ""
    if visible_canvas and pos and isinstance(pos, (list, tuple)) and len(pos) == 2:
        vis = _entity_visibility_status(pos, w, h, visible_canvas)
        if vis:
            vis_str = f" {vis}"

    return f'    {eid} "{name}"{sentiment_str}{pos_str}{dim_str}{vis_str}{tags_str}'


# ---------------------------------------------------------------------------
# Spatial arrangement description
# ---------------------------------------------------------------------------


def _describe_arrangement(
    layout: Dict[str, Any],
    entity_ids: List[str],
    display: Optional[Dict],
) -> Optional[str]:
    """Describe the spatial arrangement pattern of entities on a display.

    Returns a brief description like 'arranged in 2×2 grid' or
    'stacked vertically' to help the agent understand the current layout.
    """
    if not entity_ids or len(entity_ids) < 2:
        return None

    positions = []
    for eid in entity_ids:
        pos = layout.get("node_positions", {}).get(eid)
        if isinstance(pos, (list, tuple)) and len(pos) == 2:
            positions.append((float(pos[0]), float(pos[1])))

    if len(positions) < 2:
        return None

    xs = [p[0] for p in positions]
    ys = [p[1] for p in positions]

    # Check for vertical/horizontal/grid patterns
    unique_xs = len(set(round(x, -1) for x in xs))  # Round to nearest 10
    unique_ys = len(set(round(y, -1) for y in ys))

    # Bounding box of the group
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    # Get typical node dimensions for extent calculation
    sample_w = get_entity_dimension(layout, entity_ids[0], "width") or 0
    sample_h = get_entity_dimension(layout, entity_ids[0], "height") or 0
    extent_w = (max_x - min_x) + sample_w
    extent_h = (max_y - min_y) + sample_h

    if unique_xs == 1:
        desc = f"stacked vertically at x≈{xs[0]:.0f}"
    elif unique_ys == 1:
        desc = f"arranged in horizontal row at y≈{ys[0]:.0f}"
    elif unique_xs > 1 and unique_ys > 1:
        desc = f"in {unique_xs}×{unique_ys} grid"
    else:
        desc = "scattered"

    desc += f", occupying {extent_w:.0f}×{extent_h:.0f} canvas area"

    # Check overflow against visible canvas
    if display:
        vc = display.get("visible_canvas")
        if isinstance(vc, dict):
            vc_max_y = vc.get("max_y", float("inf"))
            vc_min_x = vc.get("min_x", float("-inf"))
            vc_max_x = vc.get("max_x", float("inf"))
            if (max_y + sample_h) > vc_max_y:
                desc += " [WARNING] overflows bottom"
            if min_x < vc_min_x:
                desc += " [WARNING] overflows left"
            if (max_x + sample_w) > vc_max_x:
                desc += " [WARNING] overflows right"

    return desc


# ---------------------------------------------------------------------------
# Per-entity visibility status
# ---------------------------------------------------------------------------


def _entity_visibility_status(
    pos: Union[Sequence, None],
    entity_w: float,
    entity_h: float,
    vc: Optional[Dict],
) -> str:
    """Return a visibility tag for one entity relative to the visible canvas.

    Returns one of:
      "[in view]", "[partially visible]", "[off-screen ↓]", "[off-screen ↑]",
      "[off-screen →]", "[off-screen ←]", "[off-screen]", or "".
    """
    if not vc or not pos:
        return ""

    ex, ey = float(pos[0]), float(pos[1])
    vc_min_x = vc.get("min_x", float("-inf"))
    vc_min_y = vc.get("min_y", float("-inf"))
    vc_max_x = vc.get("max_x", float("inf"))
    vc_max_y = vc.get("max_y", float("inf"))

    # Entity bounding box (top-left origin)
    e_right = ex + entity_w
    e_bottom = ey + entity_h

    # Fully outside?
    if e_right < vc_min_x:
        return "[off-screen ←]"
    if ex > vc_max_x:
        return "[off-screen →]"
    if e_bottom < vc_min_y:
        return "[off-screen ↑]"
    if ey > vc_max_y:
        return "[off-screen ↓]"

    # Fully inside?
    if ex >= vc_min_x and e_right <= vc_max_x and ey >= vc_min_y and e_bottom <= vc_max_y:
        return "[in view]"

    return "[partially visible]"


# ---------------------------------------------------------------------------
# Viewport analysis
# ---------------------------------------------------------------------------


def _compute_viewport_analysis(
    layout: Dict[str, Any],
    display: Optional[Dict],
    entity_ids: List[str],
) -> List[str]:
    """Compute interpreted viewport metrics for a display.

    Returns lines like:
      [Viewport Analysis]
      In view: 3 of 5 entities
      Off-screen: entity-3 (below), entity-4 (below)
      Screen-space entity size: ~300×225 px (scannable)
      Density: 58% of viewport covered
      Capacity: fits ~4 comfortably at current zoom, has 5 (near limit)
      Free space: 360px right, 560px bottom
    """
    if not display or not entity_ids:
        return []

    vc = display.get("visible_canvas")
    if not isinstance(vc, dict):
        return []

    zoom = 1.0
    camera = display.get("camera")
    if camera:
        zoom = camera.get("zoom", 1.0) or 1.0

    screen_w = display.get("width") or 0
    screen_h = display.get("height") or 0
    vc_w = vc.get("width", 0)
    vc_h = vc.get("height", 0)

    if vc_w <= 0 or vc_h <= 0:
        return []

    lines = ["  [Viewport Analysis]"]

    # --- Gather per-entity data ---
    entity_areas = []
    in_view_ids = []
    off_screen_entries = []  # (eid, direction_label)
    widths = []
    heights = []

    for eid in entity_ids:
        ew = get_entity_dimension(layout, eid, "width") or _DEFAULT_ENTITY_W
        eh = get_entity_dimension(layout, eid, "height") or _DEFAULT_ENTITY_H
        widths.append(ew)
        heights.append(eh)
        entity_areas.append(ew * eh)

        pos = layout.get("node_positions", {}).get(eid)
        vis = _entity_visibility_status(pos, ew, eh, vc)
        if vis == "[in view]" or vis == "[partially visible]":
            in_view_ids.append(eid)
        elif vis:
            # Extract direction arrow for summary
            direction = vis.replace("[off-screen", "").replace("]", "").strip()
            off_screen_entries.append((eid, direction))

    n = len(entity_ids)

    # --- Visibility summary ---
    lines.append(f"  In view: {len(in_view_ids)} of {n} entities")
    if off_screen_entries:
        off_parts = []
        for eid, direction in off_screen_entries[:6]:  # cap at 6 to save tokens
            name = layout.get("entity_names", {}).get(eid, eid)
            off_parts.append(f"{name} ({direction})" if direction else name)
        suffix = f", +{len(off_screen_entries) - 6} more" if len(off_screen_entries) > 6 else ""
        lines.append(f"  Off-screen: {', '.join(off_parts)}{suffix}")

    # --- Screen-space size & readability ---
    avg_w = sum(widths) / n if n else _DEFAULT_ENTITY_W
    avg_h = sum(heights) / n if n else _DEFAULT_ENTITY_H
    screen_entity_w = avg_w * zoom
    screen_entity_h = avg_h * zoom

    if screen_entity_w >= _READABLE_MIN_W:
        readability = "readable"
    elif screen_entity_w >= _SCANNABLE_MIN_W:
        readability = "scannable — titles readable, body text small"
    else:
        readability = "too small to read"

    lines.append(
        f"  Screen-space entity size: ~{screen_entity_w:.0f}×{screen_entity_h:.0f} px ({readability})"
    )

    # --- Density ---
    viewport_area = vc_w * vc_h
    total_entity_area = sum(entity_areas)
    coverage = total_entity_area / viewport_area if viewport_area > 0 else 0

    if coverage > 0.7:
        density_label = "crowded"
    elif coverage > 0.4:
        density_label = "moderate"
    elif coverage > 0.15:
        density_label = "comfortable"
    else:
        density_label = "sparse"

    lines.append(f"  Density: {coverage:.0%} of viewport covered ({density_label})")

    # --- Capacity estimate ---
    avg_entity_area = (avg_w + _GAP_BUDGET) * (avg_h + _GAP_BUDGET)
    capacity = int(viewport_area / avg_entity_area) if avg_entity_area > 0 else 0

    if n > capacity:
        cap_note = f"over capacity by {n - capacity}"
    elif n == capacity:
        cap_note = "at limit"
    elif n >= capacity - 1:
        cap_note = "near limit"
    else:
        cap_note = f"room for {capacity - n} more"

    lines.append(f"  Capacity: fits ~{capacity} comfortably at current zoom, has {n} ({cap_note})")

    # --- Content bounds (shared by zoom-to-fit and free space) ---
    content_bounds = _compute_content_bounds(layout, entity_ids)

    # --- Zoom-to-fit-all impact (only when there's overflow or many entities) ---
    if off_screen_entries or n > capacity:
        if content_bounds:
            cb_w = content_bounds[2] - content_bounds[0]
            cb_h = content_bounds[3] - content_bounds[1]
            if screen_w > 0 and screen_h > 0 and cb_w > 0 and cb_h > 0:
                fit_zoom = min(screen_w / cb_w, screen_h / cb_h) * 0.9  # 90% margin
                fit_zoom = max(0.05, min(fit_zoom, 4.0))  # clamp to RF limits
                fit_entity_w = avg_w * fit_zoom
                fit_entity_h = avg_h * fit_zoom
                if fit_entity_w >= _READABLE_MIN_W:
                    fit_readability = "readable"
                elif fit_entity_w >= _SCANNABLE_MIN_W:
                    fit_readability = "scannable"
                else:
                    fit_readability = "too small to read"
                lines.append(
                    f"  If zoom-to-fit-all: zoom → {fit_zoom:.2f}×, "
                    f"entities → {fit_entity_w:.0f}×{fit_entity_h:.0f} screen px ({fit_readability})"
                )

    # --- Free space margins ---
    if content_bounds:
        cb_min_x, cb_min_y, cb_max_x, cb_max_y = content_bounds
        vc_min_x = vc.get("min_x", 0)
        vc_min_y = vc.get("min_y", 0)
        vc_max_x = vc.get("max_x", 0)
        vc_max_y = vc.get("max_y", 0)

        margins = {
            "top": max(0, cb_min_y - vc_min_y),
            "bottom": max(0, vc_max_y - cb_max_y),
            "left": max(0, cb_min_x - vc_min_x),
            "right": max(0, vc_max_x - cb_max_x),
        }

        # Only report margins that are meaningfully large (>100 flow units)
        free_parts = []
        for side, px in sorted(margins.items(), key=lambda x: -x[1]):
            if px > 100:
                free_parts.append(f"{px:.0f}px {side}")
        if free_parts:
            lines.append(f"  Free space: {', '.join(free_parts)}")
        else:
            lines.append("  Free space: minimal — content fills viewport")

        # Content bounds line
        lines.append(
            f"  Content bounds: ({cb_min_x:.0f},{cb_min_y:.0f}) to ({cb_max_x:.0f},{cb_max_y:.0f})"
        )

    # --- User focus center ---
    vc_center_x = (vc.get("min_x", 0) + vc.get("max_x", 0)) / 2
    vc_center_y = (vc.get("min_y", 0) + vc.get("max_y", 0)) / 2
    lines.append(f"  User focus center: ({vc_center_x:.0f},{vc_center_y:.0f}) flow coords")

    return lines


def _compute_content_bounds(
    layout: Dict[str, Any],
    entity_ids: List[str],
) -> Optional[Tuple[float, float, float, float]]:
    """Compute bounding box (min_x, min_y, max_x, max_y) of entities including dimensions."""
    min_x = float("inf")
    min_y = float("inf")
    max_x = float("-inf")
    max_y = float("-inf")
    found = False

    for eid in entity_ids:
        pos = layout.get("node_positions", {}).get(eid)
        if not isinstance(pos, (list, tuple)) or len(pos) < 2:
            continue
        ex, ey = float(pos[0]), float(pos[1])
        ew = get_entity_dimension(layout, eid, "width") or _DEFAULT_ENTITY_W
        eh = get_entity_dimension(layout, eid, "height") or _DEFAULT_ENTITY_H
        min_x = min(min_x, ex)
        min_y = min(min_y, ey)
        max_x = max(max_x, ex + ew)
        max_y = max(max_y, ey + eh)
        found = True

    if not found:
        return None
    return (min_x, min_y, max_x, max_y)


# ---------------------------------------------------------------------------
# Cross-display readability distribution hint
# ---------------------------------------------------------------------------


def _compute_distribution_hint(
    layout: Dict[str, Any],
    surface_assignments: Dict[str, List[str]],
    display_labels: Dict[str, str],
    displays_by_id: Dict[str, Dict],
) -> List[str]:
    """Emit spatial facts when some displays have entities while others are empty.

    Provides raw measurements so the agent can reason about whether and how to
    use the empty displays.  No thresholds, no prescriptions — just data.
    """
    all_eids = [eid for eids in surface_assignments.values() for eid in eids]
    if not all_eids:
        return []

    # Separate occupied from empty displays.
    occupied: List[Tuple[str, List[str], Dict[str, Any]]] = []
    empty: List[Tuple[str, Dict[str, Any]]] = []
    for sid, eids in surface_assignments.items():
        display = displays_by_id.get(sid)
        if not display:
            continue
        if len(eids) == 0:
            empty.append((sid, display))
        else:
            occupied.append((sid, eids, display))

    # Only emit when there is at least one empty display alongside occupied ones.
    if not occupied or not empty:
        return []

    lines = ["\n[Multi-Display Space Analysis]"]
    lines.append("  Some displays are empty. Spatial facts for your layout decision:\n")

    for sid, eids, display in occupied:
        label = display_labels.get(sid, sid)
        count = len(eids)
        display_w = float(display.get("width") or 0)
        display_h = float(display.get("height") or 0)
        tags = display.get("tags", [])

        # Per-entity readability at current zoom
        widths = [get_entity_dimension(layout, e, "width") or _DEFAULT_ENTITY_W for e in eids]
        heights = [get_entity_dimension(layout, e, "height") or _DEFAULT_ENTITY_H for e in eids]
        avg_w = sum(widths) / count
        avg_h = sum(heights) / count
        est = _estimate_readability_for_display(display, count, avg_w, avg_h)

        lines.append(
            f"  Display '{label}' (tags: {tags}): {count} entities, "
            f"display size {display_w:.0f}×{display_h:.0f}px"
        )
        if est:
            lines.append(
                f"    Readability at current zoom: entity ~{est['screen_entity_w']:.0f}px wide "
                f"({est['readability']}), fit zoom would be ~{est['zoom']:.2f}x"
            )

        # Show content bounds vs display bounds so the agent can see overflow directly.
        content_bounds = layout.get("surface_content_bounds", {}).get(sid)
        if content_bounds and display_w > 0 and display_h > 0:
            cw = content_bounds[2] - content_bounds[0]
            ch = content_bounds[3] - content_bounds[1]
            lines.append(
                f"    Content extent: {cw:.0f}×{ch:.0f}px "
                f"(display is {display_w:.0f}×{display_h:.0f}px)"
            )
            if cw > display_w or ch > display_h:
                lines.append(
                    f"    Content overflows: "
                    + (f"width by {cw/display_w:.1f}×" if cw > display_w else "")
                    + (" " if cw > display_w and ch > display_h else "")
                    + (f"height by {ch/display_h:.1f}×" if ch > display_h else "")
                )

    lines.append("")
    all_displays = list(displays_by_id.values())
    for sid, display in empty:
        label = display_labels.get(sid, sid)
        tags = display.get("tags", [])
        display_w = float(display.get("width") or 0)
        display_h = float(display.get("height") or 0)
        lines.append(
            f"  Display '{label}' (tags: {tags}): 0 entities — "
            f"{display_w:.0f}×{display_h:.0f}px available"
        )
        adjacency = _compute_adjacency(display, all_displays)
        if adjacency:
            parts = [
                f"{direction}={display_labels.get(peer, peer)}"
                for direction in ("left", "right", "above", "below")
                if (peer := adjacency.get(direction))
            ]
            if parts:
                lines.append(f"    Adjacent: {', '.join(parts)}")

    return lines


# ---------------------------------------------------------------------------
# Main spatial section builder
# ---------------------------------------------------------------------------


def _build_spatial_layout_section(
    layout: Dict[str, Any],
    surface_assignments: Dict[str, List[str]],
    entity_names: Dict[str, str],
    entity_tags: Dict[str, List[str]],
    display_labels: Dict[str, str],
    sentiment_lookup: Dict[str, str],
    displays_by_id: Dict[str, Dict],
) -> str:
    """Build the full [Current Layout State] section with spatial context."""
    lines = ["[Current Layout State]"]

    surface_bounds = layout.get("surface_bounds", {})
    all_displays = list(displays_by_id.values())

    for surface_id, entity_ids in sorted(surface_assignments.items()):
        label = display_labels.get(surface_id, surface_id)
        display = displays_by_id.get(surface_id)
        bounds = surface_bounds.get(surface_id)

        # Display header with geometry
        lines.extend(
            _format_display_header(
                surface_id,
                label,
                display,
                len(entity_ids),
                bounds,
                all_displays=all_displays,
                display_labels=display_labels,
            )
        )

        # Viewport analysis (density, capacity, readability, free space)
        lines.extend(_compute_viewport_analysis(layout, display, entity_ids))

        # Arrangement description
        arrangement_desc = _describe_arrangement(layout, entity_ids, display)
        if arrangement_desc:
            lines.append(f"  Arrangement: {arrangement_desc}")

        # Entity lines with positions and visibility markers
        visible_canvas = display.get("visible_canvas") if display else None
        lines.append("  Entities:")
        for eid in entity_ids:
            lines.append(
                _format_entity_line(
                    layout, eid, entity_names, entity_tags, sentiment_lookup,
                    visible_canvas=visible_canvas,
                )
            )

    # --- Cross-display readability distribution hint ---
    # When multiple displays exist, check if nodes are concentrated on one
    # display while others sit empty, AND readability would suffer.
    if len(displays_by_id) >= 2:
        lines.extend(
            _compute_distribution_hint(
                layout, surface_assignments, display_labels, displays_by_id,
            )
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Sentiment lookup
# ---------------------------------------------------------------------------


def _build_sentiment_lookup(entities: Optional[List]) -> Dict[str, str]:
    sentiment_lookup: Dict[str, str] = {}
    if not entities:
        return sentiment_lookup

    for entity in entities:
        eid = entity.get("entity_id") or entity.get("id")
        if not eid:
            continue
        semantics = entity.get("semantics") or {}
        sentiment = semantics.get("sentiment")
        if sentiment:
            sentiment_lookup[eid] = sentiment

    return sentiment_lookup


# ---------------------------------------------------------------------------
# Tags and highlights
# ---------------------------------------------------------------------------


def _inject_grouping_user_note(
    state: Any,
    llm_request: "LlmRequest",
) -> None:
    """Prepend a hard-stop note to the last user message when active grouping exists.

    LLMs attend most strongly to content adjacent to the user's turn.
    Putting the warning here is far more effective than burying it in
    system instructions.
    """
    if state.get("_active_grouping_just_created"):
        return
    grouping = state.get("_active_grouping")
    if not grouping or not grouping.get("groups"):
        return

    group_labels = [g["label"] for g in grouping["groups"]]
    labels_str = ", ".join(f'"{l}"' for l in group_labels)

    dims = ["grouping"]
    if any(g.get("display_id") for g in grouping["groups"]):
        dims.append("display assignment")
    if grouping.get("ordered"):
        dims.append("ordering")
    dims_str = " + ".join(dims)

    note = f"[IMPORTANT — EXISTING ORGANIZATION DETECTED]\nThe current layout has established {dims_str} across groups: {labels_str}.\nSee [Active Organization] in the context for the specific invariants the user accepted.\nBefore reorganizing, decide which invariants to preserve and which to replace. If the request is ambiguous about any of them, ask the user before acting.\nDo NOT silently discard any listed invariant.\n\n"

    # Find the last user message and prepend the note
    for content in reversed(llm_request.contents):
        if content.role == "user" and content.parts:
            for part in content.parts:
                if hasattr(part, "text") and part.text:
                    part.text = note + part.text
                    logger.info("Injected active-grouping note into user message")
                    return


def _build_active_grouping_lines(state: Any) -> str:
    """Build an [Active Organization] section from prior semantic layout calls.

    Surfaces the invariants the user established on a prior turn — grouping,
    per-group display assignment, inter-group ordering — so the agent can
    preserve them (or ask before overwriting) rather than blindly re-running
    a layout from scratch.

    Skipped when the organization was just created in this invocation
    (flag set by tool_plan_semantic_layout) to avoid the agent undoing its
    own work.
    """
    if state.get("_active_grouping_just_created"):
        return ""
    grouping = state.get("_active_grouping")
    if not grouping:
        return ""

    groups = grouping.get("groups", [])
    if not groups:
        return ""

    lines = ["⚠️ [Active Organization] — STOP: the user has established the invariants below on a prior turn. Each is something the user accepted and may still expect. Preserve every listed invariant unless the current request explicitly asks to change one; when the request is ambiguous about which invariants to keep, ask before acting."]
    for g in groups:
        label = g["label"]
        names = g.get("entity_names", g.get("entity_ids", []))
        display_label = g.get("display_label")
        suffix = f" — on {display_label}" if display_label else ""
        preview = ", ".join(names[:6]) + ("..." if len(names) > 6 else "")
        lines.append(f'  - "{label}" ({len(names)} entities{suffix}): {preview}')

    if grouping.get("ordered"):
        arr = grouping.get("group_arrangement") or "sequence"
        lines.append(f"  (groups were placed in explicit {arr} order — preserve sequence unless asked to re-sort)")

    return "\n".join(lines)


def _build_active_tags_lines(entity_tags: Dict[str, List[str]]) -> str:
    if not entity_tags:
        return ""

    all_tags: set = set()
    for tags in entity_tags.values():
        if isinstance(tags, list):
            all_tags.update(tags)

    if not all_tags:
        return ""

    return f"Active entity tags: {sorted(all_tags)}"


def _build_user_highlights_lines(
    user_text_highlights: Dict[str, Any],
    entity_names: Dict[str, str],
) -> str:
    if not user_text_highlights:
        return ""

    lines = ["[User-Highlighted Text]"]
    for eid, texts in sorted(user_text_highlights.items()):
        name = entity_names.get(eid, eid)
        if isinstance(texts, list) and texts:
            quoted = [f'"{t}"' for t in texts[:5]]
            lines.append(f'  - {eid} "{name}": {", ".join(quoted)}')

    return "\n".join(lines)
