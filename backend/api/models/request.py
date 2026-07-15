from typing import Literal, Optional, Dict, Any, Union
from pydantic import BaseModel, Field


class LLM_Config(BaseModel):
    temperature: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Temperature for sampling."
    )


class SingleSpecRequest(BaseModel):
    """
    Request for extracting semantics from a SINGLE entity (visual chart, text document, or image).

    The 'type' field explicitly declares the entity type:
    - "visual": Vega-Lite chart specification (content is JSON dict)
    - "text": Text document (content is string)
    - "image": Image file path relative to STATIC_DIR (content is string, e.g. "movie_dataset/posters/the_godfather.jpg")
    """

    type: Literal["visual", "text", "image"] = Field(
        ...,
        description="Entity type: 'visual' for Vega-Lite charts, 'text' for text documents, 'image' for image files",
    )

    content: Union[Dict[str, Any], str] = Field(
        ...,
        description="Entity content - JSON object for visual charts, string for text/image",
    )

    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Optional metadata for text/image entities (filename, source, etc.)",
    )

    llm_config: Optional[LLM_Config] = Field(
        None, description="LLM configuration parameters"
    )

    def model_post_init(self, __context):
        """Validate that type matches content structure."""
        if self.type == "visual":
            if not isinstance(self.content, dict):
                raise ValueError(
                    "type='visual' requires 'content' to be a JSON object (dict)"
                )
            if self.metadata is not None:
                raise ValueError(
                    "type='visual' cannot have 'metadata' field (only for text/image)"
                )

        elif self.type == "text":
            if not isinstance(self.content, str):
                raise ValueError("type='text' requires 'content' to be a string")

        elif self.type == "image":
            if not isinstance(self.content, str):
                raise ValueError(
                    "type='image' requires 'content' to be a string (file path relative to STATIC_DIR)"
                )

    @property
    def spec(self) -> Optional[Dict[str, Any]]:
        """Convenience property for accessing visual chart spec."""
        return (
            self.content
            if self.type == "visual" and isinstance(self.content, dict)
            else None
        )

    @property
    def text_content(self) -> Optional[str]:
        """Convenience property for accessing text document content."""
        return (
            self.content
            if self.type == "text" and isinstance(self.content, str)
            else None
        )

    @property
    def image_path(self) -> Optional[str]:
        """Convenience property for accessing image file path."""
        return (
            self.content
            if self.type == "image" and isinstance(self.content, str)
            else None
        )
