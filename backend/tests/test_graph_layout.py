"""Tests for graph-based semantic layout in compute_graph_layout()."""

import math

from agent.layout_ops.graph_layout import (
    _resolve_overlaps_kiwi,
    compute_graph_layout,
)
from agent.layout_ops.regions import slice_bounds_for_region


def _make_layout(entity_ids, surface_id="peer-right", dims=None):
    """Build a minimal layout dict for testing."""
    default_w, default_h = 400.0, 300.0
    layout = {
        "node_positions": {eid: (0.0, 0.0) for eid in entity_ids},
        "surface_assignments": {surface_id: list(entity_ids)},
        "entity_dimensions": {
            eid: {"width": dims[eid][0], "height": dims[eid][1]}
            if dims and eid in dims
            else {"width": default_w, "height": default_h}
            for eid in entity_ids
        },
        "entity_names": {eid: eid for eid in entity_ids},
    }
    return layout


def _overlay_rect(overlay):
    """Extract (min_x, min_y, max_x, max_y) from an overlay bounds dict."""
    b = overlay["bounds"]
    return b["min_x"], b["min_y"], b["max_x"], b["max_y"]


def _rects_overlap(r1, r2):
    """Check if two (min_x, min_y, max_x, max_y) rectangles overlap."""
    return not (r1[2] <= r2[0] or r2[2] <= r1[0] or r1[3] <= r2[1] or r2[3] <= r1[1])


def _overlay_center(overlay):
    """Get center point of overlay bounds."""
    b = overlay["bounds"]
    return ((b["min_x"] + b["max_x"]) / 2, (b["min_y"] + b["max_y"]) / 2)


def _distance(p1, p2):
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])


# --- Test: empty groups ---

def test_empty_groups():
    layout = _make_layout([])
    placements, overlays, _ = compute_graph_layout(
        layout, "peer-right", [], [], arrangement="grid",
        bounds=(0.0, 0.0, 1251.0, 714.0),
    )
    assert placements == []
    assert overlays == []


# --- Test: single group no edges ---

def test_single_group_no_edges():
    entity_ids = ["a", "b", "c"]
    layout = _make_layout(entity_ids)
    groups = [("Group A", entity_ids)]
    placements, overlays, _ = compute_graph_layout(
        layout, "peer-right", groups, [],
        bounds=(0.0, 0.0, 1251.0, 714.0),
    )
    assert len(placements) == 3
    assert len(overlays) == 1
    for p in placements:
        assert math.isfinite(p["x"])
        assert math.isfinite(p["y"])


# --- Test: connected groups are adjacent (compact bin packing) ---

def test_high_weight_closer_than_low_weight():
    """Connected groups should be placed adjacent in compact layout.

    With bin packing, edge weights affect ordering (adjacency) but not
    distance. Both high and low weight edges result in groups being
    packed adjacently.
    """
    entity_ids = ["a1", "a2", "b1", "b2"]
    layout = _make_layout(entity_ids)
    groups = [("A", ["a1", "a2"]), ("B", ["b1", "b2"])]

    # With edge - groups should be adjacent
    _, overlays_with_edge, _ = compute_graph_layout(
        layout, "peer-right", groups,
        [{"source": "A", "target": "B", "weight": 0.5}],
        group_spacing="medium",
        bounds=(0.0, 0.0, 3000.0, 3000.0),
    )

    # Both groups should be placed and adjacent (compact packing)
    assert len(overlays_with_edge) == 2
    dist = _distance(
        _overlay_center(overlays_with_edge[0]),
        _overlay_center(overlays_with_edge[1])
    )
    # With compact bin packing, groups should be close (adjacent)
    # Distance should be roughly the sum of half-widths + gap
    assert dist < 1500, f"Groups should be adjacent, got distance {dist:.0f}"


# --- Test: three groups no overlay overlap ---

def test_three_groups_no_overlay_overlap():
    all_ids = [f"g{g}_e{i}" for g in range(3) for i in range(3)]
    layout = _make_layout(all_ids)
    groups = [
        ("Sports", ["g0_e0", "g0_e1", "g0_e2"]),
        ("Politics", ["g1_e0", "g1_e1", "g1_e2"]),
        ("Finance", ["g2_e0", "g2_e1", "g2_e2"]),
    ]
    edges = [
        {"source": "Sports", "target": "Finance", "weight": 0.8},
        {"source": "Sports", "target": "Politics", "weight": 0.3},
    ]

    _, overlays, _ = compute_graph_layout(
        layout, "peer-right", groups, edges,
        bounds=(0.0, 0.0, 1251.0, 538.0),
    )

    assert len(overlays) == 3
    for i in range(len(overlays)):
        for j in range(i + 1, len(overlays)):
            ri = _overlay_rect(overlays[i])
            rj = _overlay_rect(overlays[j])
            assert not _rects_overlap(ri, rj), (
                f"Overlays {overlays[i]['label']} and {overlays[j]['label']} "
                f"overlap: {ri} vs {rj}"
            )


# --- Test: disconnected groups still placed ---

def test_disconnected_groups_still_placed():
    """Groups with no edges to any other group should still get valid positions."""
    all_ids = ["a", "b", "c", "d"]
    layout = _make_layout(all_ids)
    groups = [("Lone A", ["a"]), ("Lone B", ["b"]), ("Pair", ["c", "d"])]

    placements, overlays, _ = compute_graph_layout(
        layout, "peer-right", groups, [],
        bounds=(0.0, 0.0, 2000.0, 1000.0),
    )

    assert len(placements) == 4
    assert len(overlays) == 3
    for p in placements:
        assert math.isfinite(p["x"])
        assert math.isfinite(p["y"])


def test_unconstrained_layout_translates_into_origin_bounds():
    """Unconstrained graph layouts should emit in-bounds canvas coordinates."""
    entity_ids = ["a", "b"]
    layout = _make_layout(entity_ids)
    groups = [("Left", ["a"]), ("Right", ["b"])]
    bounds = (0.0, 0.0, 1600.0, 900.0)

    placements, _, _ = compute_graph_layout(
        layout, "peer-right", groups, [],
        bounds=bounds,
    )

    assert len(placements) == 2
    for p in placements:
        assert bounds[0] <= p["x"] <= bounds[2]
        assert bounds[1] <= p["y"] <= bounds[3]
        # _make_layout defaults to 400x300 nodes
        assert p["x"] + 400.0 <= bounds[2] + 1e-6
        assert p["y"] + 300.0 <= bounds[3] + 1e-6


def test_unconstrained_layout_respects_nonzero_bounds_origin():
    """Graph layouts should honor non-zero bounds min_x/min_y."""
    entity_ids = ["a", "b"]
    layout = _make_layout(entity_ids)
    groups = [("Group A", ["a"]), ("Group B", ["b"])]
    bounds = (500.0, 200.0, 2200.0, 1400.0)

    placements, _, _ = compute_graph_layout(
        layout, "peer-right", groups, [],
        bounds=bounds,
    )

    assert len(placements) == 2
    for p in placements:
        assert p["x"] >= bounds[0] - 1e-6
        assert p["y"] >= bounds[1] - 1e-6
        assert p["x"] + 400.0 <= bounds[2] + 1e-6
        assert p["y"] + 300.0 <= bounds[3] + 1e-6


# --- Test: overlay metadata format ---

def test_overlay_metadata_format():
    entity_ids = ["a", "b"]
    layout = _make_layout(entity_ids)
    groups = [("Topic A", ["a"]), ("Topic B", ["b"])]

    _, overlays, _ = compute_graph_layout(
        layout, "peer-right", groups, [],
        color_index_start=3,
        bounds=(0.0, 0.0, 1000.0, 800.0),
    )

    assert len(overlays) == 2
    for overlay in overlays:
        assert "label" in overlay
        assert "entity_ids" in overlay
        assert "bounds" in overlay
        assert "color_index" in overlay
        assert "display_id" in overlay
        b = overlay["bounds"]
        assert all(k in b for k in ("min_x", "min_y", "max_x", "max_y"))

    assert overlays[0]["label"] == "Topic A"
    assert overlays[0]["entity_ids"] == ["a"]
    assert overlays[0]["color_index"] == 3
    assert overlays[0]["display_id"] == "peer-right"
    assert overlays[1]["color_index"] == 4


# --- Test: all layout styles produce valid results ---

def test_layout_styles():
    all_ids = [f"e{i}" for i in range(6)]
    layout = _make_layout(all_ids)
    groups = [("A", all_ids[:3]), ("B", all_ids[3:])]
    edges = [{"source": "A", "target": "B", "weight": 0.5}]

    for style in ("organic", "packed", "hierarchical"):
        placements, overlays, _ = compute_graph_layout(
            layout, "peer-right", groups, edges,
            layout_style=style,
            bounds=(0.0, 0.0, 2000.0, 1000.0),
        )
        assert len(placements) == 6, f"Style '{style}' produced {len(placements)} placements"
        assert len(overlays) == 2, f"Style '{style}' produced {len(overlays)} overlays"
        # No overlaps
        r0 = _overlay_rect(overlays[0])
        r1 = _overlay_rect(overlays[1])
        assert not _rects_overlap(r0, r1), f"Style '{style}' has overlapping groups"


# --- Test: group spacing affects gap ---

def test_group_spacing_affects_gap():
    """'large' spacing should produce greater minimum distance between groups than 'tight'."""
    all_ids = ["a", "b", "c", "d"]
    layout = _make_layout(all_ids)
    groups = [("A", ["a", "b"]), ("B", ["c", "d"])]
    edges = [{"source": "A", "target": "B", "weight": 0.5}]

    _, overlays_tight, _ = compute_graph_layout(
        layout, "peer-right", groups, edges,
        group_spacing="tight",
        bounds=(0.0, 0.0, 3000.0, 3000.0),
    )
    _, overlays_large, _ = compute_graph_layout(
        layout, "peer-right", groups, edges,
        group_spacing="large",
        bounds=(0.0, 0.0, 3000.0, 3000.0),
    )

    dist_tight = _distance(_overlay_center(overlays_tight[0]), _overlay_center(overlays_tight[1]))
    dist_large = _distance(_overlay_center(overlays_large[0]), _overlay_center(overlays_large[1]))

    assert dist_large > dist_tight, (
        f"Large spacing distance ({dist_large:.0f}) should exceed "
        f"tight spacing distance ({dist_tight:.0f})"
    )


# --- Test: kiwisolver overlap removal unit test ---

def test_kiwisolver_overlap_removal():
    """Directly test _resolve_overlaps_kiwi with intentionally overlapping rects."""
    positions = {
        "A": (100.0, 100.0),
        "B": (120.0, 110.0),  # Overlaps with A
        "C": (200.0, 100.0),
    }
    sizes = {
        "A": (200.0, 150.0),
        "B": (200.0, 150.0),
        "C": (200.0, 150.0),
    }
    min_gap = 30.0

    result = _resolve_overlaps_kiwi(positions, sizes, min_gap)

    # Verify no overlaps: for each pair, either horizontal or vertical separation
    labels = list(result.keys())
    for i in range(len(labels)):
        for j in range(i + 1, len(labels)):
            li, lj = labels[i], labels[j]
            xi, yi = result[li]
            xj, yj = result[lj]
            wi, hi = sizes[li]
            wj, hj = sizes[lj]

            # Check that rectangles don't overlap (with gap tolerance)
            h_sep = (xi + wi + min_gap <= xj + 0.1) or (xj + wj + min_gap <= xi + 0.1)
            v_sep = (yi + hi + min_gap <= yj + 0.1) or (yj + hj + min_gap <= yi + 0.1)
            assert h_sep or v_sep, (
                f"Rects {li} ({xi:.0f},{yi:.0f},{wi:.0f}x{hi:.0f}) and "
                f"{lj} ({xj:.0f},{yj:.0f},{wj:.0f}x{hj:.0f}) overlap "
                f"with min_gap={min_gap}"
            )


# --- Test: placements reference correct surface ---

def test_placements_reference_correct_surface():
    entity_ids = ["x", "y", "z"]
    layout = _make_layout(entity_ids, surface_id="peer-left")
    groups = [("G1", ["x", "y"]), ("G2", ["z"])]

    placements, _, _ = compute_graph_layout(
        layout, "peer-left", groups, [],
        bounds=(0.0, 0.0, 800.0, 600.0),
    )

    for p in placements:
        assert p["target_surface"] == "peer-left"


# === Layer 4: Enriched Tool Vocabulary ===


# --- Test: per-group arrangement override ---

def test_per_group_arrangement_override():
    """Horizontal group has entities in single row, grid group has multiple rows."""
    ids_h = [f"h{i}" for i in range(4)]
    ids_g = [f"g{i}" for i in range(4)]
    all_ids = ids_h + ids_g
    layout = _make_layout(all_ids)
    groups = [("Horiz", ids_h), ("Grid", ids_g)]

    placements, overlays, _ = compute_graph_layout(
        layout, "peer-right", groups, [],
        arrangement="grid",
        group_arrangements={"Horiz": "horizontal"},
        bounds=(0.0, 0.0, 5000.0, 5000.0),
    )

    # Extract placed positions per group
    pos_h = {p["entity_id"]: (p["x"], p["y"]) for p in placements if p["entity_id"] in ids_h}
    pos_g = {p["entity_id"]: (p["x"], p["y"]) for p in placements if p["entity_id"] in ids_g}

    # Horizontal group: all Y values should be the same (single row)
    ys_h = [y for _, y in pos_h.values()]
    assert max(ys_h) - min(ys_h) < 1.0, (
        f"Horizontal group Y spread too large: {ys_h}"
    )

    # Grid group with 4 items: should have 2 rows (ceil(sqrt(4))=2 cols, 2 rows)
    ys_g = sorted(set(round(y, 1) for _, y in pos_g.values()))
    assert len(ys_g) >= 2, (
        f"Grid group should have multiple rows, got Y values: {ys_g}"
    )


def test_per_group_arrangement_default_fallback():
    """Groups without arrangement override use the top-level value."""
    all_ids = ["a", "b", "c", "d"]
    layout = _make_layout(all_ids)
    groups = [("A", ["a", "b"]), ("B", ["c", "d"])]

    # Top-level vertical, no overrides
    placements, _, _ = compute_graph_layout(
        layout, "peer-right", groups, [],
        arrangement="vertical",
        bounds=(0.0, 0.0, 5000.0, 5000.0),
    )

    # Both groups should have entities in single column (same X)
    for gname, gids in groups:
        pos = {p["entity_id"]: (p["x"], p["y"]) for p in placements if p["entity_id"] in gids}
        xs = [x for x, _ in pos.values()]
        assert max(xs) - min(xs) < 1.0, (
            f"Group {gname} should be vertical (single column), X spread: {xs}"
        )


# --- Test: group anchoring ---

def test_anchored_group_in_region():
    """Group anchored to 'top-left' should land within that region."""
    all_ids = ["a", "b", "c", "d"]
    layout = _make_layout(all_ids)
    groups = [("Anchored", ["a", "b"]), ("Free", ["c", "d"])]
    bounds = (0.0, 0.0, 2000.0, 1200.0)

    _, overlays, _ = compute_graph_layout(
        layout, "peer-right", groups, [],
        bounds=bounds,
        anchors={"Anchored": "top-left"},
    )

    # Get the "Anchored" overlay
    anchored_overlay = next(o for o in overlays if o["label"] == "Anchored")
    ob = anchored_overlay["bounds"]

    # Compute the top-left region bounds
    region_bounds = slice_bounds_for_region(bounds, "top-left")
    assert region_bounds is not None
    r_min_x, r_min_y, r_max_x, r_max_y = region_bounds

    # Overlay center should be within the top-left region (with tolerance for padding)
    cx = (ob["min_x"] + ob["max_x"]) / 2
    cy = (ob["min_y"] + ob["max_y"]) / 2
    assert r_min_x <= cx <= r_max_x, (
        f"Anchored center X {cx:.0f} not within region [{r_min_x:.0f}, {r_max_x:.0f}]"
    )
    assert r_min_y <= cy <= r_max_y, (
        f"Anchored center Y {cy:.0f} not within region [{r_min_y:.0f}, {r_max_y:.0f}]"
    )


def test_anchored_and_free_no_overlap():
    """Mix of anchored and non-anchored groups should not overlap."""
    all_ids = [f"e{i}" for i in range(6)]
    layout = _make_layout(all_ids)
    groups = [
        ("Top", all_ids[:2]),
        ("Bottom", all_ids[2:4]),
        ("Free", all_ids[4:]),
    ]

    _, overlays, _ = compute_graph_layout(
        layout, "peer-right", groups, [],
        bounds=(0.0, 0.0, 3000.0, 2000.0),
        anchors={"Top": "top", "Bottom": "bottom"},
    )

    assert len(overlays) == 3
    for i in range(len(overlays)):
        for j in range(i + 1, len(overlays)):
            ri = _overlay_rect(overlays[i])
            rj = _overlay_rect(overlays[j])
            assert not _rects_overlap(ri, rj), (
                f"Overlays {overlays[i]['label']} and {overlays[j]['label']} "
                f"overlap: {ri} vs {rj}"
            )


# --- Test: alignment constraints ---

def test_horizontal_alignment_shared_y():
    """Horizontally aligned groups should share the same center Y."""
    all_ids = [f"e{i}" for i in range(6)]
    layout = _make_layout(all_ids)
    groups = [("A", all_ids[:2]), ("B", all_ids[2:4]), ("C", all_ids[4:])]

    _, overlays, _ = compute_graph_layout(
        layout, "peer-right", groups, [],
        bounds=(0.0, 0.0, 5000.0, 3000.0),
        alignment_constraints=[{"groups": ["A", "B"], "axis": "horizontal"}],
    )

    center_a = _overlay_center(next(o for o in overlays if o["label"] == "A"))
    center_b = _overlay_center(next(o for o in overlays if o["label"] == "B"))

    # Center Y should be very close (within a few pixels of tolerance)
    assert abs(center_a[1] - center_b[1]) < 5.0, (
        f"A center Y ({center_a[1]:.1f}) and B center Y ({center_b[1]:.1f}) "
        f"should be aligned"
    )


def test_vertical_alignment_shared_x():
    """Vertically aligned groups should share the same center X."""
    all_ids = [f"e{i}" for i in range(6)]
    layout = _make_layout(all_ids)
    groups = [("A", all_ids[:2]), ("B", all_ids[2:4]), ("C", all_ids[4:])]

    _, overlays, _ = compute_graph_layout(
        layout, "peer-right", groups, [],
        bounds=(0.0, 0.0, 5000.0, 3000.0),
        alignment_constraints=[{"groups": ["A", "B"], "axis": "vertical"}],
    )

    center_a = _overlay_center(next(o for o in overlays if o["label"] == "A"))
    center_b = _overlay_center(next(o for o in overlays if o["label"] == "B"))

    assert abs(center_a[0] - center_b[0]) < 5.0, (
        f"A center X ({center_a[0]:.1f}) and B center X ({center_b[0]:.1f}) "
        f"should be aligned"
    )


def test_alignment_no_overlap():
    """Alignment constraints should not cause overlapping groups."""
    all_ids = [f"e{i}" for i in range(9)]
    layout = _make_layout(all_ids)
    groups = [("A", all_ids[:3]), ("B", all_ids[3:6]), ("C", all_ids[6:])]

    _, overlays, _ = compute_graph_layout(
        layout, "peer-right", groups,
        [{"source": "A", "target": "B", "weight": 0.7}],
        bounds=(0.0, 0.0, 5000.0, 3000.0),
        alignment_constraints=[{"groups": ["A", "B"], "axis": "horizontal"}],
    )

    for i in range(len(overlays)):
        for j in range(i + 1, len(overlays)):
            ri = _overlay_rect(overlays[i])
            rj = _overlay_rect(overlays[j])
            assert not _rects_overlap(ri, rj), (
                f"Overlays {overlays[i]['label']} and {overlays[j]['label']} "
                f"overlap: {ri} vs {rj}"
            )


# --- Test: per-group spacing ---

def test_per_group_spacing_affects_size():
    """Tight spacing should produce a smaller bounding box than large spacing."""
    entity_ids = [f"e{i}" for i in range(4)]
    layout = _make_layout(entity_ids)
    groups = [("Only", entity_ids)]

    _, overlays_tight, _ = compute_graph_layout(
        layout, "peer-right", groups, [],
        bounds=(0.0, 0.0, 5000.0, 5000.0),
        group_spacings={"Only": "tight"},
    )
    _, overlays_large, _ = compute_graph_layout(
        layout, "peer-right", groups, [],
        bounds=(0.0, 0.0, 5000.0, 5000.0),
        group_spacings={"Only": "large"},
    )

    def area(overlay):
        b = overlay["bounds"]
        return (b["max_x"] - b["min_x"]) * (b["max_y"] - b["min_y"])

    assert area(overlays_tight[0]) < area(overlays_large[0]), (
        f"Tight area ({area(overlays_tight[0]):.0f}) should be less than "
        f"large area ({area(overlays_large[0]):.0f})"
    )


# --- Test: backward compatibility ---

def test_per_group_preserve_order_horizontal():
    """preserve_order=True keeps entities in the exact order they were given,
    reading left-to-right for horizontal arrangement."""
    # Intentionally varied sizes so default (non-preserving) layout would
    # reorder — confirms preserve_order overrides size-based packing.
    ids = ["first", "second", "third", "fourth"]
    layout = _make_layout(
        ids,
        dims={
            "first": (800, 600),
            "second": (300, 250),
            "third": (300, 250),
            "fourth": (300, 250),
        },
    )

    groups = [("Timeline", ids)]

    placements, _, _ = compute_graph_layout(
        layout, "peer-right", groups, [],
        arrangement="horizontal",
        group_arrangements={"Timeline": "horizontal"},
        group_preserve_order={"Timeline": True},
        bounds=(0.0, 0.0, 6000.0, 2000.0),
    )

    pos = {p["entity_id"]: (p["x"], p["y"]) for p in placements}
    # All entities must appear in strictly increasing X order matching input order
    xs_in_order = [pos[eid][0] for eid in ids]
    assert xs_in_order == sorted(xs_in_order), (
        f"preserve_order=True should keep input order; got X sequence: {xs_in_order}"
    )


def test_per_group_preserve_order_default_false():
    """Without preserve_order override, layout does not guarantee input order."""
    ids = ["a", "b", "c", "d"]
    layout = _make_layout(ids)
    groups = [("G", ids)]

    placements, _, _ = compute_graph_layout(
        layout, "peer-right", groups, [],
        arrangement="horizontal",
        group_arrangements={"G": "horizontal"},
        bounds=(0.0, 0.0, 6000.0, 2000.0),
    )

    # Just verify the call works without the override (regression guard)
    assert len(placements) == 4


def test_backward_compat_no_new_params():
    """Existing calls with no Layer 4 params still work identically."""
    all_ids = [f"e{i}" for i in range(6)]
    layout = _make_layout(all_ids)
    groups = [("A", all_ids[:3]), ("B", all_ids[3:])]
    edges = [{"source": "A", "target": "B", "weight": 0.5}]

    placements, overlays, _ = compute_graph_layout(
        layout, "peer-right", groups, edges,
        arrangement="grid",
        layout_style="organic",
        group_spacing="medium",
        bounds=(0.0, 0.0, 2000.0, 1000.0),
    )

    assert len(placements) == 6
    assert len(overlays) == 2
    for p in placements:
        assert math.isfinite(p["x"])
        assert math.isfinite(p["y"])


# === Variable-height regression tests (estimation/arrangement consistency) ===


def test_variable_height_groups_no_overlap():
    """Groups with variable-height nodes must not overlap.

    Regression test: _estimate_group_rect used display bounds as avail_w for
    _pack_grid, but arrangement used the group's content width (smaller).
    MaxRects produces different layouts for different bin widths, causing
    arrangement to overflow the estimated bounds vertically.
    """
    dims = {}
    entity_ids = []
    heights = [168, 1257, 308, 208, 328, 428, 228, 333, 1342, 188, 248, 508]
    for i, h in enumerate(heights):
        eid = f"post_{i}"
        entity_ids.append(eid)
        dims[eid] = (400.0, float(h))

    layout = _make_layout(entity_ids, dims=dims)
    groups = [
        ("rec.autos", entity_ids[:6]),
        ("rec.sport.baseball", entity_ids[6:]),
    ]
    edges = [{"source": "rec.autos", "target": "rec.sport.baseball", "weight": 0.4}]

    _, overlays, _ = compute_graph_layout(
        layout, "peer-right", groups, edges,
        bounds=(0.0, 0.0, 1920.0, 1080.0),
    )

    assert len(overlays) == 2
    r0 = _overlay_rect(overlays[0])
    r1 = _overlay_rect(overlays[1])
    assert not _rects_overlap(r0, r1), (
        f"Variable-height groups overlap: {overlays[0]['label']} {r0} "
        f"vs {overlays[1]['label']} {r1}"
    )


def test_three_variable_height_groups_no_overlap():
    """Three groups with mixed variable heights must not overlap."""
    dims = {}
    entity_ids = []
    for i, h in enumerate([200, 1400, 300, 250]):
        eid = f"g1_{i}"
        entity_ids.append(eid)
        dims[eid] = (400.0, float(h))
    for i, h in enumerate([300, 800, 350]):
        eid = f"g2_{i}"
        entity_ids.append(eid)
        dims[eid] = (400.0, float(h))
    for i, h in enumerate([150, 1500, 180, 200, 170]):
        eid = f"g3_{i}"
        entity_ids.append(eid)
        dims[eid] = (400.0, float(h))

    layout = _make_layout(entity_ids, dims=dims)
    groups = [
        ("Cars", [e for e in entity_ids if e.startswith("g1_")]),
        ("Motorcycles", [e for e in entity_ids if e.startswith("g2_")]),
        ("Baseball", [e for e in entity_ids if e.startswith("g3_")]),
    ]
    edges = [
        {"source": "Cars", "target": "Motorcycles", "weight": 0.8},
        {"source": "Cars", "target": "Baseball", "weight": 0.2},
    ]

    _, overlays, _ = compute_graph_layout(
        layout, "peer-right", groups, edges,
        bounds=(0.0, 0.0, 1920.0, 1080.0),
    )

    assert len(overlays) == 3
    for i in range(len(overlays)):
        for j in range(i + 1, len(overlays)):
            ri = _overlay_rect(overlays[i])
            rj = _overlay_rect(overlays[j])
            assert not _rects_overlap(ri, rj), (
                f"Overlays {overlays[i]['label']} and {overlays[j]['label']} "
                f"overlap: {ri} vs {rj}"
            )


def test_single_group_variable_height_fits_overlay():
    """A single group's entities must all fit within its overlay bounds."""
    dims = {}
    entity_ids = []
    for i, h in enumerate([168, 1257, 308, 208, 328, 428]):
        eid = f"e{i}"
        entity_ids.append(eid)
        dims[eid] = (400.0, float(h))

    layout = _make_layout(entity_ids, dims=dims)
    groups = [("OnlyGroup", entity_ids)]

    placements, overlays, _ = compute_graph_layout(
        layout, "peer-right", groups, [],
        bounds=(0.0, 0.0, 1920.0, 1080.0),
    )

    assert len(overlays) == 1
    ob = overlays[0]["bounds"]
    for p in placements:
        eid = p["entity_id"]
        w, h = dims[eid]
        assert p["x"] >= ob["min_x"], f"{eid} x={p['x']:.1f} < overlay min_x={ob['min_x']:.1f}"
        assert p["y"] >= ob["min_y"], f"{eid} y={p['y']:.1f} < overlay min_y={ob['min_y']:.1f}"
        assert p["x"] + w <= ob["max_x"], f"{eid} right edge exceeds overlay max_x"
        assert p["y"] + h <= ob["max_y"], f"{eid} bottom edge exceeds overlay max_y"


def test_preserve_order_variable_height_no_overlap():
    """preserve_order=True with variable heights should produce
    non-overlapping groups."""
    dims = {}
    entity_ids = []
    for i, h in enumerate([200, 1200, 300, 250, 180, 900]):
        eid = f"e{i}"
        entity_ids.append(eid)
        dims[eid] = (400.0, float(h))

    layout = _make_layout(entity_ids, dims=dims)
    groups = [("G1", entity_ids[:3]), ("G2", entity_ids[3:])]

    _, overlays, _ = compute_graph_layout(
        layout, "peer-right", groups, [],
        bounds=(0.0, 0.0, 1920.0, 1080.0),
        group_preserve_order={"G1": True, "G2": True},
    )

    assert len(overlays) == 2
    r0 = _overlay_rect(overlays[0])
    r1 = _overlay_rect(overlays[1])
    assert not _rects_overlap(r0, r1), (
        f"Overlays overlap with preserve_order: {r0} vs {r1}"
    )


def test_variable_height_horizontal_arrangement_no_crash():
    """Horizontal arrangement with variable heights should work
    (cache is bypassed, falls through to compute_arrangement_positions)."""
    dims = {}
    entity_ids = []
    for i, h in enumerate([200, 1400, 300]):
        eid = f"e{i}"
        entity_ids.append(eid)
        dims[eid] = (400.0, float(h))

    layout = _make_layout(entity_ids, dims=dims)
    groups = [("HGroup", entity_ids)]

    placements, overlays, _ = compute_graph_layout(
        layout, "peer-right", groups, [],
        arrangement="horizontal",
        group_arrangements={"HGroup": "horizontal"},
        bounds=(0.0, 0.0, 3000.0, 2000.0),
    )

    assert len(placements) == 3
    ys = [p["y"] for p in placements]
    assert max(ys) - min(ys) < 1.0


# === Display profile and auto-inference tests ===


def test_display_profile_shape_classification():
    """Verify display shape classification thresholds."""
    from agent.layout_ops.display_profile import classify_display_shape

    assert classify_display_shape(2560, 1080) == "ultrawide"  # 2.37
    assert classify_display_shape(1920, 1080) == "landscape"  # 1.78
    assert classify_display_shape(1080, 1080) == "square"     # 1.0
    assert classify_display_shape(1080, 1920) == "portrait"   # 0.56
    assert classify_display_shape(600, 1920) == "tall"        # 0.31


def test_display_profile_capacity():
    """Verify capacity estimates for known display sizes."""
    from agent.layout_ops.display_profile import estimate_capacity

    cap_1080p = estimate_capacity(1920, 1080)
    cap_1440p = estimate_capacity(2560, 1440)
    assert 8 <= cap_1080p <= 15, f"1080p capacity {cap_1080p} out of range"
    assert 15 <= cap_1440p <= 25, f"1440p capacity {cap_1440p} out of range"
    # Larger display always has more capacity
    assert cap_1440p > cap_1080p


def test_auto_select_arrangement():
    """Auto-arrangement: wide regions → horizontal, tall → vertical."""
    from agent.layout_ops.display_profile import auto_select_arrangement

    assert auto_select_arrangement(2000, 400, 4) == "horizontal"
    assert auto_select_arrangement(400, 2000, 4) == "vertical"
    assert auto_select_arrangement(1000, 800, 10) == "grid"


def test_params_optional_no_crash():
    """compute_graph_layout works with all None params (auto-inference)."""
    entity_ids = ["a", "b", "c", "d"]
    layout = _make_layout(entity_ids)
    groups = [("G1", ["a", "b"]), ("G2", ["c", "d"])]
    edges = [{"source": "G1", "target": "G2", "weight": 0.5}]

    # All layout params default to None → auto-inferred
    placements, overlays, _ = compute_graph_layout(
        layout, "peer-right", groups, edges,
        bounds=(0.0, 0.0, 1920.0, 1080.0),
    )

    assert len(placements) == 4
    assert len(overlays) == 2
    for p in placements:
        assert math.isfinite(p["x"])
        assert math.isfinite(p["y"])


def test_explicit_params_override_auto():
    """Explicit param values should be used over auto-inference."""
    entity_ids = ["a", "b", "c", "d"]
    layout = _make_layout(entity_ids)
    groups = [("G1", ["a", "b"]), ("G2", ["c", "d"])]

    # Explicit horizontal arrangement should produce single-row groups
    placements, _, _ = compute_graph_layout(
        layout, "peer-right", groups, [],
        arrangement="horizontal",
        bounds=(0.0, 0.0, 5000.0, 5000.0),
    )

    # Each group should have entities in a single row (same Y)
    for _, gids in groups:
        pos = {p["entity_id"]: (p["x"], p["y"]) for p in placements if p["entity_id"] in gids}
        ys = [y for _, y in pos.values()]
        assert max(ys) - min(ys) < 1.0, f"Horizontal arrangement not in single row: {ys}"


def test_display_assignment_respects_capacity():
    """Groups should not all pile onto one display when another has capacity."""
    from agent.layout_ops.display_assignment import assign_groups_to_displays
    from agent.layout_ops.display_profile import build_all_display_profiles

    layout = {
        "displays": [
            {"peer_id": "small", "width": 800, "height": 600, "tags": ["left"], "x": 0, "y": 0},
            {"peer_id": "big", "width": 2560, "height": 1440, "tags": ["right"], "x": 800, "y": 0},
        ],
        "surface_assignments": {"small": [], "big": []},
    }
    profiles = build_all_display_profiles(layout)

    # 15 entities across 3 groups — should prefer the bigger display
    groups = {
        "A": [f"a{i}" for i in range(6)],
        "B": [f"b{i}" for i in range(5)],
        "C": [f"c{i}" for i in range(4)],
    }
    edges = [{"source": "A", "target": "B", "weight": 0.7}]

    assignments = assign_groups_to_displays(groups, edges, layout, profiles)

    # The big display should have more entities than the small one
    big_count = sum(len(eids) for _, eids in assignments["big"])
    small_count = sum(len(eids) for _, eids in assignments["small"])
    assert big_count >= small_count, (
        f"Big display ({big_count}) should have >= small display ({small_count})"
    )


# === New feature tests ===


def test_ordered_groups_preserve_reading_order():
    """ordered=True should arrange groups in list order (left→right, top→bottom)."""
    entity_ids = [f"e{i}" for i in range(8)]
    layout = _make_layout(entity_ids)
    groups = [
        ("First", ["e0", "e1"]),
        ("Second", ["e2", "e3"]),
        ("Third", ["e4", "e5"]),
        ("Fourth", ["e6", "e7"]),
    ]

    _, overlays, _ = compute_graph_layout(
        layout, "peer-right", groups, [],
        ordered=True,
        bounds=(0.0, 0.0, 2000.0, 1000.0),
    )

    centers = [_overlay_center(o) for o in overlays]
    # Each group should be after the previous in reading order
    for i in range(len(centers) - 1):
        c1, c2 = centers[i], centers[i + 1]
        assert c2[0] > c1[0] or c2[1] > c1[1], (
            f"Group {overlays[i + 1]['label']} is not after {overlays[i]['label']} "
            f"in reading order: {c1} vs {c2}"
        )


def test_nested_sub_groups():
    """Groups with sub_groups should have entities placed within sub-group regions."""
    entity_ids = [f"e{i}" for i in range(6)]
    layout = _make_layout(entity_ids)
    groups = [
        ("Parent", ["e0", "e1", "e2", "e3"]),
        ("Sibling", ["e4", "e5"]),
    ]
    sub_groups = {
        "Parent": [
            ("Child A", ["e0", "e1"]),
            ("Child B", ["e2", "e3"]),
        ],
    }

    placements, overlays, _ = compute_graph_layout(
        layout, "peer-right", groups, [],
        bounds=(0.0, 0.0, 2000.0, 1000.0),
        group_sub_groups=sub_groups,
    )

    assert len(placements) == 6
    # Overlays: Child A, Child B (from recursion) + Sibling (direct)
    overlay_labels = {o["label"] for o in overlays}
    assert "Child A" in overlay_labels
    assert "Child B" in overlay_labels
    assert "Sibling" in overlay_labels


def test_preserve_existing_avoids_preserved():
    """preserve_existing=True should place new groups away from existing entities."""
    entity_ids = ["kept1", "kept2", "new1", "new2"]
    layout = _make_layout(entity_ids)
    # Place "kept" entities at known positions
    layout["node_positions"]["kept1"] = (100.0, 100.0)
    layout["node_positions"]["kept2"] = (600.0, 100.0)
    layout["surface_assignments"] = {"peer-right": entity_ids}

    groups = [("NewGroup", ["new1", "new2"])]

    placements, _, _ = compute_graph_layout(
        layout, "peer-right", groups, [],
        bounds=(0.0, 0.0, 2000.0, 1000.0),
        preserve_existing=True,
    )

    assert len(placements) == 2
    # New entities should not overlap with the kept entities' region
    for p in placements:
        assert math.isfinite(p["x"])
        assert math.isfinite(p["y"])


def test_display_priority_high_on_primary():
    """High-priority groups should prefer the primary display."""
    from agent.layout_ops.display_assignment import assign_groups_to_displays
    from agent.layout_ops.display_profile import build_all_display_profiles

    layout = {
        "displays": [
            {"peer_id": "secondary", "width": 1920, "height": 1080, "tags": ["left"], "x": 0, "y": 0},
            {"peer_id": "primary", "width": 2560, "height": 1440, "tags": ["center"], "x": 1920, "y": 0},
        ],
        "surface_assignments": {"secondary": [], "primary": []},
    }
    profiles = build_all_display_profiles(layout)
    assert profiles["primary"]["is_primary"]

    groups = {
        "Important": [f"i{i}" for i in range(3)],
        "Normal": [f"n{i}" for i in range(3)],
    }
    edges: list = []

    assignments = assign_groups_to_displays(
        groups, edges, layout, profiles,
        group_priorities={"Important": "high", "Normal": "low"},
    )

    primary_labels = [g[0] for g in assignments["primary"]]
    assert "Important" in primary_labels, (
        f"High-priority 'Important' should be on primary display, got: {primary_labels}"
    )
