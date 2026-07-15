"""
Simple test script for text_extractor.py service.

Usage:
    python tests/test_text_extractor.py
"""

import asyncio
import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from services.text_extractor import extract_text_semantics


async def main():
    """Test text extraction on a single document from crescent dataset."""

    # Read sample text file
    file_path = "reponses/crescent_test_subset/cia11.txt"

    with open(file_path, "r") as f:
        text_content = f.read()

    print(f"Testing text extraction on: {file_path}\n")
    print("TEXT CONTENT:")
    print("-" * 80)
    print(text_content)
    print("-" * 80)

    # Extract semantics
    semantics = await extract_text_semantics(
        text_content=text_content, metadata={"filename": "cia11.txt"}
    )

    # Print results
    print("\nEXTRACTED SEMANTICS:\n")
    print(json.dumps(semantics.model_dump(), indent=2))


if __name__ == "__main__":
    asyncio.run(main())
