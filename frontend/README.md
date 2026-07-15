# LLM Distribution UI

Interactive visualization framework for semantic relationship graphs with support for entity-only and full graph visualizations.

## Features

- **Entities-Only Mode**: Upload and visualize entities without relationships (NEW!)
  - Frontend-only processing (no backend required)
  - Automatic grid layout distribution
  - Support for text content and Vega-Lite charts
  
- **Full Graph Mode**: Upload entities + relationships for complete graph visualization
  - Backend-powered relationship analysis
  - LLM-based layout generation (optional)
  - Interactive force-directed graphs

- **Dual Visualization Modes**:
  - Entity View: React Flow-based interactive node-link diagram
  - Graph View: D3.js force simulation with partition overlays

- **Rich Content Support**:
  - Text entities
  - Interactive Vega-Lite charts
  - Custom metadata and semantics

## Quick Start

### Entities-Only Upload

1. Create a JSON file with entities (all fields required):
```json
{
  "analyzed_entities": [
    {
      "id": "entity-1",
      "name": "My Entity",
      "type": "text",
      "value": "Content here"
    }
  ]
}
```

**Required fields**: `id`, `name` (or `display_name`), `type`, `value`

2. Upload via the UI:
   - Select your entities JSON file
   - Leave relationships file empty
   - Click "Load Entities"

See [`ENTITIES_JSON_QUICK_REFERENCE.md`](ENTITIES_JSON_QUICK_REFERENCE.md) for examples.

### Full Graph Upload

Upload both entities and relationships files to enable:
- Relationship visualization
- Backend graph analysis
- LLM-based layout (optional)

## Documentation

- **[Entities-Only Upload Guide](docs/ENTITIES_ONLY_UPLOAD.md)** - Complete guide for entities-only mode
- **[Quick Reference](ENTITIES_JSON_QUICK_REFERENCE.md)** - JSON structure examples
- **[Implementation Summary](ENTITIES_ONLY_IMPLEMENTATION_SUMMARY.md)** - Technical details
- **[API Endpoints](docs/API_ENDPOINTS.md)** - Backend API documentation
- **[Project Info](docs/project_info.md)** - Architecture overview

## Sample Files

Sample entities files are provided in `data/`:
- `minimal_entities_example.json` - Simplest structure
- `sample_entities_only.json` - Full featured examples with charts

## Development

### Setup
```bash
npm install
npm run dev
```

### Build
```bash
npm run build
```

## Architecture

- **Frontend**: React 18 + TypeScript + Vite
- **Visualization**: @xyflow/react (React Flow) + D3.js
- **State Management**: Zustand
- **Charts**: Vega-Lite (via react-vega)

## Original Inspiration

Built upon NetworkX to D3.js examples:
- https://github.com/networkx/networkx/tree/main/examples/external/force
