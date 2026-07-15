"""
Pydantic models for chat endpoint requests and responses.
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List, Literal


class CameraInfo(BaseModel):
    """Camera pan and zoom mapping canvas to screen coords."""

    pan_x: float = Field(..., description="Camera X pan offset")
    pan_y: float = Field(..., description="Camera Y pan offset")
    zoom: float = Field(..., description="Camera zoom level")


class VisibleCanvas(BaseModel):
    """Visible canvas bounding box for a display in local canvas space."""

    min_x: float = Field(
        ..., description="Minimum visible X coordinate in canvas space"
    )
    min_y: float = Field(
        ..., description="Minimum visible Y coordinate in canvas space"
    )
    max_x: float = Field(
        ..., description="Maximum visible X coordinate in canvas space"
    )
    max_y: float = Field(
        ..., description="Maximum visible Y coordinate in canvas space"
    )
    width: float = Field(..., description="Visible canvas width")
    height: float = Field(..., description="Visible canvas height")


class DisplayInfo(BaseModel):
    """Metadata for a single display in a multi-display setup."""

    peer_id: str = Field(..., description="Unique peer ID for this display")
    tags: List[str] = Field(
        default_factory=list,
        description="Human-readable tags like 'left', 'right', 'top'",
    )
    x: float = Field(default=0, description="X offset in virtual desktop")
    y: float = Field(default=0, description="Y offset in virtual desktop")
    width: float = Field(..., description="Display width in pixels")
    height: float = Field(..., description="Display height in pixels")
    node_ids: List[str] = Field(
        default_factory=list,
        description="Entity IDs currently on this display",
    )
    camera: Optional[CameraInfo] = Field(
        default=None,
        description="Camera pan and zoom mapping canvas to screen coords",
    )
    visible_canvas: Optional[VisibleCanvas] = Field(
        default=None,
        description="Visible canvas bounding box for this display",
    )


class VirtualDesktop(BaseModel):
    """Virtual desktop spanning all displays."""

    total_width: float = Field(..., description="Total virtual desktop width")
    total_height: float = Field(..., description="Total virtual desktop height")
    displays: List[DisplayInfo] = Field(
        default_factory=list, description="List of displays"
    )


class DisplayContext(BaseModel):
    """Multi-display context sent by the client."""

    is_multi_display: bool = Field(
        default=False, description="Whether multiple displays are active"
    )
    local_peer_id: Optional[str] = Field(
        default=None, description="Peer ID of the local display"
    )
    virtual_desktop: Optional[VirtualDesktop] = Field(
        default=None, description="Virtual desktop layout information"
    )


class TimelineContextEntry(BaseModel):
    """Single entry in the frontend timeline."""

    index: int = Field(..., description="Index in the timeline")
    label: str = Field(..., description="Human-readable label")
    source: Literal["drag", "chat"] = Field(..., description="Source of the entry")
    timestamp: int = Field(..., description="Unix timestamp in milliseconds")


class TimelineContext(BaseModel):
    """Frontend timeline state sent with chat requests."""

    entries: List[TimelineContextEntry] = Field(
        default_factory=list, description="Timeline entries"
    )
    current_index: int = Field(
        default=-1, description="Currently active timeline index"
    )


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""

    query: str = Field(..., description="User's message to the layout agent")
    user_id: str = Field(
        default="demo_user", description="User identifier for session management"
    )
    session_id: str = Field(
        default="demo_session",
        description="Session identifier for conversation continuity",
    )
    layout: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional layout data to load. Required for first request in a session. "
        "Format: {nodes: [...], graph: {...}}",
    )
    entities: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Optional semantic entity data (Layer 1 output). "
        "Format: [{id: ..., name: ..., semantics: {...}}, ...]",
    )
    selected_entity_ids: Optional[List[str]] = Field(
        default=None,
        description="Optional user-selected entity IDs for grounding references like 'these' and 'them'",
    )
    display_context: Optional[DisplayContext] = Field(
        default=None,
        description="Multi-display context with display metadata, bounds, and node assignments",
    )
    timeline_context: Optional[TimelineContext] = Field(
        default=None,
        description="Frontend timeline state for history-aware operations",
    )
    entity_tags: Optional[Dict[str, List[str]]] = Field(
        default=None,
        description="Optional entity tags to use instead of session state. "
        "Format: {'entity_id': ['tag1', 'tag2'], ...}. "
        "If provided, replaces any existing tags in the session.",
    )
    user_text_highlights: Optional[Dict[str, List[str]]] = Field(
        default=None,
        description="User-initiated text highlights. "
        "Format: {'entity_id': ['highlighted text 1', ...], ...}.",
    )


class ChatAutocompleteRequest(BaseModel):
    """Request model for chat autocomplete endpoint."""

    partial_query: str = Field(
        ..., description="Partially typed user query to autocomplete"
    )
    user_id: str = Field(
        default="demo_user", description="User identifier for session management"
    )
    session_id: str = Field(
        default="demo_session",
        description="Session identifier for conversation continuity",
    )
    max_suggestions: int = Field(
        default=3, ge=1, le=5, description="Maximum number of suggestions to return"
    )
    max_context_turns: int = Field(
        default=6, ge=0, le=20, description="How many recent turns to use as context"
    )


class AutocompleteSuggestion(BaseModel):
    """Single autocomplete candidate with confidence score."""

    text: str = Field(..., description="Autocomplete suggestion text")
    score: float = Field(..., description="Confidence score between 0 and 1")


class ChatAutocompleteResponse(BaseModel):
    """Response model for chat autocomplete endpoint."""

    suggestions: List[AutocompleteSuggestion] = Field(
        default_factory=list, description="Top autocomplete suggestions"
    )
    user_id: str = Field(..., description="User identifier used in the session")
    session_id: str = Field(..., description="Session identifier used")


class ClearSessionRequest(BaseModel):
    """Optional request body for clearing a chat session."""

    user_id: Optional[str] = Field(
        default=None, description="User identifier for session management"
    )
    session_id: str = Field(
        ..., description="Session identifier for conversation continuity"
    )


class TextHighlightEntry(BaseModel):
    """A set of text snippets to highlight within a single entity."""

    entity_id: str = Field(..., description="Target entity ID")
    texts: List[str] = Field(..., description="Text snippets to highlight")
    color: Optional[str] = Field(
        default=None,
        description="Highlight color (CSS). Defaults to amber on the client.",
    )


class GroupOverlayModel(BaseModel):
    """Visual overlay for a group of entities after a grouping action."""

    label: str = Field(..., description="Group label (e.g., 'Positive Sentiment')")
    entity_ids: List[str] = Field(
        ..., description="Entity IDs belonging to this group"
    )
    bounds: Dict[str, float] = Field(
        ...,
        description="Bounding rectangle: {min_x, min_y, max_x, max_y}",
    )
    color_index: int = Field(
        ..., description="Ordinal index into the group color palette"
    )
    display_id: Optional[str] = Field(
        default=None, description="Display peer_id this overlay belongs to"
    )


class LayoutDelta(BaseModel):
    """Delta changes for efficient client updates."""

    updated_nodes: List[Dict[str, Any]] = Field(
        default_factory=list, description="Nodes with changed positions"
    )
    added_nodes: List[Dict[str, Any]] = Field(
        default_factory=list, description="Newly added nodes"
    )
    removed_nodes: List[str] = Field(
        default_factory=list, description="Removed entity IDs"
    )
    highlighted_nodes: List[str] = Field(
        default_factory=list, description="Entity IDs to temporarily highlight"
    )
    highlighted_node_colors: Dict[str, str] = Field(
        default_factory=dict,
        description="Optional per-entity glow colors for highlighted nodes (entity_id -> CSS color).",
    )
    text_highlights: List[TextHighlightEntry] = Field(
        default_factory=list,
        description="Text snippets to highlight within entity content",
    )
    clear_text_highlight_ids: List[str] = Field(
        default_factory=list,
        description="Entity IDs whose text highlights should be cleared. '__all__' clears all.",
    )
    entity_tags: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Per-entity string tags shown as chips on nodes (entity_id -> tag list).",
    )
    user_text_highlights: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="User-initiated text highlights (entity_id -> highlighted text list).",
    )
    camera_updates: Dict[str, Dict[str, float]] = Field(
        default_factory=dict,
        description="Per-display camera adjustments when arrangement overflows viewport. Maps display peer_id to {pan_x, pan_y, zoom}.",
    )
    group_overlays: List[GroupOverlayModel] = Field(
        default_factory=list,
        description="Visual group overlays with bounds and labels for grouping actions.",
    )


class LayoutAction(BaseModel):
    """Metadata about layout modification action."""

    type: Literal[
        "update_layout",
        "show_entity",
        "jump_to_timeline",
        "text_highlight",
        "clear_text_highlight",
        "tag_nodes",
        "clear_entity_tags",
    ] = Field(..., description="Type of action performed")
    description: str = Field(
        ..., description="Human-readable description of the action"
    )
    affected_entities: List[str] = Field(
        default_factory=list, description="Entity IDs that were affected"
    )
    layout_delta: Optional[LayoutDelta] = Field(
        default=None, description="Delta changes (optional)"
    )
    timeline_index: Optional[int] = Field(
        default=None, description="Target timeline index for jump_to_timeline actions"
    )


class ChatResponse(BaseModel):
    """Response model for chat endpoint."""

    response: str = Field(..., description="Agent's response to the user query")
    user_id: str = Field(..., description="User identifier used in the session")
    session_id: str = Field(..., description="Session identifier used")

    action: Optional[LayoutAction] = Field(
        default=None, description="Action performed (if layout was modified)"
    )
    layout: Optional[Dict[str, Any]] = Field(
        default=None, description="Updated layout in graph format"
    )
    thinking: Optional[List[str]] = Field(
        default=None,
        description="Agent reasoning steps from native model thinking",
    )
    layout_stages: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Group stage metadata for frontend staged animation",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Extra response metadata (e.g. tools_called list)",
    )
