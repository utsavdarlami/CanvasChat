"""
Regression tests for display-context-driven state_delta synchronization.
"""

import asyncio
from uuid import uuid4

from agent import APP_NAME, session_service
from api.endpoints.chat_logic.session import get_or_create_session


def _make_session_ids() -> tuple[str, str]:
    token = uuid4().hex
    return f"test_user_{token}", f"test_session_{token}"


async def _clear_session(user_id: str, session_id: str) -> None:
    existing_session = await session_service.get_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )
    if existing_session:
        await session_service.delete_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id
        )


def _sample_layout() -> dict:
    return {
        "nodes": [
            {
                "entity_id": "entity-1",
                "id": "entity-1",
                "name": "Left View",
                "display_name": "Left View",
                "x": 120.0,
                "y": 80.0,
                "display_id": "peer-left",
            },
            {
                "entity_id": "entity-2",
                "id": "entity-2",
                "name": "Right View",
                "display_name": "Right View",
                "x": 320.0,
                "y": 140.0,
                "display_id": "peer-right",
            },
        ],
        "links": [],
        "graph": {"metadata": {"approach": "frontend_only"}},
    }


def _multi_display_context() -> dict:
    return {
        "is_multi_display": True,
        "local_peer_id": "peer-left",
        "virtual_desktop": {
            "total_width": 3000,
            "total_height": 1200,
            "displays": [
                {
                    "peer_id": "peer-left",
                    "tags": ["left"],
                    "x": 0,
                    "y": 0,
                    "width": 1500,
                    "height": 900,
                    "node_ids": ["entity-1"],
                },
                {
                    "peer_id": "peer-right",
                    "tags": ["right"],
                    "x": 1500,
                    "y": 0,
                    "width": 1500,
                    "height": 900,
                    "node_ids": ["entity-2"],
                },
            ],
        },
    }


def _single_surface_context() -> dict:
    return {
        "is_multi_display": False,
        "local_peer_id": "peer-left",
    }


def test_display_context_rebuild_clears_stale_displays():
    async def scenario() -> None:
        user_id, session_id = _make_session_ids()
        await _clear_session(user_id, session_id)
        try:
            _, first_delta = await get_or_create_session(
                user_id=user_id,
                session_id=session_id,
                layout=_sample_layout(),
                display_context=_multi_display_context(),
            )
            assert first_delta is None

            _, state_delta = await get_or_create_session(
                user_id=user_id,
                session_id=session_id,
                display_context=_single_surface_context(),
            )
            assert state_delta is not None

            updated_layout = state_delta["current_layout"]
            assert updated_layout.get("displays") == []
        finally:
            await _clear_session(user_id, session_id)

    asyncio.run(scenario())


def test_layout_refresh_state_delta_updates_layout():
    async def scenario() -> None:
        user_id, session_id = _make_session_ids()
        await _clear_session(user_id, session_id)
        try:
            _, first_delta = await get_or_create_session(
                user_id=user_id,
                session_id=session_id,
                layout=_sample_layout(),
                display_context=_multi_display_context(),
            )
            assert first_delta is None

            refreshed_layout = _sample_layout()
            refreshed_layout["nodes"][0]["x"] = 555.0

            _, state_delta = await get_or_create_session(
                user_id=user_id,
                session_id=session_id,
                layout=refreshed_layout,
                display_context=_multi_display_context(),
            )
            assert state_delta is not None
            assert "current_layout" in state_delta
        finally:
            await _clear_session(user_id, session_id)

    asyncio.run(scenario())
