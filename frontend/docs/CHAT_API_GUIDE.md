# Chat API Guide - Layout Modification Agent

**Last Updated:** 2026-01-03

## Overview

The `/api/chat` endpoint provides a conversational interface for modifying visualization layouts using natural language. This agent uses Google ADK (Agent Development Kit) to enable users to interact with layout data through chat.

### What Changed

**Previous Behavior:**
- Layout was automatically loaded from `generate_llm_layout_response.json`
- Users couldn't work with their own layouts

**New Behavior (Current):**
- ✅ **Users MUST provide layout data in their first request**
- ✅ Subsequent requests use the session state (layout optional)
- ✅ Users can reload/replace layout mid-conversation
- ✅ Full state management with session persistence

---

## Quick Start

### 1. First Request (Required: Include Layout)
```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is the current layout?",
    "layout": {
      "nodes": [
        {"entity_id": "e1", "name": "Chart 1", "x": 0.0, "y": 0.0}
      ],
      "graph": {}
    }
  }'
```

### 2. Subsequent Requests (Layout Optional)
```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "Move e1 to coordinates (5, 5)"}'
```

### 3. Test with Python
```bash
python test_chat_api.py
```

---

## API Reference

### Endpoint: `POST /api/chat`

**Request Schema:**
```typescript
{
  query: string,           // Required: User's message to the agent
  user_id?: string,        // Optional: Default "demo_user"
  session_id?: string,     // Optional: Default "demo_session"
  layout?: {               // Required for first request, optional thereafter
    nodes: Array<{
      entity_id: string,
      name: string,
      x: number,
      y: number,
      clusters?: Array<object>  // Optional: Cluster membership info
    }>,
    graph: {
      metadata?: object
    }
  },
  entities?: Array<{       // NEW: Optional Layer 1 semantic analysis
    id: string,
    name: string,
    semantics: {
      data: object,        // Data semantics (source, dimensions, temporal info)
      visual: object,      // Visual semantics (chart type, size)
      interaction: object, // Interaction semantics
      composition_type?: string,
      chart_title?: string,
      description?: string
    }
  }>,
  relationships?: {        // NEW: Optional Layer 2 relationship analysis
    edges: Array<{
      source_id: string,
      target_id: string,
      relationship_type: string,  // temporal_sequence, hierarchical_detail, etc.
      strength: string,
      confidence: number,
      reasoning: string
    }>,
    clusters: Array<{
      cluster_id: string,
      cluster_type: string,
      entity_ids: Array<string>,
      cohesion_score: number,
      domain_label?: string
    }>,
    visual_similarity: object
  }
}
```

**Response Schema:**
```typescript
{
  response: string,        // Agent's response text
  user_id: string,         // User identifier used
  session_id: string,      // Session identifier used
  
  // NEW: Layout Modification Metadata (present if layout changed)
  action?: {
    type: "update_layout" | "undo" | "redo" | "revert",
    description: string,   // Human-readable description (e.g., "Moved Chart 1")
    affected_entities: Array<string>,
    layout_delta?: {       // Optimized delta for partial updates
      updated_nodes: Array<{
        entity_id: string,
        x: number,
        y: number,
        name: string
      }>,
      added_nodes: Array<object>,
      removed_nodes: Array<string>
    }
  },
  
  // NEW: Full Layout State (present if layout changed)
  layout?: {               // Complete graph format (same as request layout)
    nodes: Array<...>,
    graph: object
  },
  
  // NEW: History State (for Undo/Redo UI)
  history?: {
    can_undo: boolean,
    can_redo: boolean,
    undo_depth: number,
    redo_depth: number,
    recent_actions: Array<string> // Last 5 actions (e.g. ["Moved Chart A", "Scaled layout"])
  }
}
```

### Client-Side Integration Guide (NEW)

The API now returns structured data to help you update your UI efficiently without parsing text.

#### 1. Handling Layout Updates
When the agent modifies the layout, the `action` and `layout` fields will be present in the response.

**Option A: Full Refresh (Easiest)**
Replace your entire local layout state with the data in `response.layout`.
```javascript
if (response.layout) {
  myVisualization.updateGraph(response.layout);
}
```

**Option B: Delta Update (Efficient)**
Use `response.action.layout_delta` to animate only changed nodes.
```javascript
if (response.action && response.action.layout_delta) {
  const delta = response.action.layout_delta;
  
  // Animate specific nodes
  delta.updated_nodes.forEach(node => {
    myVisualization.animateNodeTo(node.entity_id, node.x, node.y);
  });
  
  // Remove deleted nodes
  delta.removed_nodes.forEach(id => myVisualization.removeNode(id));
}
```

#### 2. Implementing Undo/Redo UI
Use `response.history` to enable/disable UI buttons.

```javascript
function updateUI(history) {
  undoButton.disabled = !history.can_undo;
  redoButton.disabled = !history.can_redo;
  
  // Show tooltip
  undoButton.title = `Undo ${history.recent_actions[0] || 'action'}`;
}

// Button handlers
undoButton.onclick = () => sendChat("undo");
redoButton.onclick = () => sendChat("redo");
```

---

## Layout Format

### Minimal Layout
```json
{
  "nodes": [
    {"entity_id": "e1", "name": "Chart", "x": 0.0, "y": 0.0}
  ],
  "graph": {}
}
```

### Complete Layout Example
```json
{
  "nodes": [
    {
      "entity_id": "entity-1",
      "name": "Crime Trends Overview",
      "x": 0.0,
      "y": 5.0
    },
    {
      "entity_id": "entity-2",
      "name": "Monthly Breakdown",
      "x": 15.0,
      "y": 5.0
    }
  ],
  "graph": {
    "metadata": {
      "description": "Crime analysis layout",
      "layout_strategies": {
        "surface_0": "hierarchical"
      }
    }
  }
}
```

See `agent/example_layout.json` for a complete working example.

---

## Semantic Context (NEW)

**Updated:** 2026-01-03

You can now provide semantic context (entities and relationships) to give the agent better understanding of visualizations.

### Why Use Semantic Context?

**Without semantic context:**
- Agent sees: "entity-1766260520889-b24126d4" and "entity-1766260538502-a1ac21a2"
- Agent knows: Names, positions, cluster membership

**With semantic context:**
- Agent sees: Same entity IDs
- Agent knows:
  - Both are bar charts showing Q1 2023 crime data
  - One is Baltimore, other is LA
  - They have a `comparative_parallel` relationship (should be side-by-side)
  - Both have temporal context (Q1 2023)
  - They're in a high-cohesion cluster (0.95)

### Loading Semantic Context

```python
import json

# Load layout (Layer 3 output)
with open("generate_llm_layout_response.json") as f:
    layout = json.load(f)

# Load entities (Layer 1 output)
with open("reponses/test_case_5_juxtaposition_collection_analyzed.json") as f:
    entities_data = json.load(f)
    entities = entities_data["analyzed_entities"]

# Load relationships (Layer 2 output)
with open("reponses/test_case_5_juxtaposition_collection_relationships.json") as f:
    relationships = json.load(f)

# Send to agent
response = requests.post(
    "http://127.0.0.1:8000/api/chat",
    json={
        "query": "What's the current layout?",
        "layout": layout,
        "entities": entities,           # NEW: Semantic understanding
        "relationships": relationships  # NEW: Relationship understanding
    }
)
```

### Semantic-Aware Operations

With semantic context, the agent can:

```python
# Arrange by semantic meaning
chat("Arrange these views based on their temporal sequence")
# Agent understands temporal_sequence relationships

chat("Move the comparison charts side by side")
# Agent identifies comparative_parallel relationships

chat("Group the charts by their semantic domain")
# Agent uses cluster domain_labels

chat("Explain why these views are related")
# Agent references relationship reasoning
```

### Relationship Types Understood

- `temporal_sequence`: Time-ordered progression
- `hierarchical_detail`: Parent-child drill-down
- `comparative_parallel`: Cross-dataset comparison
- `spatial_sequence`: Geographic progression
- `thematic_proximity`: Domain-based grouping
- `shared_temporal_filter`: Same time period
- `causal_flow`: Causal dependencies
- `data_transformation`: Data processing steps

### Cluster Types Understood

- `sequential`: Timeline-based groups
- `hierarchical`: Parent-child groups
- `comparative_group`: Comparison sets
- `context_group`: Supporting reference views
- `thematic_group`: Domain-based groups

### Agent Semantic Guidelines

The agent uses these guidelines when semantic context is available:

- **Temporal sequences**: Arrange left-to-right or top-to-bottom
- **Hierarchical relationships**: Use radial or vertical layouts
- **Comparative entities**: Place side-by-side for comparison
- **Spatial sequences**: Follow geographic progression
- **Thematic clusters**: Group together
- **Related entities**: Position closer based on relationship strength

---

## Usage Examples

### Example 1: Basic Conversation Flow

```bash
# Step 1: Initialize session with layout (REQUIRED)
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is the current layout?",
    "user_id": "user1",
    "session_id": "session1",
    "layout": {
      "nodes": [
        {"entity_id": "e1", "name": "Chart 1", "x": 0.0, "y": 0.0},
        {"entity_id": "e2", "name": "Chart 2", "x": 10.0, "y": 0.0}
      ],
      "graph": {}
    }
  }'

# Step 2: Modify layout (layout optional)
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Move e1 to coordinates (5, 5)",
    "user_id": "user1",
    "session_id": "session1"
  }'

# Step 3: Scale layout
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Make the layout 1.5 times larger",
    "user_id": "user1",
    "session_id": "session1"
  }'

# Step 4: Export final result
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Export the layout",
    "user_id": "user1",
    "session_id": "session1"
  }'
```

### Example 2: Reload Layout Mid-Conversation

```bash
# Initial layout
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Show me the current layout",
    "layout": {
      "nodes": [{"entity_id": "e1", "name": "Chart 1", "x": 0.0, "y": 0.0}],
      "graph": {}
    }
  }'

# Work with layout
curl -X POST http://localhost:8000/api/chat \
  -d '{"query": "Move e1 to surface_1"}'

# Load NEW layout (replaces existing)
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "query": "I have a new layout to work with",
    "layout": {
      "nodes": [
        {"entity_id": "e2", "name": "New Chart", "x": 0.0, "y": 0.0}
      ],
      "graph": {}
    }
  }'
```

### Example 3: Python Client (Basic)

```python
import requests
import json

BASE_URL = "http://localhost:8000/api/chat"

# Load layout from file
with open('my_layout.json', 'r') as f:
    layout = json.load(f)

# Initialize conversation
response = requests.post(BASE_URL, json={
    "query": "Show me the current layout",
    "user_id": "user123",
    "session_id": "sess456",
    "layout": layout  # Required for first request
})
print(response.json()['response'])

# Continue conversation (no layout needed)
response = requests.post(BASE_URL, json={
    "query": "Align all entities vertically",
    "user_id": "user123",
    "session_id": "sess456"
})
print(response.json()['response'])

# Export modified layout
response = requests.post(BASE_URL, json={
    "query": "Export the layout",
    "user_id": "user123",
    "session_id": "sess456"
})
print(response.json()['response'])
```

### Example 4: Python Client with Semantic Context (NEW)

```python
import requests
import json

BASE_URL = "http://localhost:8000/api/chat"

# Load all data
with open('generate_llm_layout_response.json') as f:
    layout = json.load(f)

with open('reponses/test_case_5_juxtaposition_collection_analyzed.json') as f:
    entities_data = json.load(f)
    entities = entities_data["analyzed_entities"]

with open('reponses/test_case_5_juxtaposition_collection_relationships.json') as f:
    relationships = json.load(f)

# Initialize conversation with full semantic context
response = requests.post(BASE_URL, json={
    "query": "What's the current layout and what do these visualizations show?",
    "user_id": "user123",
    "session_id": "sess456",
    "layout": layout,
    "entities": entities,             # Agent can see semantic details
    "relationships": relationships    # Agent understands relationships
})
print(response.json()['response'])
# Agent: "The layout has 2 entities showing Q1 2023 crime data - one from Baltimore
#         and one from LA. They have a strong comparative_parallel relationship
#         (confidence 0.95), which means they should be positioned side-by-side for
#         easy cross-city comparison..."

# Agent can now make semantic-aware suggestions
response = requests.post(BASE_URL, json={
    "query": "Arrange these optimally based on their semantic relationships",
    "user_id": "user123",
    "session_id": "sess456"
})
print(response.json()['response'])
# Agent: "Based on the comparative_parallel relationship, I recommend placing
#         Baltimore and LA charts side by side. I'll adjust their positions..."

# Export final layout
response = requests.post(BASE_URL, json={
    "query": "Export the layout",
    "user_id": "user123",
    "session_id": "sess456"
})
print(response.json()['response'])
```

---

## Migration Guide

⚠️ **Breaking Change**: This update is not backwards compatible.

### For Existing Users

**Option 1: Provide layout in every request**
```python
layout = json.load(open('my_layout.json'))
response = requests.post('/api/chat', json={
    "query": "Your query",
    "layout": layout  # Include every time
})
```

**Option 2: Provide layout only once per session (Recommended)**
```python
# First request - include layout
requests.post('/api/chat', json={
    "query": "First query",
    "layout": layout  # Required
})

# Subsequent requests - no layout needed
requests.post('/api/chat', json={
    "query": "Second query"  # Uses session state
})
```

### Error You'll See Without Migration

**Before Migration:**
```json
{
  "detail": "No active session found. Please provide 'layout' data in your first request."
}
```

**After Migration:**
```json
{
  "response": "The current layout has 5 entities...",
  "user_id": "demo_user",
  "session_id": "demo_session"
}
```

---

## Session Management

### Creating Sessions
Sessions are automatically created on the first `/api/chat` request when you provide layout data.

### Session Persistence
- Same `user_id` + `session_id` = same conversation context
- Layout modifications accumulate across requests
- State persists until session is cleared or server restarts

### Clearing Sessions
```bash
curl -X DELETE "http://localhost:8000/api/chat/session?user_id=user1&session_id=session1"
```

**Response:**
```json
{
  "status": "success",
  "message": "Session cleared for user=user1, session=session1",
  "user_id": "user1",
  "session_id": "session1"
}
```

### Multi-User Support
Use different `user_id` values for different users:
```json
{"query": "...", "user_id": "alice", "session_id": "alice_session"}
{"query": "...", "user_id": "bob", "session_id": "bob_session"}
```

### Multi-Session Support
Use different `session_id` values for parallel conversations:
```json
{"query": "...", "user_id": "alice", "session_id": "project_A"}
{"query": "...", "user_id": "alice", "session_id": "project_B"}
```

---

## Common Operations

The agent supports natural language commands for:

- **View layout**: "What's the current layout?", "Show me all entities"
- **Move entity**: "Move entity-1 to surface_1", "Put chart at coordinates (10, 5)"
- **Adjust position**: "Move entity-1 to coordinates (10, 20)"
- **Scale**: "Make the layout 1.5 times larger", "Shrink everything by 50%"
- **Swap**: "Swap entity-1 and entity-2", "Switch positions"
- **Export**: "Export the layout", "Give me the final layout"

---

## Error Handling

### HTTP 400: No Active Session
```json
{
  "detail": "No active session found. Please provide 'layout' data in your first request."
}
```
**Solution:** Include `layout` field in your first request.

### HTTP 500: Invalid Layout Format
**Cause:** Malformed layout data

**Solution:** Ensure layout has required fields:
- `nodes`: Array with `entity_id`, `name`, `x`, `y`
- `graph`: Object (can be empty)

### HTTP 500: Session Service Error
**Cause:** Internal server error

**Solution:** Check server logs, restart server if needed.

---

## Testing

### Quick Test with Python Script
```bash
python test_chat_api.py
```

**What it demonstrates:**
1. Loading layout from file
2. First request with layout initialization
3. Multi-turn conversation without layout
4. Mid-conversation layout reload
5. Session clearing

**Expected Output:**
```
============================================================
Layout Modification Agent - Test Conversation
============================================================
Loading example layout...
Loaded layout with 5 nodes

>>> User: What's the current layout?
    [Provided layout with 5 nodes]
<<< Agent: The current layout has 5 entities...
```

### Interactive Testing with API Docs
1. Start server: `uvicorn main:app --reload`
2. Open browser: `http://localhost:8000/docs`
3. Navigate to **"Agent Chat"** section
4. Try the `/api/chat` endpoint with sample layout

### Manual Testing with curl
```bash
# Test with example layout
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is the current layout?",
    "layout": {
      "nodes": [{"entity_id": "e1", "name": "Chart 1", "x": 0.0, "y": 0.0}],
      "graph": {}
    }
  }'
```

---

## Implementation Details

### Files Modified

**Latest Update: 2026-01-03** - Added semantic context support

1. **`api/models/chat.py`**
   - Added `layout` field to `ChatRequest` model (optional `Dict[str, Any]`)
   - **NEW**: Added `entities` field for Layer 1 semantic analysis (optional `List[Dict[str, Any]]`)
   - **NEW**: Added `relationships` field for Layer 2 relationship analysis (optional `Dict[str, Any]`)

2. **`agent/agent.py`**
   - `initialize_session()` accepts optional `layout_data` parameter
   - **NEW**: Accepts optional `entities` and `relationships` parameters
   - **NEW**: Stores semantic context in session state
   - **NEW**: Enhanced agent instruction with semantic guidelines
   - Falls back to default JSON if no layout provided
   - Cross-platform file path handling

3. **`api/endpoints/chat.py`**
   - Processes user-provided layout with `load_layout_from_output()`
   - **NEW**: Passes `entities` and `relationships` to session initialization
   - **NEW**: Updates semantic context when reloading layout mid-conversation
   - Creates or updates session with provided layout
   - Returns HTTP 400 if no session and no layout
   - Enhanced error handling and logging

4. **`agent/tools.py`**
   - **NEW**: `tool_get_current_layout` returns semantic context if available
   - **NEW**: Includes `entities_count`, `relationships_count`, `clusters_count`

5. **`agent/layout_operations.py`**
   - **NEW**: Preserves `clusters` field during load and export
   - **NEW**: Stores and exports `entity_clusters` mapping

6. **`test_chat_api.py`**
   - `load_example_layout()` function
   - **NEW**: `load_semantic_context()` function for loading entities/relationships
   - `chat()` function accepts optional `layout` parameter
   - **NEW**: `chat()` accepts optional `entities` and `relationships` parameters
   - Demonstrates first request with layout and subsequent requests
   - **NEW**: Demonstrates loading and using semantic context

### Files Created

- `agent/example_layout.json` - Example layout format
- `CODE_REVIEW_COMPLIANCE.md` - Code quality review
- `CHAT_API_GUIDE.md` - This comprehensive guide

---

## Troubleshooting

**Q: My session state was lost**
- **A:** Server restart clears in-memory sessions (InMemorySessionService)
- **Solution:** Provide layout data again to reinitialize

**Q: Agent doesn't recognize entity names**
- **A:** Use entity IDs (e.g., "entity-1") instead of names
- **Try:** "Show me the current layout" to see all entity IDs

**Q: Layout not updating**
- **A:** Ensure you're using the same `user_id` + `session_id`
- **Verify:** Check response shows correct `session_id`

**Q: How do I start over?**
- **Option 1:** Clear session with `DELETE /api/chat/session`
- **Option 2:** Use a new `session_id`

---

## Documentation

- **Complete Guide:** `agent/README.md` - Detailed agent documentation
- **Example Layout:** `agent/example_layout.json` - Working example
- **Test Script:** `test_chat_api.py` - Interactive examples
- **API Docs:** `http://localhost:8000/docs` - Interactive API documentation
- **Code Review:** `CODE_REVIEW_COMPLIANCE.md` - Code quality compliance

---

## Quick Reference

| Action | Command |
|--------|---------|
| Start server | `uvicorn main:app --reload` |
| Run tests | `python test_chat_api.py` |
| View API docs | `http://localhost:8000/docs` |
| Clear session | `DELETE /api/chat/session?user_id=...&session_id=...` |
| Example layout | `agent/example_layout.json` |

### Semantic Context Files

| File | Description |
|------|-------------|
| `generate_llm_layout_response.json` | Layout graph (Layer 3 output) |
| `reponses/test_case_5_juxtaposition_collection_analyzed.json` | Entities (Layer 1 output) |
| `reponses/test_case_5_juxtaposition_collection_relationships.json` | Relationships (Layer 2 output) |
| `visualize_from_cache_response.json` | Alternative layout with full metadata |

---

## When to Use Semantic Context

### ✅ Use Semantic Context When:

1. **Making semantic-aware layout decisions**
   - Arranging by temporal order
   - Grouping by thematic domain
   - Positioning for comparison

2. **Need agent to explain relationships**
   - "Why are these charts related?"
   - "What's the narrative structure here?"

3. **Want intelligent suggestions**
   - "How should I arrange these optimally?"
   - "Which charts should be side-by-side?"

4. **Working with complex multi-view dashboards**
   - Multiple related visualizations
   - Clear semantic structure (temporal, hierarchical, comparative)

### ❌ Skip Semantic Context When:

1. **Simple positioning tasks**
   - "Move entity X to (10, 20)"
   - "Make the layout 2x larger"

2. **No semantic relationships**
   - Unrelated standalone charts
   - No narrative structure

3. **Performance-critical applications**
   - Semantic data adds to request/session size
   - May not be worth the overhead for simple tasks

---

## Support

For issues or questions:
1. Check this guide
2. Review `agent/README.md`
3. Run `python test_chat_api.py` for working examples
4. Check server logs for error details
5. For semantic context issues, see `RESPONSE_FORMAT_UNIFIED.md`
