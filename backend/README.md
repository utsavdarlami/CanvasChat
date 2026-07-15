# Semantic API Lite

A stripped-down version of `semantic-api` that retains only two features:

1. **Semantic Extraction** — Extract observable facts from a single entity (Vega-Lite chart or text document)
2. **Chat Agent** — Conversational layout modification agent powered by Google ADK

Everything else from the full project (Layer 2 relationship analysis, Layer 3 spatial distribution, Socket.IO collaboration, investigative layouts, narrative ranking) has been removed.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

## Setup

```bash
# Create virtual environment
uv venv
source .venv/bin/activate

# Install dependencies
uv pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and set your LLM_API_KEY
```

### Environment Variables

| Variable | Description | Default |
|---|---|---|
| `LLM_MODEL` | Model name as recognized by litellm (e.g. `gemini/gemini-pro`, `gpt-4`) | `gemini/gemini-pro` |
| `AGENT_LLM_MODEL` | Model used by the ADK layout chat agent (`/api/chat`, `/api/chat/stream`) | `gemini-3-flash-preview` |
| `LLM_API_KEY` | API key for the selected model's provider | *(required)* |
| `LLM_TEMPERATURE` | Temperature for semantic extraction (0.0–1.0) | `0.1` |
| `AUTOCOMPLETE_MODEL` | Fast model for `POST /api/chat/autocomplete` | `gemini/gemini-2.0-flash` |
| `AUTOCOMPLETE_TEMPERATURE` | Temperature for autocomplete suggestions | `0.2` |
| `AUTOCOMPLETE_TIMEOUT_SECONDS` | Timeout (seconds) for autocomplete model calls | `3` |

## Running the Server

```bash
source .venv/bin/activate
uvicorn main:app --reload
```

The server starts at `http://127.0.0.1:8000`. Interactive API docs are available at `/docs`.

## API Endpoints

### `POST /api/extract-semantics`

Extracts semantic information from a single entity.

**Visual entity (Vega-Lite chart):**

```json
{
  "type": "visual",
  "content": {
    "$schema": "https://vega-lite.github.io/schema/vega-lite/v5.json",
    "mark": "bar",
    "data": { "url": "data/cars.json" },
    "encoding": {
      "x": { "field": "Origin", "type": "nominal" },
      "y": { "aggregate": "count", "type": "quantitative" }
    }
  }
}
```

**Text entity:**

```json
{
  "type": "text",
  "content": "The quarterly sales report shows a 15% increase in revenue...",
  "metadata": {
    "filename": "Q3_report.txt",
    "source": "internal"
  }
}
```

Returns `EntitySemantics`, `VisualSemantics`, or `TextSemantics` depending on the entity type.

### `POST /api/chat`

Send a message to the layout modification agent. Supports multi-turn conversation with session state.

```json
{
  "user_id": "demo_user",
  "session_id": "demo_session",
  "query": "Move the bar chart to the left",
  "layout": { "nodes": [...] }
}
```

The `layout` field is required on the first request to initialize the session. Subsequent requests in the same session can omit it.

### `POST /api/chat/autocomplete`

Returns fast query suggestions using the same session context (`user_id`, `session_id`) without running tools or mutating layout state.

```json
{
  "user_id": "demo_user",
  "session_id": "demo_session",
  "partial_query": "move related",
  "max_suggestions": 3,
  "max_context_turns": 6
}
```

Response includes top suggestions with confidence scores:

```json
{
  "suggestions": [
    { "text": "move related views to the left display", "score": 0.91 },
    { "text": "move related views to the right display", "score": 0.84 },
    { "text": "move related views and summarize what changed", "score": 0.77 }
  ],
  "user_id": "demo_user",
  "session_id": "demo_session"
}
```

### `DELETE /api/chat/session`

Clear a chat session. Query parameters: `user_id`, `session_id`.

### Frontend Integration Doc

See `docs/frontend_chat_autocomplete.md` for client integration guidance, including debounce/cancellation patterns and TypeScript examples.

## Project Structure

```
semantic-api-lite/
├── main.py                  # FastAPI application entry point
├── requirements.txt
├── .env.example
├── api/
│   ├── endpoints/
│   │   ├── analysis.py      # /extract-semantics endpoint
│   │   ├── chat.py          # /chat and /chat/autocomplete endpoints
│   │   └── chat_logic/      # Chat endpoint orchestration helpers
│   └── models/
│       ├── request.py       # SingleSpecRequest, LLM_Config
│       ├── response.py      # EntitySemantics and related models
│       └── chat.py          # Chat request/response models
├── agent/                   # Chat agent (Google ADK)
│   ├── agent.py             # Agent configuration and initialization
│   ├── tools.py             # Agent tool definitions
│   ├── layout_operations.py # Layout manipulation utilities
│   ├── action_detector.py   # Detects what action the agent performed
│   ├── layout_delta.py      # Computes layout diffs
│   └── history.py           # Undo/redo history tracking
├── core/
│   ├── config.py            # Environment variable loading
│   ├── autocomplete_client.py # Fast autocomplete LLM client
│   ├── llm_client.py        # Shared LLM client (litellm wrapper)
│   └── logger.py            # Logging configuration (loguru)
├── services/
│   ├── extractor_factory.py # Routes extraction to visual or text extractor
│   ├── visual_extractor.py  # Vega-Lite chart semantic extraction
│   └── text_extractor.py    # Text document semantic extraction
├── prompts/                 # LLM prompt templates
│   ├── visual_semantics_extraction.txt
│   ├── text_semantics_extraction.txt
│   └── layout_agent_instruction.txt
└── tests/
    ├── test_unified_extraction.py
    ├── test_text_extractor.py
    ├── test_chat_api.py
    ├── test_chat_actions.py
    └── test_chat_autocomplete_*.py
```

## Testing

Tests are run as standalone scripts:

```bash
source .venv/bin/activate

# Test semantic extraction
python tests/test_unified_extraction.py
python tests/test_text_extractor.py

# Test chat agent
python tests/test_chat_api.py
python tests/test_chat_actions.py

# Test autocomplete helpers and endpoint behavior
python tests/test_chat_autocomplete_models.py
python tests/test_chat_autocomplete_logic.py
python tests/test_chat_autocomplete_api.py
```

## Dependencies

| Package | Purpose |
|---|---|
| `fastapi` | Web framework |
| `uvicorn` | ASGI server |
| `pydantic` | Data validation and serialization |
| `litellm` | Unified LLM API client |
| `python-dotenv` | Environment variable loading |
| `loguru` | Logging |
| `requests` | HTTP client |
| `pandas` | Data processing |

The chat agent additionally requires `google-adk` and `google-genai` (install via `uv pip install google-adk google-genai`).
