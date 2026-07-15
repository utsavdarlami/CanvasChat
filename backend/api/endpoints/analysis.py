from fastapi import APIRouter, HTTPException
from api.models.request import SingleSpecRequest
from api.models.response import EntitySemantics
from services.extractor_factory import extract_entity_semantics, get_entity_display_name
from core.logger import logger

router: APIRouter = APIRouter()


@router.post(
    "/extract-semantics",
    response_model=EntitySemantics,
    tags=["Analysis"],
)
async def extract_single_semantics(request: SingleSpecRequest):
    """
    Extracts comprehensive semantics for a single entity (visual chart OR text document).

    Supports two entity types:
    - Visual Charts: Provide type='visual' and 'spec' field with Vega-Lite JSON
    - Text Documents: Provide type='text' and 'text_content' field with raw text

    Returns:
        EntitySemantics: Extracted semantics for the entity
    """
    try:
        entity_name = get_entity_display_name(request)
        logger.info(f"Extracting semantics for {request.type} entity: {entity_name}")

        llm_config_log = "with default LLM configurations"
        if request.llm_config:
            llm_config_log = f"with custom LLM configurations: temperature={request.llm_config.temperature}"
        logger.info(llm_config_log)

        semantics = await extract_entity_semantics(request)
        return semantics

    except ValueError as e:
        logger.warning(
            f"Validation or input error for {request.type} entity extraction: {e}"
        )
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error during {request.type} entity extraction: {e}")
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred during semantic extraction.",
        )
