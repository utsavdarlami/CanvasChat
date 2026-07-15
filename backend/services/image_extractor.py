import base64
import json
import mimetypes
from pathlib import Path
from typing import Dict, Any, Optional

from pydantic import ValidationError

from core.logger import logger
from core.llm_client import LLMClient, PromptTemplateManager
from core.config import settings
from api.models.response import EntitySemantics
from api.models.request import LLM_Config


def _get_prompt_example_json() -> str:
    """Returns example JSON structure for image semantics extraction."""
    example = {
        "title": "The Godfather",
        "item_type": "movie_poster",
        "granularity": "summary",
        "sentiment": "negative",
        "key_themes": ["crime", "mafia", "Marlon Brando", "dark", "cat", "classic cinema"],
        "domain": "entertainment",
        "location": None,
        "temporal_focus": "1972",
        "summary": "Dark movie poster featuring a man in a tuxedo holding a cat, with 'The Godfather' title text at the bottom.",
        "encoded_metrics": [],
    }
    return json.dumps(example, indent=2)


def _read_image_as_base64(image_path: str) -> tuple[str, str]:
    """
    Read an image file from disk and return (base64_data, media_type).

    The image_path is relative to STATIC_DIR.

    Raises:
        FileNotFoundError: If the image file doesn't exist
        ValueError: If the file type is not a supported image format
    """
    full_path = Path(settings.STATIC_DIR) / image_path

    if not full_path.is_file():
        raise FileNotFoundError(f"Image file not found: {full_path}")

    mime_type, _ = mimetypes.guess_type(str(full_path))
    if not mime_type or not mime_type.startswith("image/"):
        raise ValueError(f"Unsupported file type: {mime_type} for {full_path}")

    with open(full_path, "rb") as f:
        image_bytes = f.read()

    return base64.b64encode(image_bytes).decode("utf-8"), mime_type


async def extract_image_semantics(
    image_path: str,
    metadata: Optional[Dict[str, Any]] = None,
    llm_config: Optional[LLM_Config] = None,
) -> EntitySemantics:
    """
    Uses a vision-capable LLM to extract semantic information from an image.

    Args:
        image_path: Path to image file relative to STATIC_DIR
        metadata: Optional metadata dict (filename, title, source, etc.)
        llm_config: Optional LLM configuration override

    Returns:
        EntitySemantics object with lean flat schema

    Raises:
        FileNotFoundError: If image file doesn't exist
        ValueError: If LLM response is invalid or cannot be parsed
    """
    logger.info(f"Reading image from disk: {image_path}")
    image_base64, media_type = _read_image_as_base64(image_path)
    logger.info(f"Image loaded: {len(image_base64)} chars base64, type={media_type}")

    logger.info("Loading prompt template for image semantics extraction...")
    prompt_template = PromptTemplateManager.load("image_semantics_extraction")
    example_json = _get_prompt_example_json()

    metadata_str = json.dumps(metadata, indent=2) if metadata else "No metadata provided."

    try:
        prompt = prompt_template.format(
            metadata=metadata_str,
            example_json=example_json,
        )
    except KeyError as e:
        logger.error(f"Error formatting prompt template: {e}")
        raise

    llm_client = LLMClient()
    try:
        response_text = await llm_client.complete_multimodal(
            prompt=prompt,
            image_base64=image_base64,
            media_type=media_type,
            llm_config=llm_config,
            default_temperature=0.1,
        )

        parsed_response = json.loads(response_text)
        return EntitySemantics(**parsed_response)

    except ValidationError as e:
        logger.error(f"LLM response validation error: {e.json()}")
        raise ValueError(f"Invalid LLM response format: {e}")
    except json.JSONDecodeError as e:
        logger.error(f"LLM response is not valid JSON: {response_text}")
        raise ValueError(f"LLM did not return valid JSON: {e}")
    except Exception as e:
        logger.error(f"Error during multimodal LLM call: {e}")
        raise
