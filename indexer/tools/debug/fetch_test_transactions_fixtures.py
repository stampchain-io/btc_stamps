#!/usr/bin/env python3
"""
Fetch specific transactions used in test_transactions.py and save them as fixtures.
This allows the test to run without requiring a live Bitcoin node.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src")))

from index_core.backend import Backend

# Transactions from test_transactions.py
TEST_TRANSACTIONS = [
    {
        "txid": "2c90a9ec6ec51c9c8644e932c72332cd1843b78b312f76bdebdcb17cb96f0c24",
        "hex": "0100000001b9c606a36b5ec4899cba9eb51fce97fbf23a1f83eabe5c0f3a628614033b7bc0010000006a4730440220398125f458a85ee8eb3afffe259ab2c423852c649a3b67186b62230493c881b4022024494de0a2dfc547d03efa2bc0e3c58cc19e483c0e4f2e5c14678dd20c6742a6012102a8cbc88f03b11c5044173ee42ec694c6c0e49906cc5a36b11d988f417248ac1dffffffff027b000000000000001976a91485a30f5244e0b8c313e92516f23a4f9dd90305bb88ac61350000000000001976a914cb4c57f8e8dbed8a0c860adcc000f2c9e3f2bdc688ac00000000",
        "description": "Test transaction 1 from test_transactions.py",
    },
    {
        "txid": "a0eb969a3c89cc8616f7683ffa95fe5bf3d3d9f5b6c4b767e45cd9aa0b30b1df",
        "hex": "0100000001a69cbed0eec39f291d7f4ad595b100fcc79dc6aa8b37a468aabfdd850fbac03c010000006a47304402204e350a5a18a8e1975c8a4b399c66631f451e0dcf39f655f38ec6edb066c31a7c022064e050e5c7449a5c3f49a2f5cc3a293e8eed9cfe5fcc187b03347ac98f7a9db6012102a8cbc88f03b11c5044173ee42ec694c6c0e49906cc5a36b11d988f417248ac1dffffffff027b000000000000001976a91485a30f5244e0b8c313e92516f23a4f9dd90305bb88ace5a30000000000001976a914cb4c57f8e8dbed8a0c860adcc000f2c9e3f2bdc688ac00000000",
        "description": "Test transaction 2 from test_transactions.py",
    },
]


def fetch_transactions_from_node():
    """
    Try to fetch transactions from a live Bitcoin node.
    Returns list of transaction data with fetched hex values.
    """
    backend = Backend()
    fetched_txs = []

    for tx in TEST_TRANSACTIONS:
        try:
            print(f"Fetching transaction {tx['txid']}...")
            raw_hex = backend.getrawtransaction(tx["txid"])

            # Verify the hex matches what we expect
            if raw_hex == tx["hex"]:
                print(f"✓ Transaction hex matches expected value")
            else:
                print(f"! WARNING: Transaction hex differs from expected value")
                print(f"  Expected: {tx['hex'][:60]}...")
                print(f"  Got:      {raw_hex[:60]}...")

            fetched_txs.append({"txid": tx["txid"], "hex": raw_hex, "description": tx["description"]})

        except Exception as e:
            print(f"✗ Could not fetch transaction {tx['txid']}: {e}")
            # Use the hardcoded hex if we can't fetch from node
            fetched_txs.append(tx)

    return fetched_txs


def save_fixtures(transactions, output_path):
    """Save transaction fixtures to JSON file."""
    fixtures_data = {
        "test_transactions": transactions,
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "generated_by": "fetch_test_transactions_fixtures.py",
            "purpose": "Fixtures for test_transactions.py",
        },
    }

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Save fixtures
    with open(output_path, "w") as f:
        json.dump(fixtures_data, f, indent=2)

    print(f"\nFixtures saved to: {output_path}")


def main():
    """Main function."""
    # Define output path
    output_path = Path(__file__).parent.parent.parent / "tests" / "fixtures" / "test_transactions_fixtures.json"

    print("Fetching test transaction fixtures...")
    print("=" * 60)

    # Try to fetch from node, fall back to hardcoded values
    try:
        transactions = fetch_transactions_from_node()
    except Exception as e:
        print(f"\nCould not connect to Bitcoin node: {e}")
        print("Using hardcoded transaction data...")
        transactions = TEST_TRANSACTIONS

    # Save fixtures
    save_fixtures(transactions, output_path)

    # Print summary
    print(f"\nSaved {len(transactions)} transaction fixtures")
    print("\nTo use these fixtures in tests, update test_transactions.py to load from:")
    print(f"  {output_path.relative_to(Path.cwd())}")


if __name__ == "__main__":
    main()
