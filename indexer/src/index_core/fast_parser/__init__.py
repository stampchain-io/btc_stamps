"""Fast Bitcoin transaction parser using Rust."""

import logging
from typing import Dict, List, Optional, Tuple

from btc_stamps_parser import FastTransactionParser, TransactionInfo

logger = logging.getLogger(__name__)


class FastParser:
    """Fast Bitcoin transaction parser using Rust."""

    def __init__(self):
        """Initialize the parser."""
        self._parser = FastTransactionParser()

    def deserialize_transaction(self, tx_hex: str) -> TransactionInfo:
        """
        Deserialize a transaction from hex string.

        Args:
            tx_hex: Transaction hex string

        Returns:
            TransactionInfo object containing parsed transaction data
        """
        return self._parser.deserialize_transaction(tx_hex)

    def batch_parse_transactions(self, tx_hexes: List[str]) -> List[TransactionInfo]:
        """
        Parse multiple transactions in parallel.

        Args:
            tx_hexes: List of transaction hex strings

        Returns:
            List of TransactionInfo objects
        """
        return self._parser.batch_parse_transactions(tx_hexes)

    def parse_block(self, block_hex: str) -> Tuple[List[str], Dict[str, str], int, Optional[str], Optional[float]]:
        """
        Parse a block and return transaction information.

        Args:
            block_hex: Block hex string

        Returns:
            Tuple containing:
            - List of transaction hashes
            - Dict mapping transaction hash to raw hex
            - Block timestamp
            - Previous block hash
            - Block bits (difficulty)
        """
        try:
            # The Rust parser now returns a tuple directly
            tx_hash_list, raw_transactions, timestamp, prev_block_hash, bits = self._parser.parse_block(block_hex)
            return tx_hash_list, raw_transactions, timestamp, prev_block_hash, bits
        except Exception as e:
            logger.error(f"Error parsing block: {e}")
            raise
