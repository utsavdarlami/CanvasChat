"""
Test script for the chat endpoint.

This script demonstrates how to interact with the layout modification agent
through the /api/chat endpoint.
"""

import requests
import json
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

BASE_URL = "http://127.0.0.1:8000/api"
USER_ID = "test_user"
SESSION_ID = "test_session"


def load_example_layout():
    """Load example layout from file."""
    layout_path = "generate_llm_layout_response.json"
    if os.path.exists(layout_path):
        with open(layout_path, "r") as f:
            return json.load(f)
    else:
        # Return a minimal example layout if file doesn't exist
        return {
            "nodes": [
                {"entity_id": "entity-1", "name": "Sample Chart 1", "x": 0.0, "y": 0.0},
                {
                    "entity_id": "entity-2",
                    "name": "Sample Chart 2",
                    "x": 10.0,
                    "y": 0.0,
                },
            ],
            "links": [],
            "graph": {"metadata": {}},
        }


def load_semantic_context():
    """Load semantic context (entities and relationships) if available."""
    entities_path = "reponses/test_case_5_juxtaposition_collection_analyzed.json"
    relationships_path = (
        "reponses/test_case_5_juxtaposition_collection_relationships.json"
    )

    entities = None
    relationships = None

    if os.path.exists(entities_path):
        with open(entities_path, "r") as f:
            data = json.load(f)
            entities = data.get("analyzed_entities")

    if os.path.exists(relationships_path):
        with open(relationships_path, "r") as f:
            relationships = json.load(f)

    return entities, relationships


def chat(
    query: str, layout: dict = None, entities: list = None, relationships: dict = None
):
    """Send a chat message to the agent.

    Args:
        query: User's message to the agent
        layout: Optional layout data to load (required for first message in a session)
        entities: Optional semantic entity data (Layer 1 output)
        relationships: Optional relationship data (Layer 2 output)
    """
    payload = {"query": query, "user_id": USER_ID, "session_id": SESSION_ID}

    if layout is not None:
        payload["layout"] = layout

    if entities is not None:
        payload["entities"] = entities

    if relationships is not None:
        payload["relationships"] = relationships

    response = requests.post(f"{BASE_URL}/chat", json=payload)

    if response.status_code == 200:
        data = response.json()
        print(f"\n>>> User: {query}")
        if layout:
            print(f"    [Provided layout with {len(layout.get('nodes', []))} nodes]")
        if entities:
            print(f"    [Provided {len(entities)} entity semantics]")
        if relationships:
            print(
                f"    [Provided {len(relationships.get('edges', []))} relationships, {len(relationships.get('clusters', []))} clusters]"
            )
        print(f"<<< Agent: {data['response']}\n")
        return data
    else:
        print(f"Error: {response.status_code}")
        print(response.text)
        return None


def clear_session():
    """Clear the current session."""
    response = requests.delete(
        f"{BASE_URL}/chat/session",
        params={"user_id": USER_ID, "session_id": SESSION_ID},
    )

    if response.status_code == 200:
        print(f"✓ Session cleared: {response.json()['message']}\n")
    else:
        print(f"Error clearing session: {response.status_code}")


def test_conversation():
    """Run a test conversation with the agent."""
    print("=" * 60)
    print("Layout Modification Agent - Test Conversation")
    print("=" * 60)

    # Clear any existing session
    clear_session()

    # Load example layout
    print("Loading example layout...")
    layout = load_example_layout()
    print(f"Loaded layout with {len(layout.get('nodes', []))} nodes")

    # Load semantic context if available
    print("Loading semantic context...")
    entities, relationships = load_semantic_context()
    if entities:
        print(f"Loaded {len(entities)} entity semantics")
    if relationships:
        print(
            f"Loaded {len(relationships.get('edges', []))} relationships, {len(relationships.get('clusters', []))} clusters"
        )
    print()

    # Test conversation flow
    # FIRST REQUEST: Must include layout data, optionally entities/relationships
    chat(
        "What's the current layout?",
        layout=layout,
        entities=entities,
        relationships=relationships,
    )

    # SUBSEQUENT REQUESTS: Layout data is optional (uses session state)
    chat("How many entities are there?")

    chat("Can you show me which entities are on which surfaces?")

    # Demonstrate layout reload mid-conversation
    print("\n" + "=" * 60)
    print("Demonstrating layout reload mid-conversation...")
    print("=" * 60)

    chat("align it vertically")

    # Create a modified layout
    # modified_layout = layout.copy()
    # if modified_layout.get('nodes'):
    #     # Add a new node
    #     modified_layout['nodes'].append({
    #         "entity_id": "entity-new",
    #         "name": "Newly Added Chart",
    #         "x": 20.0,
    #         "y": 20.0
    #     })

    # chat("I'm loading a new layout with an additional chart", layout=modified_layout)

    # chat("How many entities are there now?")

    # Note: This will work based on the actual entity IDs in your layout
    # You may need to adjust entity IDs based on the first response
    # chat("Move entity-1 to surface_1")

    # chat("Make the layout 1.5 times larger")

    chat("Export the layout")

    print("=" * 60)
    print("Test conversation complete!")
    print("=" * 60)


if __name__ == "__main__":
    try:
        test_conversation()
    except requests.exceptions.ConnectionError:
        print("\n❌ Error: Cannot connect to API server.")
        print("Make sure the server is running: uvicorn main:app --reload")
    except Exception as e:
        print(f"\n❌ Error: {e}")
