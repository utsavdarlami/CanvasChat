"""
Layout modification agent package.

Keep package import light so utility modules like ``agent.layout_ops.*`` can be
imported in tests without requiring Google ADK at import time.
"""

from typing import Any

__all__ = [
    "APP_NAME",
    "session_service",
    "runner_gemini",
    "initialize_session",
    "root_agent",
]


def __getattr__(name: str) -> Any:
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    from .agent import (
        APP_NAME,
        initialize_session,
        root_agent,
        runner_gemini,
        session_service,
    )

    values = {
        "APP_NAME": APP_NAME,
        "session_service": session_service,
        "runner_gemini": runner_gemini,
        "initialize_session": initialize_session,
        "root_agent": root_agent,
    }
    return values[name]
