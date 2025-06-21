#!/usr/bin/env python3
"""
Test script to validate both Counterparty API methods.

This script tests both the workaround (2-step) and original (verbose=true) methods
to ensure they produce identical data structures.

Usage:
    python test_api_methods.py                    # Test default blocks
    python test_api_methods.py --block 784320     # Test specific block
    python test_api_methods.py --verbose          # Verbose output
    python test_api_methods.py --compare-fields   # Deep field comparison
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Set

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Temporarily override the config to test both methods
original_env = os.environ.get("CP_API_USE_VERBOSE_WORKAROUND")

try:
    from src import config
    from src.index_core.fetch_utils import (
        _fetch_block_transactions_original,
        _fetch_block_transactions_workaround,
        fetch_block_transactions_with_pagination,
    )
finally:
    # Restore original setting
    if original_env is not None:
        os.environ["CP_API_USE_VERBOSE_WORKAROUND"] = original_env
    elif "CP_API_USE_VERBOSE_WORKAROUND" in os.environ:
        del os.environ["CP_API_USE_VERBOSE_WORKAROUND"]


def compare_transactions(tx1: Dict, tx2: Dict, verbose: bool = False) -> List[str]:
    """Compare two transaction objects and return differences."""
    differences = []

    # Check all fields from tx1
    for key in tx1:
        if key not in tx2:
            differences.append(f"Field '{key}' missing in second transaction")
        elif tx1[key] != tx2[key]:
            if key == "events":
                # Special handling for events array
                if len(tx1[key]) != len(tx2[key]):
                    differences.append(f"Different number of events: {len(tx1[key])} vs {len(tx2[key])}")
                else:
                    for i, (e1, e2) in enumerate(zip(tx1[key], tx2[key])):
                        if e1 != e2:
                            differences.append(f"Event {i} differs")
                            if verbose:
                                differences.append(f"  Event 1: {json.dumps(e1, indent=2)}")
                                differences.append(f"  Event 2: {json.dumps(e2, indent=2)}")
            else:
                differences.append(f"Field '{key}' differs: {tx1[key]} != {tx2[key]}")

    # Check for extra fields in tx2
    for key in tx2:
        if key not in tx1:
            differences.append(f"Extra field '{key}' in second transaction")

    return differences


def compare_blocks(block1: Dict, block2: Dict, verbose: bool = False) -> Dict[str, Any]:
    """Compare two block data structures."""
    result = {
        "identical": True,
        "differences": [],
        "transaction_count_match": True,
        "issuance_count_match": True,
        "field_comparison": {},
    }

    # Compare basic fields
    for field in ["block_index", "xcp_block_hash"]:
        if block1.get(field) != block2.get(field):
            result["identical"] = False
            result["differences"].append(f"{field} mismatch: {block1.get(field)} vs {block2.get(field)}")

    # Compare transaction counts
    tx_count1 = len(block1.get("transactions", []))
    tx_count2 = len(block2.get("transactions", []))
    if tx_count1 != tx_count2:
        result["identical"] = False
        result["transaction_count_match"] = False
        result["differences"].append(f"Transaction count mismatch: {tx_count1} vs {tx_count2}")

    # Compare issuance counts
    iss_count1 = len(block1.get("issuances", []))
    iss_count2 = len(block2.get("issuances", []))
    if iss_count1 != iss_count2:
        result["identical"] = False
        result["issuance_count_match"] = False
        result["differences"].append(f"Issuance count mismatch: {iss_count1} vs {iss_count2}")

    # Compare individual transactions
    if tx_count1 == tx_count2:
        tx_map1 = {tx["tx_hash"]: tx for tx in block1.get("transactions", [])}
        tx_map2 = {tx["tx_hash"]: tx for tx in block2.get("transactions", [])}

        for tx_hash, tx1 in tx_map1.items():
            if tx_hash not in tx_map2:
                result["identical"] = False
                result["differences"].append(f"Transaction {tx_hash} missing in method 2")
            else:
                tx_diffs = compare_transactions(tx1, tx_map2[tx_hash], verbose)
                if tx_diffs:
                    result["identical"] = False
                    result["differences"].append(f"Transaction {tx_hash} has differences:")
                    result["differences"].extend([f"  {d}" for d in tx_diffs])

    # Field analysis
    if block1.get("transactions") and block2.get("transactions"):
        fields1 = set()
        fields2 = set()

        for tx in block1["transactions"]:
            fields1.update(tx.keys())
        for tx in block2["transactions"]:
            fields2.update(tx.keys())

        result["field_comparison"] = {
            "method1_fields": sorted(list(fields1)),
            "method2_fields": sorted(list(fields2)),
            "missing_in_method2": sorted(list(fields1 - fields2)),
            "extra_in_method2": sorted(list(fields2 - fields1)),
        }

    return result


async def test_block(block_index: int, verbose: bool = False) -> Dict[str, Any]:
    """Test both methods on a specific block."""
    print(f"\n=== Testing block {block_index} ===")

    # Test workaround method
    print("Testing workaround method (2-step approach)...")
    try:
        workaround_result = await _fetch_block_transactions_workaround(block_index)
        if workaround_result:
            print(f"✓ Workaround method succeeded")
            print(f"  Transactions: {len(workaround_result.get('transactions', []))}")
            print(f"  Issuances: {len(workaround_result.get('issuances', []))}")
        else:
            print("✗ Workaround method returned None")
            workaround_result = None
    except Exception as e:
        print(f"✗ Workaround method failed: {e}")
        workaround_result = None

    # Test original method
    print("\nTesting original method (verbose=true)...")
    try:
        original_result = await _fetch_block_transactions_original(block_index)
        if original_result:
            print(f"✓ Original method succeeded")
            print(f"  Transactions: {len(original_result.get('transactions', []))}")
            print(f"  Issuances: {len(original_result.get('issuances', []))}")
        else:
            print("✗ Original method returned None")
            original_result = None
    except Exception as e:
        print(f"✗ Original method failed: {e}")
        original_result = None

    # Compare results
    comparison = None
    if workaround_result and original_result:
        print("\nComparing results...")
        comparison = compare_blocks(workaround_result, original_result, verbose)

        if comparison["identical"]:
            print("✓ Both methods produce IDENTICAL results!")
        else:
            print("✗ Methods produce DIFFERENT results:")
            for diff in comparison["differences"][:10]:  # Show first 10 differences
                print(f"  - {diff}")
            if len(comparison["differences"]) > 10:
                print(f"  ... and {len(comparison['differences']) - 10} more differences")

        # Field comparison
        field_comp = comparison.get("field_comparison", {})
        if field_comp.get("missing_in_method2"):
            print(f"\nFields missing in original method: {field_comp['missing_in_method2']}")
        if field_comp.get("extra_in_method2"):
            print(f"Extra fields in original method: {field_comp['extra_in_method2']}")

    return {
        "block_index": block_index,
        "workaround_success": workaround_result is not None,
        "original_success": original_result is not None,
        "comparison": comparison,
    }


async def test_current_configuration():
    """Test the current configuration setting."""
    print("\n=== Testing current configuration ===")
    print(f"CP_API_USE_VERBOSE_WORKAROUND = {config.CP_API_USE_VERBOSE_WORKAROUND}")

    # Test with a small block that should work with both methods
    test_block = 784325  # Known to have only 14 transactions
    print(f"\nTesting block {test_block} with current configuration...")

    result = await fetch_block_transactions_with_pagination(test_block)
    if result:
        print(f"✓ Success with current configuration")
        print(f"  Transactions: {len(result.get('transactions', []))}")
        print(f"  Method used: {'workaround' if config.CP_API_USE_VERBOSE_WORKAROUND else 'original'}")
    else:
        print("✗ Failed with current configuration")


async def main():
    """Main test function."""
    parser = argparse.ArgumentParser(description="Test Counterparty API methods")
    parser.add_argument("--block", type=int, help="Specific block to test")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--compare-fields", action="store_true", help="Show detailed field comparison")

    args = parser.parse_args()

    print("Counterparty API Method Testing")
    print("==============================")

    # Test current configuration
    await test_current_configuration()

    # Test blocks
    if args.block:
        test_blocks = [args.block]
    else:
        # Default test blocks
        test_blocks = [
            784325,  # 14 transactions (should work with both)
            784320,  # 65 transactions (fails with verbose=true)
            784330,  # 34 transactions (borderline case)
        ]

    results = []
    for block in test_blocks:
        result = await test_block(block, args.verbose)
        results.append(result)

    # Summary
    print("\n=== SUMMARY ===")
    print(f"Tested {len(results)} blocks")

    workaround_success = sum(1 for r in results if r["workaround_success"])
    original_success = sum(1 for r in results if r["original_success"])
    identical = sum(1 for r in results if r.get("comparison", {}).get("identical", False))

    print(f"Workaround method: {workaround_success}/{len(results)} successful")
    print(f"Original method: {original_success}/{len(results)} successful")
    print(f"Identical results: {identical}/{min(workaround_success, original_success)} matching blocks")

    if args.compare_fields and results:
        print("\n=== FIELD ANALYSIS ===")
        for result in results:
            if result.get("comparison", {}).get("field_comparison"):
                print(f"\nBlock {result['block_index']}:")
                fc = result["comparison"]["field_comparison"]
                print(f"  Workaround fields: {', '.join(fc['method1_fields'])}")
                print(f"  Original fields: {', '.join(fc['method2_fields'])}")


if __name__ == "__main__":
    asyncio.run(main())
