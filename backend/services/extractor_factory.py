"""
Extractor Factory: Routes extraction requests to appropriate service based on entity type.

This module implements the Factory pattern to decouple the endpoint logic from
specific extractor implementations. It provides a clean, extensible interface for
adding new entity types in the future.
"""

from api.models.request import SingleSpecRequest
from api.models.response import EntitySemantics
from services.visual_extractor import extract_semantics
from services.text_extractor import extract_text_semantics
from services.image_extractor import extract_image_semantics
from core.logger import logger


async def extract_entity_semantics(request: SingleSpecRequest) -> EntitySemantics:
    """
    Factory function: Routes extraction to appropriate service based on entity type.

    Args:
        request: SingleSpecRequest with validated type and content

    Returns:
        EntitySemantics: Extracted semantics for the entity

    Raises:
        ValueError: If entity type is unsupported (should not happen with Pydantic validation)
    """

    if request.type == "visual":
        assert isinstance(request.content, dict), (
            "content must be dict for visual entities"
        )
        spec = request.content
        logger.info(
            f"Routing to visual chart extractor: {spec.get('title', 'Untitled')}"
        )
        return await extract_semantics(spec, request.llm_config)

    elif request.type == "text":
        assert isinstance(request.content, str), "content must be str for text entities"
        text_content = request.content
        text_preview = (
            text_content[:50] + "..." if len(text_content) > 50 else text_content
        )
        logger.info(
            f"Routing to text document extractor ({len(text_content)} chars): {text_preview}"
        )
        return await extract_text_semantics(
            text_content=text_content,
            metadata=request.metadata,
            llm_config=request.llm_config,
        )

    elif request.type == "image":
        assert isinstance(request.content, str), "content must be str for image entities"
        image_path = request.content
        logger.info(f"Routing to image extractor: {image_path}")
        return await extract_image_semantics(
            image_path=image_path,
            metadata=request.metadata,
            llm_config=request.llm_config,
        )

    else:
        # Keep a defensive guard in case validation constraints change.
        raise ValueError(f"Unsupported entity type: {request.type}")


def get_entity_display_name(request: SingleSpecRequest) -> str:
    """
    Returns a human-readable name for the entity (useful for logging).

    Args:
        request: SingleSpecRequest with entity content

    Returns:
        str: Human-readable display name
    """
    if request.type == "visual":
        assert isinstance(request.content, dict), (
            "content must be dict for visual entities"
        )
        spec = request.content
        return spec.get("title", "Untitled Chart")
    elif request.type == "text":
        assert isinstance(request.content, str), "content must be str for text entities"
        text_content = request.content
        text_preview = (
            text_content[:50] + "..." if len(text_content) > 50 else text_content
        )
        return f"Text ({len(text_content)} chars): {text_preview}"
    elif request.type == "image":
        assert isinstance(request.content, str), "content must be str for image entities"
        return f"Image: {request.content}"
    else:
        return "Unknown Entity"
