"""
State snapshot helpers for the chat endpoint.
"""

from copy import deepcopy
from typing import Any, Dict, Optional

from core.logger import logger


def capture_state_snapshot(session: Any) -> Optional[Dict]:
    """
    Capture layout from session state.

    Returns:
        Deep-copy of current_layout, or None.
    """
    try:
        if session and hasattr(session, "state"):
            return deepcopy(session.state.get("current_layout"))
    except Exception as e:
        logger.warning(f"Failed to capture state snapshot: {e}")
    return None
