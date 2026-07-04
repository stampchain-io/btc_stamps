#!/usr/bin/env python3
"""
Test the correct verbose=true safe pagination workaround for block 784320.
"""

import asyncio
import os
import sys

# Add the indexer directory to Python path
if os.getcwd().endswith("/indexer"):
    sys.path.append("src")
else:
    sys.path.append(os.path.join(os.getcwd(), "src"))

# Load environment variables
from dotenv import load_dotenv

dotenv_path = os.path.join(os.getcwd(), ".env")
load_dotenv(dotenv_path=dotenv_path, override=True)

from index_core.fetch_utils import _fetch_block_transactions_verbose_safe_pagination


async def test_safe_pagination_workaround():
    """Test the correct workaround for block 784320."""
    print("🔍 Testing verbose=true safe pagination workaround for block 784320")

    try:
        # Test the safe pagination workaround
        result = await _fetch_block_transactions_verbose_safe_pagination(784320)

        if result:
            print(f"✅ Successfully fetched block 784320 data:")
            print(f"   Block index: {result['block_index']}")
            print(f"   Transactions: {len(result.get('transactions', []))}")
            print(f"   Issuances: {len(result.get('issuances', []))}")

            # Show some transaction details
            transactions = result.get("transactions", [])
            for i, tx in enumerate(transactions[:3]):  # Show first 3
                events_count = len(tx.get("events", []))
                print(f"   TX {i+1}: {tx.get('tx_hash', '')[:8]}... Events: {events_count}")

            if len(transactions) > 3:
                print(f"   ... and {len(transactions) - 3} more transactions")

            return True
        else:
            print("❌ Failed to fetch block data")
            return False

    except Exception as e:
        print(f"❌ Error: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_safe_pagination_workaround())
    sys.exit(0 if success else 1)
