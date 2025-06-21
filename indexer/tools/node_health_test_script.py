#!/usr/bin/env python3
"""
Test Counterparty node health and identify why nodes are being marked as unhealthy.
This script tests both the health check endpoints and actual API functionality.
"""

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

import requests

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.index_core.fetch_utils import fetch_node_version_v2, fetch_xcp, fetch_xcp_async


def test_node_health_check(node_url: str, node_name: str):
    """Test the health check endpoint for a node."""
    print(f"\n=== Testing {node_name} ({node_url}) ===")

    # Test 1: Basic connectivity
    print("\n1. Testing basic connectivity...")
    try:
        response = requests.get(node_url, timeout=5)
        print(f"   ✓ Connected successfully, status: {response.status_code}")

        # Check headers
        print("\n   Response headers:")
        important_headers = [
            "X-Counterparty-Version",
            "X-Bitcoin-Height",
            "X-Counterparty-Height",
            "X-Counterparty-Ready",
            "X-Ledger-State",
        ]
        for header in important_headers:
            value = response.headers.get(header, "NOT PRESENT")
            print(f"   - {header}: {value}")

    except requests.exceptions.Timeout:
        print(f"   ✗ TIMEOUT after 5 seconds")
        return
    except requests.exceptions.ConnectionError as e:
        print(f"   ✗ CONNECTION ERROR: {e}")
        return
    except Exception as e:
        print(f"   ✗ ERROR: {type(e).__name__}: {e}")
        return

    # Test 2: Version endpoint
    print("\n2. Testing version endpoint...")
    version_str, version_info = fetch_node_version_v2(node_url, timeout=10)
    if version_str:
        print(f"   ✓ Version: {version_str}")
        if version_info:
            print(f"   - Last block: {version_info.get('last_block')}")
            print(f"   - DB caught up: {version_info.get('db_caught_up')}")
            print(f"   - Bitcoin height: {version_info.get('bitcoin_block_count')}")
    else:
        print("   ✗ Failed to get version info")

    # Test 3: Test a simple API call
    print("\n3. Testing simple API call (/blocks/779720)...")
    try:
        test_endpoint = f"{node_url}/blocks/779720"
        response = requests.get(test_endpoint, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if "result" in data:
                block = data["result"]
                print(f"   ✓ Got block data: height={block.get('block_index')}, tx_count={block.get('transaction_count')}")
            else:
                print(f"   ⚠️  Response missing 'result' field: {list(data.keys())}")
        else:
            print(f"   ✗ HTTP {response.status_code}: {response.text[:200]}")
    except Exception as e:
        print(f"   ✗ ERROR: {type(e).__name__}: {e}")

    # Test 4: Test transactions endpoint with verbose=false
    print("\n4. Testing transactions endpoint (verbose=false)...")
    try:
        test_endpoint = f"{node_url}/blocks/779720/transactions"
        params = {"verbose": "false", "limit": "10", "show_unconfirmed": "false"}
        response = requests.get(test_endpoint, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if "result" in data:
                tx_count = len(data["result"])
                print(f"   ✓ Got {tx_count} transactions")
            else:
                print(f"   ⚠️  Response missing 'result' field")
        else:
            print(f"   ✗ HTTP {response.status_code}: {response.text[:200]}")
    except Exception as e:
        print(f"   ✗ ERROR: {type(e).__name__}: {e}")

    # Test 5: Test events endpoint (critical for workaround)
    print("\n5. Testing events endpoint (CRITICAL for workaround)...")
    try:
        test_endpoint = f"{node_url}/blocks/779720/events"
        params = {"limit": "10"}
        response = requests.get(test_endpoint, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if "result" in data:
                event_count = len(data["result"])
                print(f"   ✓ Got {event_count} events")
            else:
                print(f"   ⚠️  Response missing 'result' field")
        elif response.status_code == 500:
            print(f"   ✗ HTTP 500 ERROR - This might be triggering node failures!")
            print(f"   Response: {response.text[:200]}")
        else:
            print(f"   ✗ HTTP {response.status_code}: {response.text[:200]}")
    except Exception as e:
        print(f"   ✗ ERROR: {type(e).__name__}: {e}")

    # Test 6: Test verbose=true to confirm it fails as expected
    print("\n6. Testing transactions with verbose=true (expect failure on large blocks)...")
    try:
        # Test with block that has many transactions
        test_endpoint = f"{node_url}/blocks/784320/transactions"
        params = {"verbose": "true", "limit": "30", "show_unconfirmed": "false"}
        response = requests.get(test_endpoint, params=params, timeout=10)
        if response.status_code == 200:
            print(f"   ⚠️  Unexpected success with limit=30!")
        elif response.status_code == 500:
            print(f"   ✓ Expected HTTP 500 error with verbose=true and limit=30")
        else:
            print(f"   ? HTTP {response.status_code}")
    except Exception as e:
        print(f"   ✗ ERROR: {type(e).__name__}: {e}")


async def test_async_endpoints(node_url: str, node_name: str):
    """Test async endpoints that might be causing failures."""
    print(f"\n=== Testing async endpoints for {node_name} ===")

    # Test the exact endpoints that are failing in the logs
    failing_blocks = [779720, 779737, 779738]

    for block in failing_blocks:
        print(f"\n Testing block {block} events (async)...")
        endpoint = f"/blocks/{block}/events"
        params = {"limit": "1000"}

        try:
            # Use the actual fetch_xcp_async function
            result = await fetch_xcp_async(endpoint, params, timeout=10)
            if result and "result" in result:
                print(f"   ✓ Success: Got {len(result['result'])} events")
            else:
                print(f"   ✗ Failed: No result or empty response")
        except Exception as e:
            print(f"   ✗ ERROR: {type(e).__name__}: {e}")


def check_error_patterns():
    """Check if certain error patterns should be ignored."""
    print("\n=== Error Pattern Analysis ===")
    print("\nThe logs show:")
    print("1. Timeouts on /blocks/{block}/events endpoints")
    print("2. Node marked as failed after consecutive failures")
    print("3. Emergency health updates triggered")

    print("\nPossible issues:")
    print("1. The events endpoint might be slow for certain blocks")
    print("2. The 5-second timeout for health checks might be too short")
    print("3. HTTP 500 errors from the API might be counted as node failures")

    print("\nRecommendations:")
    print("1. Increase timeout for events endpoint (currently using 30s in workaround)")
    print("2. Don't count HTTP 500 as a node failure if it's a known API bug")
    print("3. Add specific handling for the verbose=true pagination bug")


def main():
    """Run all tests."""
    print("Counterparty Node Health Testing")
    print("================================")

    # Test configuration
    nodes = [
        ("https://api.counterparty.io:4000/v2", "counterparty-primary"),
        ("http://127.0.0.1:4000/v2", "counterparty-backup"),
    ]

    # Test each node
    for node_url, node_name in nodes:
        test_node_health_check(node_url, node_name)

    # Test async endpoints
    print("\n" + "=" * 60)
    print("ASYNC ENDPOINT TESTS")
    print("=" * 60)

    for node_url, node_name in nodes:
        asyncio.run(test_async_endpoints(node_url, node_name))

    # Analysis
    check_error_patterns()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print("\nKey findings:")
    print("1. Check if events endpoint is returning HTTP 500 errors")
    print("2. Check if timeouts are too aggressive (5s for health, 10s for API)")
    print("3. The workaround should help, but node health checks might need adjustment")
    print("\nThe CP_API_USE_VERBOSE_WORKAROUND=true should handle the verbose=true bug,")
    print("but won't help if the events endpoint itself is failing or timing out.")


if __name__ == "__main__":
    main()
