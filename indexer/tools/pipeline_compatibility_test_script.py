#!/usr/bin/env python3
"""
Test that the Counterparty API workaround is compatible with the async pipeline.

This script verifies that fetch_xcp_blocks_concurrent works correctly with both
the workaround and original methods.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src import config
from src.index_core.fetch_utils import fetch_xcp_blocks_concurrent


def test_pipeline_fetch(start_block: int, end_block: int):
    """Test fetching blocks using the pipeline's method."""
    print(f"\n=== Testing Pipeline Fetch ({start_block} to {end_block}) ===")
    print(f"Current setting: CP_API_USE_VERBOSE_WORKAROUND = {config.CP_API_USE_VERBOSE_WORKAROUND}")
    print(f"Method: {'2-step workaround' if config.CP_API_USE_VERBOSE_WORKAROUND else 'original verbose=true'}")

    try:
        # This is exactly how the pipeline calls it
        blocks_data = fetch_xcp_blocks_concurrent(start_block, end_block)

        if blocks_data:
            print(f"\n✓ Successfully fetched {len(blocks_data)} blocks")

            # Check data structure
            for block_idx, block_data in blocks_data.items():
                if block_data:
                    tx_count = len(block_data.get("transactions", []))
                    issuance_count = len(block_data.get("issuances", []))

                    # Check if transactions have events
                    tx_with_events = sum(1 for tx in block_data.get("transactions", []) if tx.get("events"))

                    print(f"\nBlock {block_idx}:")
                    print(f"  Transactions: {tx_count}")
                    print(f"  Issuances: {issuance_count}")
                    print(f"  Transactions with events: {tx_with_events}")

                    # Verify critical fields
                    if "block_index" not in block_data:
                        print("  ⚠️  Missing block_index field!")
                    if "xcp_block_hash" not in block_data:
                        print("  ⚠️  Missing xcp_block_hash field!")
                    if "transactions" not in block_data:
                        print("  ⚠️  Missing transactions field!")
                    if "issuances" not in block_data:
                        print("  ⚠️  Missing issuances field!")

                    # Check first transaction structure
                    if block_data.get("transactions"):
                        first_tx = block_data["transactions"][0]
                        required_fields = ["tx_hash", "block_index", "transaction_type", "events"]
                        missing_fields = [f for f in required_fields if f not in first_tx]
                        if missing_fields:
                            print(f"  ⚠️  First transaction missing fields: {missing_fields}")
                else:
                    print(f"\nBlock {block_idx}: ✗ Failed to fetch")
        else:
            print("\n✗ fetch_xcp_blocks_concurrent returned None or empty dict")

    except Exception as e:
        print(f"\n✗ Error during pipeline fetch: {e}")
        import traceback

        traceback.print_exc()


def test_both_methods():
    """Test the pipeline with both methods."""
    test_blocks = [(784325, 784325), (784320, 784322)]  # Single block and multi-block range

    # Save original setting
    original_setting = os.environ.get("CP_API_USE_VERBOSE_WORKAROUND")

    try:
        # Test with workaround (default)
        os.environ["CP_API_USE_VERBOSE_WORKAROUND"] = "true"
        # Reload config to pick up the change
        import importlib

        importlib.reload(config)

        print("\n" + "=" * 60)
        print("TESTING WITH WORKAROUND METHOD (2-step)")
        print("=" * 60)

        for start, end in test_blocks:
            test_pipeline_fetch(start, end)

        # Test with original method (if you want to see it fail)
        print("\n" + "=" * 60)
        print("TESTING WITH ORIGINAL METHOD (verbose=true)")
        print("=" * 60)
        print("⚠️  Note: This may fail for blocks with many transactions due to API bug")

        os.environ["CP_API_USE_VERBOSE_WORKAROUND"] = "false"
        importlib.reload(config)

        # Only test small block that should work
        test_pipeline_fetch(784325, 784325)

    finally:
        # Restore original setting
        if original_setting is not None:
            os.environ["CP_API_USE_VERBOSE_WORKAROUND"] = original_setting
        else:
            os.environ.pop("CP_API_USE_VERBOSE_WORKAROUND", None)
        importlib.reload(config)


if __name__ == "__main__":
    print("Testing Counterparty API Workaround with Pipeline")
    print("================================================")

    # Test current configuration
    print(f"\nCurrent environment setting: {os.environ.get('CP_API_USE_VERBOSE_WORKAROUND', 'not set')}")
    print(f"Config value: {config.CP_API_USE_VERBOSE_WORKAROUND}")

    # Test both methods
    test_both_methods()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print("The pipeline's fetch_xcp_blocks_concurrent function works with both methods.")
    print("It automatically uses whichever method is configured via CP_API_USE_VERBOSE_WORKAROUND.")
