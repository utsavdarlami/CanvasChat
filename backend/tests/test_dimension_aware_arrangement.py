"""
Regression tests for dimension-aware arrangement and camera-fit behavior.
"""

import json
import math

from agent.layout_delta import calculate_layout_delta
from agent.layout_ops.arrangement import (
    DEFAULT_NODE_GAP,
    compute_arrangement_positions,
    fit_display_camera_to_entities_if_needed,
)
from agent.layout_ops.io import export_to_graph_format, load_layout_from_output
from agent.layout_ops.planning import validate_layout
from agent.layout_ops.snapshot import gather_layout_snapshot, get_layout_info


def test_load_and_export_preserve_node_dimensions():
    layout_data = {
        "nodes": [
            {
                "entity_id": "node-1",
                "id": "node-1",
                "name": "Node 1",
                "x": 100.0,
                "y": 80.0,
                "width": 460.0,
                "height": 380.0,
            }
        ],
        "links": [],
        "graph": {},
    }

    loaded = load_layout_from_output(layout_data)
    assert loaded["entity_dimensions"]["node-1"]["width"] == 460.0
    assert loaded["entity_dimensions"]["node-1"]["height"] == 380.0

    exported = export_to_graph_format(loaded)
    node = exported["nodes"][0]
    assert node["width"] == 460.0
    assert node["height"] == 380.0


def test_dimension_aware_horizontal_spacing_prevents_overlap():
    bounds = (0.0, 0.0, 1251.0, 714.0)
    sizes = [(460.0, 380.0)] * 6

    positions = compute_arrangement_positions(
        bounds=bounds,
        count=6,
        arrangement="horizontal",
        padding=0.1,
        node_sizes=sizes,
    )

    for i in range(5):
        x0, _ = positions[i]
        x1, _ = positions[i + 1]
        assert x1 - x0 >= (sizes[i][0] + DEFAULT_NODE_GAP - 1e-6)


def test_camera_fit_updates_when_display_is_too_narrow():
    entity_ids = [f"node-{idx}" for idx in range(6)]
    layout = {
        "node_positions": {},
        "surface_assignments": {"peer-right": entity_ids.copy()},
        "surface_bounds": {"peer-right": (0.0, 0.0, 1251.0, 714.0)},
        "entity_names": {entity_id: entity_id for entity_id in entity_ids},
        "entity_clusters": {},
        "entity_dimensions": {
            entity_id: {"width": 460.0, "height": 380.0} for entity_id in entity_ids
        },
        "links": [],
        "metadata": {},
        "displays": [
            {
                "peer_id": "peer-right",
                "tags": ["right"],
                "x": 1363,
                "y": 0,
                "width": 1251.0,
                "height": 714.0,
                "camera": {"pan_x": 0.0, "pan_y": 0.0, "zoom": 1.0},
                "visible_canvas": {
                    "min_x": 0.0,
                    "min_y": 0.0,
                    "max_x": 1251.0,
                    "max_y": 714.0,
                    "width": 1251.0,
                    "height": 714.0,
                },
            }
        ],
        "highlighted_entities": [],
        "focused_entities": [],
        "entity_tags": {},
    }

    node_sizes = [(460.0, 380.0)] * len(entity_ids)
    positions = compute_arrangement_positions(
        bounds=(0.0, 0.0, 1251.0, 714.0),
        count=len(entity_ids),
        arrangement="horizontal",
        padding=0.1,
        node_sizes=node_sizes,
    )
    layout["node_positions"] = {
        entity_id: position for entity_id, position in zip(entity_ids, positions)
    }

    camera_update = fit_display_camera_to_entities_if_needed(
        layout, "peer-right", entity_ids
    )
    assert camera_update is not None

    right_display = layout["displays"][0]
    assert right_display["camera"]["zoom"] < 1.0

    for idx in range(len(entity_ids) - 1):
        x0, _ = positions[idx]
        x1, _ = positions[idx + 1]
        assert x1 - x0 >= (460.0 + DEFAULT_NODE_GAP - 1e-6)


def test_layout_delta_includes_dimensions_for_updated_nodes():
    previous_layout = {
        "node_positions": {"node-1": (0.0, 0.0)},
        "surface_assignments": {"peer-right": ["node-1"]},
        "entity_names": {"node-1": "Node 1"},
    }
    current_layout = {
        "node_positions": {"node-1": (500.0, 120.0)},
        "surface_assignments": {"peer-right": ["node-1"]},
        "entity_names": {"node-1": "Node 1"},
        "entity_dimensions": {"node-1": {"width": 460.0, "height": 380.0}},
    }

    delta = calculate_layout_delta(previous_layout, current_layout)
    assert len(delta["updated_nodes"]) == 1
    updated = delta["updated_nodes"][0]
    assert updated["width"] == 460.0
    assert updated["height"] == 380.0


def test_multi_display_load_uses_workspace_bounds_not_visible_canvas():
    layout_data = {
        "nodes": [
            {
                "entity_id": "node-1",
                "id": "node-1",
                "name": "Node 1",
                "x": 1200.0,
                "y": 140.0,
                "width": 200.0,
                "height": 100.0,
                "display_id": "peer-right",
            }
        ],
        "links": [],
        "graph": {},
    }
    display_context = {
        "is_multi_display": True,
        "local_peer_id": "peer-right",
        "virtual_desktop": {
            "total_width": 2000,
            "total_height": 800,
            "displays": [
                {
                    "peer_id": "peer-right",
                    "tags": ["right"],
                    "x": 1000,
                    "y": 0,
                    "width": 1000.0,
                    "height": 800.0,
                    "node_ids": ["node-1"],
                    "camera": {"pan_x": -500.0, "pan_y": 0.0, "zoom": 1.0},
                    "visible_canvas": {
                        "min_x": 500.0,
                        "min_y": 0.0,
                        "max_x": 1500.0,
                        "max_y": 800.0,
                        "width": 1000.0,
                        "height": 800.0,
                    },
                }
            ],
        },
    }

    loaded = load_layout_from_output(layout_data, display_context=display_context)

    assert loaded["surface_bounds"]["peer-right"] == (0.0, 0.0, 1000.0, 800.0)
    assert loaded["surface_visible_bounds"]["peer-right"] == (
        500.0,
        0.0,
        1500.0,
        800.0,
    )
    # Content bounds should expand to include the full node rectangle.
    assert loaded["surface_content_bounds"]["peer-right"] == (
        0.0,
        0.0,
        1400.0,
        800.0,
    )


def test_validate_layout_ignores_overlap_across_displays():
    layout = {
        "node_positions": {
            "left-node": (100.0, 100.0),
            "right-node": (100.0, 100.0),
        },
        "surface_assignments": {
            "peer-left": ["left-node"],
            "peer-right": ["right-node"],
        },
        "surface_bounds": {
            "peer-left": (0.0, 0.0, 1000.0, 800.0),
            "peer-right": (0.0, 0.0, 1000.0, 800.0),
        },
        "entity_names": {
            "left-node": "Left Node",
            "right-node": "Right Node",
        },
        "entity_dimensions": {
            "left-node": {"width": 200.0, "height": 200.0},
            "right-node": {"width": 200.0, "height": 200.0},
        },
        "displays": [
            {"peer_id": "peer-left", "tags": ["left"], "width": 1000.0, "height": 800.0},
            {"peer_id": "peer-right", "tags": ["right"], "width": 1000.0, "height": 800.0},
        ],
    }

    report = validate_layout(layout)
    issue_types = [issue["type"] for issue in report["issues"]]

    assert "overlap" not in issue_types
    assert "spacing" not in issue_types


def test_validate_layout_balance_issue_is_json_safe_when_display_is_empty():
    layout = {
        "node_positions": {"left-node": (100.0, 100.0)},
        "surface_assignments": {"peer-left": ["left-node"], "peer-right": []},
        "surface_bounds": {
            "peer-left": (0.0, 0.0, 1000.0, 800.0),
            "peer-right": (0.0, 0.0, 1000.0, 800.0),
        },
        "entity_names": {"left-node": "Left Node"},
        "entity_dimensions": {"left-node": {"width": 200.0, "height": 200.0}},
        "displays": [
            {"peer_id": "peer-left", "tags": ["left"], "width": 1000.0, "height": 800.0},
            {
                "peer_id": "peer-right",
                "tags": ["right"],
                "width": 1000.0,
                "height": 800.0,
            },
        ],
    }

    report = validate_layout(layout)
    balance_issue = next(issue for issue in report["issues"] if issue["type"] == "balance")

    assert balance_issue["status"] == "imbalanced"
    assert balance_issue["ratio"] is None
    assert balance_issue["ratio_unbounded"] is True

    # Strict JSON serialization should succeed (no NaN/Infinity tokens).
    json.dumps(report, allow_nan=False)


def test_layout_summary_reports_workspace_visible_and_content_bounds():
    layout = {
        "node_positions": {
            "node-1": (1200.0, 140.0),
        },
        "surface_assignments": {"peer-right": ["node-1"]},
        "surface_bounds": {"peer-right": (0.0, 0.0, 1000.0, 800.0)},
        "surface_visible_bounds": {"peer-right": (500.0, 0.0, 1500.0, 800.0)},
        "surface_content_bounds": {"peer-right": (0.0, 0.0, 1400.0, 800.0)},
        "entity_names": {"node-1": "Node 1"},
        "entity_clusters": {},
        "entity_dimensions": {"node-1": {"width": 200.0, "height": 100.0}},
        "displays": [
            {
                "peer_id": "peer-right",
                "tags": ["right"],
                "width": 1000.0,
                "height": 800.0,
                "camera": {"pan_x": -500.0, "pan_y": 0.0, "zoom": 1.0},
                "visible_canvas": {
                    "min_x": 500.0,
                    "min_y": 0.0,
                    "max_x": 1500.0,
                    "max_y": 800.0,
                },
            }
        ],
        "metadata": {},
    }

    summary = get_layout_info(layout)

    assert "workspace: (0.0, 0.0) to (1000.0, 800.0)" in summary
    assert "Visible canvas: (500.0, 0.0) to (1500.0, 800.0)" in summary
    assert "Content extent: (0.0, 0.0) to (1400.0, 800.0)" in summary


def test_layout_snapshot_includes_workspace_visible_and_content_bounds():
    layout = {
        "node_positions": {
            "node-1": (1200.0, 140.0),
        },
        "surface_assignments": {"peer-right": ["node-1"]},
        "surface_bounds": {"peer-right": (0.0, 0.0, 1000.0, 800.0)},
        "surface_visible_bounds": {"peer-right": (500.0, 0.0, 1500.0, 800.0)},
        "surface_content_bounds": {"peer-right": (0.0, 0.0, 1400.0, 800.0)},
        "entity_names": {"node-1": "Node 1"},
        "entity_clusters": {},
        "displays": [{"peer_id": "peer-right", "tags": ["right"]}],
    }

    snapshot = gather_layout_snapshot(layout)
    display = snapshot["displays"][0]

    assert display["workspace_bounds"] == {
        "min_x": 0.0,
        "min_y": 0.0,
        "max_x": 1000.0,
        "max_y": 800.0,
    }
    assert display["visible_bounds"] == {
        "min_x": 500.0,
        "min_y": 0.0,
        "max_x": 1500.0,
        "max_y": 800.0,
    }
    assert display["content_bounds"] == {
        "min_x": 0.0,
        "min_y": 0.0,
        "max_x": 1400.0,
        "max_y": 800.0,
    }


# ---------------------------------------------------------------------------
# Alignment tests
# ---------------------------------------------------------------------------

_ALIGN_BOUNDS = (0.0, 0.0, 2000.0, 1000.0)
_ALIGN_PADDING = 0.1
# Content area after 10% padding: x 200..1800, y 100..900
_CONTENT_MIN_X = 200.0
_CONTENT_MAX_X = 1800.0
_CONTENT_MIN_Y = 100.0
_CONTENT_MAX_Y = 900.0


def test_vertical_align_left_places_column_at_left_edge():
    sizes = [(400.0, 300.0)] * 3
    positions = compute_arrangement_positions(
        bounds=_ALIGN_BOUNDS,
        count=3,
        arrangement="vertical",
        padding=_ALIGN_PADDING,
        node_sizes=sizes,
        align="left",
    )
    # All nodes should start at content_min_x
    for x, _ in positions:
        assert x == _CONTENT_MIN_X, f"Expected x={_CONTENT_MIN_X}, got {x}"


def test_vertical_align_right_places_column_at_right_edge():
    node_w = 400.0
    sizes = [(node_w, 300.0)] * 3
    positions = compute_arrangement_positions(
        bounds=_ALIGN_BOUNDS,
        count=3,
        arrangement="vertical",
        padding=_ALIGN_PADDING,
        node_sizes=sizes,
        align="right",
    )
    expected_x = _CONTENT_MAX_X - node_w  # 1800 - 400 = 1400
    for x, _ in positions:
        assert abs(x - expected_x) < 1e-6, f"Expected x={expected_x}, got {x}"


def test_vertical_align_center_is_default_behavior():
    sizes = [(400.0, 300.0)] * 3
    positions_default = compute_arrangement_positions(
        bounds=_ALIGN_BOUNDS,
        count=3,
        arrangement="vertical",
        padding=_ALIGN_PADDING,
        node_sizes=sizes,
    )
    positions_center = compute_arrangement_positions(
        bounds=_ALIGN_BOUNDS,
        count=3,
        arrangement="vertical",
        padding=_ALIGN_PADDING,
        node_sizes=sizes,
        align="center",
    )
    assert positions_default == positions_center


def test_horizontal_align_top_places_row_at_top_edge():
    sizes = [(400.0, 300.0)] * 3
    positions = compute_arrangement_positions(
        bounds=_ALIGN_BOUNDS,
        count=3,
        arrangement="horizontal",
        padding=_ALIGN_PADDING,
        node_sizes=sizes,
        align="top",
    )
    for _, y in positions:
        assert y == _CONTENT_MIN_Y, f"Expected y={_CONTENT_MIN_Y}, got {y}"


def test_horizontal_align_bottom_places_row_at_bottom_edge():
    node_h = 300.0
    sizes = [(400.0, node_h)] * 3
    positions = compute_arrangement_positions(
        bounds=_ALIGN_BOUNDS,
        count=3,
        arrangement="horizontal",
        padding=_ALIGN_PADDING,
        node_sizes=sizes,
        align="bottom",
    )
    expected_y = _CONTENT_MAX_Y - node_h  # 900 - 300 = 600
    for _, y in positions:
        assert abs(y - expected_y) < 1e-6, f"Expected y={expected_y}, got {y}"


def test_horizontal_align_center_is_default_behavior():
    sizes = [(400.0, 300.0)] * 3
    positions_default = compute_arrangement_positions(
        bounds=_ALIGN_BOUNDS,
        count=3,
        arrangement="horizontal",
        padding=_ALIGN_PADDING,
        node_sizes=sizes,
    )
    positions_center = compute_arrangement_positions(
        bounds=_ALIGN_BOUNDS,
        count=3,
        arrangement="horizontal",
        padding=_ALIGN_PADDING,
        node_sizes=sizes,
        align="center",
    )
    assert positions_default == positions_center


def test_grid_align_left_shifts_grid_to_left_edge():
    sizes = [(200.0, 200.0)] * 4
    positions = compute_arrangement_positions(
        bounds=_ALIGN_BOUNDS,
        count=4,
        arrangement="grid",
        padding=_ALIGN_PADDING,
        node_sizes=sizes,
        align="left",
    )
    # First column should start at content_min_x
    min_x_in_positions = min(x for x, _ in positions)
    assert abs(min_x_in_positions - _CONTENT_MIN_X) < 1e-6


def test_grid_align_right_shifts_grid_to_right_edge():
    node_w = 200.0
    sizes = [(node_w, 200.0)] * 4
    positions_right = compute_arrangement_positions(
        bounds=_ALIGN_BOUNDS,
        count=4,
        arrangement="grid",
        padding=_ALIGN_PADDING,
        node_sizes=sizes,
        align="right",
    )
    positions_center = compute_arrangement_positions(
        bounds=_ALIGN_BOUNDS,
        count=4,
        arrangement="grid",
        padding=_ALIGN_PADDING,
        node_sizes=sizes,
        align="center",
    )
    # Right-aligned grid should have larger x values than centered
    max_x_right = max(x for x, _ in positions_right)
    max_x_center = max(x for x, _ in positions_center)
    assert max_x_right >= max_x_center


def test_evenly_spaced_vertical_align_left():
    """Verify alignment works in the legacy (no node_sizes) path too."""
    positions = compute_arrangement_positions(
        bounds=_ALIGN_BOUNDS,
        count=3,
        arrangement="vertical",
        padding=_ALIGN_PADDING,
        align="left",
    )
    expected_x = _CONTENT_MIN_X  # min_x + w * padding = 0 + 2000*0.1 = 200
    for x, _ in positions:
        assert abs(x - expected_x) < 1e-6, f"Expected x={expected_x}, got {x}"


def test_evenly_spaced_horizontal_align_top():
    """Verify alignment works in the legacy (no node_sizes) path too."""
    positions = compute_arrangement_positions(
        bounds=_ALIGN_BOUNDS,
        count=3,
        arrangement="horizontal",
        padding=_ALIGN_PADDING,
        align="top",
    )
    expected_y = _CONTENT_MIN_Y  # min_y + h * padding = 0 + 1000*0.1 = 100
    for _, y in positions:
        assert abs(y - expected_y) < 1e-6, f"Expected y={expected_y}, got {y}"


# ---------------------------------------------------------------------------
# 2D bin-packing (grid) tests
# ---------------------------------------------------------------------------

_MIXED_SIZES = [
    (400.0, 300.0),
    (200.0, 150.0),
    (300.0, 400.0),
    (150.0, 200.0),
    (250.0, 300.0),
]


def _rects_overlap(
    pos_a: tuple[float, float],
    size_a: tuple[float, float],
    pos_b: tuple[float, float],
    size_b: tuple[float, float],
) -> bool:
    """Return True if two axis-aligned rectangles overlap."""
    ax, ay = pos_a
    aw, ah = size_a
    bx, by = pos_b
    bw, bh = size_b
    return ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by


def test_grid_binpack_mixed_sizes_no_overlap():
    """Bin-packed grid with mixed sizes must produce zero overlaps."""
    positions = compute_arrangement_positions(
        bounds=(0.0, 0.0, 2000.0, 1000.0),
        count=len(_MIXED_SIZES),
        arrangement="grid",
        padding=0.1,
        node_sizes=_MIXED_SIZES,
    )
    assert len(positions) == len(_MIXED_SIZES)

    for i in range(len(positions)):
        for j in range(i + 1, len(positions)):
            assert not _rects_overlap(
                positions[i], _MIXED_SIZES[i],
                positions[j], _MIXED_SIZES[j],
            ), f"Overlap between rect {i} and rect {j}"


def test_grid_binpack_better_density_than_uniform():
    """Bin-packed area should be smaller than uniform-grid area for mixed sizes."""
    bounds = (0.0, 0.0, 2000.0, 1000.0)
    positions = compute_arrangement_positions(
        bounds=bounds,
        count=len(_MIXED_SIZES),
        arrangement="grid",
        padding=0.1,
        node_sizes=_MIXED_SIZES,
    )
    widths = [s[0] for s in _MIXED_SIZES]
    heights = [s[1] for s in _MIXED_SIZES]

    # Bounding box of bin-packed result
    pack_max_x = max(positions[i][0] + widths[i] for i in range(len(_MIXED_SIZES)))
    pack_min_x = min(positions[i][0] for i in range(len(_MIXED_SIZES)))
    pack_max_y = max(positions[i][1] + heights[i] for i in range(len(_MIXED_SIZES)))
    pack_min_y = min(positions[i][1] for i in range(len(_MIXED_SIZES)))
    packed_area = (pack_max_x - pack_min_x) * (pack_max_y - pack_min_y)

    # Uniform grid area (old algorithm)
    max_w = max(widths)
    max_h = max(heights)
    cols = math.ceil(math.sqrt(len(_MIXED_SIZES)))
    rows = math.ceil(len(_MIXED_SIZES) / cols)
    uniform_area = (cols * max_w + DEFAULT_NODE_GAP * (cols - 1)) * (
        rows * max_h + DEFAULT_NODE_GAP * (rows - 1)
    )

    assert packed_area < uniform_area, (
        f"Packed area ({packed_area:.0f}) should be smaller than "
        f"uniform grid area ({uniform_area:.0f})"
    )


def test_grid_binpack_preserves_entity_order():
    """positions[i] must correspond to node_sizes[i]."""
    positions = compute_arrangement_positions(
        bounds=(0.0, 0.0, 2000.0, 1000.0),
        count=len(_MIXED_SIZES),
        arrangement="grid",
        padding=0.1,
        node_sizes=_MIXED_SIZES,
    )
    assert len(positions) == len(_MIXED_SIZES)
    # Each position must be a valid (x, y) tuple
    for i, (x, y) in enumerate(positions):
        assert isinstance(x, float), f"positions[{i}] x is not float: {x}"
        assert isinstance(y, float), f"positions[{i}] y is not float: {y}"


def test_grid_binpack_fallback_on_overflow():
    """All entities must be placed even when bounds are too small."""
    tiny_bounds = (0.0, 0.0, 300.0, 200.0)
    positions = compute_arrangement_positions(
        bounds=tiny_bounds,
        count=len(_MIXED_SIZES),
        arrangement="grid",
        padding=0.1,
        node_sizes=_MIXED_SIZES,
    )
    assert len(positions) == len(_MIXED_SIZES), (
        f"Expected {len(_MIXED_SIZES)} positions, got {len(positions)}"
    )
    # All positions must be finite numbers
    for i, (x, y) in enumerate(positions):
        assert math.isfinite(x) and math.isfinite(y), (
            f"positions[{i}] is not finite: ({x}, {y})"
        )


def test_grid_binpack_single_item():
    """Edge case: 1 item should produce exactly one centered position."""
    sizes = [(300.0, 200.0)]
    positions = compute_arrangement_positions(
        bounds=_ALIGN_BOUNDS,
        count=1,
        arrangement="grid",
        padding=_ALIGN_PADDING,
        node_sizes=sizes,
    )
    assert len(positions) == 1
    x, y = positions[0]
    # Should be centered in content area
    expected_x = _CONTENT_MIN_X + (_CONTENT_MAX_X - _CONTENT_MIN_X - 300.0) * 0.5
    expected_y = _CONTENT_MIN_Y + (_CONTENT_MAX_Y - _CONTENT_MIN_Y - 200.0) * 0.5
    assert abs(x - expected_x) < 1e-6, f"Expected x={expected_x}, got {x}"
    assert abs(y - expected_y) < 1e-6, f"Expected y={expected_y}, got {y}"


# ---------------------------------------------------------------------------
# MaxRects bin packing tests
# ---------------------------------------------------------------------------

from agent.layout_ops.arrangement import (
    _flow_wrap_grid,
    _maxrects_grid,
    _pack_grid,
    _should_use_maxrects,
)


def test_should_use_maxrects_high_variance():
    """MaxRects selected when tallest node > 2.5x shortest."""
    sizes = [(400, 200), (400, 600), (400, 150), (400, 1500)]
    assert _should_use_maxrects(sizes) is True


def test_should_use_maxrects_low_variance():
    """Flow-wrap used when heights are roughly uniform."""
    sizes = [(400, 300), (400, 350), (400, 280), (400, 320)]
    assert _should_use_maxrects(sizes) is False


def test_should_use_maxrects_too_few_nodes():
    """Flow-wrap used when fewer than 3 nodes regardless of variance."""
    sizes = [(400, 100), (400, 1000)]
    assert _should_use_maxrects(sizes) is False


def test_maxrects_grid_no_overlap():
    """All nodes placed by MaxRects must not overlap each other."""
    sizes = [
        (400, 168), (400, 1257), (400, 308), (400, 208),
        (400, 328), (400, 428), (400, 228), (400, 333),
    ]
    gap = 40.0
    positions = _maxrects_grid(sizes, 2000.0, gap)

    assert len(positions) == len(sizes)

    # Check no pair overlaps (using padded rects with gap)
    for i in range(len(sizes)):
        xi, yi = positions[i]
        wi, hi = sizes[i]
        for j in range(i + 1, len(sizes)):
            xj, yj = positions[j]
            wj, hj = sizes[j]
            # Two rects don't overlap if separated on at least one axis
            x_sep = xi + wi + gap <= xj + 1e-6 or xj + wj + gap <= xi + 1e-6
            y_sep = yi + hi + gap <= yj + 1e-6 or yj + hj + gap <= yi + 1e-6
            assert x_sep or y_sep, (
                f"Nodes {i} and {j} overlap: "
                f"({xi},{yi},{wi},{hi}) vs ({xj},{yj},{wj},{hj})"
            )


def test_maxrects_tighter_than_flowwrap_for_variable_heights():
    """MaxRects should produce a smaller bounding box than flow-wrap
    when node heights vary significantly (the whole point of the change).

    One very tall node (1500px) + six short ones (200px).  Flow-wrap puts
    the tall node in row 1 with one short node, wasting 1300px of vertical
    space beside it.  MaxRects stacks the short nodes in that pocket.
    """
    sizes = [
        (400.0, 1500.0),
        (400.0, 200.0), (400.0, 200.0), (400.0, 200.0),
        (400.0, 200.0), (400.0, 200.0), (400.0, 200.0),
    ]
    gap = 40.0
    avail_w = 900.0
    avail_h = 4000.0

    flow_pos = _flow_wrap_grid(sizes, avail_w, avail_h, gap)
    rect_pos = _maxrects_grid(sizes, avail_w, gap)

    def bounding_area(positions, node_sizes):
        widths = [s[0] for s in node_sizes]
        heights = [s[1] for s in node_sizes]
        max_x = max(positions[i][0] + widths[i] for i in range(len(node_sizes)))
        max_y = max(positions[i][1] + heights[i] for i in range(len(node_sizes)))
        min_x = min(p[0] for p in positions)
        min_y = min(p[1] for p in positions)
        return (max_x - min_x) * (max_y - min_y)

    flow_area = bounding_area(flow_pos, sizes)
    rect_area = bounding_area(rect_pos, sizes)

    assert rect_area < flow_area, (
        f"MaxRects area ({rect_area:.0f}) should be smaller than "
        f"flow-wrap area ({flow_area:.0f})"
    )


def test_pack_grid_selects_maxrects_for_high_variance():
    """_pack_grid should use MaxRects for high-variance heights."""
    sizes = [(400, 168), (400, 1500), (400, 200), (400, 300)]
    gap = 40.0

    # _pack_grid should produce MaxRects positions (same as calling _maxrects_grid)
    pack_pos = _pack_grid(sizes, 2000.0, 4000.0, gap)
    rect_pos = _maxrects_grid(sizes, 2000.0, gap)

    assert pack_pos == rect_pos


def test_pack_grid_selects_flowwrap_for_uniform_heights():
    """_pack_grid should use flow-wrap for uniform heights."""
    sizes = [(400, 300), (400, 310), (400, 290), (400, 305)]
    gap = 40.0

    pack_pos = _pack_grid(sizes, 2000.0, 4000.0, gap)
    flow_pos = _flow_wrap_grid(sizes, 2000.0, 4000.0, gap)

    assert pack_pos == flow_pos


def test_pack_grid_preserves_order_uses_flowwrap():
    """preserve_order=True should always use flow-wrap, even with high variance."""
    sizes = [(400, 168), (400, 1500), (400, 200), (400, 300)]
    gap = 40.0

    pack_pos = _pack_grid(sizes, 2000.0, 4000.0, gap, preserve_order=True)
    flow_pos = _flow_wrap_grid(sizes, 2000.0, 4000.0, gap, preserve_order=True)

    assert pack_pos == flow_pos
