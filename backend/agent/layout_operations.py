"""Core layout manipulation functions.

This module is a backward-compatible facade over smaller, responsibility-focused
modules in ``agent.layout_ops``.
"""

from .layout_ops.arrangement import (
    compute_arrangement_info,
    compute_arrangement_positions,
    compute_entities_bounds,
    compute_fit_camera,
    fit_display_camera_to_entities_if_needed,
    get_node_sizes_if_available,
)
from .layout_ops.constants import (
    CAMERA_FIT_MARGIN,
    DEFAULT_MIN_NODE_DISTANCE,
    DEFAULT_NODE_GAP,
    MAX_CAMERA_ZOOM,
    MAX_THEMES_PER_ENTITY,
    MIN_CAMERA_ZOOM,
)
from .layout_ops.dimensions import _parse_positive_float, get_entity_dimension
from .layout_ops.display import (
    _build_display_surfaces,
    _single_surface_fallback,
    get_surface_visible_bounds,
    get_surface_workspace_bounds,
    recalculate_surface_content_bounds,
    resolve_display_name,
)
from .layout_ops.io import (
    export_to_graph_format,
    load_layout_from_output,
    normalize_entity_tags_map,
)
from .layout_ops.mutations import (
    adjust_entity_position,
    move_entity,
    resize_entity,
    scale_layout,
    swap_entities,
)
from .layout_ops.positioning import (
    find_available_position,
)
from .layout_ops.planning import (
    validate_layout,
)
from .layout_ops.display_assignment import assign_groups_to_displays
from .layout_ops.display_profile import (
    auto_select_arrangement,
    auto_select_group_spacing,
    auto_select_layout_style,
    build_all_display_profiles,
    build_display_profile,
    classify_display_shape,
    estimate_capacity,
)
from .layout_ops.regions import REGION_SLICES, slice_bounds_for_region
from .layout_ops.arrangement_inference import (
    infer_arrangement,
    infer_display_arrangement,
)
from .layout_ops.snapshot import (
    gather_entity_content,
    gather_layout_snapshot,
    get_layout_info,
)
from .layout_ops.spatial_summary import summarize_arrangement, summarize_group_layout

__all__ = [
    "resolve_display_name",
    "_parse_positive_float",
    "get_entity_dimension",
    "load_layout_from_output",
    "_single_surface_fallback",
    "_build_display_surfaces",
    "get_surface_workspace_bounds",
    "get_surface_visible_bounds",
    "recalculate_surface_content_bounds",
    "compute_arrangement_info",
    "compute_arrangement_positions",
    "compute_entities_bounds",
    "compute_fit_camera",
    "fit_display_camera_to_entities_if_needed",
    "get_node_sizes_if_available",
    "move_entity",
    "adjust_entity_position",
    "resize_entity",
    "scale_layout",
    "get_layout_info",
    "swap_entities",
    "export_to_graph_format",
    "normalize_entity_tags_map",
    "find_available_position",
    "gather_entity_content",
    "gather_layout_snapshot",
    "infer_arrangement",
    "infer_display_arrangement",
    "DEFAULT_NODE_GAP",
    "MIN_CAMERA_ZOOM",
    "MAX_CAMERA_ZOOM",
    "CAMERA_FIT_MARGIN",
    "MAX_THEMES_PER_ENTITY",
    "DEFAULT_MIN_NODE_DISTANCE",
    "REGION_SLICES",
    "slice_bounds_for_region",
    "validate_layout",
    "summarize_arrangement",
    "summarize_group_layout",
    "assign_groups_to_displays",
    "build_all_display_profiles",
    "build_display_profile",
    "classify_display_shape",
    "estimate_capacity",
    "auto_select_arrangement",
    "auto_select_group_spacing",
    "auto_select_layout_style",
]
