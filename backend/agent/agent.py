"""
Simple Layout Modification Agent using Google ADK.

This agent takes existing layout output from visualize_cached_data.py or
test_generate_llm_layout.py and allows users to modify it through conversation.
"""

import os

from google.adk.agents.llm_agent import Agent
from google.adk.agents.context_cache_config import ContextCacheConfig
from google.adk.apps.app import App
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from google.genai import types

from typing import Dict, Any, Optional, List
import json
from loguru import logger
from langfuse import get_client
from openinference.instrumentation.google_adk import GoogleADKInstrumentor
from core.config import settings

from .callbacks import inject_layout_context
from .tools import (
    tool_get_entity_semantics,
    tool_infer_arrangement,
    tool_move_entity,
    tool_read_entity_content,
    tool_resize_entities,
    tool_scale,
    tool_swap,
    tool_snap_edges,
    tool_maximize_to_display,
    tool_arrange_entities,
    tool_arrange_relative,
    tool_show_entity,
    tool_highlight_text,
    tool_clear_text_highlights,
    tool_clear_entity_tags,
    tool_add_entity_tags_bulk,
    tool_remove_entity_tags_bulk,
    tool_jump_to_timeline,
    tool_camera,
    tool_plan_semantic_layout,
    tool_validate_layout,
)

APP_NAME = "layout_agent"


async def call_agent_async(query: str, runner, user_id, session_id):
    """Sends a query to the agent and prints the final response."""
    print(f"\n>>> User Query: {query}")

    content = types.Content(role="user", parts=[types.Part(text=query)])

    final_response_text = "Agent did not produce a final response."

    async for event in runner.run_async(
        user_id=user_id, session_id=session_id, new_message=content
    ):
        if event.is_final_response():
            if event.content and event.content.parts:
                final_response_text = event.content.parts[0].text
            break

    print(f"<<< Agent Response: {final_response_text}")


def _load_instruction():
    """Load agent instruction from prompts directory."""
    try:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        prompt_path = os.path.join(
            project_root, "prompts", "layout_agent_instruction.txt"
        )

        with open(prompt_path, "r") as f:
            return f.read()
    except Exception as e:
        logger.warning(f"Failed to load instruction from file: {e}. Using fallback.")
        return """You are a helpful assistant for modifying visualization layouts.

        **State Management:**
        - Layout state is maintained automatically in session memory and
          injected into your context before every tool decision
        - Use `tool_get_entity_semantics` to read entity content fields
          (themes, domain, summary) that are not in the injected state
        - All modification tools automatically update the session state

        **Your job:**
        1. Help users modify layouts based on their preferences
        2. Track the current layout state automatically
        """


GoogleADKInstrumentor().instrument()

langfuse = get_client()

root_agent = Agent(
    # model=LiteLlm(model=settings.AGENT_LLM_MODEL),
    model=settings.AGENT_LLM_MODEL,
    name="Multi_Display_Layout_Agent",
    instruction=_load_instruction(),
    before_model_callback=inject_layout_context,
    generate_content_config=types.GenerateContentConfig(
        temperature=settings.AGENT_TEMPERATURE,
        thinking_config=types.ThinkingConfig(
            include_thoughts=True,
        ),
    ),
    tools=[
        tool_get_entity_semantics,
        tool_read_entity_content,
        tool_infer_arrangement,
        tool_move_entity,
        tool_resize_entities,
        tool_arrange_entities,
        tool_arrange_relative,
        tool_scale,
        tool_swap,
        tool_snap_edges,
        tool_maximize_to_display,
        tool_jump_to_timeline,
        tool_show_entity,
        tool_highlight_text,
        tool_clear_text_highlights,
        tool_clear_entity_tags,
        tool_add_entity_tags_bulk,
        tool_remove_entity_tags_bulk,
        tool_camera,
        tool_plan_semantic_layout,
        tool_validate_layout,
    ],
)

USER_ID = "user_1"
SESSION_ID = "session_1"

session_service = InMemorySessionService()

app = App(
    name=APP_NAME,
    root_agent=root_agent,
    context_cache_config=ContextCacheConfig(
        cache_intervals=10,
        ttl_seconds=1800,
        min_tokens=4000,
    ),
)

runner_gemini = Runner(
    app=app,
    session_service=session_service,
)


async def initialize_session(
    user_id: str = USER_ID,
    session_id: str = SESSION_ID,
    layout_data: Optional[Dict[str, Any]] = None,
    entities: Optional[List[Dict[str, Any]]] = None,
    display_context: Optional[Dict[str, Any]] = None,
):
    """
    Initialize session with layout state and optional semantic context.

    Args:
        user_id: User identifier for session management
        session_id: Session identifier for conversation continuity
        layout_data: Optional layout data to initialize with. If not provided, loads default layout.
        entities: Optional semantic entity data (Layer 1 output) for better context
        display_context: Optional multi-display context from client

    Returns:
        Created session object
    """
    if layout_data is None:
        layout_path = os.path.join(
            os.path.dirname(__file__), "generate_llm_layout_response.json"
        )
        with open(layout_path, "r") as f:
            layout = json.load(f)
    else:
        layout = layout_data

    state = {"current_layout": layout}

    if display_context is not None:
        state["display_context"] = display_context
        logger.info("Session initialized with multi-display context")

    if entities is not None:
        state["entities"] = entities
        logger.info(f"Session initialized with {len(entities)} entity semantics")

    session = await session_service.create_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id, state=state
    )

    logger.info(f"Session initialized with {len(layout.get('nodes', []))} entities")
    return session
