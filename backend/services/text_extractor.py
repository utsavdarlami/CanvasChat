import json
from typing import Dict, Any, Optional
from pydantic import ValidationError

from core.logger import logger
from core.llm_client import LLMClient, PromptTemplateManager
from api.models.response import EntitySemantics
from api.models.request import LLM_Config


def _get_prompt_example_json() -> str:
    """Returns example JSON structure for text semantics extraction."""
    example = {
        "title": "CIA Intelligence Report - Taliban Affiliates",
        "item_type": "intelligence_report",
        "granularity": "detailed",
        "sentiment": "neutral",
        "key_themes": ["Taliban", "Afghanistan", "alias", "passport", "identity", "terrorist"],
        "domain": "intelligence",
        "location": "Afghanistan",
        "temporal_focus": "1990 - 1993",
        "summary": "Report from laptop data captured in Afghanistan identifies Pakistani national Sahim Albakri who fought with Taliban in 1990-1992. Also identifies Muhammed bin Harazi who entered USA in March 1993 using alias Abdul Ramazi.",
        "encoded_metrics": [],
    }
    return json.dumps(example, indent=2)


async def extract_text_semantics(
    text_content: str,
    metadata: Optional[Dict[str, Any]] = None,
    llm_config: Optional[LLM_Config] = None
) -> EntitySemantics:
    """
    Uses an LLM to extract semantic information from a text document.

    Args:
        text_content: Raw text content of the document
        metadata: Optional metadata dict (filename, source, date, etc.)
        llm_config: Optional LLM configuration override

    Returns:
        EntitySemantics object with lean flat schema

    Raises:
        ValueError: If LLM response is invalid or cannot be parsed
    """
    logger.info("Loading prompt template for text semantics extraction...")
    prompt_template = PromptTemplateManager.load("text_semantics_extraction")
    example_json = _get_prompt_example_json()

    metadata_str = json.dumps(metadata, indent=2) if metadata else "No metadata provided."

    try:
        prompt = prompt_template.format(
            text_content=text_content,
            metadata=metadata_str,
            example_json=example_json
        )
    except KeyError as e:
        logger.error(f"Error formatting prompt template: {e}")
        raise

    llm_client = LLMClient()
    try:
        response_text = await llm_client.complete(prompt, llm_config, default_temperature=0.1)

        parsed_response = json.loads(response_text)
        return EntitySemantics(**parsed_response)

    except ValidationError as e:
        logger.error(f"LLM response validation error: {e.json()}")
        raise ValueError(f"Invalid LLM response format: {e}")
    except json.JSONDecodeError as e:
        logger.error(f"LLM response is not valid JSON: {response_text}")
        raise ValueError(f"LLM did not return valid JSON: {e}")
    except Exception as e:
        logger.error(f"Error during LLM call: {e}")
        raise
