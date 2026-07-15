"""Display profiling — shape, capacity, semantic role, adjacency.

Builds rich display profiles that inform layout decisions. Uses display
PIXEL dimensions for stable capacity/shape estimates, and current content
for semantic topic awareness.
"""

from typing import Any, Dict, List, Optional

from .constants import (
    CAPACITY_AREA_PER_ENTITY,
    SHAPE_LANDSCAPE,
    SHAPE_PORTRAIT,
    SHAPE_SQUARE,
    SHAPE_ULTRAWIDE,
)


def classify_display_shape(width: float, height: float) -> str:
    """Classify a display by its aspect ratio (from pixel dimensions).

    Returns one of: "ultrawide", "landscape", "square", "portrait", "tall".
    """
    if width <= 0 or height <= 0:
        return "landscape"  # safe fallback
    aspect = width / height
    if aspect >= SHAPE_ULTRAWIDE:
        return "ultrawide"
    if aspect >= SHAPE_LANDSCAPE:
        return "landscape"
    if aspect >= SHAPE_SQUARE:
        return "square"
    if aspect >= SHAPE_PORTRAIT:
        return "portrait"
    return "tall"


def estimate_capacity(width: float, height: float) -> int:
    """Estimate how many standard entities fit readably on a display.

    Uses display PIXEL dimensions (stable hardware) to compute how many
    ~400×300 entities can be shown at zoom >= 0.6 with gap budget.

    Returns at least 1.
    """
    if width <= 0 or height <= 0:
        return 1
    area = width * height
    return max(1, int(area / CAPACITY_AREA_PER_ENTITY))


def _extract_current_topics(
    entity_ids: List[str],
    entities: Optional[List[Dict]] = None,
) -> List[str]:
    """Extract semantic topics from entities currently on a display.

    Looks at entity semantics (domain, key_themes) to build a topic list.
    Returns deduplicated topic strings, most frequent first.
    """
    if not entities:
        return []

    # Build entity lookup
    entity_map: Dict[str, Dict] = {}
    for e in entities:
        eid = e.get("id") or e.get("entity_id")
        if eid:
            entity_map[eid] = e

    topic_counts: Dict[str, int] = {}
    for eid in entity_ids:
        entity = entity_map.get(eid)
        if not entity:
            continue
        semantics = entity.get("semantics") or {}
        domain = semantics.get("domain")
        if domain:
            topic_counts[domain] = topic_counts.get(domain, 0) + 1
        for theme in semantics.get("key_themes", [])[:3]:
            if isinstance(theme, str):
                topic_counts[theme] = topic_counts.get(theme, 0) + 1

    # Sort by frequency descending, take top 10
    sorted_topics = sorted(topic_counts, key=lambda t: topic_counts[t], reverse=True)
    return sorted_topics[:10]


def _compute_adjacency(
    display_meta: Dict[str, Any],
    all_displays: List[Dict[str, Any]],
) -> Dict[str, str]:
    """Compute which displays are adjacent based on virtual desktop positions.

    Returns {direction: peer_id} e.g. {"right": "peer-abc", "left": "peer-xyz"}.
    """
    peer_id = display_meta.get("peer_id")
    dx = float(display_meta.get("x", 0))
    dy = float(display_meta.get("y", 0))
    dw = float(display_meta.get("width", 0))
    dh = float(display_meta.get("height", 0))

    adjacency: Dict[str, str] = {}
    for other in all_displays:
        other_pid = other.get("peer_id")
        if not other_pid or other_pid == peer_id:
            continue
        ox = float(other.get("x", 0))
        oy = float(other.get("y", 0))

        # Check if displays share an edge (approximately)
        # Right neighbor: other starts near our right edge
        if abs(ox - (dx + dw)) < 50 and abs(oy - dy) < dh * 0.5:
            adjacency["right"] = other_pid
        # Left neighbor: other ends near our left edge
        elif abs((ox + float(other.get("width", 0))) - dx) < 50 and abs(oy - dy) < dh * 0.5:
            adjacency["left"] = other_pid
        # Below: other starts near our bottom edge
        elif abs(oy - (dy + dh)) < 50 and abs(ox - dx) < dw * 0.5:
            adjacency["below"] = other_pid
        # Above: other ends near our top edge
        elif abs((oy + float(other.get("height", 0))) - dy) < 50 and abs(ox - dx) < dw * 0.5:
            adjacency["above"] = other_pid

    return adjacency


def build_display_profile(
    layout: Dict[str, Any],
    display_meta: Dict[str, Any],
    entities: Optional[List[Dict]] = None,
) -> Dict[str, Any]:
    """Build a rich profile for a single display.

    Uses PIXEL dimensions for capacity/shape (stable).
    Uses current content for semantic topics.

    Args:
        layout: Current layout state dict.
        display_meta: Display metadata dict with peer_id, width, height, x, y, tags.
        entities: Optional entity list for topic extraction.

    Returns:
        Profile dict with shape, capacity, topics, adjacency, etc.
    """
    peer_id = display_meta.get("peer_id", "")
    width = float(display_meta.get("width", 1920))
    height = float(display_meta.get("height", 1080))

    # Current entities on this display
    assigned = layout.get("surface_assignments", {}).get(peer_id, [])

    # Adjacency from all displays
    all_displays = layout.get("displays", [])
    adjacency = _compute_adjacency(display_meta, all_displays)

    # Primary display: largest area, or tagged "center"/"primary"
    tags = display_meta.get("tags", [])
    tags_lower = [t.lower() for t in tags]
    is_primary = "center" in tags_lower or "primary" in tags_lower

    return {
        "peer_id": peer_id,
        "width": width,
        "height": height,
        "aspect_ratio": width / height if height > 0 else 1.78,
        "shape": classify_display_shape(width, height),
        "capacity": estimate_capacity(width, height),
        "tags": tags,
        "is_primary": is_primary,
        "current_entity_count": len(assigned),
        "current_topics": _extract_current_topics(assigned, entities),
        "adjacency": adjacency,
    }


def build_all_display_profiles(
    layout: Dict[str, Any],
    entities: Optional[List[Dict]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Build profiles for all displays in the layout.

    If no display is tagged "center" or "primary", the largest display
    (by pixel area) is automatically marked as primary.

    Returns {peer_id: profile_dict}.
    """
    profiles: Dict[str, Dict[str, Any]] = {}
    for display_meta in layout.get("displays", []):
        peer_id = display_meta.get("peer_id")
        if peer_id:
            profiles[peer_id] = build_display_profile(layout, display_meta, entities)

    # If no display is explicitly primary, pick the largest by area
    if profiles and not any(p.get("is_primary") for p in profiles.values()):
        largest = max(profiles, key=lambda pid: profiles[pid]["width"] * profiles[pid]["height"])
        profiles[largest]["is_primary"] = True

    return profiles


# ---------------------------------------------------------------------------
# Auto-selection helpers — infer layout params from context
# ---------------------------------------------------------------------------


def auto_select_arrangement(
    region_w: float, region_h: float, entity_count: int
) -> str:
    """Auto-select entity arrangement based on region shape.

    - Very wide region (aspect > 3:1) with few entities → horizontal
    - Very tall region (aspect < 1:3) with few entities → vertical
    - Otherwise → grid
    """
    if region_w <= 0 or region_h <= 0:
        return "grid"
    aspect = region_w / region_h
    if aspect > 3.0 and entity_count <= 8:
        return "horizontal"
    if aspect < 1.0 / 3.0 and entity_count <= 8:
        return "vertical"
    return "grid"


def auto_select_group_spacing(
    display_count: int,
    total_entity_count: int,
    capacity: int = 12,
) -> str:
    """Auto-select inter-group spacing when the LLM doesn't specify.

    Args:
        display_count: Number of displays in use.
        total_entity_count: Total entities being placed.
        capacity: Estimated single-display capacity.
    """
    if display_count <= 1:
        # Single display: tight if dense, medium otherwise
        if total_entity_count > capacity * 0.8:
            return "tight"
        return "medium"
    if display_count == 2:
        return "medium"
    # 3+ displays
    return "medium"


def auto_select_layout_style(has_constraints: bool) -> str:  # noqa: ARG001
    """Auto-select layout style when the LLM doesn't specify.

    Both paths use "organic" but the presence of constraints determines
    which code path is taken in compute_graph_layout.  The parameter is
    accepted for future use (e.g., "packed" when no constraints and many
    entities).
    """
    return "organic"
