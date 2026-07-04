#!/usr/bin/env python3
"""Fetch real Bitcoin transaction and block data for test fixtures."""

import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from index_core.backend import Backend


def main():
    """Fetch real transaction and block data for test fixtures."""
    backend = Backend()

    # Get a recent block that should have stamps transactions
    # Block 820000 is a good candidate as it's recent but not too new
    block_height = 820000

    print(f"Fetching block at height {block_height}...")

    # Get block hash from height
    block_hash = backend.getblockhash(block_height)
    print(f"Block hash: {block_hash}")

    # Get raw block hex
    print("Fetching raw block hex...")
    block_hex = backend.getblock(block_hash, verbosity=0)  # verbosity=0 returns hex

    # Get transactions from the block
    print("Fetching block transactions...")
    tx_hash_list, raw_transactions, timestamp, prev_hash, bits = backend.get_tx_list(block_hash)

    print(f"Block contains {len(tx_hash_list)} transactions")

    # Get a few sample transactions
    sample_txs = []
    for i, (tx_hash, raw_tx) in enumerate(list(raw_transactions.items())[:5]):
        print(f"Transaction {i+1}: {tx_hash}")
        sample_txs.append({"txid": tx_hash, "hex": raw_tx})

    # Create fixtures dictionary
    fixtures = {
        "block": {
            "height": block_height,
            "hash": block_hash,
            "hex": block_hex,
            "timestamp": timestamp,
            "prev_hash": prev_hash,
            "bits": bits,
            "tx_count": len(tx_hash_list),
        },
        "transactions": sample_txs,
    }

    # Save to JSON file
    output_file = Path(__file__).parent.parent.parent / "tests" / "fixtures" / "test_data.json"
    output_file.parent.mkdir(exist_ok=True)

    with open(output_file, "w") as f:
        json.dump(fixtures, f, indent=2)

    print(f"\nFixtures saved to: {output_file}")

    # Also print sample transaction hex for direct use in tests
    print("\nSample transaction hex for test_parser.py:")
    print(f'SAMPLE_TX_HEX = "{sample_txs[0]["hex"]}"')

    print("\nSample block hex (first 200 chars) for test_parser.py:")
    print(f'SAMPLE_BLOCK_HEX = "{block_hex[:200]}..."  # Full hex is too long to display')


if __name__ == "__main__":
    main()
