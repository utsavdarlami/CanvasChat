"""
Action detection and metadata building for the chat endpoint.

Compares pre- and post-agent layout state to determine what
action (if any) was performed, and builds the response metadata.
"""

from typing import Any, Dict, Literal, Optional, Tuple, cast

from api.models.chat import LayoutAction, LayoutDelta
from agent.action_detector import ActionDetector
from agent.layout_delta import calculate_layout_delta
from agent.layout_operations import export_to_graph_format
from core.logger import logger


def detect_action_and_build_metadata(
    previous_layout: Optional[Dict[str, Any]],
    current_layout: Optional[Dict[str, Any]],
    session_state: Dict[str, Any],
) -> Tuple[Optional[LayoutAction], Optional[Dict[str, Any]]]:
    """
    Compare layouts to detect an action and build response metadata.

    If a tool forward-declared its action type via ``_action_type`` in its
    return value, ``session_state["_last_action_type"]`` will contain the
    hint and is used in preference to heuristic detection.

    Args:
        previous_layout: Layout snapshot before agent execution.
        current_layout: Layout snapshot after agent execution.
        session_state: Current session state.

    Returns:
        Tuple of (LayoutAction or None, graph-formatted layout or None).
    """
    if previous_layout is None or current_layout is None:
        return None, None

    # Consume the forward-declared hints (if any) so they don't leak.
    # Use get() + explicit clear instead of pop() — ADK's State object
    # may not persist removals via pop(), causing stale hints to leak
    # across turns.
    action_type_hint = session_state.get("_last_action_type")
    timeline_index = session_state.get("_last_timeline_index")
    session_state["_last_action_type"] = None
    session_state["_last_timeline_index"] = None

    # Timeline jumps are UI navigation events and do not mutate backend layout state.
    if action_type_hint == "jump_to_timeline":
        action = LayoutAction(
            type="jump_to_timeline",
            description="jumped to timeline entry",
            timeline_index=timeline_index,
        )
        return action, None

    try:
        action = _build_action(
            previous_layout,
            current_layout,
            session_state,
            action_type_hint=action_type_hint,
        )

        layout_graph = _export_layout_graph(current_layout) if action else None
        return action, layout_graph

    except Exception as e:
        logger.warning(f"Failed to detect action: {e}")
        return None, None


_VALID_ACTION_TYPES = frozenset(
    ("update_layout", "show_entity", "jump_to_timeline",
     "text_highlight", "clear_text_highlight", "tag_nodes", "clear_entity_tags")
)


def _build_action(
    previous_layout: Dict[str, Any],
    current_layout: Dict[str, Any],
    session_state: Dict[str, Any],
    action_type_hint: Optional[str] = None,
) -> Optional[LayoutAction]:
    """
    Run action detection and assemble a LayoutAction model if a change occurred.

    If *action_type_hint* is provided (from a tool's ``_action_type``), it
    is used only for pure-transient turns (no structural layout changes).
    When the detector finds structural changes, those take precedence —
    this prevents a transient hint (e.g. highlight) from overriding
    a real layout modification that happened later in the same turn.
    """
    action_type, affected_entities, action_description = ActionDetector.detect_action(
        previous_layout=previous_layout,
        current_layout=current_layout,
    )

    # Structural diffs take priority over forward-declared transient hints.
    if (
        not affected_entities
        and action_type_hint
        and action_type_hint in _VALID_ACTION_TYPES
    ):
        action_type = action_type_hint

    if not action_type:
        return None

    valid_action_type = cast(
        Literal[
            "update_layout", "show_entity", "jump_to_timeline",
            "text_highlight", "clear_text_highlight", "tag_nodes", "clear_entity_tags",
        ],
        action_type,
    )

    layout_delta = _calculate_delta(previous_layout, current_layout)

    return LayoutAction(
        type=valid_action_type,
        description=action_description,
        affected_entities=affected_entities,
        layout_delta=layout_delta,
    )


def _calculate_delta(
    previous_layout: Dict[str, Any],
    current_layout: Dict[str, Any],
) -> Optional[LayoutDelta]:
    """Calculate a LayoutDelta between two layout snapshots."""
    try:
        delta_dict = calculate_layout_delta(previous_layout, current_layout)
        return LayoutDelta(**delta_dict)
    except Exception as e:
        logger.warning(f"Failed to calculate layout delta: {e}")
        return None


def _export_layout_graph(layout: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Convert internal layout to client-facing graph format."""
    try:
        return export_to_graph_format(layout)
    except Exception as e:
        logger.warning(f"Failed to export layout to graph format: {e}")
        return None
