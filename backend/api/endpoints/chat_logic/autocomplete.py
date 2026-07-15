"""
Autocomplete helpers for chat endpoint.

Generates lightweight intent-hint suggestions from recent session turns.
"""

import json
from typing import Any, Dict, List

from api.models.chat import AutocompleteSuggestion
from core.autocomplete_client import AutocompleteLLMClient
from core.logger import logger

MAX_SUGGESTION_CHARS = 120


def _normalize_text(text: str) -> str:
    return " ".join(text.split()).strip()


def _extract_event_text(event: Any) -> str:
    content = getattr(event, "content", None)
    parts = getattr(content, "parts", None) if content is not None else None
    if not parts:
        return ""

    chunks: List[str] = []
    for part in parts:
        text = getattr(part, "text", None)
        if isinstance(text, str):
            normalized = _normalize_text(text)
            if normalized:
                chunks.append(normalized)

    return " ".join(chunks).strip()


def extract_recent_turns(session: Any, max_context_turns: int) -> List[Dict[str, str]]:
    """
    Extract the most recent user/assistant text turns from ADK session events.
    """
    if max_context_turns <= 0:
        return []

    turns: List[Dict[str, str]] = []
    events = getattr(session, "events", None) or []

    for event in events:
        author = getattr(event, "author", None)
        if not author:
            continue

        role = "user" if author == "user" else "assistant"

        # Ignore interim assistant chunks so context only includes completed turns.
        if role == "assistant" and getattr(event, "partial", False):
            continue
        if role == "assistant" and hasattr(event, "is_final_response"):
            try:
                if not event.is_final_response():
                    continue
            except Exception:
                pass

        text = _extract_event_text(event)
        if not text:
            continue

        turns.append({"role": role, "text": text})

    if len(turns) > max_context_turns:
        turns = turns[-max_context_turns:]
    return turns


def build_autocomplete_messages(
    partial_query: str, recent_turns: List[Dict[str, str]], max_suggestions: int
) -> List[Dict[str, str]]:
    """
    Build system+user messages for autocomplete generation.
    """
    system_prompt = (
        "You generate short autocomplete suggestions for a layout-agent chat input. "
        "Return ONLY JSON with this exact schema: "
        '{"suggestions":[{"text":"...", "score":0.0}]}. '
        "Rules: provide standalone user-query suggestions, keep each <= 120 chars, "
        "avoid markdown/explanations, and prefer actionable layout-agent wording."
    )

    payload = {
        "partial_query": partial_query,
        "recent_turns": recent_turns,
        "max_suggestions": max_suggestions,
    }

    user_prompt = (
        "Generate top autocomplete suggestions using this context JSON:\n"
        f"{json.dumps(payload, ensure_ascii=True)}"
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _clamp_score(score: Any, default: float = 0.5) -> float:
    try:
        value = float(score)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, value))


def fallback_suggestions(
    _partial_query: str, _max_suggestions: int
) -> List[AutocompleteSuggestion]:
    """
    Return no suggestions when model output is unavailable.
    The client can skip rendering autocomplete in this case.
    """
    return []


def parse_suggestions(
    raw_response: str, partial_query: str, max_suggestions: int
) -> List[AutocompleteSuggestion]:
    """
    Parse model JSON response and sanitize suggestions.
    """
    try:
        payload = json.loads(raw_response)
    except Exception:
        logger.warning("Autocomplete response was not valid JSON; using fallback.")
        return fallback_suggestions(partial_query, max_suggestions)

    items = payload.get("suggestions", []) if isinstance(payload, dict) else []
    if not isinstance(items, list):
        return fallback_suggestions(partial_query, max_suggestions)

    suggestions: List[AutocompleteSuggestion] = []
    seen = set()

    for idx, item in enumerate(items):
        if isinstance(item, dict):
            text = _normalize_text(str(item.get("text", "")))
            score = _clamp_score(item.get("score"), default=max(0.2, 0.8 - (idx * 0.1)))
        elif isinstance(item, str):
            text = _normalize_text(item)
            score = max(0.2, 0.8 - (idx * 0.1))
        else:
            continue

        if not text:
            continue

        text = text[:MAX_SUGGESTION_CHARS]
        key = text.lower()
        if key in seen:
            continue

        seen.add(key)
        suggestions.append(AutocompleteSuggestion(text=text, score=score))

        if len(suggestions) >= max_suggestions:
            break

    if not suggestions:
        return fallback_suggestions(partial_query, max_suggestions)

    return suggestions


async def generate_autocomplete_suggestions(
    partial_query: str, recent_turns: List[Dict[str, str]], max_suggestions: int
) -> List[AutocompleteSuggestion]:
    """
    Generate sanitized autocomplete suggestions from the dedicated fast model.
    """
    messages = build_autocomplete_messages(
        partial_query=partial_query,
        recent_turns=recent_turns,
        max_suggestions=max_suggestions,
    )

    client = AutocompleteLLMClient()
    try:
        raw = await client.complete_json(messages)
        suggestions = parse_suggestions(raw, partial_query, max_suggestions)
        logger.info(
            f"Autocomplete generated {len(suggestions)} suggestion(s) from model output."
        )
        return suggestions
    except Exception as e:
        logger.warning(f"Autocomplete model call failed, using fallback: {e}")
        return fallback_suggestions(partial_query, max_suggestions)
