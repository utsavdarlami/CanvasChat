"""
Chat endpoint package for interacting with the layout modification agent.

Route handlers live here; business logic is delegated to the
sub-modules (_session, _state, _actions, _agent).
"""

import json
from copy import deepcopy
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import StreamingResponse

from api.models.chat import (
    ClearSessionRequest,
    ChatAutocompleteRequest,
    ChatAutocompleteResponse,
    ChatRequest,
    ChatResponse,
)
from api.endpoints.chat_logic.session import get_or_create_session
from api.endpoints.chat_logic.state import capture_state_snapshot
from api.endpoints.chat_logic.actions import detect_action_and_build_metadata
from api.endpoints.chat_logic.autocomplete import (
    extract_recent_turns,
    generate_autocomplete_suggestions,
)
from api.endpoints.chat_logic.agent import (
    run_agent_conversation,
    stream_agent_conversation,
)
from api.endpoints.chat_logic.context import build_context_summary, build_query_with_selection
from agent import APP_NAME, session_service
from agent.layout_ops.planning import validate_layout
from core.logger import logger

router = APIRouter()


@router.post("/chat", response_model=ChatResponse, tags=["Agent Chat"])
async def chat_endpoint(request: ChatRequest):
    """
    Handle chat interactions with the layout modification agent.

    Manages conversation state across multiple turns and returns
    the agent's final response together with any layout changes.
    """
    try:
        logger.info(
            f"Chat request from user={request.user_id}, "
            f"session={request.session_id}: {request.query}"
        )

        display_ctx = (
            request.display_context.model_dump() if request.display_context else None
        )

        session, state_delta = await get_or_create_session(
            user_id=request.user_id,
            session_id=request.session_id,
            layout=request.layout,
            entities=request.entities,
            display_context=display_ctx,
            entity_tags=request.entity_tags,
            user_text_highlights=request.user_text_highlights,
        )

        if not session or not hasattr(session, "state"):
            raise HTTPException(
                status_code=500, detail="Failed to retrieve valid session"
            )

        # Clear transient UI-only state so each turn starts from a neutral view.
        # Clear overlays at turn start to avoid carrying rectangles from a
        # previous query. Multi-call overlay accumulation within this turn is
        # handled inside tool_plan_semantic_layout.
        if session and hasattr(session, "state") and "current_layout" in session.state:
            session.state["current_layout"]["highlighted_entities"] = []
            session.state["current_layout"]["highlighted_entity_colors"] = {}
            session.state["current_layout"]["focused_entities"] = []
            session.state["current_layout"]["text_highlights"] = []
            session.state["current_layout"]["clear_text_highlight_ids"] = []
            session.state["current_layout"]["_group_overlays"] = []

            if state_delta is None:
                state_delta = {}
            if "current_layout" not in state_delta:
                state_delta["current_layout"] = session.state["current_layout"]

        if state_delta and "current_layout" in state_delta:
            state_delta["current_layout"]["highlighted_entities"] = []
            state_delta["current_layout"]["highlighted_entity_colors"] = {}
            state_delta["current_layout"]["focused_entities"] = []
            state_delta["current_layout"]["text_highlights"] = []
            state_delta["current_layout"]["clear_text_highlight_ids"] = []
            state_delta["current_layout"]["_group_overlays"] = []


        previous_layout = _snapshot_before_agent(session, state_delta)

        if state_delta is None:
            state_delta = {}

        # Clear stale layout-stage metadata so it doesn't leak into
        # responses that never called tool_plan_semantic_layout.
        # (ADK's get_session returns a deepcopy, so mutating session.state
        # after the run doesn't persist — we must clear via state_delta.)
        state_delta["_layout_group_stages"] = None

        if request.timeline_context is not None:
            state_delta["timeline_context"] = request.timeline_context.model_dump()

        context_state = deepcopy(session.state)
        context_state.update(state_delta)
        state_delta["context_summary"] = build_context_summary(context_state, display_ctx)

        # The model cannot inspect session state directly, so selection context
        # is injected into the query text.
        enriched_query = build_query_with_selection(
            request.query, request.selected_entity_ids, context_state
        )
        response_text, tools_called, thinking = await run_agent_conversation(
            request.user_id,
            request.session_id,
            enriched_query,
            state_delta=state_delta,
        )

        session = await session_service.get_session(
            app_name=APP_NAME,
            user_id=request.user_id,
            session_id=request.session_id,
        )
        if not session or not hasattr(session, "state"):
            raise HTTPException(
                status_code=500, detail="Session lost during processing"
            )

        current_layout = capture_state_snapshot(session)

        # logger.info(f"testing {session.state}")

        # Run one auto-fix pass when validation finds critical layout issues.
        if _layout_was_modified(previous_layout, current_layout):
            fix_text, fix_tools, fix_thinking = await _run_post_validation(
                session, request.user_id, request.session_id
            )
            if fix_text:
                response_text = f"{response_text}\n\n{fix_text}"
                tools_called.extend(fix_tools)
                thinking.extend(fix_thinking)
                session = await session_service.get_session(
                    app_name=APP_NAME,
                    user_id=request.user_id,
                    session_id=request.session_id,
                )
                if session and hasattr(session, "state"):
                    current_layout = capture_state_snapshot(session)

        action, layout_graph = detect_action_and_build_metadata(
            previous_layout,
            current_layout,
            session.state,
        )

        # Extract group stage metadata for frontend staged animation.
        # The value is set by tool_plan_semantic_layout during the agent run
        # (persisted by ADK) and cleared at the start of each turn via
        # state_delta above, so it's only present when the tool ran this turn.
        layout_stages = session.state.get("_layout_group_stages")

        return ChatResponse(
            response=response_text,
            user_id=request.user_id,
            session_id=request.session_id,
            action=action,
            layout=layout_graph,
            layout_stages=layout_stages,
            thinking=thinking if thinking else None,
            metadata={"tools_called": tools_called} if tools_called else None,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.opt(exception=True).error(f"Chat endpoint error: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to process chat request: {e}"
        )


def _sse_format(event_type: str, data) -> str:
    """Format a single Server-Sent Event."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


async def _chat_stream_helper(
    user_id: str,
    session_id: str,
    query: str,
    state_delta: dict | None,
    previous_layout: dict | None,
    enable_post_validation: bool = False,
) -> AsyncGenerator[str, None]:
    """
    Stream agent events as SSE, then run post-processing on the ``done``
    event so the client receives action/layout data — just like
    the non-streaming ``/chat`` endpoint.

    Args:
        enable_post_validation: If True, runs auto-fix pass after layout changes.
            Default is False to match tldraw-agent behavior (no automatic fixes).
    """
    async for event in stream_agent_conversation(
        user_id=user_id,
        session_id=session_id,
        query=query,
        state_delta=state_delta,
    ):
        if event["event"] != "done":
            yield _sse_format(event["event"], event["data"])
            continue

        done_data = dict(event["data"])
        done_data["user_id"] = user_id
        done_data["session_id"] = session_id

        try:
            session = await session_service.get_session(
                app_name=APP_NAME,
                user_id=user_id,
                session_id=session_id,
            )
            if session and hasattr(session, "state"):
                current_layout = capture_state_snapshot(session)

                if enable_post_validation and _layout_was_modified(
                    previous_layout, current_layout
                ):
                    fix_text, fix_tools, fix_thinking = await _run_post_validation(
                        session, user_id, session_id
                    )
                    if fix_text:
                        response_text = f"{done_data.get('response', '')}\n\n{fix_text}"
                        tools_called = done_data.get("tools", []) + fix_tools
                        thinking = done_data.get("thinking", []) + fix_thinking
                        done_data["response"] = response_text
                        done_data["tools"] = tools_called
                        done_data["thinking"] = thinking

                action, layout_graph = detect_action_and_build_metadata(
                    previous_layout,
                    current_layout,
                    session.state,
                )
                done_data["action"] = action.model_dump() if action else None
                done_data["layout"] = layout_graph
                # Extract group stage metadata for frontend staged animation.
                # Cleared via state_delta at the start of each turn, so only
                # present when tool_plan_semantic_layout ran this turn.
                done_data["layout_stages"] = session.state.get(
                    "_layout_group_stages"
                )
        except Exception as e:
            logger.opt(exception=True).warning(f"Stream post-processing failed: {e}")

        yield _sse_format("done", done_data)


@router.post("/chat/stream", tags=["Agent Chat"])
async def chat_stream_endpoint(request: ChatRequest):
    """
    Stream chat interactions with the layout modification agent.

    Uses Server-Sent Events (SSE) to stream tool calls, thinking, and
    partial responses in real-time.
    """
    try:
        logger.info(
            f"Chat stream request from user={request.user_id}, "
            f"session={request.session_id}: {request.query}"
        )

        display_ctx = (
            request.display_context.model_dump() if request.display_context else None
        )

        logger.info(f"request payload {request}")

        session, state_delta = await get_or_create_session(
            user_id=request.user_id,
            session_id=request.session_id,
            layout=request.layout,
            entities=request.entities,
            display_context=display_ctx,
            entity_tags=request.entity_tags,
            user_text_highlights=request.user_text_highlights,
        )

        if not session or not hasattr(session, "state"):
            raise HTTPException(
                status_code=500, detail="Failed to retrieve valid session"
            )

        # Clear transient UI-only state so each turn starts from a neutral view.
        # Clear overlays at turn start to avoid carrying rectangles from a
        # previous query. Multi-call overlay accumulation within this turn is
        # handled inside tool_plan_semantic_layout.
        if session and hasattr(session, "state") and "current_layout" in session.state:
            session.state["current_layout"]["highlighted_entities"] = []
            session.state["current_layout"]["highlighted_entity_colors"] = {}
            session.state["current_layout"]["focused_entities"] = []
            session.state["current_layout"]["text_highlights"] = []
            session.state["current_layout"]["clear_text_highlight_ids"] = []
            session.state["current_layout"]["_group_overlays"] = []

            if state_delta is None:
                state_delta = {}
            if "current_layout" not in state_delta:
                state_delta["current_layout"] = session.state["current_layout"]

        if state_delta and "current_layout" in state_delta:
            state_delta["current_layout"]["highlighted_entities"] = []
            state_delta["current_layout"]["highlighted_entity_colors"] = {}
            state_delta["current_layout"]["focused_entities"] = []
            state_delta["current_layout"]["text_highlights"] = []
            state_delta["current_layout"]["clear_text_highlight_ids"] = []
            state_delta["current_layout"]["_group_overlays"] = []


        previous_layout = _snapshot_before_agent(session, state_delta)

        if state_delta is None:
            state_delta = {}

        # Clear stale layout-stage metadata (see non-streaming endpoint).
        state_delta["_layout_group_stages"] = None

        if request.timeline_context is not None:
            state_delta["timeline_context"] = request.timeline_context.model_dump()

        context_state = deepcopy(session.state)
        context_state.update(state_delta)
        state_delta["context_summary"] = build_context_summary(context_state, display_ctx)

        # logger.info(f"testing {session.state}")

        # The model cannot inspect session state directly, so selection context
        # is injected into the query text.
        enriched_query = build_query_with_selection(
            request.query, request.selected_entity_ids, context_state
        )

        return StreamingResponse(
            _chat_stream_helper(
                request.user_id,
                request.session_id,
                enriched_query,
                state_delta,
                previous_layout,
                enable_post_validation=False,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.opt(exception=True).error(f"Chat stream endpoint error: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to process chat stream request: {e}"
        )


@router.post(
    "/chat/autocomplete",
    response_model=ChatAutocompleteResponse,
    tags=["Agent Chat"],
)
async def chat_autocomplete_endpoint(request: ChatAutocompleteRequest):
    """
    Return lightweight query suggestions for the current session context.
    """
    try:
        logger.info(
            f"Autocomplete request from user={request.user_id}, "
            f"session={request.session_id}: {request.partial_query}"
        )

        session = await session_service.get_session(
            app_name=APP_NAME,
            user_id=request.user_id,
            session_id=request.session_id,
        )
        if not session:
            raise HTTPException(
                status_code=400,
                detail="No active session found. Initialize the session with /api/chat first.",
            )

        recent_turns = extract_recent_turns(session, request.max_context_turns)
        suggestions = await generate_autocomplete_suggestions(
            partial_query=request.partial_query,
            recent_turns=recent_turns,
            max_suggestions=request.max_suggestions,
        )

        logger.info(
            f"Autocomplete returning {len(suggestions)} suggestion(s) "
            f"for user={request.user_id}, session={request.session_id}"
        )
        return ChatAutocompleteResponse(
            suggestions=suggestions,
            user_id=request.user_id,
            session_id=request.session_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.opt(exception=True).error(f"Autocomplete endpoint error: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to process autocomplete request: {e}"
        )


@router.delete("/chat/session", tags=["Agent Chat"])
async def clear_session(
    payload: Optional[ClearSessionRequest] = Body(default=None),
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
):
    """Clear / reset a chat session to start fresh."""
    try:
        resolved_user_id = (
            user_id
            or (payload.user_id if payload and payload.user_id is not None else None)
            or "demo_user"
        )
        resolved_session_id = (
            session_id or (payload.session_id if payload is not None else None)
        )
        if not resolved_session_id:
            raise HTTPException(
                status_code=422,
                detail="session_id is required to clear a chat session",
            )

        await session_service.delete_session(
            app_name=APP_NAME,
            user_id=resolved_user_id,
            session_id=resolved_session_id,
        )
        logger.info(
            f"Cleared session for user={resolved_user_id}, session={resolved_session_id}"
        )
        return {
            "status": "success",
            "message": (
                f"Session cleared for user={resolved_user_id}, "
                f"session={resolved_session_id}"
            ),
            "user_id": resolved_user_id,
            "session_id": resolved_session_id,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.opt(exception=True).error(f"Failed to clear session: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to clear session: {e}")


def _describe_issue(issue: dict) -> str:
    """Convert a raw validation issue dict into a human-readable string."""
    itype = issue.get("type", "unknown")
    if itype == "overlap":
        names = issue.get("entities", issue.get("entity_ids", []))
        return (
            f"overlap between {names[0]} and {names[1]}"
            if len(names) >= 2
            else "overlap"
        )
    if itype == "overflow":
        return f"{issue.get('entity', 'entity')} overflows display {issue.get('display', '?')}"
    return f"{itype} issue"


def _layout_was_modified(previous_layout, current_layout) -> bool:
    """Check whether node positions changed between snapshots."""
    if previous_layout is None or current_layout is None:
        return False
    prev_positions = previous_layout.get("node_positions", {})
    curr_positions = current_layout.get("node_positions", {})
    return prev_positions != curr_positions


async def _run_post_validation(session, user_id: str, session_id: str):
    """
    Run validation on the current layout and, if critical issues exist,
    trigger one agent pass to fix them.

    Returns (fix_text, fix_tools, fix_thinking) or (None, [], []) if clean.
    """
    try:
        layout = session.state.get("current_layout")
        entities = session.state.get("entities", [])
        if not layout:
            return None, [], []

        report = validate_layout(layout, entities)
        issues = report.get("issues", [])

        # Overlap/overflow break core usability, so auto-fix only gates on those.
        critical = [i for i in issues if i.get("type") in ("overlap", "overflow")]
        if not critical:
            return None, [], []

        issue_descriptions = "; ".join(_describe_issue(i) for i in critical[:5])
        fix_prompt = (
            f"[AUTO-REVIEW] The layout has {len(critical)} critical issue(s): "
            f"{issue_descriptions}. "
            "Please fix these issues using the appropriate tools. "
            "Focus only on the critical problems — do not reorganize the entire layout."
        )

        logger.info(
            f"Post-validation triggering fix pass: {len(critical)} critical issues"
        )
        fix_text, fix_tools, fix_thinking = await run_agent_conversation(
            user_id, session_id, fix_prompt
        )
        return fix_text, fix_tools, fix_thinking
    except Exception as e:
        logger.warning(f"Post-validation safety net failed: {e}")
        return None, [], []


def _snapshot_before_agent(session, state_delta):
    """
    Build the 'before-agent' layout snapshot.

    When a *state_delta* is pending, the agent will see the delta-merged
    state, so the comparison baseline must incorporate it too.
    """
    if state_delta and "current_layout" in state_delta:
        return deepcopy(state_delta["current_layout"])

    return capture_state_snapshot(session)
