# System Summary

## 1. Overall Goal

The agent functions as an interactive AI Layout Architect for a multi-display virtual desktop. It allows users to rearrange, scale, group, and navigate complex data visualization layouts (entities/nodes) using natural language. The agent operates on a spatial canvas with flow coordinates (stable, canvas-world) distinct from screen coordinates (pixel-space), and supports multi-display topologies.

## 2. Understanding of Nodes, Views, and Semantics

- **Semantic Context:** The agent understands what each entity represents (data sources, chart types, temporal context, granularity) and how entities relate (temporal_sequence, hierarchical_detail, comparative_parallel).
- **Multi-Display Awareness:** Recognizes a displays list where each display has a `peer_id`, human-readable tags (e.g., "left", "right"), and pixel bounds. Entities are assigned to displays via `display_id`.
- **Coordinate Systems:** Distinguishes flow coordinates (canvas-world, used for node placement) from screen coordinates (viewport pixels) and virtual desktop topology offsets. Viewport transform: `screen_x = flow_x * zoom + viewport.x`.
- **Conversational Naming:** Maps internal entity IDs to human-readable names for user interaction.

## 3. Tools

All tools are defined in `agent/tool_ops/` and re-exported via `agent/tools.py`. Each tool is wrapped with `@tool_safe()` for exception handling and state validation. **20 tools** are registered with the agent.

### Inspection

| Tool | Parameters | Description |
|------|-----------|-------------|
| `tool_get_entity_semantics` | *(none)* | Return entity semantic content (item_type, domain, key_themes, clusters) not in injected layout state |
| `tool_validate_layout` | *(none)* | Check layout quality: overlaps, overflow, spacing, split clusters, uneven display load (read-only) |

### Entity Movement & Positioning

| Tool | Parameters | Description |
|------|-----------|-------------|
| `tool_move_entity` | `entity_id`, `target_surface?`, `x?`, `y?`, `reference_entity_id?`, `region?`, `preview_only?` | Move entity via explicit coords, reference entity, or region anchor |
| `tool_arrange_relative` | `target_entity_id`, `reference_entity_id`, `direction`, `offset?` | Position entity relative to reference (above/below/left/right) |
| `tool_swap` | `entity_id_1`, `entity_id_2` | Swap positions of two entities |
| `tool_snap_edges` | `entity_ids`, `axis?` | Align entities to reference entity on x/y/both axes |

### Arrangement & Scaling

| Tool | Parameters | Description |
|------|-----------|-------------|
| `tool_arrange_entities` | `entity_ids`, `display_name?`, `arrangement?`, `align?`, `region?`, `preserve_order?` | Arrange entities in grid/horizontal/vertical pattern with optional region targeting |
| `tool_scale` | `scale_factor` | Scale entire layout by multiplier |
| `tool_resize_entities` | `entity_ids`, `width`, `height` | Batch-resize multiple entities |
| `tool_maximize_to_display` | `entity_id`, `display_id?` | Scale and position entity to fill entire display |

### Layout Planning (Graph-Based)

| Tool | Parameters | Description |
|------|-----------|-------------|
| `tool_plan_layout` | `strategy`, `arrangement?`, `dry_run?` | Auto-analyze semantics and compute optimized placement using strategies: group_by_domain, group_by_structure, group_by_granularity, cluster_separate, declutter |
| `tool_plan_semantic_layout` | `groups`, `edges`, `layout_style?`, `group_spacing?`, `arrangement?`, `display_name?`, `dry_run?`, `constraints?` | Graph-based layout: arrange groups with spatial proximity encoding semantic relatedness. Uses NetworkX (force-directed/hierarchical) + kiwisolver for overlap resolution. Per-group overrides for arrangement, region anchoring, spacing, preserve_order. Inter-group alignment constraints. |

### UI Actions (Transient - Not Tracked in History)

| Tool | Parameters | Description |
|------|-----------|-------------|
| `tool_show_entity` | `entity_ids`, `color?` | Highlight entities and pan camera to frame them |
| `tool_highlight_text` | `entity_id`, `text_snippets`, `color?` | Highlight specific text spans within entity content |
| `tool_clear_text_highlights` | `entity_ids?` | Remove text-span highlights |
| `tool_add_entity_tags_bulk` | `entity_ids`, `tags` | Add string tags to multiple entities |
| `tool_remove_entity_tags_bulk` | `entity_ids`, `tags` | Remove specific tags from multiple entities |
| `tool_clear_entity_tags` | `entity_ids?` | Remove all tags from entities |
| `tool_camera` | `display_name`, `action`, `amount?`, `direction?`, `entity_ids?`, `region?` | Viewport control: zoom, pan, fit_entities, fit_all, focus_region |
| `tool_jump_to_timeline` | `index?`, `label_query?` | Navigate interaction timeline; list entries if no args |

## 4. Agent Configuration

- **Framework:** Google ADK (`google.adk.agents.llm_agent.Agent`)
- **Model:** Configurable via `AGENT_LLM_MODEL` env var (default: `gemini-3-flash-preview`)
- **Temperature:** Configurable via `AGENT_TEMPERATURE` (default: 0.3)
- **Thinking:** Enabled via `ThinkingConfig(include_thoughts=True)`
- **Before-Model Callback:** `inject_layout_context` — injects compact spatial context before every LLM call
- **Context Cache:** 10-interval cache, TTL 1800s, min 4000 tokens
- **System Prompt:** `prompts/layout_agent_instruction.txt` (~24KB)

## 5. Interaction Flow

The agent operates under "Action First, Explain Later":

1. **Context Injection:** Before each LLM call, `inject_layout_context` callback injects a compact spatial summary including per-display entity positions, viewport analysis (density, capacity, visibility), arrangement patterns, tags, and highlighted text.
2. **Tool Execution:** The agent calls the appropriate tool(s) to mutate layout state.
3. **Validation:** After multi-entity operations, the agent calls `tool_validate_layout` and auto-fixes critical issues.
4. **Explain:** The agent responds explaining the spatial operations performed.

### Session Lifecycle

1. **Chat endpoint** (`POST /chat`) receives user query with optional layout, entities, display_context, entity_tags, timeline_context, and selected_entity_ids.
2. **Session management** creates or retrieves session, carrying forward display_context, entity_tags, and text highlights across requests.
3. **State delta** is built with current_layout, entities, display_context, and context_summary, then passed to the agent runner.
4. **Agent streams** tool calls and response text back via SSE.

## 6. Graph-Based Layout Engine

The `tool_plan_semantic_layout` tool leverages a graph-based layout engine (`agent/layout_ops/graph_layout.py`):

1. **Group Sizing:** Estimates width/height needed for each group's entities using grid-based estimation with actual node dimensions.
2. **Graph Construction:** Builds a NetworkX graph from groups (nodes) and weighted edges.
3. **Initial Positioning:** Computes group centers using layout algorithms:
   - `organic`: `nx.spring_layout` (force-directed)
   - `packed`: `nx.spring_layout` with tighter k
   - `hierarchical`: `nx.multipartite_layout` with degree centrality
4. **Weight Scaling:** Adjusts inter-group distances so higher edge weight = closer proximity (iterative pairwise adjustment).
5. **Overlap Resolution:** Uses kiwisolver constraints to remove overlaps while preserving relative positions, supporting anchored groups and alignment constraints.
6. **Intra-Group Arrangement:** Arranges entities within each group region using grid/horizontal/vertical patterns.

**Key Dependencies:** NetworkX, kiwisolver, rectpack

## 7. Layout Context Injection

The `inject_layout_context` callback (`agent/callbacks.py`) builds a compact spatial-awareness summary injected into LLM instructions:

- **Per-display:** Name, entity count, screen dims, workspace bounds, zoom, camera state
- **Viewport analysis:** In-view vs. off-screen counts, screen-space readability (readable >= 350px, scannable >= 200px), density label, capacity estimate, zoom-to-fit impact, free space margins
- **Arrangement detection:** Grid/horizontal/vertical pattern with extent and overflow warnings
- **Per-entity:** Sentiment, tags, position (x,y), dimensions, visibility status
- **Layout change tracking:** MD5 fingerprint of positions, assignments, and tags
