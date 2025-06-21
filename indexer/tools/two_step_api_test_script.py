#!/usr/bin/env python3
"""
Test the 2-step API approach to work around the verbose=true pagination bug.
Step 1: Get all transactions with verbose=false
Step 2: Get detailed events for issuance/fairminter transactions
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.index_core.fetch_utils import fetch_xcp, fetch_xcp_async


async def get_transaction_details(tx_hash: str) -> Optional[Dict]:
    """Get full transaction details including events."""
    endpoint = f"/transactions/{tx_hash}"
    try:
        response = await fetch_xcp_async(endpoint, timeout=10)
        if response and "result" in response:
            return response["result"]
    except Exception as e:
        print(f"Error fetching transaction {tx_hash}: {e}")
    return None


async def test_two_step_approach(block_index: int = 784320):
    """Test the 2-step approach for getting transaction events."""

    print(f"\n=== Testing 2-step approach for block {block_index} ===\n")

    # Step 1: Get all transactions with verbose=false
    print("Step 1: Fetching all transactions with verbose=false...")
    endpoint = f"/blocks/{block_index}/transactions"
    params = {"verbose": "false", "limit": "1000", "show_unconfirmed": "false"}

    response = await fetch_xcp_async(endpoint, params, timeout=30)
    if not response or "result" not in response:
        print("Failed to fetch transactions")
        return

    all_transactions = response["result"]
    print(f"Got {len(all_transactions)} transactions")

    # Analyze transaction types
    tx_types = {}
    for tx in all_transactions:
        tx_type = tx.get("transaction_type", "unknown")
        tx_types[tx_type] = tx_types.get(tx_type, 0) + 1

    print("\nTransaction types found:")
    for tx_type, count in sorted(tx_types.items()):
        print(f"  {tx_type}: {count}")

    # Step 2: Filter relevant transactions and get their details
    print("\nStep 2: Filtering and fetching details for issuance/fairminter transactions...")

    relevant_types = ["issuance", "fairminter"]
    filtered_txs = [tx for tx in all_transactions if tx.get("transaction_type") in relevant_types]
    print(f"Found {len(filtered_txs)} relevant transactions")

    # Get details for first few transactions as a test
    sample_size = min(5, len(filtered_txs))
    if sample_size > 0:
        print(f"\nFetching details for {sample_size} sample transactions:")

        for i, tx in enumerate(filtered_txs[:sample_size]):
            tx_hash = tx.get("tx_hash")
            tx_type = tx.get("transaction_type")
            print(f"\n{i+1}. Transaction {tx_hash[:16]}... (type: {tx_type})")

            # Get full details including events
            details = await get_transaction_details(tx_hash)
            if details:
                # Check for events
                events = details.get("events", [])
                print(f"   Events found: {len(events)}")

                # Show event types
                for event in events:
                    event_type = event.get("event")
                    asset = event.get("params", {}).get("asset", "N/A")
                    print(f"   - {event_type} for asset: {asset}")

                    # Check if it's a STAMP
                    if event_type in ["ASSET_ISSUANCE", "NEW_FAIRMINT"]:
                        description = event.get("params", {}).get("description", "")
                        if description and "stamp:" in description.lower():
                            print(f"     ✓ This is a STAMP issuance!")
            else:
                print(f"   Failed to get details")

    # Performance estimation
    print(f"\n=== Performance Analysis ===")
    print(f"Total API calls needed:")
    print(f"  1 call for all transactions (verbose=false)")
    print(f"  {len(filtered_txs)} calls for individual transaction details")
    print(f"  Total: {1 + len(filtered_txs)} API calls")

    # Compare with verbose=true approach
    verbose_true_calls = (len(all_transactions) // 25) + (1 if len(all_transactions) % 25 else 0)
    print(f"\nCompared to verbose=true pagination:")
    print(f"  Would need {verbose_true_calls} calls (limit=25 per page)")
    print(f"  But would FAIL due to pagination bug!")


async def test_issuance_parsing():
    """Test parsing issuance data from transaction details."""
    # Test with a known issuance transaction
    test_tx = "e7c9025f88195092ac99916fded344f2b5a593f3b88eab96f8f012e83ad64ebd"

    print(f"\n=== Testing issuance parsing for {test_tx} ===")

    details = await get_transaction_details(test_tx)
    if details:
        print(f"Transaction type: {details.get('transaction_type')}")
        events = details.get("events", [])
        print(f"Events: {len(events)}")

        for event in events:
            if event.get("event") == "ASSET_ISSUANCE":
                params = event.get("params", {})
                print("\nIssuance details:")
                print(f"  Asset: {params.get('asset')}")
                print(f"  Quantity: {params.get('quantity')}")
                print(f"  Description: {params.get('description', '')[:50]}...")
                print(f"  Status: {params.get('status')}")


if __name__ == "__main__":
    print("Testing 2-step API approach for Counterparty transactions")
    print("This approach works around the verbose=true pagination bug")

    # Run the tests
    asyncio.run(test_two_step_approach())
    asyncio.run(test_issuance_parsing())
