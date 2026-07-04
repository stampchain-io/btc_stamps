#!/usr/bin/env python3
"""
Fetch real SRC20 transaction data for integration testing.

This script reads the transaction hashes from real_src20_transaction_hashes.json
and fetches the complete transaction data from public APIs, caching it locally
for repeatable integration testing.
"""

import json
import logging
import sys
from pathlib import Path
from typing import List

# Add the indexer src directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from transaction_fetcher import TransactionFetcher

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def load_transaction_hashes() -> List[str]:
    """Load all transaction hashes from our JSON file."""
    hash_file = Path(__file__).parent.parent / "fixtures" / "real_src20_transaction_hashes.json"

    if not hash_file.exists():
        logger.error(f"Transaction hash file not found: {hash_file}")
        return []

    try:
        with open(hash_file, "r") as f:
            data = json.load(f)

        # Extract all transaction hashes from all categories
        all_hashes = []
        for category_name, transactions in data.get("test_categories", {}).items():
            logger.info(f"Loading {len(transactions)} hashes from {category_name}")
            for tx in transactions:
                if isinstance(tx, dict) and "tx_hash" in tx:
                    all_hashes.append(tx["tx_hash"])
                elif isinstance(tx, str):
                    all_hashes.append(tx)

        # Remove duplicates while preserving order
        unique_hashes = []
        seen = set()
        for h in all_hashes:
            if h not in seen:
                unique_hashes.append(h)
                seen.add(h)

        logger.info(f"Loaded {len(unique_hashes)} unique transaction hashes")
        return unique_hashes

    except Exception as e:
        logger.error(f"Failed to load transaction hashes: {e}")
        return []


def fetch_all_transactions(force_refresh: bool = False):
    """Fetch all transaction data and cache it locally."""
    tx_hashes = load_transaction_hashes()

    if not tx_hashes:
        logger.error("No transaction hashes to fetch")
        return

    fetcher = TransactionFetcher()

    logger.info(f"Starting to fetch {len(tx_hashes)} transactions...")
    logger.info("This may take several minutes due to API rate limiting")

    results = fetcher.fetch_multiple_transactions(tx_hashes, force_refresh)

    # Report results
    successful = sum(1 for data in results.values() if data is not None)
    failed = len(results) - successful

    logger.info(f"Fetch complete: {successful} successful, {failed} failed")

    if failed > 0:
        logger.warning("Failed transactions:")
        for tx_hash, data in results.items():
            if data is None:
                logger.warning(f"  - {tx_hash}")

    # Create a summary report
    summary_file = Path(__file__).parent.parent / "fixtures" / "transaction_cache" / "fetch_summary.json"
    summary = {
        "total_requested": len(tx_hashes),
        "successful": successful,
        "failed": failed,
        "success_rate": (successful / len(tx_hashes)) * 100 if tx_hashes else 0,
        "failed_hashes": [h for h, d in results.items() if d is None],
        "successful_hashes": [h for h, d in results.items() if d is not None],
    }

    try:
        with open(summary_file, "w") as f:
            json.dump(summary, f, indent=2)
        logger.info(f"Summary report saved to: {summary_file}")
    except Exception as e:
        logger.warning(f"Failed to save summary report: {e}")


def validate_cached_data():
    """Validate that cached transaction data has the expected structure."""
    cache_dir = Path(__file__).parent.parent / "fixtures" / "transaction_cache"

    if not cache_dir.exists():
        logger.error("Cache directory does not exist")
        return False

    json_files = list(cache_dir.glob("*.json"))
    if not json_files:
        logger.error("No cached transaction files found")
        return False

    # Skip the summary file
    json_files = [f for f in json_files if f.name != "fetch_summary.json"]

    logger.info(f"Validating {len(json_files)} cached transaction files...")

    valid_count = 0
    invalid_count = 0

    for json_file in json_files:
        try:
            with open(json_file, "r") as f:
                data = json.load(f)

            # Basic validation
            required_fields = ["source", "tx_hash", "hex"]
            missing_fields = [field for field in required_fields if field not in data]

            if missing_fields:
                logger.warning(f"{json_file.name}: Missing fields: {missing_fields}")
                invalid_count += 1
            else:
                # Additional validation
                if not data.get("hex"):
                    logger.warning(f"{json_file.name}: Empty hex data")
                    invalid_count += 1
                elif not isinstance(data.get("hex"), str):
                    logger.warning(f"{json_file.name}: Invalid hex data type")
                    invalid_count += 1
                else:
                    valid_count += 1

        except Exception as e:
            logger.error(f"Failed to validate {json_file.name}: {e}")
            invalid_count += 1

    logger.info(f"Validation complete: {valid_count} valid, {invalid_count} invalid")
    return invalid_count == 0


def main():
    """Main execution function."""
    import argparse

    parser = argparse.ArgumentParser(description="Fetch SRC20 transaction data for testing")
    parser.add_argument("--force-refresh", action="store_true", help="Force refresh of cached data")
    parser.add_argument("--validate-only", action="store_true", help="Only validate existing cached data")
    parser.add_argument("--clear-cache", action="store_true", help="Clear all cached data before fetching")

    args = parser.parse_args()

    if args.clear_cache:
        fetcher = TransactionFetcher()
        fetcher.clear_cache()
        logger.info("Cache cleared")

    if args.validate_only:
        success = validate_cached_data()
        sys.exit(0 if success else 1)
    else:
        fetch_all_transactions(args.force_refresh)
        validate_cached_data()


if __name__ == "__main__":
    main()
