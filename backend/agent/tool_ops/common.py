"""Shared tool decorators and lightweight utilities."""

from functools import wraps
from typing import Callable

from google.adk.tools.tool_context import ToolContext
from loguru import logger


def tool_safe(require_layout: bool = True):
    """
    Decorator to handle exceptions and standard layout checks for ADK tools.

    Args:
        require_layout: If True, checks if 'current_layout' exists in state.

    If the wrapped tool returns a dict with an ``_action_type`` key, the
    decorator stores it in ``state["_last_action_type"]`` so the chat
    endpoint can use it as a hint instead of inferring the action type
    from snapshot comparison.
    """

    def decorator(func: Callable):
        @wraps(func)
        def wrapper(tool_context: ToolContext, *args, **kwargs):
            try:
                if require_layout:
                    layout = tool_context.state.get("current_layout")
                    if layout is None:
                        return {
                            "status": "error",
                            "message": "No layout loaded. Please load a layout first.",
                        }
                result = func(tool_context, *args, **kwargs)

                if isinstance(result, dict) and "_action_type" in result:
                    tool_context.state["_last_action_type"] = result["_action_type"]

                if isinstance(result, dict) and "_timeline_index" in result:
                    tool_context.state["_last_timeline_index"] = result["_timeline_index"]

                return result
            except Exception as e:
                logger.opt(exception=True).error(
                    f"Tool {func.__name__} failed: {str(e)}"
                )
                return {
                    "status": "error",
                    "message": f"Failed to execute {func.__name__}: {str(e)}",
                }

        return wrapper

    return decorator
