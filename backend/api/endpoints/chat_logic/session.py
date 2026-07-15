"""
Session management helpers for the chat endpoint.

Handles creating, retrieving, and refreshing ADK sessions,
including display-context rebuilds.
"""

from copy import deepcopy
from typing import Any, Dict, Optional, Tuple

from fastapi import HTTPException

from agent.layout_operations import (
    load_layout_from_output,
    normalize_entity_tags_map,
    _build_display_surfaces,
)
from agent import APP_NAME, session_service, initialize_session
from core.logger import logger


def _rebuild_layout_for_display_context(
    current_layout: Dict[str, Any], display_context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Recompute surface assignments, bounds, and display metadata
    for an updated display topology.

    Args:
        current_layout: The layout dict to update (not mutated).
        display_context: New display topology from the client.

    Returns:
        A new layout dict with recalculated display fields.
    """
    updated_layout = deepcopy(current_layout)
    node_positions = updated_layout.get("node_positions", {})

    entity_display_ids: Dict[str, str] = {}
    for peer_id, eids in updated_layout.get("surface_assignments", {}).items():
        for eid in eids:
            entity_display_ids[eid] = peer_id

    (
        surface_assignments,
        surface_bounds,
        surface_visible_bounds,
        surface_content_bounds,
        displays,
    ) = _build_display_surfaces(
        node_positions,
        entity_display_ids,
        display_context,
        entity_dimensions=updated_layout.get("entity_dimensions", {}),
    )
    updated_layout["surface_assignments"] = surface_assignments
    updated_layout["surface_bounds"] = surface_bounds
    updated_layout["surface_visible_bounds"] = surface_visible_bounds
    updated_layout["surface_content_bounds"] = surface_content_bounds
    updated_layout["displays"] = displays

    return updated_layout


def _build_state_delta_for_existing_session(
    session: Any,
    processed_layout: Dict[str, Any],
    entities: Optional[list],
    display_context: Optional[dict],
) -> Dict[str, Any]:
    """
    Build a state delta dict for an existing session being refreshed
    with a new layout payload.
    """
    state_delta: Dict[str, Any] = {
        "current_layout": processed_layout,
    }

    if entities is not None:
        state_delta["entities"] = entities
        logger.info(f"Updated session with {len(entities)} entity semantics")

    if display_context is not None:
        state_delta["display_context"] = display_context

    return state_delta


def _handle_display_context_refresh(
    session: Any, display_context: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """
    Build a state delta when only the display context changed (no new layout).

    Returns:
        State delta dict, or None if no rebuild was needed.
    """
    current_layout = session.state.get("current_layout")
    if not current_layout:
        logger.info(
            "display_context received but current_layout missing; skipped state_delta rebuild"
        )
        return None

    updated_layout = _rebuild_layout_for_display_context(
        current_layout, display_context
    )

    state_delta = {
        "current_layout": updated_layout,
        "display_context": display_context,
    }

    logger.info(
        f"Applied display-context refresh delta: keys={list(state_delta.keys())}, "
        f"layout_surfaces={len(updated_layout.get('surface_assignments', {}))}, "
        f"display_metadata_count={len(updated_layout.get('displays', []))}"
    )
    return state_delta


async def get_or_create_session(
    user_id: str,
    session_id: str,
    layout: Optional[dict] = None,
    entities: Optional[list] = None,
    display_context: Optional[dict] = None,
    entity_tags: Optional[dict] = None,
    user_text_highlights: Optional[dict] = None,
) -> Tuple[Any, Optional[Dict[str, Any]]]:
    """
    Get an existing session or create a new one.

    Returns:
        Tuple of (session, state_delta).  *state_delta* is None when the
        session was freshly created by ``initialize_session``.

    Raises:
        HTTPException 400: No session exists and no layout was provided.
    """
    if layout is not None:
        return await _handle_layout_provided(
            user_id, session_id, layout, entities, display_context, entity_tags,
            user_text_highlights,
        )
    return await _handle_no_layout(user_id, session_id, display_context)


async def _handle_layout_provided(
    user_id: str,
    session_id: str,
    layout: dict,
    entities: Optional[list],
    display_context: Optional[dict],
    entity_tags: Optional[dict] = None,
    user_text_highlights: Optional[dict] = None,
) -> Tuple[Any, Optional[Dict[str, Any]]]:
    """Process a request that includes a layout payload."""
    logger.info(f"User provided layout data with {len(layout.get('nodes', []))} nodes")

    session = await session_service.get_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )

    # Carry forward display context from existing session when the client
    # omits it (e.g. the display topology hasn't changed).  Without this,
    # load_layout_from_output falls back to surface_0 and the agent loses
    # track of which peer display each entity belongs to.
    if display_context is None and session and hasattr(session, "state"):
        existing_ctx = session.state.get("display_context")
        if existing_ctx:
            logger.info(
                "No display_context in request; reusing existing session display_context"
            )
            display_context = existing_ctx

    processed_layout = load_layout_from_output(layout, display_context=display_context)

    if entity_tags is not None:
        processed_layout["entity_tags"] = normalize_entity_tags_map(entity_tags)
        logger.info(f"Using entity_tags from request: {list(entity_tags.keys())}")
    elif session and hasattr(session, "state"):
        existing_tags = session.state.get("current_layout", {}).get("entity_tags", {})
        if existing_tags:
            processed_layout["entity_tags"] = existing_tags
            logger.info(
                f"Carrying forward existing entity_tags: {list(existing_tags.keys())}"
            )

    if user_text_highlights is not None:
        processed_layout["user_text_highlights"] = user_text_highlights
        logger.info(f"Using user_text_highlights from request: {list(user_text_highlights.keys())}")
    elif session and hasattr(session, "state"):
        existing_hl = session.state.get("current_layout", {}).get("user_text_highlights", {})
        if existing_hl:
            processed_layout["user_text_highlights"] = existing_hl
            logger.info(
                f"Carrying forward existing user_text_highlights: {list(existing_hl.keys())}"
            )

    if session and hasattr(session, "state"):
        state_delta = _build_state_delta_for_existing_session(
            session, processed_layout, entities, display_context
        )
        _log_state_refresh(session, processed_layout, entities, display_context)
        logger.info("Updated existing session with new layout (via state_delta)")
        return session, state_delta

    session = await initialize_session(
        user_id=user_id,
        session_id=session_id,
        layout_data=processed_layout,
        entities=entities,
        display_context=display_context,
    )
    logger.info("Created new session with user-provided layout")
    return session, None


async def _handle_no_layout(
    user_id: str,
    session_id: str,
    display_context: Optional[dict],
) -> Tuple[Any, Optional[Dict[str, Any]]]:
    """Process a follow-up request that does not include a layout."""
    session = await session_service.get_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )
    if not session:
        raise HTTPException(
            status_code=400,
            detail="No active session found. Please provide 'layout' data in your first request.",
        )

    logger.info("Using existing session")

    state_delta: Optional[Dict[str, Any]] = None
    if display_context is not None:
        state_delta = _handle_display_context_refresh(session, display_context)

    return session, state_delta


def _log_state_refresh(
    session: Any,
    processed_layout: Dict[str, Any],
    entities: Optional[list],
    display_context: Optional[dict],
) -> None:
    """Emit structured log lines for a state-refresh delta."""
    prev_layout = session.state.get("current_layout", {})
    prev_node_count = len(prev_layout.get("node_positions", {}))
    new_node_count = len(processed_layout.get("node_positions", {}))
    display_count = len(
        (display_context or {}).get("virtual_desktop", {}).get("displays", [])
    )
    logger.info(
        f"Refreshing session state from request payload: prev_nodes={prev_node_count}, "
        f"new_nodes={new_node_count}, entities_update={entities is not None}, "
        f"display_context_update={display_context is not None}, display_count={display_count}"
    )
