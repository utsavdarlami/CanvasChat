"""Pure planning & validation logic for layout reorganization.

Stateless functions that take a layout dict + parameters and return placement
plans or validation reports.  No ToolContext, no side effects.
"""

from typing import Any, Dict, List, Optional

from .constants import DEFAULT_NODE_GAP
from .dimensions import get_entity_dimension
from .snapshot import (
    _build_display_labels,
    _build_entity_to_display,
)

ValidationReport = Dict[str, Any]  # {"issues", "checks"}

def _check_overlaps(layout: Dict[str, Any]) -> List[Dict]:
    """Find same-display entity pairs with intersecting bounding boxes."""
    node_positions = layout.get("node_positions", {})
    entity_names = layout.get("entity_names", {})
    entity_to_display = _build_entity_to_display(layout.get("surface_assignments", {}))
    issues = []

    ids_by_display: Dict[str, List[str]] = {}
    for eid in node_positions:
        surface_id = entity_to_display.get(eid, "__unassigned__")
        ids_by_display.setdefault(surface_id, []).append(eid)

    for ids in ids_by_display.values():
        for i in range(len(ids)):
            eid_a = ids[i]
            pos_a = node_positions[eid_a]
            w_a = get_entity_dimension(layout, eid_a, "width") or 0.0
            h_a = get_entity_dimension(layout, eid_a, "height") or 0.0

            for j in range(i + 1, len(ids)):
                eid_b = ids[j]
                pos_b = node_positions[eid_b]
                w_b = get_entity_dimension(layout, eid_b, "width") or 0.0
                h_b = get_entity_dimension(layout, eid_b, "height") or 0.0

                if (
                    pos_a[0] < pos_b[0] + w_b
                    and pos_a[0] + w_a > pos_b[0]
                    and pos_a[1] < pos_b[1] + h_b
                    and pos_a[1] + h_a > pos_b[1]
                ):
                    issues.append(
                        {
                            "type": "overlap",
                            "entities": [
                                entity_names.get(eid_a, eid_a),
                                entity_names.get(eid_b, eid_b),
                            ],
                            "entity_ids": [eid_a, eid_b],
                        }
                    )
    return issues


def _check_overflow(layout: Dict[str, Any]) -> List[Dict]:
    """Find entities extending beyond their display's surface_bounds."""
    node_positions = layout.get("node_positions", {})
    entity_names = layout.get("entity_names", {})
    surface_bounds = layout.get("surface_bounds", {})
    entity_to_display = _build_entity_to_display(layout.get("surface_assignments", {}))
    issues = []

    for eid, (px, py) in node_positions.items():
        sid = entity_to_display.get(eid)
        if not sid:
            continue
        bounds = surface_bounds.get(sid)
        if not bounds:
            continue
        w = get_entity_dimension(layout, eid, "width") or 0.0
        h = get_entity_dimension(layout, eid, "height") or 0.0
        min_x, min_y, max_x, max_y = bounds

        if px < min_x or (px + w) > max_x or py < min_y or (py + h) > max_y:
            issues.append(
                {
                    "type": "overflow",
                    "entity": entity_names.get(eid, eid),
                    "entity_id": eid,
                    "display": sid,
                }
            )
    return issues


def _check_spacing(
    layout: Dict[str, Any],
    min_distance: float = DEFAULT_NODE_GAP,
) -> List[Dict]:
    """Find same-display entity pairs closer than min_distance."""
    node_positions = layout.get("node_positions", {})
    entity_names = layout.get("entity_names", {})
    entity_to_display = _build_entity_to_display(layout.get("surface_assignments", {}))
    issues = []

    ids_by_display: Dict[str, List[str]] = {}
    for eid in node_positions:
        surface_id = entity_to_display.get(eid, "__unassigned__")
        ids_by_display.setdefault(surface_id, []).append(eid)

    for ids in ids_by_display.values():
        for i in range(len(ids)):
            eid_a = ids[i]
            ax, ay = node_positions[eid_a]
            w_a = get_entity_dimension(layout, eid_a, "width") or 0.0
            h_a = get_entity_dimension(layout, eid_a, "height") or 0.0
            for j in range(i + 1, len(ids)):
                eid_b = ids[j]
                bx, by = node_positions[eid_b]
                w_b = get_entity_dimension(layout, eid_b, "width") or 0.0
                h_b = get_entity_dimension(layout, eid_b, "height") or 0.0

                # Edge-to-edge distance between bounding boxes
                dist_x = max(0.0, max(ax - (bx + w_b), bx - (ax + w_a)))
                dist_y = max(0.0, max(ay - (by + h_b), by - (ay + h_a)))
                dist = (dist_x**2 + dist_y**2) ** 0.5

                if (
                    dist < min_distance and dist > 0.0
                ):  # Exclude actual overlaps which are caught by _check_overlaps
                    issues.append(
                        {
                            "type": "spacing",
                            "entities": [
                                entity_names.get(eid_a, eid_a),
                                entity_names.get(eid_b, eid_b),
                            ],
                            "entity_ids": [eid_a, eid_b],
                            "distance": round(dist, 1),
                            "min_required": min_distance,
                        }
                    )
    return issues


def _check_cluster_coherence(layout: Dict[str, Any]) -> List[Dict]:
    """Find clusters whose members are split across displays."""
    entity_clusters = layout.get("entity_clusters", {})
    entity_to_display = _build_entity_to_display(layout.get("surface_assignments", {}))
    display_labels = _build_display_labels(layout)

    if not entity_clusters:
        return []

    members_by_cluster: Dict[str, List[str]] = {}
    for eid, cluster_labels in entity_clusters.items():
        for label in cluster_labels:
            members_by_cluster.setdefault(label, []).append(eid)

    issues = []
    for label, members in members_by_cluster.items():
        if len(members) < 2:
            continue
        displays = set()
        for eid in members:
            sid = entity_to_display.get(eid)
            if sid:
                displays.add(sid)
        if len(displays) > 1:
            issues.append(
                {
                    "type": "cluster_split",
                    "cluster": label,
                    "member_count": len(members),
                    "displays": [
                        display_labels.get(sid, sid) for sid in sorted(displays)
                    ],
                }
            )
    return issues


def _check_display_balance(layout: Dict[str, Any]) -> Dict:
    """Check entity count disparity across displays."""
    surface_assignments = layout.get("surface_assignments", {})
    display_labels = _build_display_labels(layout)

    counts = {}
    for sid, eids in surface_assignments.items():
        label = display_labels.get(sid, sid)
        counts[label] = len(eids)

    if not counts:
        return {"status": "ok", "counts": counts}

    max_count = max(counts.values())
    min_count = min(counts.values())

    if min_count > 0 and max_count / min_count > 3:
        return {
            "status": "imbalanced",
            "counts": counts,
            "ratio": round(max_count / min_count, 1),
        }
    if min_count == 0 and max_count > 0:
        return {
            "status": "imbalanced",
            "counts": counts,
            # Keep report JSON-safe for downstream model APIs that reject NaN/Infinity.
            "ratio": None,
            "ratio_unbounded": True,
        }
    return {"status": "ok", "counts": counts}


def validate_layout(
    layout: Dict[str, Any],
    entities: Optional[List[Dict]] = None,
) -> ValidationReport:
    """Run all quality checks on the current layout.

    Returns a structured report with issues and per-check status.
    """
    issues: List[Dict] = []
    checks: Dict[str, str] = {}

    overlaps = _check_overlaps(layout)
    issues.extend(overlaps)
    checks["overlaps"] = f"{len(overlaps)} found" if overlaps else "ok"

    overflow = _check_overflow(layout)
    issues.extend(overflow)
    checks["overflow"] = f"{len(overflow)} found" if overflow else "ok"

    spacing = _check_spacing(layout)
    issues.extend(spacing)
    checks["spacing"] = f"{len(spacing)} pairs too close" if spacing else "ok"

    cluster_issues = _check_cluster_coherence(layout)
    issues.extend(cluster_issues)
    checks["cluster_coherence"] = (
        f"{len(cluster_issues)} split clusters" if cluster_issues else "ok"
    )

    balance = _check_display_balance(layout)
    checks["balance"] = balance["status"]
    if balance["status"] != "ok":
        issues.append({"type": "balance", **balance})

    return {"issues": issues, "checks": checks}
