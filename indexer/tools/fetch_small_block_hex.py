#!/usr/bin/env python3
"""
Fetch raw hex data for a small block containing SRC-20 transactions.
This is useful for creating test fixtures for the Rust parser.
"""

import json
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from index_core.backend import Backend
from index_core.database_manager import DatabaseManager


def find_small_blocks_with_src20():
    """Find blocks with SRC-20 transactions that have fewer total transactions."""
    db_manager = DatabaseManager()
    db = db_manager.connect()

    query = """
    SELECT DISTINCT b.block_index, b.block_hash, 
           COUNT(DISTINCT t.tx_hash) as tx_count
    FROM blocks b
    JOIN transactions t ON b.block_index = t.block_index
    WHERE t.source LIKE 'SRC20%'
      AND b.block_index > 780000
      AND b.block_index < 790000
    GROUP BY b.block_index, b.block_hash
    HAVING tx_count < 100
    ORDER BY tx_count ASC
    LIMIT 10
    """

    cursor = db.execute(query)
    results = cursor.fetchall()
    db.close()

    return results


def fetch_block_hex(block_hash):
    """Fetch raw block hex from Bitcoin node."""
    backend = Backend()

    try:
        # Get raw block hex (verbosity=0)
        block_hex = backend.rpc("getblock", [block_hash, 0])
        return block_hex
    except Exception as e:
        print(f"Error fetching block hex: {e}")
        return None


def save_block_hex_fixture(block_index, block_hash, block_hex):
    """Save block hex as a test fixture."""
    fixture_dir = Path(__file__).parent.parent / "tests" / "fixtures" / "block_hex"
    fixture_dir.mkdir(parents=True, exist_ok=True)

    fixture_data = {
        "block_index": block_index,
        "block_hash": block_hash,
        "block_hex": block_hex,
        "hex_length": len(block_hex),
        "description": f"Raw block hex for block {block_index} containing SRC-20 transactions",
    }

    fixture_path = fixture_dir / f"block_{block_index}_hex.json"
    with open(fixture_path, "w") as f:
        json.dump(fixture_data, f, indent=2)

    print(f"Saved block hex fixture to: {fixture_path}")
    print(f"Block hex length: {len(block_hex)} characters")


def main():
    """Main function."""
    print("Finding small blocks with SRC-20 transactions...")

    blocks = find_small_blocks_with_src20()

    if not blocks:
        print("No suitable blocks found")
        return

    print(f"\nFound {len(blocks)} suitable blocks:")
    for block_index, block_hash, tx_count in blocks:
        print(f"  Block {block_index}: {tx_count} transactions")

    # Use the smallest block
    block_index, block_hash, tx_count = blocks[0]
    print(f"\nFetching hex for block {block_index} ({tx_count} transactions)...")

    block_hex = fetch_block_hex(block_hash)

    if block_hex:
        save_block_hex_fixture(block_index, block_hash, block_hex)

        # Also save a minimal fixture with just the data needed for tests
        print("\nCreating minimal test fixture...")
        minimal_fixture = {
            "block_index": block_index,
            "block_hex": block_hex[:1000] + "...",  # First 1000 chars for preview
            "full_hex_length": len(block_hex),
        }

        minimal_path = Path(__file__).parent.parent / "tests" / "fixtures" / "test_block_hex.json"
        with open(minimal_path, "w") as f:
            json.dump(minimal_fixture, f, indent=2)

        print(f"Saved minimal fixture to: {minimal_path}")
    else:
        print("Failed to fetch block hex")


if __name__ == "__main__":
    main()
