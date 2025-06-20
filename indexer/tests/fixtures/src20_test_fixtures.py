"""
Pytest fixtures for SRC20 integration testing.

This module provides fixtures to load and manage real transaction data
for comprehensive integration testing of the SRC20 processing pipeline.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Optional

import pytest

logger = logging.getLogger(__name__)

# Paths
FIXTURES_DIR = Path(__file__).parent
TRANSACTION_CACHE_DIR = FIXTURES_DIR / "transaction_cache"
TRANSACTION_HASHES_FILE = FIXTURES_DIR / "real_src20_transaction_hashes.json"


@pytest.fixture(scope="session")
def transaction_hashes_data():
    """Load the categorized transaction hashes from JSON file."""
    if not TRANSACTION_HASHES_FILE.exists():
        pytest.skip(f"Transaction hashes file not found: {TRANSACTION_HASHES_FILE}")

    with open(TRANSACTION_HASHES_FILE, "r") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def cached_transactions():
    """Load all cached transaction data into memory for tests."""
    if not TRANSACTION_CACHE_DIR.exists():
        pytest.skip(f"Transaction cache directory not found: {TRANSACTION_CACHE_DIR}")

    transactions = {}
    cache_files = list(TRANSACTION_CACHE_DIR.glob("*.json"))

    # Skip summary file
    cache_files = [f for f in cache_files if f.name != "fetch_summary.json"]

    if not cache_files:
        pytest.skip("No cached transaction files found")

    for cache_file in cache_files:
        tx_hash = cache_file.stem  # filename without .json extension
        try:
            with open(cache_file, "r") as f:
                transactions[tx_hash] = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load cached transaction {tx_hash}: {e}")

    logger.info(f"Loaded {len(transactions)} cached transactions for testing")
    return transactions


@pytest.fixture
def invalid_transactions(transaction_hashes_data, cached_transactions):
    """Provide invalid SRC20 transactions for testing."""
    invalid_txs = []

    for tx_data in transaction_hashes_data.get("test_categories", {}).get("invalid_transactions", []):
        tx_hash = tx_data["tx_hash"]
        if tx_hash in cached_transactions:
            invalid_txs.append({"metadata": tx_data, "transaction_data": cached_transactions[tx_hash], "tx_hash": tx_hash})

    if not invalid_txs:
        pytest.skip("No invalid transactions available for testing")

    return invalid_txs


@pytest.fixture
def valid_transactions(transaction_hashes_data, cached_transactions):
    """Provide valid SRC20 transactions for testing."""
    valid_txs = []

    for tx_data in transaction_hashes_data.get("test_categories", {}).get("valid_transactions", []):
        tx_hash = tx_data["tx_hash"]
        if tx_hash in cached_transactions:
            valid_txs.append({"metadata": tx_data, "transaction_data": cached_transactions[tx_hash], "tx_hash": tx_hash})

    if not valid_txs:
        pytest.skip("No valid transactions available for testing")

    return valid_txs


@pytest.fixture
def transaction_by_hash(cached_transactions):
    """Provide a function to get transaction data by hash."""

    def get_transaction(tx_hash: str) -> Optional[Dict]:
        """Get transaction data by hash, or None if not found."""
        return cached_transactions.get(tx_hash)

    return get_transaction
