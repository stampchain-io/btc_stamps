#!/usr/bin/env python3
"""
Test script to verify Counterparty API behavior with different limit values.
Tests the workaround for the verbose=true pagination bug.
"""

import asyncio
import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.index_core.fetch_utils import fetch_block_transactions_with_pagination, fetch_xcp, fetch_xcp_async


async def test_api_limits():
    """Test different limit values and verbose settings."""

    # Test block 784320 which has 65 transactions (known problematic block)
    test_block = 784320

    print(f"\n=== Testing API limits for block {test_block} ===\n")

    # Test 1: Check basic block info
    print("1. Fetching block info...")
    block_info = fetch_xcp(f"/blocks/{test_block}")
    if block_info and "result" in block_info:
        tx_count = block_info["result"].get("transaction_count", "unknown")
        print(f"   Block {test_block} has {tx_count} transactions")
    else:
        print("   Failed to fetch block info")
        return

    # Test 2: Test with verbose=false and different limits
    print("\n2. Testing with verbose=false:")
    for limit in [100, 500, 1000, 2000]:
        endpoint = f"/blocks/{test_block}/transactions"
        params = {"verbose": "false", "limit": str(limit), "show_unconfirmed": "false"}

        try:
            response = await fetch_xcp_async(endpoint, params, timeout=30)
            if response and "result" in response:
                tx_count = len(response["result"])
                has_events = any("events" in tx for tx in response["result"])
                print(f"   Limit {limit}: Got {tx_count} transactions, has events: {has_events}")

                # Check first transaction structure
                if tx_count > 0:
                    first_tx = response["result"][0]
                    fields = list(first_tx.keys())
                    print(f"   Available fields: {', '.join(sorted(fields)[:10])}...")
                    if "events" in first_tx:
                        print(f"   First tx has {len(first_tx['events'])} events")
            else:
                print(f"   Limit {limit}: FAILED - No response or no result")
        except Exception as e:
            print(f"   Limit {limit}: ERROR - {e}")

    # Test 3: Test with current implementation
    print("\n3. Testing current implementation (fetch_block_transactions_with_pagination):")
    try:
        result = await fetch_block_transactions_with_pagination(test_block)
        if result:
            total_tx = len(result.get("transactions", []))
            issuances = len(result.get("issuances", []))
            print(f"   Successfully fetched {total_tx} transactions, {issuances} issuances")

            # Check if events are present
            if result.get("transactions"):
                has_events = any("events" in tx for tx in result["transactions"])
                print(f"   Transactions have events field: {has_events}")

                # Sample first transaction with events
                for tx in result["transactions"]:
                    if "events" in tx and tx["events"]:
                        print(f"   Sample tx {tx['tx_hash'][:16]}... has {len(tx['events'])} events")
                        break
        else:
            print("   FAILED - No result returned")
    except Exception as e:
        print(f"   ERROR - {e}")

    # Test 4: Check what happens with verbose=true (expected to fail on large blocks)
    print("\n4. Testing with verbose=true (expected to fail for large limits):")
    for limit in [10, 25, 26, 50]:
        endpoint = f"/blocks/{test_block}/transactions"
        params = {"verbose": "true", "limit": str(limit), "show_unconfirmed": "false"}

        try:
            response = await fetch_xcp_async(endpoint, params, timeout=30)
            if response and "result" in response:
                tx_count = len(response["result"])
                print(f"   Limit {limit}: SUCCESS - Got {tx_count} transactions")
            else:
                print(f"   Limit {limit}: FAILED - No response or no result")
        except Exception as e:
            print(f"   Limit {limit}: ERROR (expected for limit >= 26) - {type(e).__name__}")


if __name__ == "__main__":
    print("Testing Counterparty API limits...")
    print("This script tests the workaround for the verbose=true pagination bug")

    # Run the async test
    asyncio.run(test_api_limits())

    print("\n=== Summary ===")
    print("- verbose=false with high limits (1000-2000) should work fine")
    print("- verbose=true fails with limits >= 26 for blocks with many transactions")
    print("- The current workaround uses verbose=false with limit=100")
    print("- The 'events' field is critical for processing issuances")
