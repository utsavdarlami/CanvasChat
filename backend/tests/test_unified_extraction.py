"""
Test script for unified /extract-semantics endpoint.

Demonstrates extraction for both visual charts and text documents.
"""

import requests
import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

BASE_URL = "http://127.0.0.1:8000/api"


def test_visual_chart_extraction():
    """Test Case 1: Visual Chart (Vega-Lite specification)"""
    print("\n" + "=" * 60)
    print("TEST 1: Visual Chart Extraction")
    print("=" * 60)

    visual_request = {
        "type": "visual",
        "content": {
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "title": "Monthly Crime Incidents - Los Angeles",
            "data": {"url": "https://data.lacity.org/resource/2nrs-mtv8.json"},
            "mark": "bar",
            "encoding": {
                "x": {
                    "field": "date_occ",
                    "type": "temporal",
                    "timeUnit": "yearmonth",
                    "title": "Month",
                },
                "y": {"aggregate": "count", "title": "Number of Incidents"},
            },
            "width": 600,
            "height": 400,
        },
        "llm_config": {"temperature": 0.1},
    }

    try:
        response = requests.post(
            f"{BASE_URL}/extract-semantics", json=visual_request, timeout=30
        )
        response.raise_for_status()

        result = response.json()
        print(f"\n✅ SUCCESS: Visual extraction completed")
        print(f"Chart Type: {result.get('visual', {}).get('chart_type')}")
        print(f"Title: {result.get('title')}")
        print(f"Has Temporal: {result.get('data', {}).get('has_temporal')}")
        print(f"\nFull Response:")
        print(json.dumps(result, indent=2))

    except requests.exceptions.RequestException as e:
        print(f"❌ FAILED: {e}")


def test_text_document_extraction():
    """Test Case 2: Text Document"""
    print("\n" + "=" * 60)
    print("TEST 2: Text Document Extraction")
    print("=" * 60)

    text_request = {
        "type": "text",
        "content": """CIA Intelligence Report

Date: 27 April 2003
Classification: SECRET

Subject: Taliban Affiliate Identification

Intelligence gathered from laptop data captured in Afghanistan identifies Pakistani national Sahim Albakri, also known by the alias Bagwant Dhaliwal. Subject fought with Taliban forces from 1990-1992.

Additional intelligence indicates Muhammed bin Harazi served with Taliban from 1987-1993 and subsequently entered the United States in March 1993 using the alias Abdul Ramazi. Passport records confirm entry through JFK International Airport.

Further investigation recommended.""",
        "metadata": {
            "filename": "CIA_Report_20030427.txt",
            "source": "CIA Intelligence Archives",
            "classification": "SECRET",
            "document_date": "2003-04-27",
        },
        "llm_config": {"temperature": 0.1},
    }

    try:
        response = requests.post(
            f"{BASE_URL}/extract-semantics", json=text_request, timeout=30
        )
        response.raise_for_status()

        result = response.json()
        print(f"\n✅ SUCCESS: Text extraction completed")
        print(f"Title: {result.get('title')}")
        print(f"Summary: {result.get('summary')}")
        print(f"Keywords: {result.get('keywords')}")
        print(f"Entity Mentions: {result.get('entity_mentions')}")
        print(f"\nFull Response:")
        print(json.dumps(result, indent=2))

    except requests.exceptions.RequestException as e:
        print(f"❌ FAILED: {e}")


def test_error_no_content():
    """Test Case 3: Error - No content provided"""
    print("\n" + "=" * 60)
    print("TEST 3: Error Handling - No Content")
    print("=" * 60)

    invalid_request = {
        "type": "visual",
        "llm_config": {"temperature": 0.1},
        # Missing 'content' field
    }

    try:
        response = requests.post(
            f"{BASE_URL}/extract-semantics", json=invalid_request, timeout=30
        )
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")

        if response.status_code == 400:
            print("✅ SUCCESS: Validation error caught correctly")
        else:
            print("❌ FAILED: Expected 400 error")

    except requests.exceptions.RequestException as e:
        print(f"❌ FAILED: {e}")


def test_error_wrong_content_type():
    """Test Case 4: Error - Wrong content type for declared type"""
    print("\n" + "=" * 60)
    print("TEST 4: Error Handling - Wrong Content Type")
    print("=" * 60)

    invalid_request = {
        "type": "visual",
        "content": "This should be a dict, not a string",
    }

    try:
        response = requests.post(
            f"{BASE_URL}/extract-semantics", json=invalid_request, timeout=30
        )
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")

        if response.status_code == 400:
            print("✅ SUCCESS: Validation error caught correctly")
        else:
            print("❌ FAILED: Expected 400 error")

    except requests.exceptions.RequestException as e:
        print(f"❌ FAILED: {e}")


if __name__ == "__main__":
    print("\n🧪 Testing Unified /extract-semantics Endpoint")
    print("=" * 60)

    # Run tests
    test_visual_chart_extraction()
    test_text_document_extraction()
    test_error_no_content()
    test_error_wrong_content_type()

    print("\n" + "=" * 60)
    print("✅ All tests completed!")
    print("=" * 60)
