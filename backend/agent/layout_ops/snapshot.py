"""Layout summary and semantic snapshot helpers."""

from typing import Any, Dict, List, Optional, Tuple

from .constants import MAX_THEMES_PER_ENTITY
from .dimensions import get_entity_dimension
from .display import get_surface_visible_bounds, get_surface_workspace_bounds

_SEMANTIC_FIELDS = (
    "item_type",
    "granularity",
    "domain",
    "location",
    "temporal_focus",
    "sentiment",
)

_CONTENT_FIELDS = ("item_type", "domain", "sentiment")

_BAND_TOLERANCE = 100.0
_READING_ORDER_BUCKET = 100.0


def _count_bands(values: List[float], tolerance: float = _BAND_TOLERANCE) -> int:
    """Count distinct 1D bands by proximity tolerance."""
    if not values:
        return 0
    sorted_vals = sorted(values)
    bands = 1
    for i in range(1, len(sorted_vals)):
        if sorted_vals[i] - sorted_vals[i - 1] > tolerance:
            bands += 1
    return bands


def _compute_display_geometry(
    layout: Dict[str, Any],
    entity_ids: List[str],
) -> Optional[Dict[str, Any]]:
    """Derive a compact geometric description of entities on a display."""
    node_positions = layout.get("node_positions", {})
    xs: List[float] = []
    ys: List[float] = []
    min_x = float("inf")
    min_y = float("inf")
    max_x_extent = 0.0
    max_y_extent = 0.0
    for eid in entity_ids:
        pos = node_positions.get(eid)
        if pos is None:
            continue
        x, y = pos[0], pos[1]
        w = get_entity_dimension(layout, eid, "width") or 400.0
        h = get_entity_dimension(layout, eid, "height") or 300.0
        xs.append(x)
        ys.append(y)
        if x < min_x:
            min_x = x
        if y < min_y:
            min_y = y
        if x + w > max_x_extent:
            max_x_extent = x + w
        if y + h > max_y_extent:
            max_y_extent = y + h
    if not xs:
        return None
    return {
        "entity_count": len(xs),
        "row_bands": _count_bands(ys),
        "col_bands": _count_bands(xs),
        "bbox_width": max_x_extent - min_x,
        "bbox_height": max_y_extent - min_y,
    }


def _reading_order_key(
    entity_id: str,
    node_positions: Dict[str, Any],
) -> Tuple[float, float]:
    """Sort key for top-to-bottom, then left-to-right traversal."""
    pos = node_positions.get(entity_id, (0.0, 0.0))
    return (round(pos[1] / _READING_ORDER_BUCKET), pos[0])


def get_layout_info(layout: Dict[str, Any]) -> str:
    """
    Get human-readable summary of the layout.

    Args:
        layout: Current layout state

    Returns:
        Formatted summary string
    """
    lines = []
    lines.append("**Layout Summary**")
    lines.append("")

    total_entities = sum(
        len(entities) for entities in layout["surface_assignments"].values()
    )
    lines.append(f"Total entities: {total_entities}")
    lines.append(f"Number of surfaces: {len(layout['surface_assignments'])}")
    lines.append("")

    display_tags = {}
    for disp in layout.get("displays", []):
        pid = disp.get("peer_id", "")
        tags = disp.get("tags", [])
        if tags:
            display_tags[pid] = tags

    lines.append("**Display Assignments (`display_id`):**")
    entity_names = layout.get("entity_names", {})
    for surface_id, entity_ids in sorted(layout["surface_assignments"].items()):
        tags = display_tags.get(surface_id)
        if tags:
            label = f"{', '.join(tags)} display ({surface_id})"
        else:
            label = surface_id

        workspace_bounds = get_surface_workspace_bounds(layout, surface_id)
        visible_bounds = get_surface_visible_bounds(layout, surface_id)

        disp_info = next(
            (d for d in layout.get("displays", []) if d.get("peer_id") == surface_id),
            None,
        )

        if workspace_bounds:
            lines.append(
                f"- {label}: {len(entity_ids)} entities "
                f"[workspace: {_format_bounds(workspace_bounds)}]"
            )
        else:
            lines.append(f"- {label}: {len(entity_ids)} entities")

        content_bounds = layout.get("surface_content_bounds", {}).get(surface_id)
        if visible_bounds and visible_bounds != workspace_bounds:
            lines.append(f"  Visible canvas: {_format_bounds(visible_bounds)}")

        if (
            workspace_bounds
            and content_bounds
            and content_bounds != workspace_bounds
        ):
            lines.append(
                f"  Content extent: {_format_bounds(content_bounds)}"
            )

        if disp_info:
            camera = disp_info.get("camera")
            if camera:
                lines.append(
                    f"  Camera: pan_x={camera.get('pan_x', 0):.1f}, pan_y={camera.get('pan_y', 0):.1f}, zoom={camera.get('zoom', 1):.2f}"
                )

        geometry = _compute_display_geometry(layout, entity_ids)
        if geometry and geometry["entity_count"] >= 2:
            lines.append(
                f"  Arrangement: {geometry['entity_count']} views in "
                f"{geometry['row_bands']} row bands × {geometry['col_bands']} col bands, "
                f"{geometry['bbox_width']:.0f}×{geometry['bbox_height']:.0f}px"
            )

        for entity_id in entity_ids:
            pos = layout["node_positions"].get(entity_id, (0, 0))
            name = entity_names.get(entity_id, entity_id)
            lines.append(f"  - {name}")
            lines.append(f"    ID: {entity_id}")
            lines.append(f"    Position: ({pos[0]:.1f}, {pos[1]:.1f})")

    if layout.get("metadata"):
        lines.append("")
        lines.append("**Layout Metadata:**")
        metadata = layout["metadata"]
        if "layout_strategies" in metadata:
            lines.append("- Layout strategies:")
            for surface_id, strategy in metadata["layout_strategies"].items():
                lines.append(f"  - {surface_id}: {strategy}")
        if "zone_distribution" in metadata:
            lines.append("- Zone distribution:")
            for zone, count in metadata["zone_distribution"].items():
                lines.append(f"  - {zone}: {count}")

    return "\n".join(lines)


def _build_display_labels(layout: Dict[str, Any]) -> Dict[str, str]:
    """Map each surface/peer_id to a human-readable display label."""
    labels: Dict[str, str] = {}
    for disp in layout.get("displays", []):
        peer_id = disp.get("peer_id", "")
        tags = disp.get("tags", [])
        labels[peer_id] = ", ".join(tags) if tags else peer_id
    return labels


def _format_bounds(bounds: tuple[float, float, float, float]) -> str:
    """Render bounds tuple consistently for summaries."""
    return (
        f"({bounds[0]:.1f}, {bounds[1]:.1f}) "
        f"to ({bounds[2]:.1f}, {bounds[3]:.1f})"
    )


def _build_entity_to_display(surface_assignments: Dict[str, list]) -> Dict[str, str]:
    """Invert surface_assignments into an entity_id -> surface_id lookup."""
    result: Dict[str, str] = {}
    for surface_id, entity_ids in surface_assignments.items():
        for eid in entity_ids:
            result[eid] = surface_id
    return result


def _summarize_displays(
    layout: Dict[str, Any],
    surface_assignments: Dict[str, list],
    entity_names: Dict[str, str],
    display_labels: Dict[str, str],
    semantics_by_id: Dict[str, Dict[str, Any]],
) -> list:
    """Build a per-display summary with per-view positions and semantics."""
    summary = []
    node_positions = layout.get("node_positions", {})
    for surface_id, entity_ids in surface_assignments.items():
        sorted_ids = sorted(
            entity_ids, key=lambda e: _reading_order_key(e, node_positions)
        )
        views = []
        for eid in sorted_ids:
            pos = node_positions.get(eid, (0.0, 0.0))
            entry: Dict[str, Any] = {
                "name": entity_names.get(eid, eid),
                "entity_id": eid,
                "position": {"x": round(pos[0], 1), "y": round(pos[1], 1)},
            }
            sem = semantics_by_id.get(eid, {})
            for field in _SEMANTIC_FIELDS:
                val = sem.get(field)
                if val:
                    entry[field] = val
            themes = sem.get("key_themes")
            if themes:
                entry["key_themes"] = themes[:MAX_THEMES_PER_ENTITY]
            views.append(entry)

        summary.append(
            {
                "display": display_labels.get(surface_id, surface_id),
                "display_id": surface_id,
                "entity_count": len(entity_ids),
                "views": views,
                "geometry": _compute_display_geometry(layout, entity_ids),
                "workspace_bounds": _bounds_to_dict(
                    get_surface_workspace_bounds(layout, surface_id)
                ),
                "visible_bounds": _bounds_to_dict(
                    get_surface_visible_bounds(layout, surface_id)
                ),
                "content_bounds": _bounds_to_dict(
                    layout.get("surface_content_bounds", {}).get(surface_id)
                ),
            }
        )
    return summary


def _bounds_to_dict(
    bounds: Optional[tuple[float, float, float, float]],
) -> Optional[Dict[str, float]]:
    """Convert tuple bounds to a JSON-friendly dict."""
    if bounds is None:
        return None
    min_x, min_y, max_x, max_y = bounds
    return {
        "min_x": min_x,
        "min_y": min_y,
        "max_x": max_x,
        "max_y": max_y,
    }


def _summarize_clusters(
    entity_clusters: Dict[str, list],
    entity_names: Dict[str, str],
    entity_to_display: Dict[str, str],
    display_labels: Dict[str, str],
) -> list:
    """Build cluster groupings showing how members are distributed across displays."""
    members_by_cluster: Dict[str, list] = {}
    for eid, cluster_labels in entity_clusters.items():
        for label in cluster_labels:
            members_by_cluster.setdefault(label, []).append(eid)

    summary = []
    for label, members in members_by_cluster.items():
        if len(members) < 2:
            continue

        views_by_display: Dict[str, list] = {}
        for eid in members:
            surface_id = entity_to_display.get(eid)
            if surface_id is None:
                continue
            display_name = display_labels.get(surface_id, surface_id)
            views_by_display.setdefault(display_name, []).append(
                entity_names.get(eid, eid)
            )

        summary.append(
            {
                "cluster": label,
                "member_count": len(members),
                "by_display": views_by_display,
            }
        )

    return summary


def _build_semantics_by_id(
    entities: Optional[list],
    valid_ids: set,
) -> Dict[str, Dict[str, Any]]:
    """Build entity_id → semantic-fields lookup map."""
    result: Dict[str, Dict[str, Any]] = {}
    if not entities:
        return result
    for entity in entities:
        entity_id = entity.get("entity_id") or entity.get("id")
        if not entity_id or entity_id not in valid_ids:
            continue
        semantics = entity.get("semantics") or {}
        fields: Dict[str, Any] = {}
        for field in _SEMANTIC_FIELDS:
            val = semantics.get(field)
            if val:
                fields[field] = val
        themes = semantics.get("key_themes")
        if themes:
            fields["key_themes"] = themes
        result[entity_id] = fields
    return result


def gather_layout_snapshot(
    layout: Dict[str, Any],
    entities: Optional[list] = None,
    display_id: Optional[str] = None,
    entity_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Gather a semantic snapshot of the current layout for the LLM to reason about.

    Pure read-only. Joins positions with per-view semantics inside each display,
    sorted in reading order, and surfaces a geometric fingerprint per display.

    Scoping: `entity_ids` takes precedence over `display_id`. With either set,
    cluster and display entries are strictly filtered to in-scope members.
    """
    entity_names = layout.get("entity_names", {})
    entity_clusters = layout.get("entity_clusters", {})
    surface_assignments = layout.get("surface_assignments", {})

    if entity_ids:
        scope_set: Optional[set] = set(entity_ids)
    elif display_id:
        scope_set = set(surface_assignments.get(display_id, []))
    else:
        scope_set = None

    if scope_set is not None:
        scoped_assignments = {
            sid: [e for e in eids if e in scope_set]
            for sid, eids in surface_assignments.items()
        }
        scoped_assignments = {k: v for k, v in scoped_assignments.items() if v}
    else:
        scoped_assignments = surface_assignments

    display_labels = _build_display_labels(layout)
    entity_to_display = _build_entity_to_display(scoped_assignments)

    valid_ids = set(layout.get("node_positions", {}).keys())
    if scope_set is not None:
        valid_ids &= scope_set
    semantics_by_id = _build_semantics_by_id(entities, valid_ids)

    snapshot: Dict[str, Any] = {
        "displays": _summarize_displays(
            layout,
            scoped_assignments,
            entity_names,
            display_labels,
            semantics_by_id,
        ),
    }

    if scope_set is not None:
        scoped_clusters = {
            eid: lbls for eid, lbls in entity_clusters.items() if eid in scope_set
        }
    else:
        scoped_clusters = entity_clusters

    clusters = _summarize_clusters(
        scoped_clusters, entity_names, entity_to_display, display_labels
    )
    if clusters:
        snapshot["clusters"] = clusters

    return snapshot


def gather_entity_content(
    layout: Dict[str, Any],
    entities: Optional[list],
    entity_ids: List[str],
) -> Dict[str, Any]:
    """
    Return raw `value` text and `summary` for the requested entity IDs.

    Separate from `gather_layout_snapshot` so the agent opts in to verbose
    content only when a query actually needs to read the text. Scope is
    required: callers must pass a narrowed list of IDs.
    """
    valid_ids = (
        set(layout.get("node_positions", {}).keys()) if layout else set()
    )
    entity_names = layout.get("entity_names", {}) if layout else {}

    requested = [eid for eid in entity_ids if eid]
    wanted_set = {eid for eid in requested if eid in valid_ids}
    missing = [eid for eid in requested if eid not in valid_ids]

    entries: List[Dict[str, Any]] = []
    seen: set = set()
    if entities:
        for entity in entities:
            eid = entity.get("entity_id") or entity.get("id")
            if not eid or eid not in wanted_set or eid in seen:
                continue
            seen.add(eid)
            semantics = entity.get("semantics") or {}
            record: Dict[str, Any] = {
                "entity_id": eid,
                "name": entity_names.get(eid, eid),
            }
            etype = entity.get("type")
            if etype:
                record["type"] = etype
            for field in _CONTENT_FIELDS:
                val = semantics.get(field)
                if val:
                    record[field] = val
            value = entity.get("value")
            if isinstance(value, str) and value:
                record["value"] = value
            summary = semantics.get("summary")
            if summary:
                record["summary"] = summary
            entries.append(record)

    entries.sort(key=lambda r: requested.index(r["entity_id"]))

    unresolved = [eid for eid in wanted_set if eid not in seen]
    for eid in unresolved:
        missing.append(eid)

    result: Dict[str, Any] = {"entries": entries}
    if missing:
        result["missing"] = missing
    return result
