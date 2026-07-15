"""Graph-based semantic layout engine.

Hybrid layout strategy:
  - **Without constraints** (anchors/alignments): Uses edge-based ordering +
    MaxRects bin packing for compact, viewport-matching layouts. Related
    groups (connected by edges) are placed adjacent in the packing order.
  - **With constraints**: Uses spring layout + kiwisolver for explicit
    positioning (anchors to regions, alignment between groups).

Intra-group node arrangement uses flow-wrap grids (see arrangement.py).
"""

import math
from typing import Any, Dict, List, Optional, Tuple

import kiwisolver
import networkx as nx
from rectpack.geometry import Rectangle
from rectpack.maxrects import MaxRectsBssf

from .arrangement import (
    _aspect_aware_cols,
    _pack_grid,
    compute_arrangement_positions,
    get_node_sizes_if_available,
)
from .constants import (
    DEFAULT_NODE_GAP,
    GROUP_GAP,
    INTRA_GROUP_SPACING_MULTIPLIERS,
    REGION_GAP_FRACTION,
    REGION_MAX_GAP_PX,
    REGION_MIN_GAP_PX,
)
from .display_profile import auto_select_arrangement, auto_select_group_spacing, auto_select_layout_style
from .regions import slice_bounds_for_region

Placement = Dict[str, Any]
GroupOverlay = Dict[str, Any]

_ARRANGEMENT_PADDING = 0.1
_OVERLAY_PADDING = 20.0
_FALLBACK_NODE_W = 400.0
_FALLBACK_NODE_H = 300.0

_SPACING_MULTIPLIERS = {
    "tight": 1.0,
    "medium": 1.5,
    "large": 2.5,
}

# Viewport-relative cap for base_scale: groups spread across at most this
# fraction of the longest display dimension.
_VIEWPORT_BUDGET_FRACTION = 0.5

# Fallback available dimensions when display bounds are unknown.
_FALLBACK_AVAIL = 4000.0

# Weight-to-distance mapping:  target_dist = base_scale * (_WEIGHT_DIST_BASE - _WEIGHT_DIST_SLOPE * w)
# weight 1.0 → 0.5x base_scale (close), weight 0.0 → 1.4x base_scale (far).
_WEIGHT_DIST_BASE = 1.4
_WEIGHT_DIST_SLOPE = 0.9

# Max spread multiplier: total layout extent is capped at
# desired_spread * _MAX_SPREAD_CONTENT_MULT.
_MAX_SPREAD_CONTENT_MULT = 1.6

# Weight-to-gap multipliers for bin-packing post-processing:
# weight 1.0 → _WEIGHT_GAP_MIN × base_gap (tight), weight 0.0 → _WEIGHT_GAP_MAX × base_gap (wide).
_WEIGHT_GAP_MIN = 0.5
_WEIGHT_GAP_MAX = 2.0

def _compute_display_proportional_gap(
    viewport_dims: Optional[Tuple[float, float]],
    spacing_mult: float,
) -> float:
    """Compute inter-group gap from display PIXEL dimensions (stable).

    Uses REGION_GAP_FRACTION from constants, scaled by the spacing
    multiplier and clamped to [REGION_MIN_GAP_PX, REGION_MAX_GAP_PX].

    Falls back to GROUP_GAP * spacing_mult when viewport_dims unavailable.
    """
    if viewport_dims and viewport_dims[0] > 0 and viewport_dims[1] > 0:
        shorter_dim = min(viewport_dims[0], viewport_dims[1])
        gap = shorter_dim * REGION_GAP_FRACTION * spacing_mult
        return max(REGION_MIN_GAP_PX, min(REGION_MAX_GAP_PX, gap))
    return GROUP_GAP * spacing_mult


def _estimate_group_rect(
    layout: Dict[str, Any],
    entity_ids: List[str],
    _arrangement: str,
    gap: float = DEFAULT_NODE_GAP,
    avail_w: float = 0.0,
    avail_h: float = 0.0,
    preserve_order: bool = False,
) -> Tuple[float, float, Optional[List[Tuple[float, float]]]]:
    """Estimate the width and height needed for a group's entities.

    When per-node dimensions are available, runs the actual flow-wrap
    grid algorithm to compute the true bounding box.  This avoids the
    old ``max_h × rows`` approach which inflated estimates whenever a
    single tall node was present in the group.

    Falls back to uniform-cell estimation when dimensions are missing.

    Returns:
        (padded_w, padded_h, cached_packed) where cached_packed is the
        list of (x, y) positions relative to (0, 0) from ``_pack_grid``,
        or ``None`` when node sizes are unavailable.  Callers can reuse
        cached_packed to avoid a second ``_pack_grid`` call that may
        produce a different layout due to changed ``avail_w``.
    """
    node_sizes = get_node_sizes_if_available(layout, entity_ids)
    n = len(entity_ids)
    if n == 0:
        return (_FALLBACK_NODE_W, _FALLBACK_NODE_H, None)

    if node_sizes:
        # Use the real packing algorithm to get the true packed extent.
        eff_avail_w = avail_w if avail_w > 0 else _FALLBACK_AVAIL
        eff_avail_h = avail_h if avail_h > 0 else _FALLBACK_AVAIL
        # Ensure groups get a compact shape (≥ ceil(sqrt(n)) columns).
        # On narrow displays, MaxRects bin packing hard-constrains the
        # bin width to avail_w, producing single-column vertical stacks
        # when nodes are wide relative to the display.  Widening the
        # budget lets groups pack into compact grids; the camera zooms
        # out to accommodate any overflow.
        max_node_w = max(max(s[0], 1.0) for s in node_sizes)
        min_cols = math.ceil(math.sqrt(n))
        eff_avail_w = max(eff_avail_w, min_cols * (max_node_w + gap))
        packed = _pack_grid(
            node_sizes, eff_avail_w, eff_avail_h, gap, preserve_order,
        )
        widths = [max(s[0], 1.0) for s in node_sizes]
        heights = [max(s[1], 1.0) for s in node_sizes]
        needed_w = max(packed[i][0] + widths[i] for i in range(n))
        needed_h = max(packed[i][1] + heights[i] for i in range(n))
    else:
        packed = None
        max_w, max_h = _FALLBACK_NODE_W, _FALLBACK_NODE_H
        cols = max(1, _aspect_aware_cols(n, avail_w, avail_h, max_w, max_h))
        rows = max(1, math.ceil(n / cols))
        needed_w = cols * max_w + (cols - 1) * gap
        needed_h = rows * max_h + (rows - 1) * gap

    padded_w = needed_w / (1.0 - 2.0 * _ARRANGEMENT_PADDING)
    padded_h = needed_h / (1.0 - 2.0 * _ARRANGEMENT_PADDING)
    return (padded_w, padded_h, packed)


def _build_graph(
    groups: List[Tuple[str, List[str]]],
    edges: List[Dict[str, Any]],
) -> nx.Graph:
    """Build a NetworkX graph from groups (nodes) and weighted edges."""
    G = nx.Graph()
    for label, _entity_ids in groups:
        G.add_node(label)
    for edge in edges:
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        weight = float(edge.get("weight", 0.5))
        if src in G and tgt in G and src != tgt:
            G.add_edge(src, tgt, weight=weight)
    return G


def _order_groups_by_edges(
    graph: nx.Graph,
    group_sizes: Dict[str, Tuple[float, float]],
) -> List[str]:
    """Order groups so that edge-connected groups are adjacent in the sequence.

    Uses DFS traversal starting from the most connected node, processing
    highest-weight edges first. This ensures related groups end up adjacent
    when packed sequentially into a grid.

    Falls back to size-based ordering (largest first) for disconnected groups.
    """
    labels = list(graph.nodes())
    if not labels:
        return []
    if len(labels) == 1:
        return labels

    # Track visited nodes
    visited: set[str] = set()
    ordered: List[str] = []

    def dfs(node: str) -> None:
        if node in visited:
            return
        visited.add(node)
        ordered.append(node)
        # Process neighbors by edge weight (highest first = most related)
        neighbors = [
            (neighbor, graph[node][neighbor].get("weight", 0.5))
            for neighbor in graph.neighbors(node)
            if neighbor not in visited
        ]
        neighbors.sort(key=lambda x: x[1], reverse=True)
        for neighbor, _ in neighbors:
            dfs(neighbor)

    # Start DFS from the most connected node
    if graph.number_of_edges() > 0:
        start_node = max(labels, key=lambda n: int(graph.degree(n)))
        dfs(start_node)

    # Add any disconnected nodes (sorted by size, largest first)
    unvisited = [l for l in labels if l not in visited]
    unvisited.sort(key=lambda l: group_sizes.get(l, (0, 0))[0] * group_sizes.get(l, (0, 0))[1], reverse=True)
    ordered.extend(unvisited)

    return ordered


def _pack_groups_maxrects(
    ordered_labels: List[str],
    group_sizes: Dict[str, Tuple[float, float]],
    viewport_dims: Optional[Tuple[float, float]],
    effective_gap: float,
) -> Dict[str, Tuple[float, float]]:
    """Pack groups into a compact rectangle using MaxRects bin packing.

    Groups are packed in the given order, which should have related groups
    adjacent so they end up near each other in the final layout.

    Args:
        effective_gap: Pre-computed gap (already scaled for viewport).

    Returns:
        {label: (top_left_x, top_left_y)} positions for each group.
    """
    if not ordered_labels:
        return {}

    # Determine bin dimensions based on viewport aspect ratio
    if viewport_dims and viewport_dims[0] > 0 and viewport_dims[1] > 0:
        aspect_ratio = viewport_dims[0] / viewport_dims[1]
    else:
        aspect_ratio = 16.0 / 9.0  # Default landscape

    # Calculate total area needed
    total_area = sum(
        (group_sizes.get(l, (400, 300))[0] + effective_gap) *
        (group_sizes.get(l, (400, 300))[1] + effective_gap)
        for l in ordered_labels
    )

    # Estimate bin dimensions to match viewport aspect ratio
    # area = w * h, aspect = w / h => w = sqrt(area * aspect), h = sqrt(area / aspect)
    bin_w = math.sqrt(total_area * aspect_ratio) * 1.3  # 30% margin
    bin_h = math.sqrt(total_area / aspect_ratio) * 1.3

    # Ensure bin is large enough for the largest group
    max_w = max(group_sizes.get(l, (400, 300))[0] + effective_gap for l in ordered_labels)
    max_h = max(group_sizes.get(l, (400, 300))[1] + effective_gap for l in ordered_labels)
    bin_w = max(bin_w, max_w * 1.5)
    bin_h = max(bin_h, max_h * 1.5)

    algo = MaxRectsBssf(bin_w, bin_h, rot=False)
    positions: Dict[str, Tuple[float, float]] = {}

    for label in ordered_labels:
        w, h = group_sizes.get(label, (400, 300))
        pw, ph = w + effective_gap, h + effective_gap

        # Find best free rect (Best Short Side Fit)
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
            # Overflow fallback — extend below current content
            pos = (0.0, bin_h)
            bin_h += ph

        positions[label] = pos

    # Center the layout around origin
    if positions:
        xs = [positions[l][0] for l in positions]
        ys = [positions[l][1] for l in positions]
        ws = [group_sizes.get(l, (400, 300))[0] for l in positions]
        hs = [group_sizes.get(l, (400, 300))[1] for l in positions]
        center_x = (min(xs) + max(xs[i] + ws[i] for i in range(len(xs)))) / 2
        center_y = (min(ys) + max(ys[i] + hs[i] for i in range(len(ys)))) / 2
        positions = {
            l: (positions[l][0] - center_x, positions[l][1] - center_y)
            for l in positions
        }

    return positions


def _adjust_gaps_by_weight(
    positions: Dict[str, Tuple[float, float]],
    sizes: Dict[str, Tuple[float, float]],
    graph: nx.Graph,
    base_gap: float,
) -> Dict[str, Tuple[float, float]]:
    """Post-process bin-packed positions to encode edge weights as gap sizes.

    Strongly-related groups (high weight) get tighter gaps;
    weakly-related groups (low weight) get wider gaps.

    Operates on top-left positions.  Runs a final overlap resolution pass
    to ensure no rectangles overlap after adjustment.
    """
    if not positions or graph.number_of_edges() == 0:
        return positions

    pos = dict(positions)

    for _ in range(5):
        for u, v, data in sorted(graph.edges(data=True), key=lambda e: (e[0], e[1])):
            if u not in pos or v not in pos:
                continue
            w = data.get("weight", 0.5)
            # Target gap: high weight → tight, low weight → wide
            target_gap = base_gap * (_WEIGHT_GAP_MAX - (_WEIGHT_GAP_MAX - _WEIGHT_GAP_MIN) * w)

            wu, hu = sizes.get(u, (_FALLBACK_NODE_W, _FALLBACK_NODE_H))
            wv, hv = sizes.get(v, (_FALLBACK_NODE_W, _FALLBACK_NODE_H))

            # Compute center-to-center positions
            cx_u = pos[u][0] + wu / 2
            cy_u = pos[u][1] + hu / 2
            cx_v = pos[v][0] + wv / 2
            cy_v = pos[v][1] + hv / 2

            dx = cx_v - cx_u
            dy = cy_v - cy_u
            current_dist = math.hypot(dx, dy)
            if current_dist < 1e-6:
                continue

            # Target distance = half-sizes along the line + target gap
            # Simplified: use the average half-diagonal as min separation
            min_sep = (wu + wv) / 4 + (hu + hv) / 4 + target_gap
            ratio = min_sep / current_dist
            adjustment = (ratio - 1.0) * 0.25  # gentle adjustment factor

            mx, my = (cx_u + cx_v) / 2, (cy_u + cy_v) / 2
            new_cx_u = mx + (cx_u - mx) * (1.0 + adjustment)
            new_cy_u = my + (cy_u - my) * (1.0 + adjustment)
            new_cx_v = mx + (cx_v - mx) * (1.0 + adjustment)
            new_cy_v = my + (cy_v - my) * (1.0 + adjustment)

            pos[u] = (new_cx_u - wu / 2, new_cy_u - hu / 2)
            pos[v] = (new_cx_v - wv / 2, new_cy_v - hv / 2)

    # Final overlap resolution to ensure no groups overlap after adjustment
    pos = _resolve_packing_overlaps(pos, sizes, base_gap * _WEIGHT_GAP_MIN)
    return pos


def _resolve_packing_overlaps(
    positions: Dict[str, Tuple[float, float]],
    sizes: Dict[str, Tuple[float, float]],
    min_gap: float,
) -> Dict[str, Tuple[float, float]]:
    """Push apart any overlapping group rectangles after gap adjustment.

    Lightweight iterative sweep: for each overlapping pair, push apart
    along the axis of least penetration.
    """
    pos = dict(positions)
    labels = sorted(pos.keys())
    n = len(labels)

    for _ in range(5):
        moved = False
        for i in range(n):
            for j in range(i + 1, n):
                li, lj = labels[i], labels[j]
                xi, yi = pos[li]
                xj, yj = pos[lj]
                wi, hi = sizes.get(li, (_FALLBACK_NODE_W, _FALLBACK_NODE_H))
                wj, hj = sizes.get(lj, (_FALLBACK_NODE_W, _FALLBACK_NODE_H))

                # Check overlap with min_gap margin
                overlap_x = (xi + wi + min_gap) - xj
                overlap_y = (yi + hi + min_gap) - yj
                # Also check reverse direction
                overlap_x2 = (xj + wj + min_gap) - xi
                overlap_y2 = (yj + hj + min_gap) - yi

                # Overlapping if both axes overlap
                if overlap_x > 0 and overlap_x2 > 0 and overlap_y > 0 and overlap_y2 > 0:
                    # Push apart along axis of least penetration
                    pen_x = min(overlap_x, overlap_x2)
                    pen_y = min(overlap_y, overlap_y2)
                    if pen_x <= pen_y:
                        shift = pen_x / 2 + 0.5
                        if xi <= xj:
                            pos[li] = (xi - shift, yi)
                            pos[lj] = (xj + shift, yj)
                        else:
                            pos[li] = (xi + shift, yi)
                            pos[lj] = (xj - shift, yj)
                    else:
                        shift = pen_y / 2 + 0.5
                        if yi <= yj:
                            pos[li] = (xi, yi - shift)
                            pos[lj] = (xj, yj + shift)
                        else:
                            pos[li] = (xi, yi + shift)
                            pos[lj] = (xj, yj - shift)
                    moved = True
        if not moved:
            break

    return pos


def _fit_group_positions_to_bounds(
    positions: Dict[str, Tuple[float, float]],
    group_sizes: Dict[str, Tuple[float, float]],
    bounds: Optional[Tuple[float, float, float, float]],
    *,
    center_when_fit: bool = True,
) -> Tuple[Dict[str, Tuple[float, float]], Dict[str, float]]:
    """Translate group top-left positions into the target bounds.

    Graph/packing solvers can emit coordinates centered around the origin
    (often negative X/Y). React Flow uses stable display-local canvas
    coordinates, so we shift the whole solution into the target bounds.

    Returns:
        (shifted_positions, {"dx": float, "dy": float})
    """
    if not positions or bounds is None:
        return positions, {"dx": 0.0, "dy": 0.0}

    b_min_x, b_min_y, b_max_x, b_max_y = bounds
    b_w = b_max_x - b_min_x
    b_h = b_max_y - b_min_y
    if b_w <= 0 or b_h <= 0:
        return positions, {"dx": 0.0, "dy": 0.0}

    min_x = min(positions[label][0] for label in positions)
    min_y = min(positions[label][1] for label in positions)
    max_x = max(
        positions[label][0] + group_sizes.get(label, (_FALLBACK_NODE_W, _FALLBACK_NODE_H))[0]
        for label in positions
    )
    max_y = max(
        positions[label][1] + group_sizes.get(label, (_FALLBACK_NODE_W, _FALLBACK_NODE_H))[1]
        for label in positions
    )

    # Already fully inside bounds; no adjustment needed.
    if min_x >= b_min_x and min_y >= b_min_y and max_x <= b_max_x and max_y <= b_max_y:
        return positions, {"dx": 0.0, "dy": 0.0}

    content_w = max_x - min_x
    content_h = max_y - min_y

    if content_w <= b_w:
        target_min_x = b_min_x + (b_w - content_w) * 0.5
    else:
        target_min_x = b_min_x

    if content_h <= b_h:
        target_min_y = b_min_y + (b_h - content_h) * 0.5
    else:
        target_min_y = b_min_y

    if not center_when_fit:
        if content_w <= b_w:
            target_min_x = b_min_x
        if content_h <= b_h:
            target_min_y = b_min_y

    dx = target_min_x - min_x
    dy = target_min_y - min_y
    if abs(dx) < 1e-6 and abs(dy) < 1e-6:
        return positions, {"dx": 0.0, "dy": 0.0}

    shifted = {
        label: (pos[0] + dx, pos[1] + dy)
        for label, pos in positions.items()
    }
    return shifted, {"dx": dx, "dy": dy}


def _compute_initial_positions(
    graph: nx.Graph,
    group_sizes: Dict[str, Tuple[float, float]],
    layout_style: str,
    spacing_multiplier: float,
    bounds: Optional[Tuple[float, float, float, float]] = None,
    viewport_dims: Optional[Tuple[float, float]] = None,
) -> Tuple[Dict[str, Tuple[float, float]], float]:
    """Compute initial group center positions using NetworkX layout algorithms.

    Returns (positions, base_scale) where positions is in an arbitrary
    coordinate space (will be scaled later) and base_scale is the computed
    spacing scale factor (useful for diagnostics).

    When *viewport_dims* (actual display width/height) are provided, the
    scale is capped to keep groups within readable viewport bounds.
    Falls back to *bounds* when viewport_dims is not available.
    """
    n = graph.number_of_nodes()
    if n == 0:
        return ({}, 0.0)
    if n == 1:
        label = list(graph.nodes)[0]
        return ({label: (0.0, 0.0)}, 0.0)

    avg_diag = sum(
        math.hypot(w, h) for w, h in group_sizes.values()
    ) / max(len(group_sizes), 1)

    base_scale = avg_diag * spacing_multiplier

    # Cap base_scale relative to the actual display viewport so inter-group
    # distances never blow up beyond what the screen can show readably.
    # Prefer viewport_dims (stable display size) over bounds (which may be
    # the zoomed-out visible_canvas).
    if viewport_dims is not None:
        viewport_budget = max(viewport_dims[0], viewport_dims[1], 1.0) * _VIEWPORT_BUDGET_FRACTION
        base_scale = min(base_scale, viewport_budget)
    elif bounds is not None:
        bounds_w = bounds[2] - bounds[0]
        bounds_h = bounds[3] - bounds[1]
        viewport_budget = max(bounds_w, bounds_h, 1.0) * _VIEWPORT_BUDGET_FRACTION
        base_scale = min(base_scale, viewport_budget)

    if layout_style == "hierarchical":
        centrality = nx.degree_centrality(graph)
        sorted_nodes = sorted(centrality.items(), key=lambda x: x[1], reverse=True)
        num_layers = min(3, n)
        for i, (node, _) in enumerate(sorted_nodes):
            graph.nodes[node]["subset"] = i * num_layers // n
        pos = nx.multipartite_layout(graph, subset_key="subset", scale=base_scale)
    elif layout_style == "packed":
        pos = nx.spring_layout(
            graph, k=base_scale * 0.8, weight="weight", iterations=100, seed=42
        )
    else:  # "organic" (default)
        pos = nx.spring_layout(
            graph, k=base_scale, weight="weight", iterations=100, seed=42
        )

    pos_out: Dict[str, Tuple[float, float]] = {
        label: (float(x), float(y)) for label, (x, y) in pos.items()
    }
    if graph.number_of_edges() > 0:
        pos_out = _apply_weight_scaling(pos_out, graph, base_scale)

    return pos_out, base_scale


def _apply_weight_scaling(
    positions: Dict[str, Tuple[float, float]],
    graph: nx.Graph,
    base_scale: float,
) -> Dict[str, Tuple[float, float]]:
    """Adjust inter-group distances so higher edge weight = closer.

    Uses iterative pairwise adjustment: for each edge, moves connected
    nodes toward/away from their midpoint proportional to weight.
    """
    pos = dict(positions)
    for _ in range(5):  # iterate to settle
        for u, v, data in sorted(graph.edges(data=True), key=lambda e: (e[0], e[1])):
            w = data.get("weight", 0.5)
            target_dist = base_scale * (_WEIGHT_DIST_BASE - _WEIGHT_DIST_SLOPE * w)

            ux, uy = pos[u]
            vx, vy = pos[v]
            current_dist = math.hypot(vx - ux, vy - uy)
            if current_dist < 1e-6:
                continue

            ratio = target_dist / current_dist
            # Move each node halfway toward the target
            adjustment = (ratio - 1.0) * 0.3
            mx, my = (ux + vx) / 2, (uy + vy) / 2
            pos[u] = (
                mx + (ux - mx) * (1.0 + adjustment),
                my + (uy - my) * (1.0 + adjustment),
            )
            pos[v] = (
                mx + (vx - mx) * (1.0 + adjustment),
                my + (vy - my) * (1.0 + adjustment),
            )
    return pos


def _resolve_overlaps_kiwi(
    positions: Dict[str, Tuple[float, float]],
    sizes: Dict[str, Tuple[float, float]],
    min_gap: float,
    anchors: Optional[Dict[str, str]] = None,
    full_bounds: Optional[Tuple[float, float, float, float]] = None,
    alignment_constraints: Optional[List[Dict[str, Any]]] = None,
    viewport_dims: Optional[Tuple[float, float]] = None,
) -> Dict[str, Tuple[float, float]]:
    """Push group rectangles apart using kiwisolver constraints.

    Preserves relative positions from spring layout while ensuring:
      - No two group rectangles overlap (REQUIRED)
      - The layout shape matches viewport aspect ratio (STRONG)
      - Layout spread is capped to prevent runaway (MEDIUM)
      - Anchored groups stay in their named regions (STRONG)
      - Aligned groups share a common axis (STRONG)
      - Spring-layout positions are preferred (WEAK)

    Args:
        positions: {label: (center_x, center_y)} from spring layout.
        sizes: {label: (width, height)} per group.
        min_gap: Minimum pixel gap between group edges.
        anchors: {label: region_name} for groups pinned to named regions.
        full_bounds: (min_x, min_y, max_x, max_y) of the display, needed
            for computing anchor region bounds.
        alignment_constraints: List of {"groups": [str], "axis": str}
            for inter-group center alignment.
        viewport_dims: (width, height) of actual display viewport for
            aspect ratio calculation. Falls back to full_bounds if None.

    Returns:
        {label: (top_left_x, top_left_y)} adjusted positions.
    """
    labels = sorted(positions.keys())  # sorted for deterministic constraint generation
    n = len(labels)
    if n == 0:
        return {}
    if n == 1:
        label = labels[0]
        cx, cy = positions[label]
        w, h = sizes[label]
        return {label: (cx - w / 2, cy - h / 2)}

    _anchors = anchors or {}
    solver = kiwisolver.Solver()

    vars_x: Dict[str, kiwisolver.Variable] = {}
    vars_y: Dict[str, kiwisolver.Variable] = {}
    for label in labels:
        vars_x[label] = kiwisolver.Variable(f"{label}_x")
        vars_y[label] = kiwisolver.Variable(f"{label}_y")

    # --- WEAK: Prefer spring-layout positions ---
    for label in labels:
        cx, cy = positions[label]
        w, h = sizes[label]

        if label in _anchors and full_bounds is not None:
            region_bounds = slice_bounds_for_region(full_bounds, _anchors[label])
            if region_bounds:
                r_min_x, r_min_y, r_max_x, r_max_y = region_bounds
                solver.addConstraint(
                    (vars_x[label] >= r_min_x) | kiwisolver.strength.strong
                )
                solver.addConstraint(
                    (vars_x[label] + w <= r_max_x) | kiwisolver.strength.strong
                )
                solver.addConstraint(
                    (vars_y[label] >= r_min_y) | kiwisolver.strength.strong
                )
                solver.addConstraint(
                    (vars_y[label] + h <= r_max_y) | kiwisolver.strength.strong
                )
            else:
                ideal_x = cx - w / 2
                ideal_y = cy - h / 2
                solver.addConstraint(
                    (vars_x[label] == ideal_x) | kiwisolver.strength.weak
                )
                solver.addConstraint(
                    (vars_y[label] == ideal_y) | kiwisolver.strength.weak
                )
        else:
            ideal_x = cx - w / 2
            ideal_y = cy - h / 2
            solver.addConstraint(
                (vars_x[label] == ideal_x) | kiwisolver.strength.weak
            )
            solver.addConstraint(
                (vars_y[label] == ideal_y) | kiwisolver.strength.weak
            )

    # --- STRONG: Alignment constraints between groups ---
    for ac in (alignment_constraints or []):
        ac_groups = ac.get("groups", [])
        ac_axis = ac.get("axis", "")
        for i in range(len(ac_groups) - 1):
            a, b = ac_groups[i], ac_groups[i + 1]
            if a not in vars_x or b not in vars_x:
                continue
            wa, ha = sizes.get(a, (0, 0))
            wb, hb = sizes.get(b, (0, 0))
            if ac_axis == "horizontal":
                solver.addConstraint(
                    (vars_y[a] + ha / 2 == vars_y[b] + hb / 2)
                    | kiwisolver.strength.strong
                )
            elif ac_axis == "vertical":
                solver.addConstraint(
                    (vars_x[a] + wa / 2 == vars_x[b] + wb / 2)
                    | kiwisolver.strength.strong
                )

    # --- STRONG: Aspect-aware spread constraints ---
    # Enforce layout shape to match viewport aspect ratio.
    # Use viewport_dims (actual display size) for aspect calculation,
    # falling back to full_bounds if not available.
    aspect_w: float = 0.0
    aspect_h: float = 0.0
    if viewport_dims is not None:
        aspect_w, aspect_h = viewport_dims
    elif full_bounds is not None:
        aspect_w = full_bounds[2] - full_bounds[0]
        aspect_h = full_bounds[3] - full_bounds[1]

    if aspect_w > 0 and aspect_h > 0 and n >= 2:
        avg_w = sum(sizes[l][0] for l in labels) / n
        avg_h = sum(sizes[l][1] for l in labels) / n

        cols = max(1, _aspect_aware_cols(n, aspect_w, aspect_h, avg_w, avg_h))
        rows = max(1, math.ceil(n / cols))

        desired_spread_x = cols * avg_w + (cols - 1) * min_gap
        desired_spread_y = rows * avg_h + (rows - 1) * min_gap

        # Identify extreme groups from spring layout positions
        x_sorted = sorted(labels, key=lambda l: positions[l][0])
        y_sorted = sorted(labels, key=lambda l: positions[l][1])

        leftmost, rightmost = x_sorted[0], x_sorted[-1]
        topmost, bottommost = y_sorted[0], y_sorted[-1]

        # "Right edge of rightmost − left edge of leftmost >= desired"
        # STRONG strength enforces the calculated aspect ratio shape
        if leftmost != rightmost:
            solver.addConstraint(
                (vars_x[rightmost] + sizes[rightmost][0]
                 - vars_x[leftmost] >= desired_spread_x)
                | kiwisolver.strength.strong
            )
        if topmost != bottommost:
            solver.addConstraint(
                (vars_y[bottommost] + sizes[bottommost][1]
                 - vars_y[topmost] >= desired_spread_y)
                | kiwisolver.strength.strong
            )

        # --- MEDIUM: Max spread cap ---
        # Prevent runaway layout spread by capping total extent.
        # Uses MEDIUM strength so it yields to REQUIRED non-overlap
        # but still pulls groups inward when spring layout over-spreads.
        max_spread_x = desired_spread_x * _MAX_SPREAD_CONTENT_MULT
        max_spread_y = desired_spread_y * _MAX_SPREAD_CONTENT_MULT
        if leftmost != rightmost:
            solver.addConstraint(
                (vars_x[rightmost] + sizes[rightmost][0]
                 - vars_x[leftmost] <= max_spread_x)
                | kiwisolver.strength.medium
            )
        if topmost != bottommost:
            solver.addConstraint(
                (vars_y[bottommost] + sizes[bottommost][1]
                 - vars_y[topmost] <= max_spread_y)
                | kiwisolver.strength.medium
            )

    # Build alignment-forced separation map
    _forced_sep: Dict[Tuple[str, str], str] = {}
    for ac in (alignment_constraints or []):
        ac_groups = ac.get("groups", [])
        ac_axis = ac.get("axis", "")
        for ii in range(len(ac_groups)):
            for jj in range(ii + 1, len(ac_groups)):
                pair = (min(ac_groups[ii], ac_groups[jj]),
                        max(ac_groups[ii], ac_groups[jj]))
                if ac_axis == "vertical":
                    _forced_sep[pair] = "y"
                elif ac_axis == "horizontal":
                    _forced_sep[pair] = "x"

    # --- REQUIRED: Non-overlap constraints for all pairs ---
    for i in range(n):
        for j in range(i + 1, n):
            li, lj = labels[i], labels[j]
            wi, hi = sizes[li]
            wj, hj = sizes[lj]

            cxi, cyi = positions[li]
            cxj, cyj = positions[lj]

            pair_key = (min(li, lj), max(li, lj))
            forced = _forced_sep.get(pair_key)

            if forced == "y":
                sep_axis = "y"
            elif forced == "x":
                sep_axis = "x"
            else:
                dx = abs(cxj - cxi)
                dy = abs(cyj - cyi)
                if abs(dx - dy) < 1e-6:
                    # Tie: use lexicographic label comparison for determinism
                    sep_axis = "x" if li < lj else "y"
                else:
                    sep_axis = "x" if dx >= dy else "y"

            if sep_axis == "x":
                if cxi <= cxj:
                    solver.addConstraint(
                        (vars_x[li] + wi + min_gap <= vars_x[lj])
                        | kiwisolver.strength.required
                    )
                else:
                    solver.addConstraint(
                        (vars_x[lj] + wj + min_gap <= vars_x[li])
                        | kiwisolver.strength.required
                    )
            else:
                if cyi <= cyj:
                    solver.addConstraint(
                        (vars_y[li] + hi + min_gap <= vars_y[lj])
                        | kiwisolver.strength.required
                    )
                else:
                    solver.addConstraint(
                        (vars_y[lj] + hj + min_gap <= vars_y[li])
                        | kiwisolver.strength.required
                    )

    solver.updateVariables()

    result = {}
    for label in labels:
        result[label] = (vars_x[label].value(), vars_y[label].value())
    return result


LayoutDiagnostics = Dict[str, Any]


def compute_graph_layout(
    layout: Dict[str, Any],
    surface_id: str,
    groups: List[Tuple[str, List[str]]],
    edges: List[Dict[str, Any]],
    arrangement: Optional[str] = None,
    layout_style: Optional[str] = None,
    group_spacing: Optional[str] = None,
    bounds: tuple = (0.0, 0.0, 1920.0, 1080.0),
    color_index_start: int = 0,
    group_arrangements: Optional[Dict[str, str]] = None,
    anchors: Optional[Dict[str, str]] = None,
    alignment_constraints: Optional[List[Dict[str, Any]]] = None,
    group_spacings: Optional[Dict[str, str]] = None,
    group_preserve_order: Optional[Dict[str, bool]] = None,
    viewport_dims: Optional[Tuple[float, float]] = None,
    ordered: bool = False,
    preserve_existing: bool = False,
    group_sub_groups: Optional[Dict[str, List[Tuple[str, List[str]]]]] = None,
    group_sub_group_edges: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    group_arrangement: Optional[str] = None,
    include_diagnostics: bool = False,
) -> Tuple[List[Placement], List[GroupOverlay], Optional[LayoutDiagnostics]]:
    """Compute placements using graph-based semantic proximity.

    Phase 1 — Spring layout positions groups so edge weight encodes
    proximity (higher weight = closer).

    Phase 2 — Kiwisolver resolves overlaps and enforces aspect-aware
    spread so the layout fills the display instead of collapsing
    onto a diagonal.

    Phase 3 — Flow-wrap grid arranges entities within each group.

    All parameters (arrangement, layout_style, group_spacing) are optional.
    When None, the engine auto-selects based on display geometry and context.

    Args:
        arrangement: Entity layout within groups ("grid", "horizontal",
            "vertical"). None → auto-select per group based on region shape.
        layout_style: Group positioning strategy ("organic", "packed",
            "hierarchical"). None → auto-select based on constraints.
        group_spacing: Gap between groups ("tight", "medium", "large").
            None → auto-select based on display count and entity count.
        viewport_dims: Display PIXEL dimensions (width, height) for stable
            gap computation. Use display hardware size, not canvas bounds.
        ordered: If True, groups are arranged in list order (left→right,
            top→bottom) using grid packing. Overrides edge-based and
            spring-layout positioning. Use for chronological sequences
            or sorted group displays.
        group_arrangement: Inter-group layout shape when ordered=True.
            "row" → single horizontal line (overflow allowed), "column"
            → single vertical stack, "grid" (default) → 2D pack that
            wraps by aspect ratio. Ignored when ordered=False.
        include_diagnostics: If True, returns diagnostic info.

    Returns:
        Tuple of (placements, group_overlays, diagnostics).
        diagnostics is None unless include_diagnostics=True.
    """
    placements: List[Placement] = []
    overlays: List[GroupOverlay] = []

    if not groups:
        return placements, overlays, None

    # --- Auto-inference for optional params ---
    has_constraints = bool(anchors) or bool(alignment_constraints)
    total_entities = sum(len(eids) for _, eids in groups)

    if layout_style is None:
        layout_style = auto_select_layout_style(has_constraints)
    if group_spacing is None:
        group_spacing = auto_select_group_spacing(
            display_count=1,  # caller handles multi-display
            total_entity_count=total_entities,
        )
    if arrangement is None:
        # Will be auto-selected per group in Step 4 based on region shape.
        # Use "grid" as the default for group size estimation in Step 1.
        arrangement = "grid"
        _auto_arrangement = True
    else:
        _auto_arrangement = False

    spacing_mult = _SPACING_MULTIPLIERS.get(group_spacing, 1.5)
    min_gap = GROUP_GAP * spacing_mult

    # Step 1: Estimate rectangle sizes for each group
    group_sizes: Dict[str, Tuple[float, float]] = {}
    group_node_sizes: Dict[str, Optional[List[Tuple[float, float]]]] = {}
    group_cached_packed: Dict[str, Optional[List[Tuple[float, float]]]] = {}
    _ga = group_arrangements or {}
    _gs = group_spacings or {}
    _gpo = group_preserve_order or {}
    group_gaps: Dict[str, float] = {}
    bounds_w = bounds[2] - bounds[0] if bounds else 0.0
    bounds_h = bounds[3] - bounds[1] if bounds else 0.0
    for label, entity_ids in groups:
        arr = _ga.get(label, arrangement)
        sp = _gs.get(label, "medium")
        intra_gap = DEFAULT_NODE_GAP * INTRA_GROUP_SPACING_MULTIPLIERS.get(sp, 1.0)
        group_gaps[label] = intra_gap
        w, h, cached_packed = _estimate_group_rect(
            layout, entity_ids, arr, gap=intra_gap,
            avail_w=bounds_w, avail_h=bounds_h,
            preserve_order=_gpo.get(label, False),
        )
        group_sizes[label] = (w, h)
        group_node_sizes[label] = get_node_sizes_if_available(layout, entity_ids)
        group_cached_packed[label] = cached_packed

    # Compute display-proportional gap early — needed for preserve_existing
    # and for group positioning.
    display_gap = _compute_display_proportional_gap(viewport_dims, spacing_mult)
    effective_gap = max(min_gap, display_gap)

    # Step 1.5: If preserve_existing, shrink bounds to avoid preserved entities
    if preserve_existing:
        all_group_eids = set()
        for _, eids in groups:
            all_group_eids.update(eids)
        preserved_eids = [
            eid for eid in layout.get("node_positions", {})
            if eid not in all_group_eids
            and layout.get("surface_assignments", {}).get(surface_id)
            and eid in layout["surface_assignments"][surface_id]
        ]
        if preserved_eids:
            from .dimensions import get_entity_dimension as _get_dim
            # Find bounding box of preserved content
            pmin_x = float("inf")
            pmin_y = float("inf")
            pmax_x = float("-inf")
            pmax_y = float("-inf")
            for eid in preserved_eids:
                ex, ey = layout["node_positions"][eid]
                ew = _get_dim(layout, eid, "width") or _FALLBACK_NODE_W
                eh = _get_dim(layout, eid, "height") or _FALLBACK_NODE_H
                pmin_x = min(pmin_x, ex)
                pmin_y = min(pmin_y, ey)
                pmax_x = max(pmax_x, ex + ew)
                pmax_y = max(pmax_y, ey + eh)

            # Determine best available region: right of, below, or above
            # preserved content. Pick the largest remaining strip.
            bx0, by0, bx1, by1 = bounds
            right_strip = (pmax_x + effective_gap, by0, bx1, by1)
            bottom_strip = (bx0, pmax_y + effective_gap, bx1, by1)
            left_strip = (bx0, by0, pmin_x - effective_gap, by1)
            top_strip = (bx0, by0, bx1, pmin_y - effective_gap)

            def _area(b: tuple) -> float:
                w = max(0, b[2] - b[0])
                h = max(0, b[3] - b[1])
                return w * h

            candidates = [right_strip, bottom_strip, left_strip, top_strip]
            best_strip = max(candidates, key=_area)
            if _area(best_strip) > 0:
                bounds = best_strip

    # Step 2: Position groups using appropriate strategy
    graph = _build_graph(groups, edges)
    has_constraints = bool(anchors) or bool(alignment_constraints)

    if ordered:
        # Ordered mode: arrange groups in list order (left→right, top→bottom)
        # using grid packing. This preserves the semantic ordering the LLM
        # applied (e.g., chronological, by rating, by count).
        group_labels_ordered = [label for label, _ in groups]
        group_size_list = [
            (group_sizes[label][0] + effective_gap,
             group_sizes[label][1] + effective_gap)
            for label in group_labels_ordered
        ]
        avail_w = bounds[2] - bounds[0] if bounds else _FALLBACK_AVAIL
        avail_h = bounds[3] - bounds[1] if bounds else _FALLBACK_AVAIL
        if group_arrangement == "row":
            _force_cols = len(group_labels_ordered)
        elif group_arrangement == "column":
            _force_cols = 1
        else:
            _force_cols = None
        packed_positions = _pack_grid(
            group_size_list, avail_w, avail_h, effective_gap,
            preserve_order=True, force_cols=_force_cols,
        )
        resolved_pos = {
            label: (px + effective_gap / 2, py + effective_gap / 2)
            for label, (px, py) in zip(group_labels_ordered, packed_positions)
        }
        base_scale = 0.0
    elif has_constraints:
        # Use spring layout + kiwisolver when explicit constraints exist
        initial_pos, base_scale = _compute_initial_positions(
            graph, group_sizes, layout_style, spacing_mult,
            bounds=bounds, viewport_dims=viewport_dims,
        )
        # Step 3: Constraint phase — overlap removal + anchors/alignments
        resolved_pos = _resolve_overlaps_kiwi(
            initial_pos,
            group_sizes,
            effective_gap,
            anchors=anchors,
            full_bounds=bounds,
            alignment_constraints=alignment_constraints,
            viewport_dims=viewport_dims,
        )
    else:
        # Use edge-ordering + bin packing for compact, viewport-matching layout
        ordered_labels = _order_groups_by_edges(graph, group_sizes)
        resolved_pos = _pack_groups_maxrects(
            ordered_labels,
            group_sizes,
            viewport_dims,
            effective_gap,
        )
        # Post-process: adjust gaps so edge weights affect spacing,
        # not just adjacency.  High weight → tighter gap, low → wider.
        if graph.number_of_edges() > 0:
            resolved_pos = _adjust_gaps_by_weight(
                resolved_pos, group_sizes, graph, effective_gap,
            )
        base_scale = 0.0  # Not applicable for bin packing

    # Step 3.5: Normalize solver output into target bounds (display-local space)
    if anchors:
        # Preserve explicit region anchors exactly as solved by constraints.
        bounds_shift = {"dx": 0.0, "dy": 0.0}
    else:
        resolved_pos, bounds_shift = _fit_group_positions_to_bounds(
            resolved_pos,
            group_sizes,
            bounds,
            center_when_fit=True,
        )

    # Step 4: Arrange entities within each group region (flow-wrap)
    _sub_groups = group_sub_groups or {}
    _sub_group_edges = group_sub_group_edges or {}
    for idx, (label, entity_ids) in enumerate(groups):
        if label not in resolved_pos:
            continue
        tl_x, tl_y = resolved_pos[label]
        gw, gh = group_sizes[label]
        group_bounds = (tl_x, tl_y, tl_x + gw, tl_y + gh)

        # --- Nested sub-groups: recurse into the parent's region ---
        if label in _sub_groups:
            sub_placements, sub_overlays, _ = compute_graph_layout(
                layout,
                surface_id,
                _sub_groups[label],
                _sub_group_edges.get(label, []),
                bounds=group_bounds,
                color_index_start=color_index_start + idx,
                viewport_dims=viewport_dims,
            )
            for sp in sub_placements:
                placements.append(sp)
            for so in sub_overlays:
                overlays.append(so)
            continue  # skip normal entity placement for this group

        node_sizes = group_node_sizes[label]
        # Per-group arrangement: explicit override > auto-select > default
        if label in _ga:
            arr = _ga[label]
        elif _auto_arrangement:
            arr = auto_select_arrangement(gw, gh, len(entity_ids))
        else:
            arr = arrangement
        intra_gap = group_gaps.get(label, DEFAULT_NODE_GAP)
        preserve_order = _gpo.get(label, False)
        cached_packed = group_cached_packed.get(label)

        if cached_packed is not None and arr == "grid" and node_sizes:
            # Use cached grid positions to avoid a second _pack_grid call
            # that may produce a different layout due to changed avail_w.
            padding = _ARRANGEMENT_PADDING
            content_min_x = tl_x + gw * padding
            content_min_y = tl_y + gh * padding
            avail_w_inner = gw * (1.0 - 2.0 * padding)
            avail_h_inner = gh * (1.0 - 2.0 * padding)

            widths = [max(s[0], 1.0) for s in node_sizes]
            heights = [max(s[1], 1.0) for s in node_sizes]
            n = len(entity_ids)
            pack_w = max(cached_packed[i][0] + widths[i] for i in range(n))
            pack_h = max(cached_packed[i][1] + heights[i] for i in range(n))

            offset_x = content_min_x + max((avail_w_inner - pack_w) * 0.5, 0.0)
            offset_y = content_min_y + max((avail_h_inner - pack_h) * 0.5, 0.0)

            positions = [
                (offset_x + px, offset_y + py) for px, py in cached_packed
            ]
        else:
            # Non-grid arrangements or no cache: use compute_arrangement_positions
            positions = compute_arrangement_positions(
                group_bounds,
                len(entity_ids),
                arr,
                _ARRANGEMENT_PADDING,
                node_sizes=node_sizes,
                gap=intra_gap,
                preserve_order=preserve_order,
            )

        for eid, (px, py) in zip(entity_ids, positions):
            placements.append(
                {"entity_id": eid, "target_surface": surface_id, "x": px, "y": py}
            )

        # Compute overlay bounds from actual placed positions + node sizes
        ob_min_x = float("inf")
        ob_min_y = float("inf")
        ob_max_x = float("-inf")
        ob_max_y = float("-inf")
        for i, (px, py) in enumerate(positions):
            nw, nh = (
                node_sizes[i]
                if node_sizes
                else (_FALLBACK_NODE_W, _FALLBACK_NODE_H)
            )
            ob_min_x = min(ob_min_x, px)
            ob_min_y = min(ob_min_y, py)
            ob_max_x = max(ob_max_x, px + nw)
            ob_max_y = max(ob_max_y, py + nh)

        overlays.append({
            "label": label,
            "entity_ids": list(entity_ids),
            "bounds": {
                "min_x": ob_min_x - _OVERLAY_PADDING,
                "min_y": ob_min_y - _OVERLAY_PADDING,
                "max_x": ob_max_x + _OVERLAY_PADDING,
                "max_y": ob_max_y + _OVERLAY_PADDING,
            },
            "color_index": color_index_start + idx,
            "display_id": surface_id,
        })

    # Build diagnostics if requested
    diagnostics: Optional[LayoutDiagnostics] = None
    if include_diagnostics:
        diagnostics = {
            "bounds_used": list(bounds) if bounds else None,
            "viewport_dims": list(viewport_dims) if viewport_dims else None,
            "bounds_shift": bounds_shift,
            "base_scale": base_scale,
            "spacing_multiplier": spacing_mult,
            "min_gap": min_gap,
            "group_sizes": {k: list(v) for k, v in group_sizes.items()},
            "group_count": len(groups),
            "entity_count": sum(len(eids) for _, eids in groups),
        }

    return placements, overlays, diagnostics
