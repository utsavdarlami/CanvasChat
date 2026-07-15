"""
Agent conversation runner for the chat endpoint.

Wraps the ADK async runner, streaming events until the final
response is collected.
"""

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from google.genai.types import Content, Part
from google.adk.agents.run_config import RunConfig, StreamingMode

from agent import runner_gemini
from core.logger import logger

DEFAULT_AGENT_RESPONSE = "Agent did not produce a response."
MAX_REASONING_STEP_CHARS = 600
MAX_REASONING_STEPS = 24

_CODE_BLOCK_RE = re.compile(r"```[\s\S]*?```")
_BOLD_HEADING_RE = re.compile(r"\*\*(?P<title>[^*\n]{1,120})\*\*")
_WHITESPACE_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9 ]+")


def _normalize_for_dedupe(text: str) -> str:
    normalized = _NON_ALNUM_RE.sub(" ", text.lower())
    normalized = _WHITESPACE_RE.sub(" ", normalized)
    return normalized.strip()


def _looks_like_structured_blob(text: str) -> bool:
    """Skip large JSON/code-like chunks in display reasoning."""
    stripped = text.strip()
    if len(stripped) < 120:
        return False
    lines = [line.strip() for line in stripped.splitlines() if line.strip()]
    if not lines:
        return False
    structured_lines = sum(
        1
        for line in lines
        if line.startswith(("{", "}", "[", "]", '"', "},", "],"))
        or '"entity_ids"' in line
        or line.endswith(",")
    )
    return structured_lines >= max(6, len(lines) // 2)


def _extract_reasoning_steps(raw_thought: str) -> List[str]:
    if not raw_thought:
        return []

    text = raw_thought.replace("\r\n", "\n")
    text = _CODE_BLOCK_RE.sub("\n", text)
    text = text.strip()
    if not text:
        return []

    steps: List[str] = []
    heading_matches = list(_BOLD_HEADING_RE.finditer(text))

    if heading_matches:
        for idx, match in enumerate(heading_matches):
            title = match.group("title").strip()
            body_start = match.end()
            body_end = (
                heading_matches[idx + 1].start()
                if idx + 1 < len(heading_matches)
                else len(text)
            )
            body = text[body_start:body_end].strip()
            step = f"**{title}**\n\n{body}" if body else f"**{title}**"
            steps.append(step)
    else:
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        steps.extend(paragraphs)

    cleaned: List[str] = []
    for step in steps:
        if _looks_like_structured_blob(step):
            continue
        compact = _WHITESPACE_RE.sub(" ", step).strip()
        if len(compact) > MAX_REASONING_STEP_CHARS:
            compact = f"{compact[:MAX_REASONING_STEP_CHARS].rstrip()}..."
        if compact:
            cleaned.append(compact)
    return cleaned


def _tool_call_signature(name: str, args: Dict[str, Any]) -> str:
    """Stable dedupe key for streamed/non-streamed tool call events."""
    try:
        args_key = json.dumps(args, sort_keys=True, default=str)
    except Exception:
        args_key = str(args)
    return f"{name}:{args_key}"


def _record_tool_call(
    call: Any,
    seen_signatures: set[str],
    tools_called: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Record a tool call once, returning normalized payload if new."""
    name = str(getattr(call, "name", "") or "")
    args = dict(getattr(call, "args", {}) or {})
    signature = _tool_call_signature(name, args)
    if signature in seen_signatures:
        return None

    seen_signatures.add(signature)
    tool_data = {"name": name, "args": args}
    tools_called.append(tool_data)
    return tool_data


class ReasoningCollector:
    """Collect display-safe reasoning steps from native model thought text."""

    def __init__(self) -> None:
        self._steps: List[str] = []
        self._seen: set[str] = set()

    def ingest_raw(self, raw_thought: str) -> List[str]:
        new_steps: List[str] = []
        for step in _extract_reasoning_steps(raw_thought):
            normalized = _normalize_for_dedupe(step)
            if len(normalized) < 24 or normalized in self._seen:
                continue
            if len(self._steps) >= MAX_REASONING_STEPS:
                break
            self._seen.add(normalized)
            self._steps.append(step)
            new_steps.append(step)
        return new_steps

    def steps(self) -> List[str]:
        return list(self._steps)


async def run_agent_conversation(
    user_id: str,
    session_id: str,
    query: str,
    state_delta: Optional[Dict[str, Any]] = None,
) -> Tuple[str, List[Dict[str, Any]], List[str]]:
    """
    Execute the agent conversation loop and return the final response text
    along with a record of every tool the agent called and any thinking steps.

    Args:
        user_id: User identifier for the session.
        session_id: Session identifier.
        query: The user's natural-language query.
        state_delta: Optional state delta to inject before the run.

    Returns:
        Tuple of (response_text, tools_called, thinking).
        *tools_called* is a list of ``{"name": ..., "args": ...}`` dicts
        in the order the agent invoked them.
        *thinking* is a list of reasoning strings from native model thought parts.
    """
    response_text = ""
    tools_called: List[Dict[str, Any]] = []
    seen_tool_signatures: set[str] = set()
    reasoning = ReasoningCollector()
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_tokens = 0

    async for event in runner_gemini.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=Content(role="user", parts=[Part.from_text(text=query)]),
        state_delta=state_delta,
    ):
        for call in event.get_function_calls():
            tool_data = _record_tool_call(call, seen_tool_signatures, tools_called)
            if tool_data is None:
                continue
            logger.info(
                f"Agent calling tool: {tool_data['name']}(args={tool_data['args']})"
            )

        # Extract native thought parts from model response.
        if event.content and event.content.parts:
            for p in event.content.parts:
                if getattr(p, "thought", False) and p.text:
                    reasoning.ingest_raw(p.text)

        if event.is_final_response() and event.content and event.content.parts:
            response_text = "".join(
                p.text or "" for p in event.content.parts
                if hasattr(p, "text") and p.text and not getattr(p, "thought", False)
            )

        if hasattr(event, "usage_metadata") and event.usage_metadata:
            total_prompt_tokens += event.usage_metadata.prompt_token_count or 0
            total_completion_tokens += event.usage_metadata.candidates_token_count or 0
            total_tokens += event.usage_metadata.total_token_count or 0

    if response_text:
        logger.info(
            f"Token usage - prompt: {total_prompt_tokens}, completion: {total_completion_tokens}, total: {total_tokens}"
        )
        return response_text, tools_called, reasoning.steps()
    else:
        logger.warning("Agent did not produce a final response; returning default.")
        logger.info(
            f"Token usage - prompt: {total_prompt_tokens}, completion: {total_completion_tokens}, total: {total_tokens}"
        )
        return DEFAULT_AGENT_RESPONSE, tools_called, reasoning.steps()


async def stream_agent_conversation(
    user_id: str,
    session_id: str,
    query: str,
    state_delta: Optional[Dict[str, Any]] = None,
):
    """
    Stream agent conversation events as structured dicts.

    Yields dicts with ``{"event": <type>, "data": <payload>}``:

    - ``tool_call``: ``{"name": "...", "args": {...}}``
    - ``thinking``: ``"reasoning text"``
    - ``text``: ``"partial response text"``
    - ``done``: ``{"response": "...", "tools": [...], "thinking": [...]}``

    The caller is responsible for SSE formatting and any post-processing
    of the ``done`` event (e.g. layout action detection).

    Args:
        user_id: User identifier for the session.
        session_id: Session identifier.
        query: The user's natural-language query.
        state_delta: Optional state delta to inject before the run.

    Yields:
        Dicts of ``{"event": str, "data": Any}``.
    """
    tools_called: List[Dict[str, Any]] = []
    seen_tool_signatures: set[str] = set()
    reasoning = ReasoningCollector()
    _last_thought = ""
    response_text = ""
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_tokens = 0

    run_config = RunConfig(streaming_mode=StreamingMode.SSE)

    logger.info(
        f"Starting agent conversation stream for user={user_id}, session={session_id}"
    )

    async for event in runner_gemini.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=Content(role="user", parts=[Part.from_text(text=query)]),
        state_delta=state_delta,
        run_config=run_config,
    ):
        is_partial = getattr(event, "partial", False)

        # Capture tool calls from both partial and final events.
        # Some providers surface function calls incrementally.
        for call in event.get_function_calls():
            tool_data = _record_tool_call(call, seen_tool_signatures, tools_called)
            if tool_data is None:
                continue
            logger.info(
                "Agent calling tool (streaming mode): "
                f"{tool_data['name']}(args={tool_data['args']})"
            )
            yield {"event": "tool_call", "data": tool_data}

        # ── Extract native thought parts from any event ──────────────
        # Streaming returns rolling/incremental thought summaries so we
        # stream the latest version and deduplicate for the final list.
        if event.content and event.content.parts:
            for p in event.content.parts:
                if getattr(p, "thought", False) and p.text and p.text != _last_thought:
                    _last_thought = p.text
                    new_steps = reasoning.ingest_raw(p.text)
                    for step in new_steps:
                        logger.debug("Yielding curated reasoning event")
                        yield {"event": "thinking", "data": step}

        if is_partial:
            if event.content and event.content.parts:
                has_text = any(
                    hasattr(p, "text") and p.text
                    and not getattr(p, "thought", False)
                    for p in event.content.parts
                )
                has_fc = any(
                    hasattr(p, "function_call") and p.function_call
                    for p in event.content.parts
                )

                # Ignore mixed text+function-call partials to prevent duplicate tool events.
                if has_text and not has_fc:
                    chunk = "".join(
                        p.text or "" for p in event.content.parts
                        if hasattr(p, "text") and p.text
                        and not getattr(p, "thought", False)
                    )
                    if chunk:
                        response_text += chunk
                        logger.debug(
                            f"Yielding partial text chunk (length: {len(chunk)}), total length so far: {len(response_text)}"
                        )
                        yield {"event": "text", "data": response_text}

        else:
            if event.is_final_response():
                # Some providers skip partial text; recover from final payload when needed.
                if not response_text and event.content and event.content.parts:
                    has_text = any(
                        hasattr(p, "text") and p.text
                        and not getattr(p, "thought", False)
                        for p in event.content.parts
                    )
                    has_fc = any(
                        hasattr(p, "function_call") and p.function_call
                        for p in event.content.parts
                    )

                    if has_text and not has_fc:
                        response_text = "".join(
                            p.text or ""
                            for p in event.content.parts
                            if hasattr(p, "text") and p.text
                            and not getattr(p, "thought", False)
                        )
                        if response_text:
                            logger.debug(
                                f"Yielding final text fallback (length: {len(response_text)})"
                            )
                            yield {"event": "text", "data": response_text}

                final_data = {
                    "response": response_text
                    if response_text
                    else DEFAULT_AGENT_RESPONSE,
                    "tools": tools_called,
                    "thinking": reasoning.steps(),
                }

                logger.info("Stream complete, yielding final done event")
                yield {"event": "done", "data": final_data}

        if not is_partial and hasattr(event, "usage_metadata") and event.usage_metadata:
            total_prompt_tokens += event.usage_metadata.prompt_token_count or 0
            total_completion_tokens += event.usage_metadata.candidates_token_count or 0
            total_tokens += event.usage_metadata.total_token_count or 0

            if event.is_final_response():
                logger.info(
                    f"Token usage - prompt: {total_prompt_tokens}, completion: {total_completion_tokens}, total: {total_tokens}"
                )
