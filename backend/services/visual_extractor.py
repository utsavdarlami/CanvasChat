import json
from typing import Dict, Any, Optional
from pydantic import ValidationError
import pandas as pd

from core.logger import logger
from core.llm_client import LLMClient, PromptTemplateManager
from api.models.response import EntitySemantics
from api.models.request import LLM_Config


def _get_data_summary(spec: Dict[str, Any]) -> Optional[str]:
    """
    If spec has a data URL, fetches the data and returns an enhanced summary.
    Returns None if data is inline or URL is invalid.
    """
    if "data" in spec and "url" in spec["data"]:
        url = spec["data"]["url"]
        try:
            logger.info(f"Fetching data for grounding from URL: {url}")
            if url.endswith(".json"):
                df = pd.read_json(url)
            else:
                df = pd.read_csv(url)

            summary = f"""Dataset Summary:
- Total Rows: {len(df)}
- Columns: {list(df.columns)}
- Column Types: {df.dtypes.to_dict().__repr__()}
- Cardinalities: {df.nunique().to_dict().__repr__()}
- Sample Values (first 3 rows):
{df.head(3).to_string()}"""
            return summary
        except Exception as e:
            logger.warning(f"Could not fetch or parse data from URL {url}: {e}")
            return "Data from URL could not be fetched or parsed."
    return None


def _get_prompt_example_json() -> str:
    """Returns example JSON structure for visual semantics extraction."""
    example = {
        "title": "Monthly Sales Trend",
        "item_type": "line_chart",
        "granularity": "regional",
        "sentiment": None,
        "key_themes": ["sales", "trend", "monthly", "revenue"],
        "domain": "sales",
        "location": "United States",
        "temporal_focus": "Jan - Mar 2023",
        "summary": "Line chart showing monthly sales trends over a three-month period.",
        "encoded_metrics": ["Sales", "Month"],
    }
    return json.dumps(example, indent=2)


async def extract_semantics(
    spec: Dict[str, Any], llm_config: Optional[LLM_Config] = None
) -> EntitySemantics:
    """
    Uses an LLM to extract semantic information from a Vega-Lite specification.
    """
    logger.info("Loading prompt template for visual semantics extraction...")
    prompt_template = PromptTemplateManager.load("visual_semantics_extraction")
    data_summary = _get_data_summary(spec)
    example_json = _get_prompt_example_json()

    try:
        prompt = prompt_template.format(
            spec_json=json.dumps(spec, indent=2),
            data_summary=data_summary
            if data_summary
            else "Data is embedded directly in the specification or not applicable.",
            example_json=example_json,
        )
    except KeyError as e:
        logger.error(f"Error formatting prompt template: {e}")
        raise

    llm_client = LLMClient()
    response_text = ""
    try:
        response_text = await llm_client.complete(
            prompt, llm_config, default_temperature=0.1
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
        logger.error(f"Error during LLM call: {e}")
        raise
