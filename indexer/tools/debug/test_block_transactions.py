#!/usr/bin/env python
"""
Consolidated test script to verify SRC-20 transactions in specific blocks.

This script provides a framework for testing SRC-20 transaction processing within
specific Bitcoin blocks. It contains predefined test cases for blocks 865002 and 867315,
which are important reference points for Bitcoin Stamps development.

Usage:
    python test_block_transactions.py [--block=BLOCK_NUMBER] [--verbose]

Examples:
    python test_block_transactions.py --block=865002  # Test 10.10 token deployment block
    python test_block_transactions.py --block=867315  # Test pi. token transactions block
"""

import argparse
import json
import logging
import os
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Add src to path
sys.path.insert(0, ".")

# Load environment variables from .env if exists
env_path = Path(".") / ".env"
if env_path.exists():
    logger.info(f"Loading environment variables from {env_path}")
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key] = value

# Import after environment setup
try:
    from btc_stamps_parser import FastTransactionParser
    from src.config import BTC_SRC20_OLGA_BLOCK, PREFIX, SRC20_VALID_TABLE
    from src.index_core import arc4, backend, blocks, script
    from src.index_core.backend import Backend
    from src.index_core.models import StampData
    from src.index_core.src20 import check_format, convert_to_utf8_string, matches_any_pattern, parse_src20
    from src.index_core.stamp import parse_stamp
    from src.index_core.util import escape_non_ascii_characters
except ImportError as e:
    logger.error(f"Failed to import required modules: {e}")
    logger.error("Make sure you're running this script from the /indexer directory")
    sys.exit(1)

# =====================================================================
# TEST CASE DATA
# =====================================================================

# Block 865002: Important SRC-20 transactions including "10.10" token deployment
BLOCK_865002_TX_HASHES = [
    "572be558f1260117c134c1d4a770a443a713c778c4afdfe4139a8da15cb5d5ef",  # The '10.10' tick
    "b87b0eba8256ceb2273b15093a7ad6b08d31dce0f1d1487a3384580ee8df9ce5",
    "582a46f2077fe53ec3d1b7cb49c9f962294d6dc261256413ba5968190f171a3f",
    "0d5a0c9f4e29646d2dbafab12aaad8465f9e2dc637697ef83899f9d7086cc56b",
    "a13ae5e83c9fa5047ed7a8eadaaece54a1074507491e37220062387d52215288",
    "9174184e356960de236d311d27e7e1d72c26a9733a394ff7b0be3e0918f728da",
    "b73e9595717961bba02736dcf5ffc72ddabb6e22c2af27147df490fef2f70c62",
    "93e044d86513bfca016945546b390daeb82085d38226e7398d8532bf33a815d0",
    "0c8abe2f767c63ab6eaf1509bf49dfdf24922b53f3759cd4d0b41c787e08c7f8",
    "ee9ff3706b0bf0828d4fa781315c1c72f7ef3fab9baf39c2769fee0929e0ca0f",
    "b1a697299c79349956ec570e288be0d89469a32d193573eaf262f40b5543ed20",
    "02de5fe97f9b3e8b363054fb62fe3757b9bb5cdf8f909d749e1afb8f64b32b41",
]

# Block 867315: Known pi. token transactions with detailed information
BLOCK_867315_PI_TRANSACTIONS = [
    {
        "tx_hash": "00d91249c4e66b49334388487c7dfc3c5403f837159badce7088cf6afe57d9cb",
        "tx_index": 787506,
        "creator": "bc1qqqy0jmg3u0w5rvykv3ejmkw0f8uguvzhjen36l",
        "destination": "bc1quhruqrghgcca950rvhtrg7cpd7u8k6svpzgzmrjy8xyukacl5lkq0r8l2d",
        "amount": Decimal("500000.000000000000000000"),
    },
    {
        "tx_hash": "a31fb0b06fd0580d9723820c70d465af755829407c9d9161feb96a173caca2b5",
        "tx_index": 787507,
        "creator": "bc1qqqy0jmg3u0w5rvykv3ejmkw0f8uguvzhjen36l",
        "destination": "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
        "amount": Decimal("5000000.000000000000000000"),
    },
    {
        "tx_hash": "f3ce106cb0fc412bfc3f63203d0771b62c0da6faf2baea786f42db9174b5712a",
        "tx_index": 787508,
        "creator": "bc1qqqy0jmg3u0w5rvykv3ejmkw0f8uguvzhjen36l",
        "destination": "bc1q7226jt0chcdst9glmty9uu38kd4mcgxv465h2x",
        "amount": Decimal("4500000.000000000000000000"),
    },
    {
        "tx_hash": "ce541e7c8cb9e97b612bc2b27cab62b607311dfc54b10e67d8c14f9f40795b62",
        "tx_index": 787509,
        "creator": "bc1qqqy0jmg3u0w5rvykv3ejmkw0f8uguvzhjen36l",
        "destination": "bc1qlu6d2yjfv7hvqz2504zlw2jdgszq9td4flzuyk",
        "amount": Decimal("4800000.000000000000000000"),
    },
    {
        "tx_hash": "d2f5e1bbe1a39b689f86d8be3d35c5b819881714afe72a20c410c0de19f956ef",
        "tx_index": 787510,
        "creator": "bc1qqqy0jmg3u0w5rvykv3ejmkw0f8uguvzhjen36l",
        "destination": "bc1qe3l23wxlu08vv062l3p35dah8kpjnaa7cd3chm",
        "amount": Decimal("3200000.000000000000000000"),
    },
    {
        "tx_hash": "da1a8d7f2821ef3c9fd7b3bf6bddbcda3cff65fee17caa23d0400379f57565fc",
        "tx_index": 787511,
        "creator": "bc1qqqy0jmg3u0w5rvykv3ejmkw0f8uguvzhjen36l",
        "destination": "bc1qu82kg99cjadkhc07t3mltgkd2d90535wqlxuz0",
        "amount": Decimal("3500000.000000000000000000"),
    },
    {
        "tx_hash": "db6e917b181ca1e16cfbe1b0da5bad1ec9e43ca4f2d0876af0c27bfab99500cc",
        "tx_index": 787512,
        "creator": "bc1qqqy0jmg3u0w5rvykv3ejmkw0f8uguvzhjen36l",
        "destination": "bc1qjud2ly9hudkyesd99p87den3h8qtzzhg0r9adv",
        "amount": Decimal("3400000.000000000000000000"),
    },
    {
        "tx_hash": "33bba3a9aaf98f4fa043dddf9c135d24049fd2102830b9dec32723281c13f9ea",
        "tx_index": 787513,
        "creator": "bc1qqqy0jmg3u0w5rvykv3ejmkw0f8uguvzhjen36l",
        "destination": "bc1pdgs68c4h0sngcnze3pss05yua2aqmmn0szxe2ujgqcdd3eud3x2qghdkge",
        "amount": Decimal("10000.000000000000000000"),
    },
]

# Extract just transaction hashes for block 867315
BLOCK_867315_TX_HASHES = [tx["tx_hash"] for tx in BLOCK_867315_PI_TRANSACTIONS]

# Map block numbers to their transaction data
BLOCK_TEST_DATA = {865002: BLOCK_865002_TX_HASHES, 867315: BLOCK_867315_TX_HASHES}

# =====================================================================
# MOCK DATABASE CLASS
# =====================================================================


class MockDB:
    """Mock database to track SQL queries and provide necessary responses"""

    def __init__(self, advanced_tracking=False):
        self.sql_inserts = []
        self.sql_params = []
        self.all_queries = []

        # Advanced tracking options (used for block 867315)
        self.advanced_tracking = advanced_tracking
        if advanced_tracking:
            self.balances = {}  # Track balances for addresses
            self.minted = {}  # Track minted amounts for ticks
            self.next_stamp_number = 1
            self.next_cursed_number = 1

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def execute(self, query, params=None):
        """Record the query and handle specific queries"""
        self.all_queries.append((query, params))

        if isinstance(query, str):
            # Handle SRC20_VALID_TABLE inserts
            if f"INSERT INTO {SRC20_VALID_TABLE}" in query:
                self.sql_inserts.append(query)
                if params:
                    self.sql_params.append(params)

            if self.advanced_tracking:
                # Handle balance queries
                if "balances" in query.lower() and "SELECT" in query.upper():
                    # Return empty balance for new addresses
                    return self

                # Handle mint total queries
                if "total_minted" in query.lower():
                    # Return 0 for new ticks
                    return self

                # Handle next stamp number queries
                if "SELECT MAX(stamp)" in query:
                    if "cursed" in query.lower():
                        return self  # Will return next_cursed_number in fetchone
                    else:
                        return self  # Will return next_stamp_number in fetchone

                # Handle reissue checks
                if "reissue" in query.lower():
                    return self  # Will return None in fetchone

        return self

    def fetchone(self):
        """Mock response for various queries"""
        # Get the last executed query
        if not self.all_queries:
            return None

        last_query, params = self.all_queries[-1]

        # Common queries
        if "src20_valid" in last_query.lower() and "deploy" in last_query.lower():
            return None  # No existing deploy

        if not self.advanced_tracking:
            return None

        # Advanced tracking queries (for block 867315)
        if "balances" in last_query.lower():
            return (0,)  # Return 0 balance

        if "total_minted" in last_query.lower():
            return (0,)  # Return 0 minted

        if "SELECT MAX(stamp)" in last_query:
            if "cursed" in last_query.lower():
                result = (self.next_cursed_number - 1,)
                self.next_cursed_number += 1
                return result
            else:
                result = (self.next_stamp_number - 1,)
                self.next_stamp_number += 1
                return result

        if "reissue" in last_query.lower():
            return None

        return None

    def fetchall(self):
        """Mock response for fetchall queries"""
        # Get the last executed query
        if not self.all_queries:
            return []

        last_query, params = self.all_queries[-1]

        # For balance queries - return empty list
        if "balances" in last_query.lower():
            return []

        return []

    def commit(self):
        """Mock commit operation"""
        pass

    def rollback(self):
        """Mock rollback operation"""
        pass


# =====================================================================
# MAIN FUNCTIONS
# =====================================================================


def get_transactions_from_block(block_index: int, tx_hashes: List[str]) -> Dict[str, str]:
    """Get transactions directly from our list of expected hashes."""
    logger.info(f"Getting transactions for block {block_index} using transaction hash list")

    # Initialize backend
    backend = Backend()

    # Get the block hash to verify it exists
    block_hash = backend.getblockhash(block_index)
    if not block_hash:
        logger.error(f"Could not get block hash for block {block_index}")
        return {}

    logger.info(f"Block {block_index} has hash {block_hash}")

    # Get transaction data directly for our expected hashes
    tx_data = {}
    found_count = 0
    for tx_hash in tx_hashes:
        tx_hex = backend.getrawtransaction(tx_hash)
        if tx_hex:
            tx_data[tx_hash] = tx_hex
            found_count += 1
        else:
            logger.warning(f"Could not get raw transaction for {tx_hash}")

    logger.info(f"Retrieved {found_count} out of {len(tx_hashes)} expected transactions")
    return tx_data


def test_expected_transactions_included(
    tx_data: Dict[str, str], expected_tx_hashes: List[str], block_index: int
) -> Tuple[int, int, Set[str]]:
    """Test that expected transactions are included in the filtered transactions."""
    # Initialize Rust parser
    parser = FastTransactionParser()

    # Process each transaction
    included_count = 0
    expected_found = 0
    missing_txs = set()

    for tx_hash, tx_hex in tx_data.items():
        # Parse with Rust parser
        tx_info = parser.deserialize_transaction(tx_hex)

        # Log transaction details
        should_include = tx_info.should_include
        has_valid_pattern = tx_info.has_valid_pattern if hasattr(tx_info, "has_valid_pattern") else False
        has_valid_data = tx_info.has_valid_data if hasattr(tx_info, "has_valid_data") else False
        keyburn = tx_info.keyburn

        if should_include:
            included_count += 1
            logger.info(
                f"Transaction {tx_hash} INCLUDED: pattern={has_valid_pattern}, data={has_valid_data}, keyburn={keyburn}"
            )

            # Check if this is the '10.10' tick transaction by processing with blocks module
            if block_index == 865002:
                try:
                    tx_result = blocks.process_tx(None, tx_hash, block_index, None, {tx_hash: tx_hex})
                    if tx_result and hasattr(tx_result, "data") and tx_result.data:
                        try:
                            json_data = json.loads(tx_result.data)
                            if json_data.get("p", "").lower() == "src-20" and json_data.get("tick") == "10.10":
                                logger.info(f"Found '10.10' tick transaction: {tx_hash}")
                        except Exception as e:
                            logger.warning(f"Error parsing JSON data for {tx_hash}: {e}")
                except Exception as e:
                    logger.warning(f"Error checking for '10.10' tick in {tx_hash}: {e}")
        else:
            logger.debug(
                f"Transaction {tx_hash} not included: pattern={has_valid_pattern}, data={has_valid_data}, keyburn={keyburn}"
            )

        # Check if this is one of our expected transactions
        if tx_hash in expected_tx_hashes:
            if should_include:
                expected_found += 1
                logger.info(f"✅ EXPECTED transaction {tx_hash} is included")
            else:
                logger.error(f"❌ EXPECTED transaction {tx_hash} is NOT included")
                missing_txs.add(tx_hash)

    # Check for missing transactions (not found in tx_data)
    for tx_hash in expected_tx_hashes:
        if tx_hash not in tx_data:
            logger.error(f"❌ EXPECTED transaction {tx_hash} was not retrieved from the node")
            missing_txs.add(tx_hash)

    return included_count, expected_found, missing_txs


def test_src20_processing_simplified(
    tx_data: Dict[str, str], expected_tx_hashes: List[str], block_index: int
) -> Tuple[int, int]:
    """Test SRC-20 processing for transactions (simplified version)."""
    processed_count = 0
    successful_count = 0

    # Initialize MockDB for tracking SQL operations
    db = MockDB()

    # Process each transaction in our expected list
    for tx_hash in expected_tx_hashes:
        if tx_hash not in tx_data:
            logger.error(f"❌ Expected transaction {tx_hash} not found in block data")
            continue

        tx_hex = tx_data[tx_hash]
        processed_count += 1

        # Initialize the FastTransactionParser
        parser = FastTransactionParser()
        tx_info = parser.deserialize_transaction(tx_hex)

        # Basic checks with FastTransactionParser
        if not tx_info.should_include:
            logger.error(f"❌ Transaction {tx_hash} not included by FastTransactionParser")
            continue

        # Process using blocks module
        try:
            # Process the transaction using our code
            tx_result = blocks.process_tx(None, tx_hash, block_index, None, {tx_hash: tx_hex})

            # Check if transaction was successfully processed
            if tx_result and tx_result.tx_hash == tx_hash:
                successful_count += 1
                logger.info(f"✅ Transaction {tx_hash} successfully processed")
            else:
                logger.error(f"❌ Transaction {tx_hash} processing did not return expected result")
        except Exception as e:
            logger.error(f"❌ Error processing transaction {tx_hash}: {e}")

    return processed_count, successful_count


def test_src20_processing_advanced(tx_data: Dict[str, str], expected_tx_hashes: List[str], block_index: int) -> Set[str]:
    """Test SRC-20 transaction processing (advanced version with StampData)"""
    logger.info(f"Testing SRC-20 processing for block {block_index} (advanced)")

    # Initialize mock database with advanced tracking
    mock_db = MockDB(advanced_tracking=True)

    # Initialize transaction parser
    parser = FastTransactionParser()

    # Track processed transactions
    processed_txs = set()

    # Process each transaction
    for tx_hash, raw_tx in tx_data.items():
        logger.info(f"\nProcessing transaction {tx_hash}")

        # Parse transaction
        tx_info = parser.deserialize_transaction(raw_tx)
        if not tx_info:
            logger.error(f"Failed to parse transaction {tx_hash}")
            continue

        # Check for should_include
        if not tx_info.should_include:
            logger.error(f"Transaction {tx_hash} should not be included according to FastTransactionParser")
            continue

        # Process transaction through blocks module
        try:
            tx_result = blocks.process_tx(None, tx_hash, block_index, None, {tx_hash: raw_tx})
            if not tx_result:
                logger.error(f"Failed to process transaction {tx_hash}")
                continue

            # Create StampData instance with required parameters
            stamp_data = StampData(
                tx_hash=tx_hash,
                source=tx_result.source,
                prev_tx_hash=getattr(tx_result, "prev_tx_hash", ""),
                destination=tx_result.destination,
                destination_nvalue=getattr(tx_result, "destination_nvalue", 0),
                btc_amount=getattr(tx_result, "btc_amount", 0),
                fee=getattr(tx_result, "fee", 0),
                data=tx_result.data,
                keyburn=tx_result.keyburn,
                tx_index=getattr(tx_result, "tx_index", 0),
                block_index=block_index,
                block_time=getattr(tx_result, "block_time", 0),
                is_op_return=tx_result.is_op_return,
            )

            # Parse and validate stamp
            try:
                # Check if it's a valid SRC-20 transaction
                if check_format(stamp_data.data, tx_hash):
                    processed_txs.add(tx_hash)
                    logger.info(f"Successfully processed SRC-20 transaction {tx_hash}")
                else:
                    logger.info(f"Transaction {tx_hash} is not a valid SRC-20 transaction")
            except Exception as e:
                logger.error(f"Error checking SRC-20 format for {tx_hash}: {str(e)}")
        except Exception as e:
            logger.error(f"Error processing transaction {tx_hash}: {str(e)}")
            continue

    # Check results
    missing_txs = set(expected_tx_hashes) - processed_txs
    logger.info(f"\nProcessed {len(processed_txs)} out of {len(expected_tx_hashes)} expected transactions")
    if missing_txs:
        logger.error("Missing transactions:")
        for tx_hash in missing_txs:
            logger.error(f"- {tx_hash}")
    else:
        logger.info("All expected transactions were processed successfully")

    return processed_txs


def test_block(block_index: int, verbose: bool = False):
    """Main test function that can test any block with predefined test data."""
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Check if we have test data for this block
    if block_index not in BLOCK_TEST_DATA:
        logger.error(f"No test data available for block {block_index}")
        logger.info(f"Available blocks for testing: {sorted(BLOCK_TEST_DATA.keys())}")
        return

    tx_hashes = BLOCK_TEST_DATA[block_index]
    logger.info(f"Testing block {block_index}")
    logger.info(f"Expected transactions: {len(tx_hashes)}")

    # Get transactions from the block
    tx_data = get_transactions_from_block(block_index, tx_hashes)
    if not tx_data:
        logger.error("No transactions found")
        return

    # Test 1: Count of included transactions with Rust parser
    included_count, expected_found, missing_txs = test_expected_transactions_included(tx_data, tx_hashes, block_index)

    logger.info(f"Total transactions retrieved: {len(tx_data)}")
    logger.info(f"Included transactions: {included_count}")
    logger.info(f"Expected transactions found: {expected_found} out of {len(tx_hashes)}")

    if missing_txs:
        logger.error(f"❌ Missing expected transactions: {missing_txs}")
    else:
        logger.info("✅ All expected transactions are included")

    # Test 2: Process transactions using blocks module
    if block_index == 865002:
        # Use simplified processing for 865002
        processed_count, successful_count = test_src20_processing_simplified(tx_data, tx_hashes, block_index)
        logger.info(f"Transactions processed: {processed_count}")
        logger.info(f"Transactions successfully processed: {successful_count}")

        # Overall test result
        if not missing_txs and successful_count == len(tx_hashes):
            logger.info("✅ TEST PASSED: All expected transactions are processed correctly")
        else:
            logger.error("❌ TEST FAILED: Some expected transactions are not processed correctly")

    elif block_index == 867315:
        # Use advanced processing for 867315
        processed_txs = test_src20_processing_advanced(tx_data, tx_hashes, block_index)

        # Overall test result
        if not missing_txs and len(processed_txs) == len(tx_hashes):
            logger.info("✅ TEST PASSED: All expected transactions are processed correctly")
        else:
            logger.error("❌ TEST FAILED: Some expected transactions are not processed correctly")
            missing_processed = set(tx_hashes) - processed_txs
            if missing_processed:
                logger.error(f"Missing processed transactions: {missing_processed}")


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Test SRC-20 transaction processing in specific blocks")
    parser.add_argument(
        "--block", type=int, default=865002, help="Block number to test (default: 865002, also available: 867315)"
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    test_block(args.block, args.verbose)
