"""Tests for overlay/highlight state merging in semantic planning tools."""

from agent.tool_ops.planning_tools import (
    _build_highlight_state_from_overlays,
    _merge_group_overlays,
)


def test_merge_group_overlays_preserves_other_displays_and_replaces_same_key():
    existing = [
        {
            "label": "Left Group",
            "display_id": "left",
            "entity_ids": ["e1"],
            "bounds": {"min_x": 0, "min_y": 0, "max_x": 10, "max_y": 10},
            "color_index": 0,
        },
        {
            "label": "Center Group",
            "display_id": "center",
            "entity_ids": ["e2"],
            "bounds": {"min_x": 10, "min_y": 0, "max_x": 20, "max_y": 10},
            "color_index": 1,
        },
    ]
    incoming = [
        {
            "label": "Center Group",
            "display_id": "center",
            "entity_ids": ["e2", "e3"],
            "bounds": {"min_x": 12, "min_y": 1, "max_x": 24, "max_y": 12},
            "color_index": 2,
        },
        {
            "label": "Right Group",
            "display_id": "right",
            "entity_ids": ["e4"],
            "bounds": {"min_x": 20, "min_y": 0, "max_x": 30, "max_y": 10},
            "color_index": 3,
        },
    ]

    merged = _merge_group_overlays(existing, incoming)

    assert len(merged) == 3
    by_key = {(o.get("display_id"), o["label"]): o for o in merged}
    assert ("left", "Left Group") in by_key
    assert ("center", "Center Group") in by_key
    assert ("right", "Right Group") in by_key
    assert by_key[("center", "Center Group")]["entity_ids"] == ["e2", "e3"]
    assert by_key[("center", "Center Group")]["color_index"] == 2


def test_build_highlight_state_from_overlays_dedupes_entities_and_merges_tags():
    overlays = [
        {
            "label": "Group A",
            "entity_ids": ["e1", "e2"],
            "color_index": 0,  # blue
        },
        {
            "label": "Group B",
            "entity_ids": ["e2", "e3"],
            "color_index": 1,  # red
        },
    ]
    base_tags = {"e1": ["Pre 2010"], "e2": ["Post 2010"]}

    highlight_ids, highlight_colors, merged_tags = _build_highlight_state_from_overlays(
        overlays,
        base_tags,
    )

    assert highlight_ids == ["e1", "e2", "e3"]
    # e2 appears in both groups; latest overlay color should win.
    assert highlight_colors["e2"] == "#ef4444"
    assert highlight_colors["e1"] == "#3b82f6"
    assert merged_tags["e1"] == ["Pre 2010", "Group A"]
    assert merged_tags["e2"] == ["Post 2010", "Group A", "Group B"]
    assert merged_tags["e3"] == ["Group B"]
