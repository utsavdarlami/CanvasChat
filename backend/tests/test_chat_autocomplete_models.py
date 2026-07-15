from pydantic import ValidationError
import sys
from pathlib import Path

# Add project root to path for standalone script execution
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from api.models.chat import (
    AutocompleteSuggestion,
    ChatAutocompleteRequest,
    ChatAutocompleteResponse,
)


def test_chat_autocomplete_request_defaults():
    request = ChatAutocompleteRequest(partial_query="move the chart")
    assert request.user_id == "demo_user"
    assert request.session_id == "demo_session"
    assert request.max_suggestions == 3
    assert request.max_context_turns == 6


def test_chat_autocomplete_request_validates_bounds():
    try:
        ChatAutocompleteRequest(partial_query="move", max_suggestions=0)
        assert False, "Expected ValidationError for max_suggestions=0"
    except ValidationError:
        pass

    try:
        ChatAutocompleteRequest(partial_query="move", max_context_turns=21)
        assert False, "Expected ValidationError for max_context_turns=21"
    except ValidationError:
        pass


def test_chat_autocomplete_response_schema():
    response = ChatAutocompleteResponse(
        suggestions=[AutocompleteSuggestion(text="move this left", score=0.9)],
        user_id="u1",
        session_id="s1",
    )
    assert len(response.suggestions) == 1
    assert response.suggestions[0].text == "move this left"


if __name__ == "__main__":
    test_chat_autocomplete_request_defaults()
    test_chat_autocomplete_request_validates_bounds()
    test_chat_autocomplete_response_schema()
    print("test_chat_autocomplete_models passed")
