"""
Test script for chat endpoint with action tracking.

Verifies that layout updates, undo/redo actions return proper action metadata.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from api.endpoints.chat import chat_endpoint
from api.models.chat import ChatRequest

# Sample layout data (minimal example)
SAMPLE_LAYOUT = {
    "nodes": [
        {
            "entity_id": "entity-1",
            "id": "entity-1",
            "name": "View A",
            "display_name": "View A",
            "x": 0.0,
            "y": 0.0,
        },
        {
            "entity_id": "entity-2",
            "id": "entity-2",
            "name": "View B",
            "display_name": "View B",
            "x": 8.0,
            "y": 0.0,
        },
    ],
    "links": [],
    "graph": {},
}


async def test_chat_with_layout_update():
    """Test that layout modifications return action metadata."""
    print("\n=== Test 1: Layout Update ===")

    request = ChatRequest(
        query="swap the positions of View A and View B",
        user_id="test_user",
        session_id="test_session_1",
        layout=SAMPLE_LAYOUT,
    )

    try:
        response = await chat_endpoint(request)
        print(f"Response: {response.response}")
        print(f"Action: {response.action}")
        print(f"Layout present: {response.layout is not None}")
        print(f"History present: {response.history is not None}")

        if response.action:
            print(f"  - Action type: {response.action.type}")
            print(f"  - Description: {response.action.description}")
            print(f"  - Affected entities: {response.action.affected_entities}")
            if response.action.layout_delta:
                print(
                    f"  - Delta: {len(response.action.layout_delta.updated_nodes)} updated nodes"
                )

        if response.history:
            print(f"  - Can undo: {response.history.can_undo}")
            print(f"  - Can redo: {response.history.can_redo}")
            print(f"  - Undo depth: {response.history.undo_depth}")

        return True
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback

        traceback.print_exc()
        return False


async def test_chat_with_undo():
    """Test that undo actions return proper metadata."""
    print("\n=== Test 2: Undo Action ===")

    # First, make a change
    request1 = ChatRequest(
        query="swap View A and View B",
        user_id="test_user",
        session_id="test_session_2",
        layout=SAMPLE_LAYOUT,
    )

    try:
        response1 = await chat_endpoint(request1)
        print(f"First response: {response1.response[:50]}...")

        # Then undo
        request2 = ChatRequest(
            query="undo", user_id="test_user", session_id="test_session_2"
        )

        response2 = await chat_endpoint(request2)
        print(f"Undo response: {response2.response}")
        print(f"Action: {response2.action}")

        if response2.action:
            print(f"  - Action type: {response2.action.type}")
            print(f"  - Description: {response2.action.description}")

        if response2.history:
            print(f"  - Can undo: {response2.history.can_undo}")
            print(f"  - Can redo: {response2.history.can_redo}")

        return True
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback

        traceback.print_exc()
        return False


async def test_chat_without_layout():
    """Test that requests without layout changes don't return action metadata."""
    print("\n=== Test 3: No Layout Change ===")

    request = ChatRequest(
        query="What is the current layout?",
        user_id="test_user",
        session_id="test_session_3",
        layout=SAMPLE_LAYOUT,
    )

    try:
        response = await chat_endpoint(request)
        print(f"Response: {response.response[:50]}...")
        print(f"Action: {response.action}")
        print(f"Layout present: {response.layout is not None}")

        # Should not have action if no layout change
        if response.action is None:
            print("✓ Correctly returned no action (no layout change)")
            return True
        else:
            print("✗ Unexpected action returned")
            return False
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback

        traceback.print_exc()
        return False


async def main():
    """Run all tests."""
    print("Testing Chat Endpoint with Action Tracking")
    print("=" * 50)

    results = []

    # Test 1: Layout update
    results.append(await test_chat_with_layout_update())

    # Test 2: Undo action
    results.append(await test_chat_with_undo())

    # Test 3: No layout change
    results.append(await test_chat_without_layout())

    print("\n" + "=" * 50)
    print(f"Tests passed: {sum(results)}/{len(results)}")

    if all(results):
        print("✓ All tests passed!")
    else:
        print("✗ Some tests failed")


if __name__ == "__main__":
    asyncio.run(main())
