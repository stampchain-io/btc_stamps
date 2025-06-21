#!/usr/bin/env python3
"""
Test getting events data from Counterparty API.
Try different endpoints to find the best way to get event details.
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.index_core.fetch_utils import fetch_xcp, fetch_xcp_async


async def test_events_endpoints():
    """Test various endpoints to get event data."""

    print("\n=== Testing different endpoints for event data ===\n")

    # Known issuance transaction
    test_tx = "a28a6453d4265cd01e2a7b31f8502c1b58e8b3251bc45f4d96f5c4a10de088d8"
    test_block = 784320

    # Test 1: Transaction endpoint with verbose
    print("1. Testing /transactions/{tx_hash} with verbose=true:")
    endpoint = f"/transactions/{test_tx}"
    params = {"verbose": "true"}
    response = await fetch_xcp_async(endpoint, params, timeout=10)
    if response and "result" in response:
        result = response["result"]
        print(f"   Response received, type: {result.get('transaction_type')}")
        print(f"   Has events field: {'events' in result}")
        if "events" in result:
            print(f"   Events count: {len(result['events'])}")
    else:
        print("   Failed to get response")

    # Test 2: Events endpoint for a block
    print("\n2. Testing /blocks/{block_index}/events:")
    endpoint = f"/blocks/{test_block}/events"
    params = {"limit": "10"}
    response = await fetch_xcp_async(endpoint, params, timeout=10)
    if response and "result" in response:
        events = response["result"]
        print(f"   Got {len(events)} events")
        # Check for issuance events
        issuance_events = [e for e in events if e.get("event") in ["ASSET_ISSUANCE", "NEW_FAIRMINT"]]
        print(f"   Issuance events: {len(issuance_events)}")
        if issuance_events:
            print(f"   Sample event: {issuance_events[0].get('event')} for tx {issuance_events[0].get('tx_hash', '')[:16]}...")
    else:
        print("   Failed to get response")

    # Test 3: Events endpoint with event type filter
    print("\n3. Testing /events with event_type filter:")
    endpoint = "/events"
    params = {"event": "ASSET_ISSUANCE", "limit": "5"}
    response = await fetch_xcp_async(endpoint, params, timeout=10)
    if response and "result" in response:
        events = response["result"]
        print(f"   Got {len(events)} ASSET_ISSUANCE events")
        for event in events:
            tx_hash = event.get("tx_hash", "")
            asset = event.get("params", {}).get("asset", "") if event.get("params") else ""
            if tx_hash:
                print(f"   - TX {tx_hash[:16]}... Asset: {asset}")
    else:
        print("   Failed to get response")

    # Test 4: Get events for specific transaction
    print("\n4. Testing /transactions/{tx_hash}/events:")
    endpoint = f"/transactions/{test_tx}/events"
    response = await fetch_xcp_async(endpoint, {}, timeout=10)
    if response and "result" in response:
        events = response["result"]
        print(f"   Got {len(events)} events for transaction")
        for event in events:
            print(f"   - {event.get('event')} at index {event.get('event_index')}")
    else:
        print("   Failed to get response")


async def test_optimized_approach():
    """Test an optimized approach to get issuance data."""

    test_block = 784320
    print(f"\n=== Testing optimized approach for block {test_block} ===\n")

    # Step 1: Get all events for the block (instead of transactions)
    print("Step 1: Get all events for the block...")
    endpoint = f"/blocks/{test_block}/events"
    all_events = []
    next_cursor = None

    while True:
        params = {"limit": "100"}
        if next_cursor:
            params["cursor"] = next_cursor

        response = await fetch_xcp_async(endpoint, params, timeout=30)
        if not response or "result" not in response:
            break

        events = response["result"]
        all_events.extend(events)

        if "next_cursor" in response and response["next_cursor"]:
            next_cursor = response["next_cursor"]
        else:
            break

    print(f"Got {len(all_events)} total events")

    # Analyze event types
    event_types = {}
    for event in all_events:
        event_type = event.get("event", "unknown")
        event_types[event_type] = event_types.get(event_type, 0) + 1

    print("\nEvent types found:")
    for event_type, count in sorted(event_types.items()):
        print(f"  {event_type}: {count}")

    # Step 2: Filter for issuance events
    issuance_events = [e for e in all_events if e.get("event") in ["ASSET_ISSUANCE", "NEW_FAIRMINT"]]
    print(f"\nFound {len(issuance_events)} issuance events")

    # Step 3: Check for STAMP issuances
    stamp_issuances = []
    for event in issuance_events[:5]:  # Check first 5 as sample
        params = event.get("params", {})
        description = params.get("description", "")
        if description and "stamp:" in description.lower():
            stamp_issuances.append(event)
            print(f"\nSTAMP found:")
            print(f"  TX: {event.get('tx_hash', '')[:32]}...")
            print(f"  Asset: {params.get('asset')}")
            print(f"  Description: {description[:50]}...")


if __name__ == "__main__":
    print("Testing Counterparty API endpoints for event data")

    # Run the tests
    asyncio.run(test_events_endpoints())
    asyncio.run(test_optimized_approach())
