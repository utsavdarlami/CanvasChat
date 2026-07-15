"""Node dimension parsing and lookup helpers."""

from typing import Any, Dict, Optional


def _parse_positive_float(value: Any) -> Optional[float]:
    """Parse value into a positive float, returning None when invalid."""
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return parsed


def get_entity_dimension(
    layout: Dict[str, Any],
    entity_id: str,
    axis: str,
) -> Optional[float]:
    """
    Get a stored node dimension value for an entity.

    Supports both dict-based entries: {"width": 460, "height": 380}
    and tuple/list entries: [460, 380] for backward compatibility.
    """
    dims = layout.get("entity_dimensions", {}).get(entity_id)
    if isinstance(dims, dict):
        return _parse_positive_float(dims.get(axis))
    if isinstance(dims, (list, tuple)) and len(dims) == 2:
        idx = 0 if axis == "width" else 1
        return _parse_positive_float(dims[idx])
    return None
