"""Layout input/output transformation helpers."""

import re
from typing import Any, Dict, Optional

from .dimensions import _parse_positive_float, get_entity_dimension
from .display import _build_display_surfaces

_TAG_SEPARATOR_RE = re.compile(r"[_\s]+")


def _normalize_tag_display(tag: str) -> str:
    return _TAG_SEPARATOR_RE.sub(" ", tag.strip()).strip()


def _canonical_tag_key(tag: str) -> str:
    normalized = _normalize_tag_display(tag)
    return normalized.lower() if normalized else ""


def normalize_entity_tags_map(raw: Any) -> Dict[str, list[str]]:
    if not isinstance(raw, dict):
        return {}

    normalized: Dict[str, list[str]] = {}
    for entity_id, tags in raw.items():
        if not isinstance(entity_id, str) or not isinstance(tags, list):
            continue
        seen: set[str] = set()
        cleaned: list[str] = []
        for tag in tags:
            if not isinstance(tag, str):
                continue
            label = _normalize_tag_display(tag)
            key = _canonical_tag_key(label)
            if not key or key in seen:
                continue
            seen.add(key)
            cleaned.append(label)
        if cleaned:
            normalized[entity_id] = cleaned
    return normalized


def load_layout_from_output(
    layout_data: Dict[str, Any],
    display_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Load an existing layout from visualize_cached_data.py or test_generate_llm_layout.py output.

    Args:
        layout_data: Dictionary containing layout information in graph format:
            - nodes: List of nodes with entity_id, name, x, y, clusters
            - links: List of edges
            - graph: Optional metadata
        display_context: Optional display context from client with multi-display info

    Returns:
        Normalized layout state dictionary
    """
    if "nodes" in layout_data:
        node_positions = {}
        entity_names = {}
        entity_clusters = {}
        entity_dimensions = {}
        entity_display_ids = {}

        for node in layout_data["nodes"]:
            entity_id = node.get("entity_id") or node.get("id")
            x = node.get("x", 0.0)
            y = node.get("y", 0.0)
            name = node.get("name") or node.get("display_name", entity_id)
            clusters = node.get("clusters", [])
            display_id = node.get("display_id")

            node_positions[entity_id] = (x, y)
            entity_names[entity_id] = name
            entity_clusters[entity_id] = clusters
            if display_id:
                entity_display_ids[entity_id] = display_id

            width = _parse_positive_float(node.get("width"))
            height = _parse_positive_float(node.get("height"))
            if width is not None or height is not None:
                entry = {}
                if width is not None:
                    entry["width"] = width
                if height is not None:
                    entry["height"] = height
                entity_dimensions[entity_id] = entry

        (
            surface_assignments,
            surface_bounds,
            surface_visible_bounds,
            surface_content_bounds,
            displays,
        ) = (
            _build_display_surfaces(
                node_positions,
                entity_display_ids,
                display_context,
                entity_dimensions=entity_dimensions,
            )
        )

        metadata = layout_data.get("graph", {}).get("metadata", {})
        if "layout_reasoning" in layout_data.get("graph", {}):
            metadata["layout_reasoning"] = layout_data["graph"]["layout_reasoning"]

        result = {
            "node_positions": node_positions,
            "surface_assignments": surface_assignments,
            "surface_bounds": surface_bounds,
            "surface_visible_bounds": surface_visible_bounds,
            "surface_content_bounds": surface_content_bounds,
            "metadata": metadata,
            "entity_names": entity_names,
            "entity_clusters": entity_clusters,
            "entity_dimensions": entity_dimensions,
            "highlighted_entities": [],
            "focused_entities": [],
            "entity_tags": normalize_entity_tags_map(layout_data.get("entity_tags")),
        }

        if displays:
            result["displays"] = displays

        return result

    if "distribution" in layout_data:
        dist = layout_data["distribution"]
        sb = (
            dist.surface_bounds
            if hasattr(dist, "surface_bounds")
            else dist.get("surface_bounds", {})
        )
        return {
            "node_positions": dist.node_positions
            if hasattr(dist, "node_positions")
            else dist.get("node_positions", {}),
            "surface_assignments": dist.surface_assignments
            if hasattr(dist, "surface_assignments")
            else dist.get("surface_assignments", {}),
            "surface_bounds": sb,
            "surface_visible_bounds": dist.surface_visible_bounds
            if hasattr(dist, "surface_visible_bounds")
            else dist.get("surface_visible_bounds", dict(sb)),
            "surface_content_bounds": dict(sb),
            "metadata": dist.metadata
            if hasattr(dist, "metadata")
            else dist.get("metadata", {}),
            "entity_names": {},
            "entity_clusters": {},
            "entity_dimensions": {},
            "displays": [],
            "highlighted_entities": [],
            "focused_entities": [],
            "entity_tags": {},
        }

    sb = layout_data.get("surface_bounds", {})
    return {
        "node_positions": layout_data.get("node_positions", {}),
        "surface_assignments": layout_data.get("surface_assignments", {}),
        "surface_bounds": sb,
        "surface_visible_bounds": layout_data.get("surface_visible_bounds", dict(sb)),
        "surface_content_bounds": layout_data.get("surface_content_bounds", dict(sb)),
        "metadata": layout_data.get("metadata", {}),
        "entity_names": layout_data.get("entity_names", {}),
        "entity_clusters": layout_data.get("entity_clusters", {}),
        "entity_dimensions": layout_data.get("entity_dimensions", {}),
        "displays": layout_data.get("displays", []),
        "highlighted_entities": layout_data.get("highlighted_entities", []),
        "focused_entities": layout_data.get("focused_entities", []),
        "entity_tags": normalize_entity_tags_map(layout_data.get("entity_tags")),
        "user_text_highlights": layout_data.get("user_text_highlights") or {},
    }


def export_to_graph_format(layout: Dict[str, Any]) -> Dict[str, Any]:
    """
    Export layout back to graph format.

    Args:
        layout: Current layout state

    Returns:
        Dictionary in graph format with nodes and links
    """
    entity_names = layout.get("entity_names", {})
    entity_clusters = layout.get("entity_clusters", {})

    entity_to_surface = {}
    for surface_id, entity_ids in layout.get("surface_assignments", {}).items():
        for eid in entity_ids:
            entity_to_surface[eid] = surface_id

    nodes = []
    for entity_id, (x, y) in layout["node_positions"].items():
        node = {
            "entity_id": entity_id,
            "id": entity_id,
            "name": entity_names.get(entity_id, entity_id),
            "display_name": entity_names.get(entity_id, entity_id),
            "clusters": entity_clusters.get(entity_id, []),
            "x": x,
            "y": y,
        }

        width = get_entity_dimension(layout, entity_id, "width")
        height = get_entity_dimension(layout, entity_id, "height")
        if width is not None:
            node["width"] = width
        if height is not None:
            node["height"] = height

        surface = entity_to_surface.get(entity_id)
        if surface and surface != "surface_0":
            node["display_id"] = surface

        nodes.append(node)

    graph_metadata = layout.get("metadata", {})

    result = {
        "graph": graph_metadata,
        "nodes": nodes,
    }

    displays = layout.get("displays", [])
    if displays:
        result["display_context"] = {"displays": displays}

    return result
