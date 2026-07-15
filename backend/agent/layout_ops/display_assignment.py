"""Semantic-aware group → display assignment.

Assigns entity groups to displays considering capacity, shape affinity,
semantic topic overlap, and load balance.  Replaces the basic
load-balancing heuristic in planning.py.
"""

from typing import Any, Dict, List, Optional, Tuple


# Minimum edge weight to cluster groups onto the same display.
AFFINITY_THRESHOLD = 0.4

# Scoring weights (must sum to 1.0)
_W_CAPACITY = 0.35
_W_SHAPE = 0.25
_W_TOPIC = 0.15
_W_BALANCE = 0.1
_W_PRIORITY = 0.15  # bonus for high-priority groups on primary display

# Priority values → numeric boost
_PRIORITY_BOOST = {
    "high": 1.0,
    "medium": 0.5,
    "low": 0.0,
}


def _cluster_groups_by_edges(
    groups: Dict[str, List[str]],
    edges: List[Dict],
    threshold: float = AFFINITY_THRESHOLD,
) -> List[List[str]]:
    """Cluster groups connected by strong edges using union-find.

    Groups linked by edges with weight >= threshold are kept together.
    Returns list of clusters (each a list of group labels), sorted by
    total entity count descending.
    """
    parent: Dict[str, str] = {label: label for label in groups}

    def _find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def _union(a: str, b: str) -> None:
        ra, rb = _find(a), _find(b)
        if ra != rb:
            parent[ra] = rb

    for edge in edges:
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        weight = float(edge.get("weight", 0.0))
        if src in parent and tgt in parent and weight >= threshold:
            _union(src, tgt)

    # Group labels by cluster root
    clusters: Dict[str, List[str]] = {}
    for label in groups:
        root = _find(label)
        clusters.setdefault(root, []).append(label)

    # Sort clusters by total entity count descending (largest first)
    return sorted(
        clusters.values(),
        key=lambda labels: sum(len(groups[l]) for l in labels),
        reverse=True,
    )


def _estimate_group_shape_preference(
    group_entity_count: int,
) -> str:
    """Rough estimate of whether a group prefers wide or tall space.

    Simple heuristic: large groups benefit from wide displays (more columns),
    small groups are fine anywhere.

    Returns: "wide", "tall", or "balanced".
    """
    if group_entity_count >= 8:
        return "wide"  # large groups pack better in wide space
    return "balanced"


def _shape_affinity_score(group_shape: str, display_shape: str) -> float:
    """Score how well a group's shape preference matches a display shape.

    Returns 0.0 (mismatch) to 1.0 (perfect match).
    """
    if group_shape == "balanced":
        return 0.7  # neutral — ok anywhere

    wide_displays = {"ultrawide", "landscape"}
    tall_displays = {"portrait", "tall"}

    if group_shape == "wide" and display_shape in wide_displays:
        return 1.0
    if group_shape == "tall" and display_shape in tall_displays:
        return 1.0
    if group_shape == "wide" and display_shape == "square":
        return 0.6
    if group_shape == "tall" and display_shape == "square":
        return 0.6
    return 0.3  # mismatch


def _topic_overlap_score(
    group_topics: List[str],
    display_topics: List[str],
) -> float:
    """Jaccard-like overlap between group topics and display's current topics.

    Returns 0.0 (no overlap) to 1.0 (perfect match).
    """
    if not group_topics or not display_topics:
        return 0.5  # neutral when no topic info available

    group_set = set(t.lower() for t in group_topics)
    display_set = set(t.lower() for t in display_topics)

    intersection = len(group_set & display_set)
    union = len(group_set | display_set)

    if union == 0:
        return 0.5
    return intersection / union


def _extract_cluster_topics(
    cluster_labels: List[str],
    groups: Dict[str, List[str]],
    entities: Optional[List[Dict]] = None,
) -> List[str]:
    """Extract topic keywords from entities in a cluster's groups."""
    if not entities:
        return []

    entity_map: Dict[str, Dict] = {}
    for e in entities:
        eid = e.get("id") or e.get("entity_id")
        if eid:
            entity_map[eid] = e

    topics: List[str] = []
    for label in cluster_labels:
        for eid in groups.get(label, []):
            entity = entity_map.get(eid)
            if not entity:
                continue
            semantics = entity.get("semantics") or {}
            domain = semantics.get("domain")
            if domain:
                topics.append(domain)
            for theme in semantics.get("key_themes", [])[:2]:
                if isinstance(theme, str):
                    topics.append(theme)

    return topics


def _score_assignment(
    cluster_labels: List[str],
    groups: Dict[str, List[str]],
    profile: Dict[str, Any],
    current_load: int,
    cluster_topics: List[str],
    group_priorities: Optional[Dict[str, str]] = None,
) -> float:
    """Score how well a cluster fits on a display.

    Factors (weighted sum, all normalized to 0-1):
        - capacity_fit (0.35): does cluster entity count fit remaining capacity?
        - shape_affinity (0.25): do group shapes match display shape?
        - topic_overlap (0.15): do group topics match display's current topics?
        - load_balance (0.10): prefer less-loaded displays
        - priority_match (0.15): high-priority groups prefer primary display
    """
    cluster_count = sum(len(groups[l]) for l in cluster_labels)
    capacity = profile.get("capacity", 12)
    remaining = max(0, capacity - current_load)

    # Capacity fit: 1.0 if cluster fits, degrades linearly if overflowing
    if remaining >= cluster_count:
        cap_score = 1.0
    elif remaining > 0:
        cap_score = remaining / cluster_count
    else:
        cap_score = 0.1  # display is full, but don't completely exclude

    # Shape affinity
    group_shape = _estimate_group_shape_preference(cluster_count)
    display_shape = profile.get("shape", "landscape")
    shape_score = _shape_affinity_score(group_shape, display_shape)

    # Topic overlap
    display_topics = profile.get("current_topics", [])
    topic_score = _topic_overlap_score(cluster_topics, display_topics)

    # Load balance: prefer emptier displays
    if capacity > 0:
        balance_score = 1.0 - (current_load / capacity)
    else:
        balance_score = 0.5

    # Priority match: high-priority groups get a boost on primary displays
    priority_score = 0.5  # neutral default
    _gp = group_priorities or {}
    if _gp:
        # Use the highest priority in the cluster
        max_boost = max(
            _PRIORITY_BOOST.get(_gp.get(label, "medium"), 0.5)
            for label in cluster_labels
        )
        is_primary = profile.get("is_primary", False)
        if is_primary:
            priority_score = max_boost  # high priority + primary = high score
        else:
            # Non-primary display: invert — high priority groups penalized here
            priority_score = 1.0 - max_boost * 0.5

    return (
        _W_CAPACITY * cap_score
        + _W_SHAPE * shape_score
        + _W_TOPIC * topic_score
        + _W_BALANCE * max(0.0, balance_score)
        + _W_PRIORITY * priority_score
    )


def assign_groups_to_displays(
    groups: Dict[str, List[str]],
    edges: List[Dict],
    layout: Dict[str, Any],
    display_profiles: Dict[str, Dict[str, Any]],
    entities: Optional[List[Dict]] = None,
    group_priorities: Optional[Dict[str, str]] = None,
) -> Dict[str, List[Tuple[str, List[str]]]]:
    """Assign entity groups to displays using semantic-aware scoring.

    Algorithm:
        1. Cluster groups by edge connectivity (union-find, threshold 0.4)
        2. Sort clusters largest-first
        3. For each cluster, score all displays → assign to highest-scoring
        4. Track per-display load for balance scoring

    Args:
        groups: {label: [entity_ids]} mapping.
        edges: List of edge dicts with source, target, weight.
        layout: Current layout state.
        display_profiles: {peer_id: profile} from build_all_display_profiles.
        entities: Optional entity list for topic extraction.
        group_priorities: Optional {label: "high"|"medium"|"low"}.
            High-priority groups prefer the primary display.

    Returns:
        {display_id: [(group_label, entity_ids)]}
    """
    display_ids = list(display_profiles.keys())
    if not display_ids:
        return {}

    # Initialize assignment and load tracking
    assignment: Dict[str, List[Tuple[str, List[str]]]] = {
        did: [] for did in display_ids
    }
    load: Dict[str, int] = {did: 0 for did in display_ids}

    # Cluster groups by edge connectivity
    clusters = _cluster_groups_by_edges(groups, edges)

    # Assign each cluster to the best-scoring display
    for cluster_labels in clusters:
        cluster_topics = _extract_cluster_topics(
            cluster_labels, groups, entities
        )

        best_display = display_ids[0]
        best_score = -1.0

        for did in display_ids:
            score = _score_assignment(
                cluster_labels,
                groups,
                display_profiles[did],
                load[did],
                cluster_topics,
                group_priorities=group_priorities,
            )
            if score > best_score:
                best_score = score
                best_display = did

        # Assign all groups in this cluster to the winning display
        for label in cluster_labels:
            assignment[best_display].append((label, groups[label]))
        load[best_display] += sum(len(groups[l]) for l in cluster_labels)

    return assignment
