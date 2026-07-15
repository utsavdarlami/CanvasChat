"""
Dedicated low-latency LLM client for chat autocomplete suggestions.
"""

import time
from typing import Dict, List

from litellm import acompletion

from core.config import settings
from core.logger import logger


class AutocompleteLLMClient:
    """
    Lightweight JSON-completion client for autocomplete suggestions.
    """

    def __init__(self, model: str = None, api_key: str = None):
        self.model = model or settings.AUTOCOMPLETE_MODEL
        self.api_key = api_key or settings.LLM_API_KEY

    async def complete_json(self, messages: List[Dict[str, str]]) -> str:
        """
        Call the autocomplete model and return raw JSON-string content.
        """
        if not self.api_key:
            raise ValueError("LLM_API_KEY is not set in environment variables.")

        params = {
            "model": self.model,
            "messages": messages,
            "api_key": self.api_key,
            "temperature": settings.AUTOCOMPLETE_TEMPERATURE,
            "response_format": {"type": "json_object"},
            "timeout": settings.AUTOCOMPLETE_TIMEOUT_SECONDS,
        }

        logger.info(
            "Autocomplete LLM request: "
            f"model={self.model}, temperature={settings.AUTOCOMPLETE_TEMPERATURE}, "
            f"timeout={settings.AUTOCOMPLETE_TIMEOUT_SECONDS}s"
        )

        start_time = time.time()
        response = await acompletion(**params)
        elapsed_time = time.time() - start_time
        logger.info(f"Autocomplete LLM call completed in {elapsed_time:.2f}s")
        logger.info(f"Raw autocomplete response: {response}")

        return response.choices[0].message.content or ""
