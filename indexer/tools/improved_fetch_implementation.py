#!/usr/bin/env python3
"""
Improved implementation of fetch_block_transactions_with_pagination.
Uses a 2-step approach to work around the verbose=true pagination bug:
1. Get all transactions with verbose=false (supports high limits)
2. Get all events for the block separately
3. Match events to transactions
"""

import asyncio
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


async def fetch_block_transactions_with_pagination_improved(
    block_index: int, node_url: Optional[str] = None
) -> Optional[Dict[str, any]]:
    """
    Fetch all transactions for a block using an improved 2-step approach.

    This implementation works around the Counterparty API verbose=true pagination bug by:
    1. Fetching all transactions with verbose=false (which supports high limits)
    2. Fetching all events for the block separately
    3. Matching events to their corresponding transactions

    Args:
        block_index: The block index to fetch transactions for
        node_url: Optional specific node URL to use

    Returns:
        Dictionary containing:
        - block_index: The block index
        - xcp_block_hash: The block hash
        - transactions: List of all transactions with their events
        - issuances: List of issuance transactions
    """
    from src.index_core.fetch_utils import fetch_xcp_async, parse_issuance_from_transaction

    logger.debug(f"Fetching block {block_index} transactions with improved 2-step approach")

    # Step 1: Get all transactions with verbose=false (supports high limits)
    logger.debug("Step 1: Fetching all transactions with verbose=false")
    tx_endpoint = f"/blocks/{block_index}/transactions"
    tx_params = {"verbose": "false", "limit": "2000", "show_unconfirmed": "false"}

    tx_response = await fetch_xcp_async(tx_endpoint, tx_params, timeout=30)
    if not tx_response or "result" not in tx_response:
        logger.error(f"Failed to fetch transactions for block {block_index}")
        return None

    all_transactions = tx_response["result"]
    logger.debug(f"Got {len(all_transactions)} transactions")

    # Create a mapping of tx_hash to transaction for quick lookup
    tx_map = {tx["tx_hash"]: tx for tx in all_transactions}

    # Step 2: Get all events for the block
    logger.debug("Step 2: Fetching all events for the block")
    events_endpoint = f"/blocks/{block_index}/events"
    all_events = []
    next_cursor = None
    page_count = 0

    while True:
        page_count += 1
        params = {"limit": "1000"}  # Events endpoint supports high limits
        if next_cursor:
            params["cursor"] = next_cursor

        events_response = await fetch_xcp_async(events_endpoint, params, timeout=30)
        if not events_response or "result" not in events_response:
            logger.warning(f"Failed to fetch events page {page_count} for block {block_index}")
            break

        page_events = events_response["result"]
        all_events.extend(page_events)
        logger.debug(f"Page {page_count}: Got {len(page_events)} events, total: {len(all_events)}")

        # Check for more pages
        if "next_cursor" in events_response and events_response["next_cursor"]:
            next_cursor = events_response["next_cursor"]
        else:
            break

    logger.debug(f"Got {len(all_events)} total events for block {block_index}")

    # Step 3: Match events to transactions
    logger.debug("Step 3: Matching events to transactions")
    for event in all_events:
        tx_hash = event.get("tx_hash")
        if tx_hash and tx_hash in tx_map:
            # Initialize events list if not present
            if "events" not in tx_map[tx_hash]:
                tx_map[tx_hash]["events"] = []
            # Add event to the transaction
            tx_map[tx_hash]["events"].append(event)

    # Ensure all transactions have an events field (even if empty)
    for tx in all_transactions:
        if "events" not in tx:
            tx["events"] = []

    # Step 4: Parse issuances
    logger.debug("Step 4: Parsing issuances from transactions")
    issuances = []

    for tx in all_transactions:
        tx_type = tx.get("transaction_type")
        if tx_type in ["issuance", "fairminter"]:
            # Check for events in the transaction
            events = tx.get("events", [])
            for event in events:
                if event.get("event") in ["ASSET_ISSUANCE", "NEW_FAIRMINT"]:
                    # Parse issuance data
                    issuance_data = parse_issuance_from_transaction(tx, event)
                    if issuance_data:
                        # This is a valid STAMP issuance
                        issuances.append(issuance_data)

    logger.debug(f"Found {len(issuances)} stamp issuances")

    # Get block hash from the first transaction if available
    block_hash = all_transactions[0].get("block_hash") if all_transactions else None

    # Create result structure
    result = {
        "block_index": block_index,
        "xcp_block_hash": block_hash,
        "transactions": all_transactions,
        "issuances": issuances,
    }

    return result


async def test_implementation():
    """Test the improved implementation."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent))

    # Test with block 784320 (65 transactions, known problematic)
    test_block = 784320

    print(f"\n=== Testing improved implementation for block {test_block} ===")

    result = await fetch_block_transactions_with_pagination_improved(test_block)

    if result:
        print(f"\nSuccess!")
        print(f"Block: {result['block_index']}")
        print(f"Transactions: {len(result['transactions'])}")
        print(f"Issuances: {len(result['issuances'])}")

        # Check events
        tx_with_events = sum(1 for tx in result["transactions"] if tx.get("events"))
        total_events = sum(len(tx.get("events", [])) for tx in result["transactions"])
        print(f"Transactions with events: {tx_with_events}")
        print(f"Total events: {total_events}")

        # Show sample issuance
        if result["issuances"]:
            sample = result["issuances"][0]
            print(f"\nSample issuance:")
            print(f"  CPID: {sample.get('cpid')}")
            print(f"  TX: {sample.get('tx_hash', '')[:32]}...")
            print(f"  Description: {sample.get('description', '')[:50]}...")
    else:
        print("Failed to fetch block data")


if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(level=logging.DEBUG)

    # Run test
    asyncio.run(test_implementation())
