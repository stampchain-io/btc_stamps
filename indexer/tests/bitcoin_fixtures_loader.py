"""
Bitcoin fixtures loader utility.

This module provides utilities for loading and working with Bitcoin node fixtures
used in tests that were migrated from requiring live Bitcoin node connectivity.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Union

logger = logging.getLogger(__name__)


class BitcoinFixturesLoader:
    """
    Utility class for loading and accessing Bitcoin fixtures data.

    This class provides a convenient interface for tests to access Bitcoin
    transaction and block data from fixtures without requiring a live Bitcoin node.
    """

    def __init__(self, fixtures_path: Optional[Union[str, Path]] = None):
        """
        Initialize the fixtures loader.

        Args:
            fixtures_path: Path to the bitcoin_node_fixtures.json file.
                          If None, uses the default location in tests/fixtures/
        """
        if fixtures_path is None:
            fixtures_path = Path(__file__).parent / "fixtures" / "bitcoin_node_fixtures.json"

        self.fixtures_path = Path(fixtures_path)
        self._fixtures_data = None

    def _load_fixtures(self) -> Dict:
        """Load fixtures data from file (cached after first load)."""
        if self._fixtures_data is None:
            logger.debug(f"Loading Bitcoin fixtures from {self.fixtures_path}")
            with open(self.fixtures_path, "r") as f:
                self._fixtures_data = json.load(f)
            logger.debug(f"Loaded fixtures with keys: {list(self._fixtures_data.keys())}")
        return self._fixtures_data

    @property
    def fixtures_data(self) -> Dict:
        """Get the complete fixtures data."""
        return self._load_fixtures()

    def get_special_transactions(self) -> List[Dict]:
        """
        Get all special transactions from fixtures.

        Returns:
            List of transaction dictionaries, each containing:
            - txid: Transaction ID
            - hex: Raw transaction hex data
            - description: Description of what the transaction tests
        """
        return self.fixtures_data.get("special_transactions", [])

    def get_special_transaction(self, txid: str) -> Optional[Dict]:
        """
        Get a specific special transaction by TXID.

        Args:
            txid: The transaction ID to look for

        Returns:
            Transaction dictionary if found, None otherwise
        """
        for tx in self.get_special_transactions():
            if tx.get("txid") == txid:
                return tx
        return None

    def get_special_transaction_hex(self, txid: str) -> Optional[str]:
        """
        Get the raw hex data for a special transaction.

        Args:
            txid: The transaction ID to look for

        Returns:
            Raw transaction hex string if found, None otherwise
        """
        tx = self.get_special_transaction(txid)
        return tx.get("hex") if tx else None

    def get_test_block_data(self) -> Optional[Dict]:
        """
        Get test block data from fixtures.

        Returns:
            Block dictionary containing:
            - height: Block height
            - hash: Block hash
            - hex: Raw block hex data
        """
        return self.fixtures_data.get("test_block_700000")

    def get_test_block_hex(self) -> Optional[str]:
        """
        Get the raw hex data for the test block.

        Returns:
            Raw block hex string if available, None otherwise
        """
        block_data = self.get_test_block_data()
        return block_data.get("hex") if block_data else None

    def get_metadata(self) -> Dict:
        """
        Get metadata about the fixtures.

        Returns:
            Metadata dictionary with information about the fixtures
        """
        return self.fixtures_data.get("metadata", {})

    def create_mock_getrawtransaction(self):
        """
        Create a mock getrawtransaction function for use in tests.

        Returns:
            Function that can be used to mock backend.getrawtransaction()
        """
        special_txs = {tx["txid"]: tx["hex"] for tx in self.get_special_transactions()}

        def mock_getrawtransaction(txid: str) -> str:
            if txid in special_txs:
                return special_txs[txid]
            raise Exception(f"Transaction {txid} not found in fixtures")

        return mock_getrawtransaction

    def create_mock_rpc(self):
        """
        Create a mock RPC function for use in tests.

        Returns:
            Function that can be used to mock backend.rpc()
        """
        test_block = self.get_test_block_data()

        def mock_rpc(method: str, params: List):
            if method == "getblockcount":
                return test_block.get("height", 700000) if test_block else 700000
            elif method == "getblock":
                if len(params) < 1:
                    raise Exception("getblock requires block hash parameter")

                block_hash = params[0]
                verbosity = params[1] if len(params) > 1 else 1

                if test_block and block_hash == test_block.get("hash"):
                    if verbosity == 0:
                        # Return raw block data
                        return test_block.get("hex", "")
                    else:
                        # Return structured block data
                        return {
                            "hash": test_block.get("hash"),
                            "height": test_block.get("height"),
                            "tx": [],  # Would contain transaction list in real data
                        }
                else:
                    raise Exception(f"Block {block_hash} not found in fixtures")
            else:
                raise Exception(f"RPC method {method} not mocked")

        return mock_rpc

    def validate_fixtures(self) -> bool:
        """
        Validate that the fixtures data is complete and well-formed.

        Returns:
            True if fixtures are valid, False otherwise
        """
        try:
            data = self.fixtures_data

            # Check top-level structure
            required_keys = ["special_transactions", "test_block_700000"]
            for key in required_keys:
                if key not in data:
                    logger.error(f"Missing required key: {key}")
                    return False

            # Validate special transactions
            special_txs = data["special_transactions"]
            if not isinstance(special_txs, list) or len(special_txs) == 0:
                logger.error("special_transactions must be a non-empty list")
                return False

            for i, tx in enumerate(special_txs):
                required_tx_keys = ["txid", "hex", "description"]
                for key in required_tx_keys:
                    if key not in tx:
                        logger.error(f"Transaction {i} missing required key: {key}")
                        return False

                if not tx["txid"] or not tx["hex"]:
                    logger.error(f"Transaction {i} has empty txid or hex")
                    return False

            # Validate test block
            test_block = data["test_block_700000"]
            required_block_keys = ["height", "hash", "hex"]
            for key in required_block_keys:
                if key not in test_block:
                    logger.error(f"Test block missing required key: {key}")
                    return False

            if not test_block["hash"] or not test_block["hex"]:
                logger.error("Test block has empty hash or hex")
                return False

            logger.info("Bitcoin fixtures validation passed")
            return True

        except Exception as e:
            logger.error(f"Error validating fixtures: {e}")
            return False


# Convenience functions for quick access
def load_bitcoin_fixtures(fixtures_path: Optional[Union[str, Path]] = None) -> BitcoinFixturesLoader:
    """
    Load Bitcoin fixtures with default path.

    Args:
        fixtures_path: Optional custom path to fixtures file

    Returns:
        BitcoinFixturesLoader instance
    """
    return BitcoinFixturesLoader(fixtures_path)


def get_special_transaction_hex(txid: str, fixtures_path: Optional[Union[str, Path]] = None) -> Optional[str]:
    """
    Quick access to get hex data for a special transaction.

    Args:
        txid: Transaction ID to look for
        fixtures_path: Optional custom path to fixtures file

    Returns:
        Raw transaction hex string if found, None otherwise
    """
    loader = load_bitcoin_fixtures(fixtures_path)
    return loader.get_special_transaction_hex(txid)


def get_test_block_hex(fixtures_path: Optional[Union[str, Path]] = None) -> Optional[str]:
    """
    Quick access to get hex data for the test block.

    Args:
        fixtures_path: Optional custom path to fixtures file

    Returns:
        Raw block hex string if available, None otherwise
    """
    loader = load_bitcoin_fixtures(fixtures_path)
    return loader.get_test_block_hex()
