"""Human-readable spatial summaries for layout tool responses.

Converts raw placement coordinates into natural-language descriptions
that the LLM can use to assess layout quality and iterate.
"""

import math
from typing import Any, Dict, List, Tuple

from .dimensions import get_entity_dimension


def _centroid(
    positions: List[Tuple[float, float]],
    sizes: List[Tuple[float, float]],
) -> Tuple[float, float]:
    """Compute the center-of-mass for a set of positioned rectangles."""
    if not positions:
        return (0.0, 0.0)
    cx = sum(p[0] + s[0] / 2 for p, s in zip(positions, sizes)) / len(positions)
    cy = sum(p[1] + s[1] / 2 for p, s in zip(positions, sizes)) / len(positions)
    return (cx, cy)


def _compass_direction(dx: float, dy: float) -> str:
    """Return a compass label for a vector (dx, dy) in screen coords (y-down)."""
    if abs(dx) < 1 and abs(dy) < 1:
        return "overlapping"
    angle = math.degrees(math.atan2(dy, dx))  # 0=right, 90=down
    if -22.5 <= angle < 22.5:
        return "to the right of"
    if 22.5 <= angle < 67.5:
        return "to the bottom-right of"
    if 67.5 <= angle < 112.5:
        return "below"
    if 112.5 <= angle < 157.5:
        return "to the bottom-left of"
    if angle >= 157.5 or angle < -157.5:
        return "to the left of"
    if -157.5 <= angle < -112.5:
        return "to the top-left of"
    if -112.5 <= angle < -67.5:
        return "above"
    return "to the top-right of"


def _format_distance(dist: float) -> str:
    """Human-friendly distance description."""
    if dist < 80:
        return "very close"
    if dist < 250:
        return "nearby"
    if dist < 600:
        return "moderately spaced"
    if dist < 1200:
        return "spread apart"
    return "far apart"


def summarize_group_layout(
    layout: Dict[str, Any],
    group_overlays: List[Dict[str, Any]],
    placements: List[Dict[str, Any]],
) -> str:
    """Build a human-readable spatial summary of a multi-group layout.

    Args:
        layout: Current layout state dict.
        group_overlays: List of overlay dicts from compute_graph_layout,
            each with "label", "entity_ids", "bounds", "display_id".
        placements: List of placement dicts with "entity_id", "x", "y",
            "target_surface".

    Returns:
        A multi-line natural-language summary suitable for the LLM.
    """
    if not group_overlays:
        return ""

    placement_map: Dict[str, Tuple[float, float]] = {
        p["entity_id"]: (p["x"], p["y"]) for p in placements
    }

    # Compute per-group centroids and bounding info
    group_info: List[Dict[str, Any]] = []
    for overlay in group_overlays:
        label = overlay["label"]
        eids = overlay["entity_ids"]
        display_id = overlay.get("display_id", "")

        positions = []
        sizes = []
        for eid in eids:
            pos = placement_map.get(eid)
            if pos is None:
                continue
            w = get_entity_dimension(layout, eid, "width") or 400.0
            h = get_entity_dimension(layout, eid, "height") or 300.0
            positions.append(pos)
            sizes.append((w, h))

        if not positions:
            continue

        cx, cy = _centroid(positions, sizes)
        bounds = overlay.get("bounds", {})
        bw = bounds.get("max_x", 0) - bounds.get("min_x", 0)
        bh = bounds.get("max_y", 0) - bounds.get("min_y", 0)

        group_info.append({
            "label": label,
            "count": len(eids),
            "center": (cx, cy),
            "width": bw,
            "height": bh,
            "display_id": display_id,
        })

    if not group_info:
        return ""

    lines = []
    lines.append(f"{len(group_info)} groups placed:")

    # Describe each group
    for g in group_info:
        lines.append(
            f"  - {g['label']} ({g['count']} entities, "
            f"{g['width']:.0f}x{g['height']:.0f}px)"
        )

    # Describe relative positions between groups
    if len(group_info) >= 2:
        lines.append("Relative positions:")
        described = set()
        for i, g1 in enumerate(group_info):
            for j, g2 in enumerate(group_info):
                if i >= j:
                    continue
                pair = (g1["label"], g2["label"])
                if pair in described:
                    continue
                described.add(pair)

                dx = g2["center"][0] - g1["center"][0]
                dy = g2["center"][1] - g1["center"][1]
                dist = math.hypot(dx, dy)
                direction = _compass_direction(dx, dy)
                closeness = _format_distance(dist)

                lines.append(
                    f"  - {g2['label']} is {direction} {g1['label']} "
                    f"({closeness}, ~{dist:.0f}px)"
                )

    return "\n".join(lines)


def summarize_arrangement(
    layout: Dict[str, Any],
    entity_ids: List[str],
    positions: List[Tuple[float, float]],
    display_name: str,
    arrangement: str,
) -> str:
    """Build a human-readable summary of an entity arrangement.

    Args:
        layout: Current layout state dict.
        entity_ids: IDs of arranged entities.
        positions: Computed positions for each entity.
        display_name: Display where entities were placed.
        arrangement: The arrangement type used ("grid", "horizontal", "vertical").

    Returns:
        A short natural-language summary.
    """
    if not entity_ids or not positions:
        return ""

    sizes = []
    for eid in entity_ids:
        w = get_entity_dimension(layout, eid, "width") or 400.0
        h = get_entity_dimension(layout, eid, "height") or 300.0
        sizes.append((w, h))

    # Compute bounding box
    min_x = min(p[0] for p in positions)
    min_y = min(p[1] for p in positions)
    max_x = max(p[0] + s[0] for p, s in zip(positions, sizes))
    max_y = max(p[1] + s[1] for p, s in zip(positions, sizes))
    total_w = max_x - min_x
    total_h = max_y - min_y

    shape = "landscape" if total_w > total_h * 1.3 else (
        "portrait" if total_h > total_w * 1.3 else "roughly square"
    )

    lines = [
        f"{len(entity_ids)} entities in {arrangement} arrangement on {display_name}: "
        f"{total_w:.0f}x{total_h:.0f}px total ({shape})"
    ]

    return "\n".join(lines)
