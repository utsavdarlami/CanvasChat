import asyncio
import sys
from uuid import uuid4
from unittest.mock import patch
from pathlib import Path

from fastapi import HTTPException

# Add project root to path for standalone script execution
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from agent import APP_NAME, session_service
from api.endpoints import chat as chat_endpoint_module
from api.models.chat import (
    AutocompleteSuggestion,
    ChatAutocompleteRequest,
)


def _make_session_ids() -> tuple[str, str]:
    token = uuid4().hex
    return f"ac_user_{token}", f"ac_session_{token}"


async def _clear_session(user_id: str, session_id: str) -> None:
    session = await session_service.get_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )
    if session:
        await session_service.delete_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id
        )


def test_chat_autocomplete_requires_existing_session():
    async def scenario() -> None:
        user_id, session_id = _make_session_ids()
        await _clear_session(user_id, session_id)

        request = ChatAutocompleteRequest(
            partial_query="move the chart",
            user_id=user_id,
            session_id=session_id,
        )

        try:
            await chat_endpoint_module.chat_autocomplete_endpoint(request)
            assert False, "Expected HTTPException for missing session"
        except HTTPException as exc:
            assert exc.status_code == 400
            assert "No active session found" in str(exc.detail)

    asyncio.run(scenario())


def test_chat_autocomplete_returns_suggestions():
    captured = {"recent_turns": None, "max_context_turns": None}

    def fake_extract_recent_turns(_session, max_context_turns):
        captured["max_context_turns"] = max_context_turns
        return [{"role": "user", "text": "move related views"}]

    async def fake_generate(partial_query, recent_turns, max_suggestions):
        captured["recent_turns"] = recent_turns
        assert partial_query == "move"
        return [
            AutocompleteSuggestion(text="move related views to the left display", score=0.9),
            AutocompleteSuggestion(text="move related views to the right display", score=0.8),
            AutocompleteSuggestion(text="move related views and summarize changes", score=0.7),
        ][:max_suggestions]

    async def scenario() -> None:
        user_id, session_id = _make_session_ids()
        await _clear_session(user_id, session_id)
        try:
            await session_service.create_session(
                app_name=APP_NAME,
                user_id=user_id,
                session_id=session_id,
                state={"current_layout": {"node_positions": {}}},
            )

            request = ChatAutocompleteRequest(
                partial_query="move",
                user_id=user_id,
                session_id=session_id,
                max_suggestions=2,
                max_context_turns=4,
            )
            with patch.object(
                chat_endpoint_module,
                "extract_recent_turns",
                side_effect=fake_extract_recent_turns,
            ), patch.object(
                chat_endpoint_module,
                "generate_autocomplete_suggestions",
                side_effect=fake_generate,
            ):
                response = await chat_endpoint_module.chat_autocomplete_endpoint(
                    request
                )

            assert response.user_id == user_id
            assert response.session_id == session_id
            assert len(response.suggestions) == 2
            assert response.suggestions[0].text.startswith("move related views")
            assert captured["max_context_turns"] == 4
            assert captured["recent_turns"] == [
                {"role": "user", "text": "move related views"}
            ]
        finally:
            await _clear_session(user_id, session_id)

    asyncio.run(scenario())


if __name__ == "__main__":
    test_chat_autocomplete_requires_existing_session()
    test_chat_autocomplete_returns_suggestions()
    print("test_chat_autocomplete_api passed")
