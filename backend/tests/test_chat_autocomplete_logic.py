import asyncio
import json
import sys
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path

# Add project root to path for standalone script execution
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from api.endpoints.chat_logic import autocomplete as autocomplete_logic


class DummyEvent:
    def __init__(self, author: str, text: str = "", partial: bool = False, final: bool = True):
        self.author = author
        self.partial = partial
        self._final = final
        parts = [SimpleNamespace(text=text)] if text else []
        self.content = SimpleNamespace(parts=parts)

    def is_final_response(self) -> bool:
        return self._final


def test_extract_recent_turns_filters_and_limits():
    session = SimpleNamespace(
        events=[
            DummyEvent("user", "First question"),
            DummyEvent("layout_agent", "intermediate", final=False),
            DummyEvent("layout_agent", "First answer", final=True),
            DummyEvent("user", "Second question"),
            DummyEvent("layout_agent", "", final=True),
            DummyEvent("layout_agent", "Second answer", final=True),
        ]
    )

    turns = autocomplete_logic.extract_recent_turns(session, max_context_turns=3)

    assert len(turns) == 3
    assert turns[0] == {"role": "assistant", "text": "First answer"}
    assert turns[1] == {"role": "user", "text": "Second question"}
    assert turns[2] == {"role": "assistant", "text": "Second answer"}


def test_parse_suggestions_sanitizes_and_deduplicates():
    raw = json.dumps(
        {
            "suggestions": [
                {"text": "  Move View A to the left  ", "score": 1.4},
                {"text": "Move View A to the left", "score": 0.8},
                {"text": "x" * 200, "score": "bad"},
            ]
        }
    )

    suggestions = autocomplete_logic.parse_suggestions(
        raw_response=raw,
        partial_query="move",
        max_suggestions=3,
    )

    assert len(suggestions) == 2
    assert suggestions[0].text == "Move View A to the left"
    assert suggestions[0].score == 1.0
    assert len(suggestions[1].text) == 120
    assert 0.0 <= suggestions[1].score <= 1.0


def test_parse_suggestions_uses_fallback_for_invalid_json():
    suggestions = autocomplete_logic.parse_suggestions(
        raw_response="not-json",
        partial_query="move this",
        max_suggestions=3,
    )

    assert suggestions == []


def test_generate_autocomplete_suggestions_fallback_on_llm_failure():
    class BrokenClient:
        async def complete_json(self, _messages):
            raise RuntimeError("model unavailable")

    async def scenario():
        with patch.object(
            autocomplete_logic,
            "AutocompleteLLMClient",
            return_value=BrokenClient(),
        ):
            suggestions = await autocomplete_logic.generate_autocomplete_suggestions(
                partial_query="group these views",
                recent_turns=[],
                max_suggestions=3,
            )
        assert suggestions == []

    asyncio.run(scenario())


if __name__ == "__main__":
    test_extract_recent_turns_filters_and_limits()
    test_parse_suggestions_sanitizes_and_deduplicates()
    test_parse_suggestions_uses_fallback_for_invalid_json()
    test_generate_autocomplete_suggestions_fallback_on_llm_failure()
    print("test_chat_autocomplete_logic passed")
