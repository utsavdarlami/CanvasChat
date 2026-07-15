import os
from dotenv import load_dotenv
from typing import Optional
from core.logger import logger

load_dotenv(override=True)


def _parse_optional_float(
    env_key: str, default: Optional[float] = None
) -> Optional[float]:
    value = os.getenv(env_key)
    if value is None or value == "":
        return default
    try:
        return float(value)
    except ValueError:
        logger.warning(f"Invalid float for {env_key}: {value!r}. Ignoring value.")
        return default


def _parse_int(env_key: str, default: int) -> int:
    value = os.getenv(env_key)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError:
        logger.warning(f"Invalid int for {env_key}: {value!r}. Using default.")
        return default


class Settings:
    # Directory for serving static files (images, etc.)
    STATIC_DIR: str = os.getenv(
        "STATIC_DIR",
        os.path.join(os.path.dirname(__file__), "..", "static"),
    )

    LLM_MODEL: str = os.getenv("LLM_MODEL", "gemini/gemini-pro") or "gemini/gemini-pro"
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    AGENT_LLM_MODEL: str = (
        os.getenv("AGENT_LLM_MODEL", "gemini-3-flash-preview")
        or "gemini-3-flash-preview"
    )

    LLM_TEMPERATURE: Optional[float] = _parse_optional_float("LLM_TEMPERATURE")
    AGENT_TEMPERATURE: float = (
        _parse_optional_float("AGENT_TEMPERATURE", default=0.3) or 0.3
    )

    AUTOCOMPLETE_MODEL: str = (
        os.getenv("AUTOCOMPLETE_MODEL", "gemini/gemini-2.0-flash")
        or "gemini/gemini-2.0-flash"
    )
    AUTOCOMPLETE_TEMPERATURE: float = (
        _parse_optional_float("AUTOCOMPLETE_TEMPERATURE") or 0.2
    )
    AUTOCOMPLETE_TIMEOUT_SECONDS: int = _parse_int(
        "AUTOCOMPLETE_TIMEOUT_SECONDS", default=3
    )


settings = Settings()
logger.info(
    f"LLM_MODEL set to: {settings.LLM_MODEL} with temperature: {settings.LLM_TEMPERATURE}"
)
logger.info(
    f"AGENT_LLM_MODEL set to: {settings.AGENT_LLM_MODEL} with temperature: {settings.AGENT_TEMPERATURE}"
)
logger.info(
    f"AUTOCOMPLETE_MODEL set to: {settings.AUTOCOMPLETE_MODEL} with temperature: {settings.AUTOCOMPLETE_TEMPERATURE} and timeout: {settings.AUTOCOMPLETE_TIMEOUT_SECONDS}s"
)
