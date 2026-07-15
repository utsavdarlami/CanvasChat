"""
Action detection for layout modifications.

Detects what action was performed by comparing layouts,
without needing to track tool calls from ADK events.
"""

from typing import Optional, List, Tuple, Dict, Any


class ActionDetector:
    """Detects and categorizes layout actions from layout changes."""

    @staticmethod
    def detect_action(
        previous_layout: Optional[Dict[str, Any]],
        current_layout: Optional[Dict[str, Any]],
    ) -> Tuple[Optional[str], List[str], str]:
        """
        Detect what action occurred by comparing layouts.

        Args:
            previous_layout: Layout state before agent execution
            current_layout: Layout state after agent execution

        Returns:
            Tuple of (action_type, affected_entity_ids, action_description)
            - action_type: "update_layout", "show_entity", or None
            - affected_entity_ids: List of entity IDs that changed
            - action_description: Human-readable description
        """
        if previous_layout is None or current_layout is None:
            return None, [], ""

        changed_entities = ActionDetector._get_changed_entities(
            previous_layout, current_layout
        )

        curr_highlights = current_layout.get("highlighted_entities", [])
        curr_focused = current_layout.get("focused_entities", [])
        prev_highlights = previous_layout.get("highlighted_entities", [])
        prev_focused = previous_layout.get("focused_entities", [])

        has_highlights = curr_highlights != prev_highlights and bool(curr_highlights)
        has_focused = curr_focused != prev_focused and bool(curr_focused)

        curr_text_hl = current_layout.get("text_highlights", [])
        prev_text_hl = previous_layout.get("text_highlights", [])
        has_text_highlights = curr_text_hl != prev_text_hl and bool(curr_text_hl)

        curr_clear_hl = current_layout.get("clear_text_highlight_ids", [])
        prev_clear_hl = previous_layout.get("clear_text_highlight_ids", [])
        has_clear_text_highlights = curr_clear_hl != prev_clear_hl and bool(curr_clear_hl)

        prev_tags = previous_layout.get("entity_tags") or {}
        curr_tags = current_layout.get("entity_tags") or {}
        if not isinstance(prev_tags, dict):
            prev_tags = {}
        if not isinstance(curr_tags, dict):
            curr_tags = {}
        has_entity_tag_change = prev_tags != curr_tags

        if (
            not changed_entities
            and not has_highlights
            and not has_focused
            and not has_text_highlights
            and not has_clear_text_highlights
            and not has_entity_tag_change
        ):
            return None, [], ""

        if changed_entities:
            action_type = "update_layout"
            action_description = "modified layout"
            return action_type, changed_entities, action_description

        if has_text_highlights:
            affected = list({e["entity_id"] for e in curr_text_hl if "entity_id" in e})
            action_type = "text_highlight"
            action_description = f"highlighted text in {len(affected)} entity(ies)"
            return action_type, affected, action_description

        if has_clear_text_highlights:
            affected = [eid for eid in curr_clear_hl if eid != "__all__"]
            action_type = "clear_text_highlight"
            if "__all__" in curr_clear_hl:
                action_description = "cleared all text highlights"
            else:
                action_description = f"cleared text highlights from {len(affected)} entity(ies)"
            return action_type, affected, action_description

        if has_entity_tag_change:
            removed_keys = set(prev_tags.keys()) - set(curr_tags.keys())
            unchanged_remaining = all(
                curr_tags.get(eid) == prev_tags.get(eid) for eid in curr_tags
            )
            if not curr_tags and prev_tags:
                action_type = "clear_entity_tags"
                affected = list(prev_tags.keys())
                action_description = "cleared all entity tags"
                return action_type, affected, action_description
            if removed_keys and unchanged_remaining:
                action_type = "clear_entity_tags"
                affected = sorted(removed_keys)
                action_description = f"cleared tags from {len(affected)} entity(ies)"
                return action_type, affected, action_description
            touched = ActionDetector._entity_ids_with_tag_diff(prev_tags, curr_tags)
            action_type = "tag_nodes"
            action_description = f"updated tags on {len(touched)} entity(ies)"
            return action_type, touched, action_description

        if has_highlights and has_focused:
            action_type = "show_entity"
            action_description = f"showing {len(curr_highlights)} entities"
            return action_type, curr_highlights, action_description

        if has_focused:
            action_type = "show_entity"
            action_description = f"showing {len(curr_focused)} entities"
            return action_type, curr_focused, action_description

        if has_highlights:
            action_type = "show_entity"
            action_description = f"showing {len(curr_highlights)} entities"
            return action_type, curr_highlights, action_description

        return None, [], ""

    @staticmethod
    def _entity_ids_with_tag_diff(prev_tags: Dict[str, Any], curr_tags: Dict[str, Any]) -> List[str]:
        ids = set(prev_tags.keys()) | set(curr_tags.keys())
        changed: List[str] = []
        for eid in ids:
            p = prev_tags.get(eid)
            c = curr_tags.get(eid)
            if not isinstance(p, list):
                p = []
            if not isinstance(c, list):
                c = []
            if p != c:
                changed.append(eid)
        return sorted(changed)

    @staticmethod
    def _get_changed_entities(
        prev_layout: Dict[str, Any], curr_layout: Dict[str, Any]
    ) -> List[str]:
        """
        Find which entities changed position by comparing layouts.

        Args:
            prev_layout: Previous layout state
            curr_layout: Current layout state

        Returns:
            List of entity IDs that changed position
        """
        changed = set()

        prev_positions = prev_layout.get("node_positions", {})
        curr_positions = curr_layout.get("node_positions", {})

        for entity_id in curr_positions:
            if entity_id in prev_positions:
                prev_pos = prev_positions[entity_id]
                curr_pos = curr_positions[entity_id]
                if prev_pos != curr_pos:
                    changed.add(entity_id)
            else:
                changed.add(entity_id)

        for entity_id in prev_positions:
            if entity_id not in curr_positions:
                changed.add(entity_id)

        prev_surfaces = prev_layout.get("surface_assignments", {})
        curr_surfaces = curr_layout.get("surface_assignments", {})

        # Compare assignments at entity granularity so surface IDs never enter the diff set.
        prev_entity_surface = {}
        for surface_id, entity_ids in prev_surfaces.items():
            for eid in entity_ids:
                prev_entity_surface[eid] = surface_id

        curr_entity_surface = {}
        for surface_id, entity_ids in curr_surfaces.items():
            for eid in entity_ids:
                curr_entity_surface[eid] = surface_id

        for entity_id in curr_entity_surface:
            if entity_id in prev_entity_surface:
                if prev_entity_surface[entity_id] != curr_entity_surface[entity_id]:
                    changed.add(entity_id)
            else:
                changed.add(entity_id)

        for entity_id in prev_entity_surface:
            if entity_id not in curr_entity_surface:
                changed.add(entity_id)

        return list(changed)
