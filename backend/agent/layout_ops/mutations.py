"""Core layout mutation operations."""

from typing import Any, Dict, Optional

from .display import recalculate_surface_content_bounds


def _refresh_content_bounds(layout: Dict[str, Any]) -> Dict[str, Any]:
    """Recompute content bounds after a layout mutation."""
    layout["surface_content_bounds"] = recalculate_surface_content_bounds(layout)
    if "surface_visible_bounds" not in layout:
        layout["surface_visible_bounds"] = dict(layout.get("surface_bounds", {}))
    return layout


def move_entity(
    layout: Dict[str, Any],
    entity_id: str,
    target_surface: str,
    target_position: Optional[tuple] = None,
) -> Dict[str, Any]:
    """
    Move an entity to a different surface and optionally set its position.

    Args:
        layout: Current layout state
        entity_id: ID of entity to move
        target_surface: Target surface ID (e.g., "surface_0" or a peer_id)
        target_position: Optional (x, y) position on target surface

    Returns:
        Updated layout state
    """
    current_surface = None
    for surface_id, entities in layout["surface_assignments"].items():
        if entity_id in entities:
            current_surface = surface_id
            entities.remove(entity_id)
            break

    if current_surface is None:
        raise ValueError(f"Entity {entity_id} not found in any surface")

    if target_surface not in layout["surface_assignments"]:
        layout["surface_assignments"][target_surface] = []
    layout["surface_assignments"][target_surface].append(entity_id)

    if target_position:
        layout["node_positions"][entity_id] = target_position

    return _refresh_content_bounds(layout)


def adjust_entity_position(
    layout: Dict[str, Any], entity_id: str, new_position: tuple
) -> Dict[str, Any]:
    """
    Adjust the position of a specific entity.

    Args:
        layout: Current layout state
        entity_id: ID of entity to move
        new_position: New (x, y) position

    Returns:
        Updated layout state
    """
    if entity_id not in layout["node_positions"]:
        raise ValueError(f"Entity {entity_id} not found")

    layout["node_positions"][entity_id] = new_position
    return _refresh_content_bounds(layout)


def scale_layout(layout: Dict[str, Any], scale_factor: float) -> Dict[str, Any]:
    """
    Scale all positions in the layout by a factor.

    Args:
        layout: Current layout state
        scale_factor: Multiplier for all positions (e.g., 1.5 makes everything 50% larger)

    Returns:
        Updated layout state
    """
    for entity_id, (x, y) in layout["node_positions"].items():
        layout["node_positions"][entity_id] = (x * scale_factor, y * scale_factor)

    # Multi-display workspaces are display-local and should not be rescaled.
    # Without display metadata (single-surface fallback), bounds track content.
    if not layout.get("displays"):
        for surface_id, (min_x, min_y, max_x, max_y) in layout["surface_bounds"].items():
            layout["surface_bounds"][surface_id] = (
                min_x * scale_factor,
                min_y * scale_factor,
                max_x * scale_factor,
                max_y * scale_factor,
            )
        for surface_id, (min_x, min_y, max_x, max_y) in layout.get(
            "surface_visible_bounds", {}
        ).items():
            layout["surface_visible_bounds"][surface_id] = (
                min_x * scale_factor,
                min_y * scale_factor,
                max_x * scale_factor,
                max_y * scale_factor,
            )

    return _refresh_content_bounds(layout)


def resize_entity(
    layout: Dict[str, Any], entity_id: str, width: float, height: float
) -> Dict[str, Any]:
    """
    Resize a specific entity.

    Args:
        layout: Current layout state
        entity_id: ID of entity to resize
        width: New width
        height: New height

    Returns:
        Updated layout state
    """
    if entity_id not in layout.get("node_positions", {}):
        raise ValueError(f"Entity {entity_id} not found")

    if width <= 0 or height <= 0:
        raise ValueError("Width and height must be positive")

    if "node_sizes" not in layout:
        layout["node_sizes"] = {}
    layout["node_sizes"][entity_id] = [width, height]

    if "entity_dimensions" not in layout:
        layout["entity_dimensions"] = {}
    layout["entity_dimensions"][entity_id] = {"width": width, "height": height}

    return _refresh_content_bounds(layout)


def swap_entities(
    layout: Dict[str, Any], entity_id_1: str, entity_id_2: str
) -> Dict[str, Any]:
    """
    Swap the positions of two entities.

    Args:
        layout: Current layout state
        entity_id_1: First entity ID
        entity_id_2: Second entity ID

    Returns:
        Updated layout state
    """
    if (
        entity_id_1 not in layout["node_positions"]
        or entity_id_2 not in layout["node_positions"]
    ):
        raise ValueError("One or both entities not found")

    pos1 = layout["node_positions"][entity_id_1]
    pos2 = layout["node_positions"][entity_id_2]
    layout["node_positions"][entity_id_1] = pos2
    layout["node_positions"][entity_id_2] = pos1

    return _refresh_content_bounds(layout)
