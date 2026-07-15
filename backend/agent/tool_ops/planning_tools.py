"""ADK tool wrappers for layout planning and validation."""

from typing import Any, Dict, Optional

from google.adk.tools.tool_context import ToolContext

from ..layout_ops.arrangement import fit_display_camera_to_entities_if_needed
from ..layout_ops.dimensions import get_entity_dimension
from ..layout_ops.display import (
    resolve_display_name,
    get_surface_visible_bounds,
    get_surface_workspace_bounds,
    get_surface_viewport_dims,
)
from ..layout_ops.graph_layout import compute_graph_layout
from ..layout_ops.mutations import move_entity
from ..layout_ops.regions import REGION_SLICES
from ..layout_ops.display_assignment import assign_groups_to_displays
from ..layout_ops.display_profile import build_all_display_profiles
from ..layout_ops.planning import validate_layout
from ..layout_ops.spatial_summary import summarize_group_layout
from .common import tool_safe

# 8-color palette for group overlays (matches frontend GROUP_PALETTE)
_GROUP_COLORS = [
    "#3b82f6",  # blue
    "#ef4444",  # red
    "#10b981",  # emerald
    "#f59e0b",  # amber
    "#8b5cf6",  # violet
    "#ec4899",  # pink
    "#06b6d4",  # cyan
    "#84cc16",  # lime
]

_VALID_LAYOUT_STYLES = {"organic", "packed", "hierarchical"}
_VALID_GROUP_SPACINGS = {"tight", "medium", "large"}
_VALID_ARRANGEMENTS = {"grid", "horizontal", "vertical"}
_VALID_GROUP_ARRANGEMENTS = {"row", "column", "grid"}

# Qualitative weight labels → numeric values.  Allows the agent to express
# semantic relatedness without picking an arbitrary float.
_QUALITATIVE_WEIGHTS = {
    "strongly_related": 0.9,
    "related": 0.7,
    "somewhat_related": 0.45,
    "weakly_related": 0.25,
    "unrelated": 0.05,
}
_QUALITATIVE_WEIGHT_NAMES = ", ".join(
    f'"{k}" ({v})' for k, v in _QUALITATIVE_WEIGHTS.items()
)


def _merge_group_overlays(
    existing_overlays: list[dict[str, Any]] | None,
    incoming_overlays: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Merge overlays across repeated tool calls in the same turn.

    Overlay identity is (display_id, label). Incoming overlays replace prior
    overlays with the same identity. This allows iterative refinement on the
    same display while preserving overlays from other displays.
    """
    merged_by_key: dict[tuple[str | None, str], dict[str, Any]] = {}
    ordered_keys: list[tuple[str | None, str]] = []

    for overlay in (existing_overlays or []):
        key = (overlay.get("display_id"), str(overlay.get("label", "")))
        if key not in merged_by_key:
            ordered_keys.append(key)
        merged_by_key[key] = dict(overlay)

    for overlay in (incoming_overlays or []):
        key = (overlay.get("display_id"), str(overlay.get("label", "")))
        if key not in merged_by_key:
            ordered_keys.append(key)
        merged_by_key[key] = dict(overlay)

    return [merged_by_key[key] for key in ordered_keys]


def _build_highlight_state_from_overlays(
    overlays: list[dict[str, Any]],
    entity_tags: dict[str, list[str]] | None = None,
) -> tuple[list[str], dict[str, str], dict[str, list[str]]]:
    """Derive highlight IDs/colors and overlay-label tags from overlays."""
    highlight_all: list[str] = []
    seen: set[str] = set()
    highlight_colors: dict[str, str] = {}
    merged_tags: dict[str, list[str]] = dict(entity_tags or {})

    for overlay in overlays:
        color = _GROUP_COLORS[int(overlay["color_index"]) % len(_GROUP_COLORS)]
        label = str(overlay.get("label", ""))
        for eid in overlay.get("entity_ids", []):
            if eid not in seen:
                highlight_all.append(eid)
                seen.add(eid)
            highlight_colors[eid] = color
            existing = merged_tags.get(eid, [])
            if label and label not in existing:
                merged_tags[eid] = existing + [label]

    return highlight_all, highlight_colors, merged_tags

def _compute_cross_display_anchors(
    assignments: dict[str, list[tuple[str, list[str]]]],
    edges: list[dict],
    layout: dict,
    user_anchors: Optional[dict[str, str]],
) -> dict[str, dict[str, str]]:
    """Derive region anchors for groups whose semantic partners are on other displays.

    For each cross-display edge, determines which display boundary is
    closest to the partner display (using virtual-desktop coordinates)
    and returns a per-surface mapping of ``{group_label: region_name}``.

    User-provided anchors take precedence and are never overridden.
    """
    label_to_surface: dict[str, str] = {}
    for sid, groups_on_surface in assignments.items():
        for label, _ in groups_on_surface:
            label_to_surface[label] = sid

    # Virtual desktop (x, y) per peer_id
    display_positions: dict[str, tuple[float, float]] = {}
    for disp in layout.get("displays", []):
        pid = disp.get("peer_id")
        if pid:
            display_positions[pid] = (
                float(disp.get("x", 0)),
                float(disp.get("y", 0)),
            )

    anchors: dict[str, dict[str, str]] = {sid: {} for sid in assignments}
    _user = user_anchors or {}

    for edge in edges:
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        src_sid = label_to_surface.get(src)
        tgt_sid = label_to_surface.get(tgt)
        if not src_sid or not tgt_sid or src_sid == tgt_sid:
            continue

        src_pos = display_positions.get(src_sid, (0.0, 0.0))
        tgt_pos = display_positions.get(tgt_sid, (0.0, 0.0))
        dx = tgt_pos[0] - src_pos[0]
        dy = tgt_pos[1] - src_pos[1]

        if abs(dx) >= abs(dy):
            src_region = "right" if dx > 0 else "left"
            tgt_region = "left" if dx > 0 else "right"
        else:
            src_region = "bottom" if dy > 0 else "top"
            tgt_region = "top" if dy > 0 else "bottom"

        if src not in _user:
            anchors[src_sid].setdefault(src, src_region)
        if tgt not in _user:
            anchors[tgt_sid].setdefault(tgt, tgt_region)

    return anchors


_SPANNING_OVERLAY_PADDING = 20.0


def _compute_spanning_layout(
    layout: dict,
    parsed_groups: list[tuple[str, list[str]]],
    edges: list[dict],
    arrangement,
    layout_style,
    group_spacing,
    group_arrangements,
    group_anchors,
    parsed_constraints,
    group_spacings_map,
    group_preserve_order_map,
    ordered: bool,
    preserve_existing: bool,
    group_sub_groups,
    group_sub_group_edges,
    group_arrangement: Optional[str] = None,
) -> tuple[list, list]:
    """Lay out horizontal groups across adjacent displays left-to-right.

    Computes positions on a combined virtual canvas (sum of all display
    widths), then splits each placement into the correct display using
    display-local x coordinates.  Overlays are also split per display.

    When the packed row extends past the summed physical widths (e.g. a
    single-row timeline of many groups), each display's segment stretches
    proportionally to carry its share of the row.  The downstream camera
    fit (``fit_display_camera_to_entities_if_needed``) then zooms each
    display out to reveal its slice — the user's mental model of
    "zoom out and look across".
    """
    displays = layout.get("displays", [])
    sorted_displays = sorted(
        [d for d in displays if d.get("peer_id") and float(d.get("width") or 0) > 0],
        key=lambda d: float(d.get("x", 0)),
    )
    if not sorted_displays:
        return [], []

    # Physical segments are the stable mapping from virtual-canvas x to a
    # display.  Each segment: (surface_id, x_start, x_end, display_height).
    physical_segments: list[tuple[str, float, float, float]] = []
    cursor = 0.0
    for disp in sorted_displays:
        sid = disp["peer_id"]
        w = float(disp.get("width") or 0)
        h = float(disp.get("height") or 0)
        physical_segments.append((sid, cursor, cursor + w, h))
        cursor += w

    physical_total_w = cursor
    total_h = max(s[3] for s in physical_segments)
    primary_sid = physical_segments[0][0]

    raw_placements, raw_overlays, _ = compute_graph_layout(
        layout,
        primary_sid,
        parsed_groups,
        edges,
        arrangement=arrangement,
        layout_style=layout_style,
        group_spacing=group_spacing,
        bounds=(0.0, 0.0, physical_total_w, total_h),
        group_arrangements=group_arrangements or None,
        anchors=group_anchors or None,
        alignment_constraints=parsed_constraints or None,
        group_spacings=group_spacings_map or None,
        group_preserve_order=group_preserve_order_map or None,
        viewport_dims=(physical_total_w, total_h),
        ordered=ordered,
        preserve_existing=preserve_existing,
        group_sub_groups=group_sub_groups or None,
        group_sub_group_edges=group_sub_group_edges or None,
        group_arrangement=group_arrangement,
    )

    # Measure the true packed extent.  With ``group_arrangement="row"`` and
    # many groups, the packer (force_cols=count) produces a single row that
    # may exceed ``physical_total_w`` — and that's intentional.  If we left
    # segments at physical widths, every placement past the last segment's
    # x_end would collapse onto the last display; see ``_resolve_display``.
    packed_max_x = 0.0
    for p in raw_placements:
        nw = get_entity_dimension(layout, p["entity_id"], "width") or 400.0
        packed_max_x = max(packed_max_x, p["x"] + nw)

    if packed_max_x > physical_total_w and physical_total_w > 0:
        scale = packed_max_x / physical_total_w
        segments: list[tuple[str, float, float, float]] = []
        cursor_v = 0.0
        for sid, phys_start, phys_end, h in physical_segments:
            seg_w = (phys_end - phys_start) * scale
            segments.append((sid, cursor_v, cursor_v + seg_w, h))
            cursor_v += seg_w
    else:
        segments = physical_segments

    def _resolve_display(x: float) -> tuple[str, float]:
        """Map a combined-canvas x to (surface_id, display-local x)."""
        for sid, x_start, x_end, _ in segments:
            if x < x_end:
                return sid, x - x_start
        last_sid, last_start, _, _ = segments[-1]
        return last_sid, x - last_start

    # Re-assign placements with display-local coordinates.
    eid_to_label: dict[str, str] = {}
    for label, eids in parsed_groups:
        for eid in eids:
            eid_to_label[eid] = label

    label_to_color = {ov["label"]: ov["color_index"] for ov in raw_overlays}

    placements: list[dict] = []
    label_surface_items: dict[tuple[str, str], list[tuple[str, float, float]]] = {}
    for p in raw_placements:
        sid, local_x = _resolve_display(p["x"])
        placements.append({**p, "target_surface": sid, "x": local_x})
        key = (eid_to_label.get(p["entity_id"], ""), sid)
        label_surface_items.setdefault(key, []).append(
            (p["entity_id"], local_x, p["y"])
        )

    # Build per-display per-group overlays from adjusted positions.
    group_overlays: list[dict] = []
    for (label, sid), items in label_surface_items.items():
        min_x = min_y = float("inf")
        max_x = max_y = float("-inf")
        entity_ids: list[str] = []
        for eid, px, py in items:
            nw = get_entity_dimension(layout, eid, "width") or 400.0
            nh = get_entity_dimension(layout, eid, "height") or 300.0
            min_x = min(min_x, px)
            min_y = min(min_y, py)
            max_x = max(max_x, px + nw)
            max_y = max(max_y, py + nh)
            entity_ids.append(eid)
        group_overlays.append({
            "label": label,
            "entity_ids": entity_ids,
            "bounds": {
                "min_x": min_x - _SPANNING_OVERLAY_PADDING,
                "min_y": min_y - _SPANNING_OVERLAY_PADDING,
                "max_x": max_x + _SPANNING_OVERLAY_PADDING,
                "max_y": max_y + _SPANNING_OVERLAY_PADDING,
            },
            "color_index": label_to_color.get(label, 0),
            "display_id": sid,
        })

    return placements, group_overlays


@tool_safe(require_layout=True)
def tool_plan_semantic_layout(
    tool_context: ToolContext,
    groups: list[dict],
    edges: list[dict],
    layout_style: Optional[str] = None,
    group_spacing: Optional[str] = None,
    arrangement: Optional[str] = None,
    display_name: Optional[str] = None,
    span_displays: bool = False,
    dry_run: bool = False,
    constraints: Optional[list[dict]] = None,
    ordered: bool = False,
    preserve_existing: bool = False,
    group_arrangement: Optional[str] = None,
) -> dict:
    """
    Arrange entity groups so spatial proximity encodes semantic relatedness.
    The agent specifies which entities belong to each group and how strongly
    groups are related via weighted edges.

    All layout parameters (layout_style, group_spacing, arrangement) are
    optional.  When omitted, the engine auto-selects based on display
    geometry, entity count, and constraints.  The engine considers display
    shape, capacity, and current content when distributing groups.

    Args:
        tool_context: ADK tool context for state management
        groups: List of {"label": str, "entity_ids": list[str]} defining
            semantic groups. Each group dict also supports optional fields:
            - "arrangement": "grid"|"horizontal"|"vertical" — overrides
              the top-level arrangement for this group only.
            - "region": named region to anchor this group (e.g. "top-left",
              "bottom-right", "center"). Other groups flow around it.
            - "spacing": "tight"|"medium"|"large" — per-group internal
              spacing, independent of top-level group_spacing.
            - "preserve_order": bool — when True, entities are placed in
              the exact order given in "entity_ids" (no size-based
              reordering). Use when reading order matters.
            - "priority": "high"|"medium"|"low" — high-priority groups
              prefer the primary display (largest or center-tagged) when
              distributing across multiple displays.
            - "sub_groups": list of {"label": str, "entity_ids": list[str]}
              for nested/hierarchical layout. The engine allocates a region
              for the parent group, then lays out sub-groups within it.
              Sub-group entity_ids must be a subset of the parent's
              entity_ids.
            - "sub_group_edges": list of {"source": str, "target": str,
              "weight": float|str} — edges between sub-groups within this
              parent, controlling sub-group proximity. Same weight format
              as top-level edges (numeric or qualitative labels).
        edges: List of {"source": str, "target": str, "weight": float|str}
            where source/target are group labels and weight expresses
            semantic relatedness. Weight can be:
            - A number 0.0-1.0 (1.0 = very related/close, 0.0 = unrelated/far)
            - A qualitative label: "strongly_related" (0.9),
              "related" (0.7), "somewhat_related" (0.45),
              "weakly_related" (0.25), "unrelated" (0.05)
            Prefer qualitative labels for clearer intent. Weights control
            both adjacency (which groups neighbor each other) and gap size
            (how much space between them).
        layout_style: "organic" (force-directed), "packed" (compact with
            proximity), or "hierarchical" (layered by connectivity).
            Omit to auto-select.
        group_spacing: "tight", "medium", or "large" gap between groups.
            Omit to auto-select based on display count and entity count.
        arrangement: Intra-group layout - "grid", "horizontal", or "vertical".
            Omit to auto-select per group based on region shape.
        display_name: Optional target display name/tag. If omitted,
            groups are distributed across displays using semantic-aware
            assignment (considering display capacity, shape, and topics).
            Ignored when span_displays=True.
        span_displays: If True, lay out horizontal groups across ALL
            displays left-to-right as a continuous timeline. Each group
            row flows from the leftmost display into adjacent displays
            when it overflows. Use for sequential/timeline layouts that
            would be too wide for a single display. Ignores display_name.
        dry_run: If True, returns plan without applying (default False)
        constraints: Optional inter-group constraints. Each dict has:
            - "type": "align"
            - "groups": list of group labels to align
            - "axis": "horizontal" (same row) or "vertical" (same column)
        ordered: If True, groups are arranged in the exact order given in
            the `groups` list (left-to-right, top-to-bottom). Use when
            the sequence of groups matters — any sortable dimension the
            caller determines. The caller is responsible for sorting the
            groups list before passing. Default False.
        preserve_existing: If True, entities NOT in any provided group
            keep their current positions. The engine repositions only the
            grouped entities, working around preserved content. Default False.
        group_arrangement: Inter-group layout shape. Controls how GROUPS
            (not entities within groups) are laid out relative to each
            other.  "row" → all groups in a single horizontal line
            (overflow onto adjacent displays via span_displays). "column"
            → a single vertical stack. "grid" → 2D packing that wraps
            based on display aspect ratio. Only applies when ordered=True.
            When ordered=True and this is omitted, defaults to "row".
            Pass "grid" explicitly to opt into aspect-aware wrapping.

    Returns:
        Dictionary with plan details, spatial summary, and validation warnings
    """
    layout = tool_context.state.get("current_layout")
    entities = tool_context.state.get("entities", [])
    node_positions = layout.get("node_positions", {})

    # --- Validate parameters ---
    if not groups:
        return {"status": "error", "message": "No groups provided."}

    # Validate explicit params; None means auto-infer (skip validation)
    if layout_style is not None and layout_style not in _VALID_LAYOUT_STYLES:
        return {
            "status": "error",
            "message": (
                f"Unknown layout_style '{layout_style}'. "
                f"Use one of: {', '.join(sorted(_VALID_LAYOUT_STYLES))}"
            ),
        }
    if group_spacing is not None and group_spacing not in _VALID_GROUP_SPACINGS:
        return {
            "status": "error",
            "message": (
                f"Unknown group_spacing '{group_spacing}'. "
                f"Use one of: {', '.join(sorted(_VALID_GROUP_SPACINGS))}"
            ),
        }
    if arrangement is not None and arrangement not in _VALID_ARRANGEMENTS:
        return {
            "status": "error",
            "message": (
                f"Unknown arrangement '{arrangement}'. "
                f"Use one of: {', '.join(sorted(_VALID_ARRANGEMENTS))}"
            ),
        }
    if (
        group_arrangement is not None
        and group_arrangement not in _VALID_GROUP_ARRANGEMENTS
    ):
        return {
            "status": "error",
            "message": (
                f"Unknown group_arrangement '{group_arrangement}'. "
                f"Use one of: {', '.join(sorted(_VALID_GROUP_ARRANGEMENTS))}"
            ),
        }

    # ordered=True without an explicit group_arrangement implies a single
    # horizontal sequence.  Without this default the engine falls back to
    # aspect-aware wrapping, which can produce a 1–2 column stack when group
    # rects are tall — the opposite of what "ordered" usually implies.
    if ordered and group_arrangement is None:
        group_arrangement = "row"

    # Validate group structure and entity existence
    group_labels = set()
    all_entity_ids_in_groups = []
    parsed_groups: list[tuple[str, list[str]]] = []
    group_sub_groups: dict[str, list[tuple[str, list[str]]]] = {}
    group_sub_group_edges: dict[str, list[dict]] = {}
    for g in groups:
        label = g.get("label")
        eids = g.get("entity_ids", [])
        if not label or not isinstance(label, str):
            return {"status": "error", "message": f"Group missing 'label': {g}"}
        if not eids:
            return {
                "status": "error",
                "message": f"Group '{label}' has no entity_ids.",
            }
        missing = [eid for eid in eids if eid not in node_positions]
        if missing:
            return {
                "status": "error",
                "message": (
                    f"Group '{label}' references unknown entities: "
                    f"{missing[:5]}"
                ),
            }
        group_labels.add(label)
        all_entity_ids_in_groups.extend(eids)
        parsed_groups.append((label, eids))

        # Parse optional sub_groups for nested layout
        raw_subs = g.get("sub_groups")
        if raw_subs and isinstance(raw_subs, list):
            parsed_subs: list[tuple[str, list[str]]] = []
            for sg in raw_subs:
                sg_label = sg.get("label")
                sg_eids = sg.get("entity_ids", [])
                if not sg_label or not sg_eids:
                    continue
                # Validate sub-group entities are subset of parent
                sg_missing = [eid for eid in sg_eids if eid not in eids]
                if sg_missing:
                    return {
                        "status": "error",
                        "message": (
                            f"Sub-group '{sg_label}' of '{label}' references "
                            f"entities not in parent group: {sg_missing[:5]}"
                        ),
                    }
                parsed_subs.append((sg_label, sg_eids))
            if parsed_subs:
                group_sub_groups[label] = parsed_subs

                # Parse optional edges between sub-groups
                raw_sub_edges = g.get("sub_group_edges", [])
                if raw_sub_edges and isinstance(raw_sub_edges, list):
                    sub_label_set = {s[0] for s in parsed_subs}
                    sub_edges_list: list[dict] = []
                    for se in raw_sub_edges:
                        se_src = se.get("source")
                        se_tgt = se.get("target")
                        se_weight = se.get("weight", 0.5)
                        if se_src not in sub_label_set or se_tgt not in sub_label_set:
                            return {
                                "status": "error",
                                "message": (
                                    f"Sub-group edge in '{label}' references "
                                    f"unknown sub-group: {se_src} -> {se_tgt}"
                                ),
                            }
                        # Resolve qualitative weight labels
                        if isinstance(se_weight, str) and se_weight in _QUALITATIVE_WEIGHTS:
                            se_weight = _QUALITATIVE_WEIGHTS[se_weight]
                        sub_edges_list.append({
                            "source": se_src,
                            "target": se_tgt,
                            "weight": se_weight,
                        })
                    if sub_edges_list:
                        group_sub_group_edges[label] = sub_edges_list

    # Validate edges — accept both numeric (0.0-1.0) and qualitative labels
    for edge in edges:
        src = edge.get("source")
        tgt = edge.get("target")
        weight = edge.get("weight")
        if src not in group_labels:
            return {
                "status": "error",
                "message": f"Edge source '{src}' is not a group label.",
            }
        if tgt not in group_labels:
            return {
                "status": "error",
                "message": f"Edge target '{tgt}' is not a group label.",
            }
        if weight is not None:
            # Resolve qualitative label to numeric weight
            if isinstance(weight, str) and weight in _QUALITATIVE_WEIGHTS:
                edge["weight"] = _QUALITATIVE_WEIGHTS[weight]
            elif isinstance(weight, str):
                # Try parsing as a numeric string first
                try:
                    w = float(weight)
                    if not (0.0 <= w <= 1.0):
                        return {
                            "status": "error",
                            "message": f"Edge weight must be 0.0-1.0, got {w}.",
                        }
                    edge["weight"] = w
                except (TypeError, ValueError):
                    return {
                        "status": "error",
                        "message": (
                            f"Unknown edge weight '{weight}'. Use a number "
                            f"(0.0-1.0) or one of: {_QUALITATIVE_WEIGHT_NAMES}"
                        ),
                    }
            else:
                try:
                    w = float(weight)
                    if not (0.0 <= w <= 1.0):
                        return {
                            "status": "error",
                            "message": f"Edge weight must be 0.0-1.0, got {w}.",
                        }
                except (TypeError, ValueError):
                    return {
                        "status": "error",
                        "message": (
                            f"Edge weight must be numeric or one of: "
                            f"{_QUALITATIVE_WEIGHT_NAMES}. Got {weight!r}."
                        ),
                    }

    # --- Parse per-group overrides (Layer 4) ---
    _valid_regions = set(REGION_SLICES.keys())
    group_arrangements: dict[str, str] = {}
    group_anchors: dict[str, str] = {}
    group_spacings_map: dict[str, str] = {}
    group_preserve_order_map: dict[str, bool] = {}
    group_priorities_map: dict[str, str] = {}
    _valid_priorities = {"high", "medium", "low"}
    for g in groups:
        label = g.get("label", "")
        g_arr = g.get("arrangement")
        if g_arr is not None:
            if g_arr not in _VALID_ARRANGEMENTS:
                return {
                    "status": "error",
                    "message": (
                        f"Group '{label}' has invalid arrangement '{g_arr}'. "
                        f"Use one of: {', '.join(sorted(_VALID_ARRANGEMENTS))}"
                    ),
                }
            group_arrangements[label] = g_arr
        g_region = g.get("region")
        if g_region is not None:
            if g_region.lower() not in _valid_regions:
                return {
                    "status": "error",
                    "message": (
                        f"Group '{label}' has invalid region '{g_region}'. "
                        f"Use one of: {', '.join(sorted(_valid_regions))}"
                    ),
                }
            group_anchors[label] = g_region.lower()
        g_spacing = g.get("spacing")
        if g_spacing is not None:
            if g_spacing not in _VALID_GROUP_SPACINGS:
                return {
                    "status": "error",
                    "message": (
                        f"Group '{label}' has invalid spacing '{g_spacing}'. "
                        f"Use one of: {', '.join(sorted(_VALID_GROUP_SPACINGS))}"
                    ),
                }
            group_spacings_map[label] = g_spacing
        g_preserve = g.get("preserve_order")
        if g_preserve is not None:
            if not isinstance(g_preserve, bool):
                return {
                    "status": "error",
                    "message": (
                        f"Group '{label}' has invalid preserve_order "
                        f"{g_preserve!r}. Must be a boolean."
                    ),
                }
            group_preserve_order_map[label] = g_preserve
        g_priority = g.get("priority")
        if g_priority is not None:
            if g_priority not in _valid_priorities:
                return {
                    "status": "error",
                    "message": (
                        f"Group '{label}' has invalid priority '{g_priority}'. "
                        f"Use one of: {', '.join(sorted(_valid_priorities))}"
                    ),
                }
            group_priorities_map[label] = g_priority

    # Validate inter-group constraints
    parsed_constraints: list[dict] = []
    _valid_constraint_axes = {"horizontal", "vertical"}
    for c in (constraints or []):
        c_type = c.get("type")
        if c_type != "align":
            return {
                "status": "error",
                "message": (
                    f"Unknown constraint type '{c_type}'. "
                    "Only 'align' is supported."
                ),
            }
        c_groups = c.get("groups", [])
        if len(c_groups) < 2:
            return {
                "status": "error",
                "message": "Align constraint requires at least 2 groups.",
            }
        for cg in c_groups:
            if cg not in group_labels:
                return {
                    "status": "error",
                    "message": (
                        f"Constraint references unknown group '{cg}'."
                    ),
                }
        c_axis = c.get("axis", "")
        if c_axis not in _valid_constraint_axes:
            return {
                "status": "error",
                "message": (
                    f"Unknown constraint axis '{c_axis}'. "
                    f"Use one of: {', '.join(sorted(_valid_constraint_axes))}"
                ),
            }
        parsed_constraints.append({"groups": c_groups, "axis": c_axis})

    # --- Resolve display and compute layout ---
    surface_bounds = layout.get("surface_bounds", {})

    if span_displays:
        placements, group_overlays = _compute_spanning_layout(
            layout,
            parsed_groups,
            edges,
            arrangement=arrangement,
            layout_style=layout_style,
            group_spacing=group_spacing,
            group_arrangements=group_arrangements or None,
            group_anchors=group_anchors or None,
            parsed_constraints=parsed_constraints or None,
            group_spacings_map=group_spacings_map or None,
            group_preserve_order_map=group_preserve_order_map or None,
            ordered=ordered,
            preserve_existing=preserve_existing,
            group_sub_groups=group_sub_groups or None,
            group_sub_group_edges=group_sub_group_edges or None,
            group_arrangement=group_arrangement,
        )
    elif display_name:
        surface_id = resolve_display_name(layout, display_name)
        if not surface_id:
            return {
                "status": "error",
                "message": f"Display '{display_name}' not found.",
            }
        # Use stable workspace bounds first so semantic layouts map into
        # display-local canvas coordinates predictably across camera changes.
        # Fall back to visible/content bounds for legacy payloads.
        bounds = (
            get_surface_workspace_bounds(layout, surface_id)
            or get_surface_visible_bounds(layout, surface_id)
            or layout.get("surface_content_bounds", {}).get(surface_id)
            or surface_bounds.get(surface_id, (0.0, 0.0, 1920.0, 1080.0))
        )
        viewport_dims = get_surface_viewport_dims(layout, surface_id)
        surface_placements, surface_overlays, _ = compute_graph_layout(
            layout,
            surface_id,
            parsed_groups,
            edges,
            arrangement=arrangement,
            layout_style=layout_style,
            group_spacing=group_spacing,
            bounds=bounds,
            group_arrangements=group_arrangements or None,
            anchors=group_anchors or None,
            alignment_constraints=parsed_constraints or None,
            group_spacings=group_spacings_map or None,
            group_preserve_order=group_preserve_order_map or None,
            viewport_dims=viewport_dims,
            ordered=ordered,
            preserve_existing=preserve_existing,
            group_sub_groups=group_sub_groups or None,
            group_sub_group_edges=group_sub_group_edges or None,
            group_arrangement=group_arrangement,
        )
        placements = surface_placements
        group_overlays = surface_overlays
    else:
        # Distribute groups across displays using semantic-aware assignment
        groups_dict = {label: eids for label, eids in parsed_groups}
        display_profiles = build_all_display_profiles(layout, entities)
        assignments = assign_groups_to_displays(
            groups_dict, edges, layout, display_profiles, entities,
            group_priorities=group_priorities_map or None,
        )

        cross_display_anchors = _compute_cross_display_anchors(
            assignments, edges, layout, group_anchors,
        )

        placements = []
        group_overlays = []
        color_index = 0
        for surface_id, groups_on_surface in assignments.items():
            bounds = (
                get_surface_workspace_bounds(layout, surface_id)
                or get_surface_visible_bounds(layout, surface_id)
                or layout.get("surface_content_bounds", {}).get(surface_id)
                or surface_bounds.get(surface_id)
            )
            if not bounds:
                continue
            # Filter edges to only include groups on this surface
            labels_on_surface = {label for label, _ in groups_on_surface}
            surface_edges = [
                e for e in edges
                if e.get("source") in labels_on_surface
                and e.get("target") in labels_on_surface
            ]
            # Merge user-provided anchors with cross-display proximity anchors
            merged_anchors = dict(cross_display_anchors.get(surface_id, {}))
            if group_anchors:
                merged_anchors.update(group_anchors)
            viewport_dims = get_surface_viewport_dims(layout, surface_id)
            surface_placements, surface_overlays, _ = compute_graph_layout(
                layout,
                surface_id,
                groups_on_surface,
                surface_edges,
                arrangement=arrangement,
                layout_style=layout_style,
                group_spacing=group_spacing,
                bounds=bounds,
                color_index_start=color_index,
                group_arrangements=group_arrangements or None,
                anchors=merged_anchors or None,
                alignment_constraints=parsed_constraints or None,
                group_spacings=group_spacings_map or None,
                group_preserve_order=group_preserve_order_map or None,
                viewport_dims=viewport_dims,
                ordered=ordered,
                preserve_existing=preserve_existing,
                group_arrangement=group_arrangement,
            )
            placements.extend(surface_placements)
            group_overlays.extend(surface_overlays)
            color_index += len(groups_on_surface)

    if not placements:
        return {
            "status": "info",
            "message": "No placements computed — check group entity IDs.",
        }

    plan = {
        "placements": placements,
        "strategy": "semantic_layout",
        "groups": [
            {"label": label, "entity_count": len(eids)}
            for label, eids in parsed_groups
        ],
        "group_overlays": group_overlays,
        "summary": (
            f"Semantic layout: {len(placements)} entities in "
            f"{len(parsed_groups)} groups ({layout_style}, {group_spacing} spacing)."
        ),
    }

    if dry_run:
        return {
            "status": "preview",
            "message": f"Dry run — {plan['summary']}",
            "plan": plan,
        }

    # Apply placements
    for placement in placements:
        layout = move_entity(
            layout,
            placement["entity_id"],
            placement["target_surface"],
            (placement["x"], placement["y"]),
        )

    # Auto-fit camera on each affected display so the new layout is visible.
    # Force unconditional fit: plan_semantic_layout is a major reorganization
    # and the user should always see the full result, even if content
    # technically fits in the current viewport.
    surface_entity_ids: dict[str, list[str]] = {}
    for placement in placements:
        sid = placement["target_surface"]
        surface_entity_ids.setdefault(sid, []).append(placement["entity_id"])
    for sid, eids in surface_entity_ids.items():
        camera_update = fit_display_camera_to_entities_if_needed(
            layout, sid, eids, force=True,
        )
        if camera_update:
            layout.setdefault("_camera_updates", {})[sid] = camera_update

    # Inject group overlay metadata for frontend visualization. Merge with
    # overlays already generated earlier in this turn (e.g. one call per display).
    if group_overlays:
        merged_overlays = _merge_group_overlays(
            layout.get("_group_overlays"),
            group_overlays,
        )
        layout["_group_overlays"] = merged_overlays

        highlight_all, highlight_colors, entity_tags = _build_highlight_state_from_overlays(
            merged_overlays,
            dict(layout.get("entity_tags") or {}),
        )
        layout["highlighted_entities"] = highlight_all
        layout["highlighted_entity_colors"] = highlight_colors
        layout["entity_tags"] = entity_tags

    # Compute group stage metadata for frontend staged animation
    if group_overlays:
        group_stages = []
        for overlay in group_overlays:
            member_ids = overlay["entity_ids"]
            positions = [
                layout["node_positions"][eid]
                for eid in member_ids
                if eid in layout.get("node_positions", {})
            ]
            if positions:
                cx = sum(p[0] for p in positions) / len(positions)
                cy = sum(p[1] for p in positions) / len(positions)
                group_stages.append({
                    "label": overlay["label"],
                    "entity_ids": member_ids,
                    "center": [cx, cy],
                })
        # Extend rather than overwrite so that multiple calls per turn
        # (e.g. one per display) accumulate all group stages.
        existing = tool_context.state.get("_layout_group_stages") or []
        tool_context.state["_layout_group_stages"] = existing + group_stages

    # Snapshot invariants so the agent can detect what the user established
    # on a prior turn (grouping, display assignment, ordering) and offer to
    # preserve them instead of blindly reorganizing.
    entity_names = layout.get("entity_names", {})

    display_label_map: Dict[str, str] = {}
    for disp in layout.get("displays", []):
        peer_id = disp.get("peer_id", "")
        tags = disp.get("tags", [])
        if peer_id:
            display_label_map[peer_id] = ", ".join(tags) if tags else peer_id

    entity_to_display = {p["entity_id"]: p["target_surface"] for p in placements}
    prior_by_label = {
        g.get("label"): g
        for g in (tool_context.state.get("_active_grouping") or {}).get("groups", [])
    }

    new_group_snapshots = []
    constraint_changes = []
    for label, eids in parsed_groups:
        counts: Dict[str, int] = {}
        for eid in eids:
            did = entity_to_display.get(eid)
            if did:
                counts[did] = counts.get(did, 0) + 1

        dominant_display = None
        dominant_label = None
        if counts:
            total = sum(counts.values())
            top_did, top_count = max(counts.items(), key=lambda kv: kv[1])
            # Treat ≥80% concentration as a per-display assignment invariant.
            if top_count / total >= 0.8:
                dominant_display = top_did
                dominant_label = display_label_map.get(top_did, top_did)

        new_group_snapshots.append({
            "label": label,
            "entity_ids": eids,
            "entity_names": [entity_names.get(eid, eid) for eid in eids],
            "display_id": dominant_display,
            "display_label": dominant_label,
        })

        prior = prior_by_label.get(label)
        if prior and prior.get("display_id"):
            prior_label = prior.get("display_label") or prior["display_id"]
            if dominant_display is None:
                constraint_changes.append({
                    "kind": "display_assignment_lost",
                    "group": label,
                    "from": prior_label,
                    "to": "split across multiple displays",
                })
            elif dominant_display != prior["display_id"]:
                constraint_changes.append({
                    "kind": "display_assignment_changed",
                    "group": label,
                    "from": prior_label,
                    "to": dominant_label,
                })

    # Detect whether the agent re-submitted the exact same grouping (same
    # labels + entity_ids, any order).  When true, the tool call is really a
    # re-arrangement of an existing grouping, not a new regrouping; surface a
    # flag so the agent can phrase its response accordingly and avoid
    # redundant group-authoring work on the next turn.
    prior_groups = (tool_context.state.get("_active_grouping") or {}).get("groups") or []
    prior_fp = {g.get("label"): tuple(g.get("entity_ids", [])) for g in prior_groups}
    new_fp = {label: tuple(eids) for label, eids in parsed_groups}
    grouping_unchanged = bool(prior_fp) and prior_fp == new_fp

    tool_context.state["_active_grouping"] = {
        "groups": new_group_snapshots,
        "ordered": bool(ordered),
        "group_arrangement": group_arrangement,
    }
    # Suppress the Active Grouping warning for the remainder of this
    # invocation.  The warning is meant to protect groupings from a
    # *previous* turn — not groups the agent just created.  Without
    # this flag the before-model callback sees the new grouping on the
    # very next LLM call and injects a STOP warning, causing the agent
    # to undo its own work.
    tool_context.state["_active_grouping_just_created"] = True
    tool_context.state["_grouping_created_at_user_count"] = (
        tool_context.state.get("_user_msg_count", 0)
    )

    tool_context.state["current_layout"] = layout

    report = validate_layout(layout, entities)
    validation_warnings = report["issues"] if report["issues"] else None

    result = {
        "status": "success",
        "message": plan["summary"],
        "plan": plan,
    }

    # Add human-readable spatial summary so the agent can assess the
    # layout in natural language rather than parsing raw coordinates.
    spatial_summary = summarize_group_layout(layout, group_overlays, placements)
    if spatial_summary:
        result["spatial_summary"] = spatial_summary

    if validation_warnings:
        result["validation_warnings"] = validation_warnings

    if grouping_unchanged:
        result["grouping_reused"] = True
        result["grouping_reused_note"] = (
            "Same grouping as the prior turn — this call re-arranged existing "
            "groups rather than regrouping. If that was not the intent, check "
            "the labels and entity_ids you passed."
        )

    if constraint_changes:
        result["constraint_changes"] = constraint_changes
        lines = ["This layout changes invariants established on a prior turn:"]
        for ch in constraint_changes:
            lines.append(f"  - Group '{ch['group']}' was on {ch['from']} → now {ch['to']}.")
        lines.append("If the user did not ask for these changes, either call again with parameters that preserve the prior placement (e.g. display_name, or one plan call per target display), or acknowledge the change explicitly in your response.")
        result["constraint_change_note"] = "\n".join(lines)

    return result


@tool_safe(require_layout=True)
def tool_validate_layout(tool_context: ToolContext) -> dict:
    """
    Check layout quality — overlaps, overflow, poor spacing, split clusters,
    uneven display load. Read-only, no history.

    Args:
        tool_context: ADK tool context for state management

    Returns:
        Dictionary with structured quality report:
        - status: "ok" (no issues) or "issues_found"
        - report.issues: list of {type, severity, entities, message}
          Issue types: "overlap", "overflow", "spacing", "split_cluster", "uneven_load"
        - report.summary: human-readable overview
    """
    layout = tool_context.state.get("current_layout")
    entities = tool_context.state.get("entities", [])

    report = validate_layout(layout, entities)

    issue_count = len(report["issues"])
    if issue_count == 0:
        message = "Layout looks good — no issues detected."
    else:
        message = f"Found {issue_count} issue(s) in the layout."

    return {
        "status": "ok" if issue_count == 0 else "issues_found",
        "message": message,
        "report": report,
    }
