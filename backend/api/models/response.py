from typing import List, Optional
from pydantic import BaseModel, Field


class EntitySemantics(BaseModel):
    """
    Lean semantic extraction for all entity types.

    Flat structure optimized for downstream layout agent consumption.
    No nested objects — every field is directly accessible.
    """

    title: Optional[str] = Field(None, description="Entity title")

    item_type: str = Field(
        ...,
        description="Entity type: 'bar_chart', 'line_chart', 'scatter_plot', 'review', 'intelligence_report', 'memo', etc.",
    )
    granularity: Optional[str] = Field(
        None,
        description="Aggregation level: 'overview', 'summary', 'regional', 'detailed', 'comprehensive'",
    )

    sentiment: Optional[str] = Field(
        None, description="Tone: 'positive', 'negative', 'neutral', 'mixed'"
    )

    key_themes: List[str] = Field(
        default_factory=list,
        description="3-8 key terms for thematic clustering",
    )
    domain: Optional[str] = Field(
        None,
        description="Subject area: 'crime', 'sales', 'intelligence', 'health', etc.",
    )
    location: Optional[str] = Field(
        None,
        description="Primary geographic focus: 'Baltimore', 'Los Angeles', 'Afghanistan'",
    )

    temporal_focus: Optional[str] = Field(
        None,
        description="Time period as simple string: '2023', 'Q1 2023', 'Jan - Mar 2023', '1990 - 1992'",
    )

    summary: Optional[str] = Field(
        None, description="1-2 sentence summary (null if text < 40 words)"
    )

    encoded_metrics: List[str] = Field(
        default_factory=list,
        description="Human-readable encoded field names for charts: ['Sales', 'Time']",
    )
