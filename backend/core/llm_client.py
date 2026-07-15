"""
Shared LLM client for all semantic analysis operations.
Eliminates duplication in prompt loading, parameter construction, and LLM calls.
"""

from typing import Optional, Dict, Any, List
from pathlib import Path
import time
from litellm import acompletion

from core.config import settings
from core.logger import logger
from api.models.request import LLM_Config


class PromptTemplateManager:
    """
    Centralized prompt template loader.
    Eliminates duplicate _load_prompt_template() implementations.
    """

    @staticmethod
    def load(filename: str) -> str:
        """
        Load prompt template from prompts/ directory.
        
        Args:
            filename: Template filename (with or without .txt extension)
            
        Returns:
            Template content as string
            
        Raises:
            FileNotFoundError: If template file doesn't exist
        """
        if not filename.endswith('.txt'):
            filename = f"{filename}.txt"
            
        prompt_path = Path(__file__).parent.parent / "prompts" / filename

        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt template not found: {prompt_path}")

        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()


class LLMClient:
    """
    Unified LLM client with consistent parameter handling.

    Benefits:
    - Single source of truth for LLM configuration
    - Testable via dependency injection
    - Consistent temperature priority logic
    - Centralized debug logging
    """

    def __init__(self, model: str = None, api_key: str = None):
        """
        Initialize LLM client with optional overrides.
        
        Args:
            model: Override default model (defaults to settings.LLM_MODEL)
            api_key: Override default API key (defaults to settings.LLM_API_KEY)
        """
        self.model = model or settings.LLM_MODEL
        self.api_key = api_key or settings.LLM_API_KEY

    async def complete(
        self,
        prompt: str,
        llm_config: Optional[LLM_Config] = None,
        default_temperature: float = 0.1
    ) -> str:
        """
        Execute LLM completion with standardized parameter handling.

        Temperature priority (from highest to lowest):
        1. Environment variable (LLM_TEMPERATURE)
        2. Request-specific config (llm_config.temperature)
        3. Function default (default_temperature)

        Args:
            prompt: Formatted prompt string
            llm_config: Optional per-request LLM configuration
            default_temperature: Fallback temperature if not specified

        Returns:
            JSON string response from LLM
            
        Raises:
            ValueError: If LLM_API_KEY is not set
            Exception: Propagates LLM call errors (caller handles domain-specific parsing)
        """
        if not self.api_key:
            raise ValueError("LLM_API_KEY is not set in environment variables.")
            
        completion_params = self._build_params(prompt, llm_config, default_temperature)

        self._log_request(completion_params)

        start_time = time.time()
        response = await acompletion(**completion_params)
        elapsed_time = time.time() - start_time
        
        logger.info(f"LLM call completed in {elapsed_time:.2f}s (model: {self.model})")
        
        return response.choices[0].message.content

    async def complete_multimodal(
        self,
        prompt: str,
        image_base64: str,
        media_type: str = "image/jpeg",
        llm_config: Optional[LLM_Config] = None,
        default_temperature: float = 0.1,
    ) -> str:
        """
        Execute LLM completion with an image + text prompt (vision).

        Uses the OpenAI-compatible content array format supported by litellm
        for Gemini, OpenAI, and Anthropic vision models.

        Args:
            prompt: Text prompt to accompany the image
            image_base64: Base64-encoded image data (no data URL prefix)
            media_type: MIME type of the image (default: image/jpeg)
            llm_config: Optional per-request LLM configuration
            default_temperature: Fallback temperature

        Returns:
            JSON string response from LLM
        """
        if not self.api_key:
            raise ValueError("LLM_API_KEY is not set in environment variables.")

        data_url = f"data:{media_type};base64,{image_base64}"

        content: List[Dict[str, Any]] = [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": data_url}},
        ]

        params = self._build_params_with_content(content, llm_config, default_temperature)

        self._log_request(params)

        start_time = time.time()
        response = await acompletion(**params)
        elapsed_time = time.time() - start_time

        logger.info(f"Multimodal LLM call completed in {elapsed_time:.2f}s (model: {self.model})")

        return response.choices[0].message.content

    def _build_params(
        self,
        prompt: str,
        llm_config: Optional[LLM_Config],
        default_temperature: float
    ) -> Dict[str, Any]:
        """Build completion parameters with priority-based temperature."""
        content: Any = prompt
        return self._build_params_with_content(content, llm_config, default_temperature)

    def _build_params_with_content(
        self,
        content: Any,
        llm_config: Optional[LLM_Config],
        default_temperature: float,
    ) -> Dict[str, Any]:
        """Build completion parameters with arbitrary content and priority-based temperature."""
        params = {
            "model": self.model,
            "messages": [{"role": "user", "content": content}],
            "api_key": self.api_key,
            "response_format": {"type": "json_object"}
        }

        if settings.LLM_TEMPERATURE is not None:
            params["temperature"] = settings.LLM_TEMPERATURE
        elif llm_config and llm_config.temperature is not None:
            params["temperature"] = llm_config.temperature
        else:
            params["temperature"] = default_temperature

        return params

    def _log_request(self, params: Dict[str, Any]) -> None:
        """Log request parameters without sensitive data."""
        safe_params = params.copy()
        safe_params.pop("messages", None)
        safe_params.pop("api_key", None)
        logger.info(f"LLM request: {safe_params}")
