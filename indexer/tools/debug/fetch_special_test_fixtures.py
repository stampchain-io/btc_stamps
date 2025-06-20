#!/usr/bin/env python3
"""Fetch specific Bitcoin transactions needed for tests that currently require a Bitcoin node."""

import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from index_core.backend import Backend


def main():
    """Fetch specific transactions needed for test_special_txs.py and test_rust_parser.py."""
    backend = Backend()
    
    # Special transactions from test_special_txs.py
    special_txids = [
        # Transaction 1: Has a multisig output with keyburn and valid SRC-20 data
        "e2aa459ebfe0ba3625c917143452678a3e80636489fe0ec8cc7e9651cfd4ddb2",
        # Transaction 2: Has two multisig outputs with keyburn, one with valid SRC-20 data
        "359aefd7bf0bbd8398ee5c8c0f206799b78b158578f0f98e1e06bf58e70008dc",
    ]
    
    # Block for test_rust_parser.py
    test_block_hash = "00000000000000000007878ec04bb2b2e12317804810f4c26033585b3f81ffaa"  # Block 700,000
    
    print("Fetching special transactions for test fixtures...")
    
    # Fetch special transactions
    special_transactions = []
    for txid in special_txids:
        try:
            print(f"Fetching transaction: {txid}")
            tx_hex = backend.getrawtransaction(txid)
            
            special_transactions.append({
                "txid": txid,
                "hex": tx_hex,
                "description": f"Special transaction {len(special_transactions) + 1}: Used in test_special_txs.py"
            })
            print(f"  ✓ Successfully fetched")
        except Exception as e:
            print(f"  ✗ Failed to fetch: {e}")
            raise
    
    print(f"\nFetching block {test_block_hash} (height 700000)...")
    
    # Fetch the block used in test_rust_parser.py
    try:
        # Get raw block hex
        block_hex = backend.getblock(test_block_hash, verbosity=0)
        
        # Get block info
        block_info = backend.getblock(test_block_hash, verbosity=1)
        
        # Get transactions from the block
        tx_hash_list, raw_transactions, timestamp, prev_hash, bits = backend.get_tx_list(test_block_hash)
        
        block_data = {
            "height": 700000,
            "hash": test_block_hash,
            "hex": block_hex,
            "timestamp": timestamp,
            "prev_hash": prev_hash,
            "bits": bits,
            "tx_count": len(tx_hash_list),
            "sample_txs": []
        }
        
        # Include first 5 transactions as samples
        for i, (tx_hash, raw_tx) in enumerate(list(raw_transactions.items())[:5]):
            block_data["sample_txs"].append({
                "txid": tx_hash,
                "hex": raw_tx
            })
        
        print(f"  ✓ Successfully fetched block with {len(tx_hash_list)} transactions")
    except Exception as e:
        print(f"  ✗ Failed to fetch block: {e}")
        raise
    
    # Create comprehensive fixtures
    fixtures = {
        "special_transactions": special_transactions,
        "test_block_700000": block_data,
        "metadata": {
            "description": "Fixtures for tests that require Bitcoin node access",
            "generated_at": str(Path(__file__).stat().st_mtime),
            "purpose": "Enable tests marked with @pytest.mark.requires_bitcoin_node to run without a node"
        }
    }
    
    # Save to JSON file
    output_file = Path(__file__).parent.parent.parent / "tests" / "fixtures" / "bitcoin_node_fixtures.json"
    output_file.parent.mkdir(exist_ok=True)
    
    with open(output_file, "w") as f:
        json.dump(fixtures, f, indent=2)
    
    print(f"\nFixtures saved to: {output_file}")
    print(f"Total file size: {output_file.stat().st_size / 1024 / 1024:.2f} MB")
    
    # Print summary
    print("\nFixture Summary:")
    print(f"- Special transactions: {len(special_transactions)}")
    print(f"- Test block transactions: {block_data['tx_count']}")
    print("\nThese fixtures can be used to run tests without a Bitcoin node.")


if __name__ == "__main__":
    main()