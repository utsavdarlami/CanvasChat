# Backend API Endpoints

This document details the API endpoints available in the backend (`main.py`) and expected by the frontend (`static/*.js`).

## System Endpoints

### `GET /health`
Basic health check to verify the server is running.
- **Response**: `{"status": "ok"}`

### `POST /analyze/`
Generic file upload endpoint.
- **Input**: `multipart/form-data`
  - `files`: List of files (currently processes the first file).
- **Response**: JSON content of the first uploaded file.
- **Used by**: `static/upload.js` (legacy/testing flow)

## Visualization Endpoints

### `POST /api/distribution/visualize-from-cache`
Generates a graph distribution from cached semantic analysis files using heuristic algorithms.
- **Input**: `multipart/form-data`
  - `entities_file`: JSON file containing analyzed entities (Layer 1 output).
  - `relationships_file`: JSON file containing relationship analysis (Layer 2 output).
  - `num_surfaces` (query param, optional): Number of surfaces (default: 1).
- **Response**: NetworkX node-link format JSON.
  ```json
  {
    "directed": true,
    "multigraph": false,
    "graph": {},
    "nodes": [ ... ]
  }
  ```
- **Used by**: `static/upload.js`

### `POST /api/generate-llm-layout`
Generates a spatial layout using an LLM based on pre-computed semantics and relationships.
- **Input**: `application/json`
  ```json
  {
    "analyzed_entities": [ ... ],       // Layer 1 output
    "relational_semantics": { ... },    // Layer 2 output
    "llm_config": {
      "temperature": 0.0
    }
  }
  ```
- **Response**: NetworkX node-link format JSON (same as `visualize-from-cache`).
  - Metadata includes `"approach": "layer_3_llm_only"`.
- **Used by**: `static/upload.js`

## Chat Agent Endpoints

### `POST /api/chat`
Conversational interface for modifying visualization layouts.
- **Input**: `application/json`
  ```json
  {
    "query": "Move entity-1 to the right",
    "user_id": "user1",
    "session_id": "session1",
    "layout": { ... },         // Required for first request
    "entities": [ ... ],       // Optional: Semantic context
    "relationships": { ... }   // Optional: Relationship context
  }
  ```
- **Response**:
  ```json
  {
    "response": "I've moved entity-1...",
    "user_id": "user1",
    "session_id": "session1",
    "action": {
      "type": "update_layout",
      "description": "Moved entity-1",
      "layout_delta": { ... }
    },
    "layout": { ... },        // Complete new layout
    "history": { ... }
  }
  ```
- **Used by**: `static/chat.js`

### `DELETE /api/chat/session`
Clears the chat session state.
- **Input**: Query parameters
  - `user_id`: ID of the user.
  - `session_id`: ID of the session to clear.
- **Response**:
  ```json
  {
    "status": "success",
    "message": "Session cleared...",
    "user_id": "user1",
    "session_id": "session1"
  }
  ```
- **Used by**: `static/chat.js` (via `clearChatMessages` or manual call)
