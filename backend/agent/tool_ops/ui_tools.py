"""Transient UI-action tools (show/highlight/focus/camera/tags/timeline)."""

import re
from typing import Optional
from google.adk.tools.tool_context import ToolContext

from .common import tool_safe
from ..layout_operations import (
    compute_entities_bounds,
    compute_fit_camera,
    resolve_display_name,
)
from ..layout_ops.constants import MAX_CAMERA_ZOOM, MIN_CAMERA_ZOOM
from ..layout_ops.dimensions import _parse_positive_float
from ..layout_ops.regions import REGION_SLICES, slice_bounds_for_region


_UI_COLOR_TOKENS: dict[str, str] = {
    "ui_red": "#ef4444",
    "ui_green": "#22c55e",
    "ui_blue": "#3b82f6",
    "ui_yellow": "#eab308",
    "ui_orange": "#f97316",
    "ui_purple": "#a855f7",
    "ui_pink": "#ec4899",
    "ui_teal": "#14b8a6",
}

_TAG_SEPARATOR_RE = re.compile(r"[_\s]+")


def _normalize_color(color: str | None) -> str | None:
    """Return a sanitised CSS color string, or None."""
    if not isinstance(color, str):
        return None
    candidate = color.strip()
    if candidate in _UI_COLOR_TOKENS:
        return _UI_COLOR_TOKENS[candidate]
    if candidate and len(candidate) <= 64 and "\n" not in candidate and "\r" not in candidate:
        return candidate
    return None


def _normalize_tag_display(tag: str) -> str:
    """Normalize tag label for display (collapse spaces/underscores)."""
    return _TAG_SEPARATOR_RE.sub(" ", tag.strip()).strip()


def _canonical_tag_key(tag: str) -> str:
    """Canonical key for tag dedupe/removal comparisons."""
    normalized = _normalize_tag_display(tag)
    return normalized.lower() if normalized else ""


@tool_safe(require_layout=True)
def tool_show_entity(
    tool_context: ToolContext,
    color_map: dict[str, list[str]],
) -> dict:
    """
    Show entities in the UI — applies a visual highlight glow and pans the
    camera to frame them. Transient action, NOT added to history.

    Use for: "where is X?", "which views show Y?", "find views about Z",
    "show me X". Use color to encode meaning (e.g., green for positive,
    red for negative).

    Args:
        color_map: CSS color string → list of entity IDs to highlight with
            that color. Use standard CSS colors: "red", "#ef4444", "blue",
            "#3b82f6", "green", "orange", "purple". Use the key "default"
            for entities that should glow without a specific color.
    """
    layout = tool_context.state.get("current_layout")

    if not color_map:
        return {"status": "error", "message": "color_map cannot be empty."}

    node_positions = layout.get("node_positions", {})
    existing_ids = layout.get("highlighted_entities", [])
    if not isinstance(existing_ids, list):
        existing_ids = []
    existing_colors = layout.get("highlighted_entity_colors", {})
    if not isinstance(existing_colors, dict):
        existing_colors = {}

    all_valid_ids: list[str] = []
    for color_key, entity_ids in color_map.items():
        if not isinstance(entity_ids, list):
            continue
        normalized_color = None if color_key == "default" else _normalize_color(color_key)
        for eid in entity_ids:
            if eid not in node_positions:
                continue
            all_valid_ids.append(eid)
            if normalized_color is None:
                existing_colors.pop(eid, None)
            else:
                existing_colors[eid] = normalized_color

    if not all_valid_ids:
        return {
            "status": "error",
            "message": "No valid entities found in color_map.",
        }

    merged_ids = list(dict.fromkeys([*existing_ids, *all_valid_ids]))
    layout["highlighted_entities"] = merged_ids
    layout["highlighted_entity_colors"] = {
        eid: value
        for eid, value in existing_colors.items()
        if eid in merged_ids and isinstance(value, str) and value.strip()
    }
    tool_context.state["current_layout"] = layout

    names = [layout.get("entity_names", {}).get(eid, eid) for eid in all_valid_ids]
    return {
        "status": "success",
        "_action_type": "show_entity",
        "message": f"Showing {len(all_valid_ids)} entities: {', '.join(names)}",
    }


@tool_safe(require_layout=True)
def tool_highlight_text(
    tool_context: ToolContext,
    highlights: dict[str, list[str]],
    color: str = "#fde68a",
) -> dict:
    """
    Highlight specific text snippets inside entity text content.
    Transient action, NOT added to history.

    Use when the user asks to highlight particular phrases, sentences, or
    keywords within entity nodes — as opposed to tool_show_entity which
    glows the whole node.

    Args:
        highlights: Entity ID → list of exact text substrings to highlight
            in that entity. Snippets must be case-sensitive exact matches
            of text within the entity's content.
        color: CSS color for the highlight background (default amber).
            Applied uniformly to all highlights in this call.
    """
    layout = tool_context.state.get("current_layout")

    if not highlights:
        return {"status": "error", "message": "highlights cannot be empty."}

    node_positions = layout.get("node_positions", {})
    entities = tool_context.state.get("entities", [])

    # Build entity text lookup
    entity_text_map: dict[str, str] = {}
    for e in entities:
        eid = e.get("entity_id") or e.get("id")
        if eid:
            val = e.get("value", "")
            if isinstance(val, str):
                entity_text_map[eid] = val

    existing = layout.get("text_highlights", [])
    total_highlighted = 0
    total_missing = 0
    processed_entities: list[str] = []

    for entity_id, text_snippets in highlights.items():
        if entity_id not in node_positions:
            continue
        if not isinstance(text_snippets, list) or not text_snippets:
            continue

        entity_text = entity_text_map.get(entity_id, "")

        valid_snippets = []
        for snippet in text_snippets:
            if not snippet:
                continue
            if entity_text and snippet in entity_text:
                valid_snippets.append(snippet)
            elif entity_text:
                total_missing += 1
            else:
                valid_snippets.append(snippet)

        if valid_snippets:
            existing.append(
                {
                    "entity_id": entity_id,
                    "texts": valid_snippets,
                    "color": color,
                }
            )
            total_highlighted += len(valid_snippets)
            processed_entities.append(entity_id)

    if not processed_entities:
        return {
            "status": "error",
            "message": "No valid snippets found in any of the specified entities.",
        }

    layout["text_highlights"] = existing
    tool_context.state["current_layout"] = layout

    entity_names = layout.get("entity_names", {})
    names = [entity_names.get(eid, eid) for eid in processed_entities]
    msg = f"Highlighted {total_highlighted} snippet(s) across {len(processed_entities)} entity(ies): {', '.join(names)}"
    if total_missing:
        msg += f" ({total_missing} snippet(s) not found in text)"
    return {
        "status": "success",
        "_action_type": "text_highlight",
        "message": msg,
    }


@tool_safe(require_layout=True)
def tool_clear_text_highlights(
    tool_context: ToolContext,
    entity_ids: Optional[list[str]] = None,
) -> dict:
    """
    Remove text-span highlights previously applied by tool_highlight_text.

    Args:
        entity_ids: Entity IDs whose text highlights to clear.
            Omit or pass empty list to clear ALL text highlights.
    """
    layout = tool_context.state.get("current_layout")

    if not entity_ids:
        layout["clear_text_highlight_ids"] = ["__all__"]
        tool_context.state["current_layout"] = layout
        return {
            "status": "success",
            "_action_type": "clear_text_highlight",
            "message": "Cleared all text highlights.",
        }

    node_positions = layout.get("node_positions", {})
    valid_ids = [eid for eid in entity_ids if eid in node_positions]
    if not valid_ids:
        return {
            "status": "error",
            "message": "No valid entities found in the provided list.",
        }

    layout["clear_text_highlight_ids"] = valid_ids
    tool_context.state["current_layout"] = layout

    names = [layout.get("entity_names", {}).get(eid, eid) for eid in valid_ids]
    return {
        "status": "success",
        "_action_type": "clear_text_highlight",
        "message": f"Cleared text highlights from {len(valid_ids)} entity(ies): {', '.join(names)}",
    }


def _ensure_entity_tags(layout: dict) -> dict:
    tags = layout.get("entity_tags")
    if not isinstance(tags, dict):
        tags = {}
        layout["entity_tags"] = tags
    return tags


def _normalize_tag_strings(raw: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for t in raw:
        if not t or not isinstance(t, str):
            continue
        display = _normalize_tag_display(t)
        key = _canonical_tag_key(display)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(display)
    return out


def _stringify_tag_value(value: object) -> str:
    """Coerce a single tag value (number, bool, or string) to a display string.

    Renders whole-number floats without a trailing ``.0`` (``8.0`` → ``"8"``)
    so computed averages tag cleanly.
    """
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else str(value)
    if isinstance(value, (int, str)):
        return str(value)
    return ""


def _tag_value_to_strings(value: object) -> list[str]:
    """Coerce a tag value (scalar number/string, or list thereof) to tag strings."""
    items = value if isinstance(value, list) else [value]
    out: list[str] = []
    for item in items:
        s = _stringify_tag_value(item)
        if s:
            out.append(s)
    return out


def _build_entity_new_tags(
    tag_map: dict, node_positions: dict
) -> tuple[dict[str, list[str]], list[str]]:
    """Invert a tag_map into per-entity tag lists, tolerant of input orientation.

    Accepts two shapes the agent commonly produces:
      * tag-keyed   ``{tag_string: [entity_id, ...]}`` (the documented form), and
      * entity-keyed ``{entity_id: tag | [tag, ...]}`` (natural when every entity
        gets a *distinct* computed value, e.g. averages).

    Orientation is inferred from whether the keys are known entity IDs. Numeric
    values are coerced to strings so ``{entity_id: 8.9}`` works.

    Returns ``(entity_new_tags, valid_tag_names)``.
    """
    entity_new_tags: dict[str, list[str]] = {}
    valid_tag_names: list[str] = []

    keys = list(tag_map.keys())
    entity_key_count = sum(1 for k in keys if k in node_positions)

    # Entity-keyed: keys are entity IDs, values are the tag(s) for that entity.
    if entity_key_count and entity_key_count >= len(keys) / 2:
        for eid, raw_tags in tag_map.items():
            if eid not in node_positions:
                continue
            for tag in _tag_value_to_strings(raw_tags):
                tag_clean = _normalize_tag_display(tag)
                if not tag_clean:
                    continue
                valid_tag_names.append(tag_clean)
                entity_new_tags.setdefault(eid, []).append(tag_clean)
        return entity_new_tags, valid_tag_names

    # Tag-keyed: keys are tags, values are the entity IDs receiving that tag.
    for tag, entity_ids in tag_map.items():
        tag_clean = _normalize_tag_display(tag) if isinstance(tag, str) else ""
        if not tag_clean:
            continue
        valid_tag_names.append(tag_clean)
        if isinstance(entity_ids, str):  # tolerate a single id passed as a string
            entity_ids = [entity_ids]
        if not isinstance(entity_ids, list):
            continue
        for eid in entity_ids:
            if eid in node_positions:
                entity_new_tags.setdefault(eid, []).append(tag_clean)

    return entity_new_tags, valid_tag_names


@tool_safe(require_layout=True)
def tool_clear_entity_tags(
    tool_context: ToolContext,
    entity_ids: list[str] | None = None,
) -> dict:
    """
    Clear all tags from specific entities, or from every entity on the canvas.

    Args:
        tool_context: ADK tool context for state management
        entity_ids: List of entity IDs to clear tags from. When omitted
            or empty, clears tags from ALL entities on the canvas.
            Does not move entities.
    """
    layout = tool_context.state.get("current_layout")
    entity_tags = _ensure_entity_tags(layout)

    if not entity_ids:
        entity_tags.clear()
        layout["_group_overlays"] = []
        tool_context.state["current_layout"] = layout
        return {
            "status": "success",
            "_action_type": "clear_entity_tags",
            "message": "Cleared all entity tags.",
        }

    node_positions = layout.get("node_positions", {})
    valid_ids = [eid for eid in entity_ids if eid in node_positions]
    if not valid_ids:
        return {
            "status": "error",
            "message": "No valid entities found in the provided list.",
        }

    for eid in valid_ids:
        entity_tags.pop(eid, None)

    cleared = set(valid_ids)
    overlays = layout.get("_group_overlays") or []
    pruned_overlays = []
    for overlay in overlays:
        remaining = [eid for eid in overlay.get("entity_ids", []) if eid not in cleared]
        if remaining:
            new_overlay = dict(overlay)
            new_overlay["entity_ids"] = remaining
            pruned_overlays.append(new_overlay)
    layout["_group_overlays"] = pruned_overlays

    tool_context.state["current_layout"] = layout

    names = [layout.get("entity_names", {}).get(eid, eid) for eid in valid_ids]
    return {
        "status": "success",
        "_action_type": "clear_entity_tags",
        "message": f"Cleared tags from {len(valid_ids)} entity(ies): {', '.join(names)}",
    }


@tool_safe(require_layout=True)
def tool_add_entity_tags_bulk(
    tool_context: ToolContext,
    tag_map: dict[str, list[str]],
) -> dict:
    """
    Add tags to entity nodes. Tags appear as visible chips on nodes and
    persist until removed or cleared. Does not move entities.

    Use when annotating entities with classifications — user-requested labels
    or analytical dimensions you determined (sentiment, priority, year, etc.).

    Args:
        tag_map: Maps a tag string to the list of entity IDs that should
            receive it — ``{"Positive": ["entity-1", "entity-2"]}``. Use this
            shape when a few labels each apply to many entities.

            When instead EVERY entity gets a DISTINCT value (e.g. tagging each
            poster with its own computed average), pass the entity-keyed shape
            ``{"entity-1": "8.8", "entity-2": "10"}`` — keys are entity IDs and
            each value is that entity's tag. Numbers are accepted and rendered
            as text. Do NOT collapse distinct per-entity values into a single
            tag like ``{"Avg": 8.9}``; that drops the entity bindings.
    """
    layout = tool_context.state.get("current_layout")

    if not tag_map:
        return {"status": "error", "message": "tag_map cannot be empty."}

    node_positions = layout.get("node_positions", {})
    entity_tags = _ensure_entity_tags(layout)

    entity_new_tags, valid_tag_names = _build_entity_new_tags(tag_map, node_positions)

    if not valid_tag_names:
        return {"status": "error", "message": "No valid tag strings in tag_map."}
    if not entity_new_tags:
        return {"status": "error", "message": "No valid entities found in tag_map."}

    for entity_id, new_tags in entity_new_tags.items():
        existing = entity_tags.get(entity_id)
        if not isinstance(existing, list):
            existing = []
        entity_tags[entity_id] = _normalize_tag_strings(existing + new_tags)

    tool_context.state["current_layout"] = layout

    unique_tags = list(dict.fromkeys(valid_tag_names))
    return {
        "status": "success",
        "_action_type": "tag_nodes",
        "message": f"Added {len(unique_tags)} tag(s) to {len(entity_new_tags)} entity(ies): {', '.join(unique_tags)}",
    }


@tool_safe(require_layout=True)
def tool_remove_entity_tags_bulk(
    tool_context: ToolContext,
    tag_map: dict[str, list[str]],
) -> dict:
    """
    Remove specific tags from entity nodes. Mirrors tag_map format of
    tool_add_entity_tags_bulk.

    Args:
        tag_map: Tag string → list of entity IDs to remove that tag from.
    """
    layout = tool_context.state.get("current_layout")

    if not tag_map:
        return {"status": "error", "message": "tag_map cannot be empty."}

    node_positions = layout.get("node_positions", {})
    entity_tags = _ensure_entity_tags(layout)

    # Invert tag_map → per-entity set of tags to remove
    entity_removals: dict[str, set[str]] = {}
    valid_tag_names: list[str] = []
    for tag, entity_ids in tag_map.items():
        tag_clean = _normalize_tag_display(tag) if isinstance(tag, str) else ""
        tag_key = _canonical_tag_key(tag_clean)
        if not tag_key:
            continue
        valid_tag_names.append(tag_clean)
        if not isinstance(entity_ids, list):
            continue
        for eid in entity_ids:
            if eid in node_positions:
                entity_removals.setdefault(eid, set()).add(tag_key)

    if not valid_tag_names:
        return {"status": "error", "message": "No valid tag strings in tag_map."}
    if not entity_removals:
        return {"status": "error", "message": "No valid entities found in tag_map."}

    removed_count = 0
    for entity_id, tags_to_remove in entity_removals.items():
        existing = entity_tags.get(entity_id)
        if not isinstance(existing, list) or not existing:
            continue

        kept = [
            t
            for t in existing
            if isinstance(t, str) and _canonical_tag_key(t) not in tags_to_remove
        ]
        if len(kept) != len(existing):
            if kept:
                entity_tags[entity_id] = kept
            else:
                del entity_tags[entity_id]
            removed_count += 1

    if removed_count == 0:
        return {
            "status": "error",
            "message": "None of the given tags were present on the specified entities.",
        }

    tool_context.state["current_layout"] = layout

    unique_tags = list(dict.fromkeys(valid_tag_names))
    return {
        "status": "success",
        "_action_type": "tag_nodes",
        "message": f"Removed {len(unique_tags)} tag(s) from {removed_count} entity(ies): {', '.join(unique_tags)}",
    }


def _resolve_display_for_camera(
    layout: dict, display_name: str
) -> tuple[dict | None, str | None, dict | None]:
    """Resolve display_name to (display_dict, peer_id, error_dict)."""
    resolved = resolve_display_name(layout, display_name)
    if not resolved:
        if display_name in layout.get("surface_assignments", {}):
            resolved = display_name
        else:
            available = ", ".join(
                f"{d.get('tags', [])} ({d['peer_id']})"
                for d in layout.get("displays", [])
            )
            return None, None, {
                "status": "error",
                "message": f"Display '{display_name}' not found. Available: {available}",
            }

    display = next(
        (d for d in layout.get("displays", []) if d.get("peer_id") == resolved),
        None,
    )
    if display is None:
        return None, None, {
            "status": "error",
            "message": f"Display metadata not found for '{resolved}'.",
        }
    return display, resolved, None


def _get_current_camera(display: dict) -> dict:
    """Read the current camera from a display, with sensible defaults."""
    camera = display.get("camera") or {}
    return {
        "pan_x": float(camera.get("pan_x", 0.0)),
        "pan_y": float(camera.get("pan_y", 0.0)),
        "zoom": float(camera.get("zoom", 1.0)),
    }


def _apply_camera_update(
    layout: dict, surface_id: str, display: dict, camera: dict
) -> None:
    """Write camera update into layout state for the delta pipeline."""
    display["camera"] = camera
    # Recompute visible_canvas so subsequent tools see fresh bounds.
    screen_w = _parse_positive_float(display.get("width"))
    screen_h = _parse_positive_float(display.get("height"))
    if screen_w is not None and screen_h is not None:
        z = camera["zoom"]
        px, py = camera["pan_x"], camera["pan_y"]
        display["visible_canvas"] = {
            "min_x": -px / z,
            "min_y": -py / z,
            "max_x": (screen_w - px) / z,
            "max_y": (screen_h - py) / z,
            "width": (screen_w) / z,
            "height": (screen_h) / z,
        }
    layout.setdefault("_camera_updates", {})[surface_id] = camera


@tool_safe(require_layout=True)
def tool_camera(
    tool_context: ToolContext,
    display_name: str,
    action: str,
    amount: float = 0.2,
    direction: str = "",
    entity_ids: Optional[list[str]] = None,
    region: Optional[str] = None,
) -> dict:
    """
    Control a display's camera (viewport). Use after arranging entities to
    create breathing room, or when the user asks to zoom/pan a specific display.

    Actions:
        zoom     — Relative zoom. amount > 0 zooms in, amount < 0 zooms out.
                   e.g. amount=0.3 → zoom in 30%, amount=-0.3 → zoom out 30%.
        pan      — Pan the viewport in a direction by a fraction of the screen.
                   direction: "left", "right", "up", "down". amount = fraction
                   of viewport to shift (default 0.2 = 20%).
        fit_entities — Zoom/pan to frame specific entity_ids with padding.
        fit_all  — Zoom/pan to frame all entities on this display.
        focus_region — Zoom/pan to focus on a sub-region of the existing content.
                   region: "left", "right", "top", "bottom", "top-left", etc.

    Args:
        display_name: Target display reference (e.g., "left", "right", "center")
        action: One of "zoom", "pan", "fit_entities", "fit_all", "focus_region"
        amount: For zoom: multiplier (-1 to 1 range, positive=in, negative=out).
                For pan: fraction of viewport to shift (default 0.2).
        direction: For pan action only. "left", "right", "up", "down".
        entity_ids: For fit_entities action. List of entity IDs to frame.
        region: For focus_region action. Region name from the standard set.

    Returns:
        Dictionary with status and the applied camera state.
    """
    layout = tool_context.state.get("current_layout")

    display, surface_id, error = _resolve_display_for_camera(layout, display_name)
    if error:
        return error

    screen_w = _parse_positive_float(display.get("width"))
    screen_h = _parse_positive_float(display.get("height"))
    if screen_w is None or screen_h is None:
        return {
            "status": "error",
            "message": f"Display '{display_name}' has no screen dimensions.",
        }

    current = _get_current_camera(display)
    action = action.lower().strip()

    # ── zoom ────────────────────────────────────────────────────────────
    if action == "zoom":
        factor = 1.0 + amount
        if factor <= 0:
            return {
                "status": "error",
                "message": f"Zoom factor must be positive. amount={amount} gives factor={factor}.",
            }
        new_zoom = max(MIN_CAMERA_ZOOM, min(MAX_CAMERA_ZOOM, current["zoom"] * factor))

        # Keep the viewport center stationary during zoom.
        cx = (screen_w / 2.0 - current["pan_x"]) / current["zoom"]
        cy = (screen_h / 2.0 - current["pan_y"]) / current["zoom"]
        new_pan_x = screen_w / 2.0 - cx * new_zoom
        new_pan_y = screen_h / 2.0 - cy * new_zoom

        new_camera = {"pan_x": new_pan_x, "pan_y": new_pan_y, "zoom": new_zoom}
        _apply_camera_update(layout, surface_id, display, new_camera)
        tool_context.state["current_layout"] = layout

        direction_label = "in" if amount > 0 else "out"
        return {
            "status": "success",
            "_action_type": "update_layout",
            "message": f"Zoomed {direction_label} {abs(amount)*100:.0f}% on {display_name} (zoom: {new_zoom:.2f}).",
        }

    # ── pan ──────────────────────────────────────────────────────────────
    if action == "pan":
        direction = direction.lower().strip()
        if direction not in ("left", "right", "up", "down"):
            return {
                "status": "error",
                "message": f"Invalid direction '{direction}'. Use left, right, up, or down.",
            }
        # Shift by `amount` fraction of the viewport in canvas-space.
        shift_x, shift_y = 0.0, 0.0
        if direction == "left":
            shift_x = amount * screen_w
        elif direction == "right":
            shift_x = -amount * screen_w
        elif direction == "up":
            shift_y = amount * screen_h
        elif direction == "down":
            shift_y = -amount * screen_h

        new_camera = {
            "pan_x": current["pan_x"] + shift_x,
            "pan_y": current["pan_y"] + shift_y,
            "zoom": current["zoom"],
        }
        _apply_camera_update(layout, surface_id, display, new_camera)
        tool_context.state["current_layout"] = layout

        return {
            "status": "success",
            "_action_type": "update_layout",
            "message": f"Panned {direction} {amount*100:.0f}% on {display_name}.",
        }

    # ── fit_entities ─────────────────────────────────────────────────────
    if action == "fit_entities":
        if not entity_ids:
            return {
                "status": "error",
                "message": "entity_ids required for fit_entities action.",
            }
        node_positions = layout.get("node_positions", {})
        valid_ids = [eid for eid in entity_ids if eid in node_positions]
        if not valid_ids:
            return {
                "status": "error",
                "message": "No valid entities found in the provided list.",
            }

        bounds = compute_entities_bounds(layout, valid_ids)
        if bounds is None:
            return {"status": "error", "message": "Could not compute entity bounds."}

        new_camera = compute_fit_camera(display, bounds)
        if new_camera is None:
            return {"status": "error", "message": "Could not compute camera fit."}

        _apply_camera_update(layout, surface_id, display, new_camera)
        tool_context.state["current_layout"] = layout

        return {
            "status": "success",
            "_action_type": "update_layout",
            "message": f"Camera fitted to {len(valid_ids)} entities on {display_name}.",
        }

    # ── fit_all ──────────────────────────────────────────────────────────
    if action == "fit_all":
        all_entity_ids = layout.get("surface_assignments", {}).get(surface_id, [])
        if not all_entity_ids:
            return {
                "status": "error",
                "message": f"No entities on display '{display_name}'.",
            }

        bounds = compute_entities_bounds(layout, all_entity_ids)
        if bounds is None:
            return {"status": "error", "message": "Could not compute entity bounds."}

        new_camera = compute_fit_camera(display, bounds)
        if new_camera is None:
            return {"status": "error", "message": "Could not compute camera fit."}

        _apply_camera_update(layout, surface_id, display, new_camera)
        tool_context.state["current_layout"] = layout

        return {
            "status": "success",
            "_action_type": "update_layout",
            "message": f"Camera fitted to all {len(all_entity_ids)} entities on {display_name}.",
        }

    # ── focus_region ─────────────────────────────────────────────────────
    if action == "focus_region":
        if not region:
            return {
                "status": "error",
                "message": f"region required for focus_region. Use one of: {', '.join(REGION_SLICES.keys())}",
            }

        all_entity_ids = layout.get("surface_assignments", {}).get(surface_id, [])
        if not all_entity_ids:
            return {
                "status": "error",
                "message": f"No entities on display '{display_name}'.",
            }

        # Compute full content bounds, then slice to the requested region.
        full_bounds = compute_entities_bounds(layout, all_entity_ids)
        if full_bounds is None:
            return {"status": "error", "message": "Could not compute entity bounds."}

        region_bounds = slice_bounds_for_region(full_bounds, region)
        if region_bounds is None:
            return {
                "status": "error",
                "message": f"Unknown region '{region}'. Use one of: {', '.join(REGION_SLICES.keys())}",
            }

        new_camera = compute_fit_camera(display, region_bounds)
        if new_camera is None:
            return {"status": "error", "message": "Could not compute camera fit."}

        _apply_camera_update(layout, surface_id, display, new_camera)
        tool_context.state["current_layout"] = layout

        return {
            "status": "success",
            "_action_type": "update_layout",
            "message": f"Camera focused on {region} region of {display_name}.",
        }

    return {
        "status": "error",
        "message": f"Unknown action '{action}'. Use: zoom, pan, fit_entities, fit_all, focus_region.",
    }


@tool_safe(require_layout=False)
def tool_jump_to_timeline(
    tool_context: ToolContext,
    index: int = -1,
    label_query: str = "",
) -> dict:
    """
    Navigate the user's interaction timeline. The timeline tracks layout
    snapshots from both drag operations and chat modifications.

    Supports three modes:
    - Explicit index: jump to a specific timeline entry (e.g., "go to step 3")
    - Label match: find a timeline entry by label substring (e.g., "go back to when charts were in a grid")
    - List entries: call with no arguments to show available timeline entries

    For undo/redo: use index = current_index - 1 (undo) or current_index + 1 (redo).
    Read current_index from timeline_context in the context.

    IMPORTANT: After calling this tool, do NOT call any layout modification
    tools in the same turn — the backend layout state is stale until the
    next request.

    Args:
        tool_context: ADK tool context for state management
        index: Timeline entry index to jump to (0-based). Use -1 to skip explicit index.
        label_query: Case-insensitive substring to match against timeline entry labels.

    Returns:
        Dictionary with status, matched entry info, and action metadata
    """
    tc = tool_context.state.get("timeline_context")

    if not tc or not tc.get("entries"):
        return {
            "status": "info",
            "message": "No timeline entries available. The timeline is empty — make some layout changes first.",
        }

    entries = tc["entries"]
    current_index = tc.get("current_index", len(entries) - 1)

    if index < 0 and not label_query:
        entry_list = []
        for e in entries:
            marker = " ← current" if e["index"] == current_index else ""
            entry_list.append(f"[{e['index']}] {e['label']} ({e['source']}){marker}")
        return {
            "status": "success",
            "message": f"Timeline has {len(entries)} entries (current: {current_index}):\n"
            + "\n".join(entry_list),
            "current_index": current_index,
            "entry_count": len(entries),
        }

    matched_index = None

    if index >= 0:
        if index >= len(entries):
            return {
                "status": "error",
                "message": f"Timeline index {index} out of range. Valid range: 0-{len(entries) - 1}.",
            }
        matched_index = index

    if label_query and matched_index is None:
        query_lower = label_query.lower()
        # Prefer the most recent match to align with user recency intent.
        for e in reversed(entries):
            if query_lower in e["label"].lower():
                matched_index = e["index"]
                break

        if matched_index is None:
            return {
                "status": "error",
                "message": f"No timeline entry matching '{label_query}'. "
                f"Use tool_jump_to_timeline() with no args to list available entries.",
            }

    if matched_index is None:
        return {"status": "error", "message": "No valid index or label_query provided."}

    matched_entry = entries[matched_index]
    return {
        "status": "success",
        "_action_type": "jump_to_timeline",
        "_timeline_index": matched_index,
        "message": f"Jumping to timeline entry [{matched_index}]: {matched_entry['label']}",
        "matched_entry": {
            "index": matched_index,
            "label": matched_entry["label"],
            "source": matched_entry["source"],
        },
    }
