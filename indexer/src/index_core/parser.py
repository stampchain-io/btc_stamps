"""Fast Bitcoin transaction parser using Rust."""

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from bitcoin.core import COutPoint, CScript, CTransaction, CTxIn, CTxOut, x

try:
    from btc_stamps_parser import FastTransactionParser

    RUST_PARSER_AVAILABLE = True
except ImportError:
    RUST_PARSER_AVAILABLE = False
    logging.warning("Rust parser not available. Make sure to build it with 'poetry run maturin develop'")

logger = logging.getLogger(__name__)


class ParserError(Exception):
    """Base exception for parser errors."""

    pass


class Parser:
    """Fast Bitcoin transaction parser using Rust."""

    def __init__(self):
        """Initialize the parser with Rust backend."""
        if not RUST_PARSER_AVAILABLE:
            raise ParserError("Rust parser not available. Run 'poetry run maturin develop' in the indexer directory")

        try:
            self._parser = FastTransactionParser()
            logger.debug("Initialized Rust parser backend")
        except Exception as e:
            logger.error(f"Failed to initialize Rust parser: {e}")
            raise ParserError(f"Parser initialization failed: {e}")

    def deserialize_transaction(self, tx_hex: str) -> CTransaction:
        """
        Deserialize a transaction from hex string.
        Returns a CTransaction object for compatibility with existing code.
        """
        try:
            tx_info = self._parser.deserialize_transaction(tx_hex)
            return self._convert_to_ctransaction(tx_info)
        except Exception as e:
            logger.error(f"Failed to parse transaction: {e}")
            raise ParserError(f"Transaction parsing failed: {e}")

    def batch_parse_transactions(self, tx_hexes: List[str]) -> List[CTransaction]:
        """
        Parse multiple transactions in parallel.
        Returns CTransaction objects for compatibility.
        """
        try:
            tx_infos = self._parser.batch_parse_transactions(tx_hexes)
            return [self._convert_to_ctransaction(tx_info) for tx_info in tx_infos]
        except Exception as e:
            logger.error(f"Failed to batch parse transactions: {e}")
            raise ParserError(f"Batch transaction parsing failed: {e}")

    def parse_block(self, block_hex: str) -> Tuple[List[str], Dict[str, str], int, Optional[str], Optional[float]]:
        """Parse a block and return transaction information."""
        try:
            block_info = self._parser.parse_block(block_hex)

            tx_hash_list = []
            raw_transactions = {}

            for tx in block_info.transactions:
                tx_hash_list.append(tx.txid)
                raw_transactions[tx.txid] = tx.hex

            return (
                tx_hash_list,
                raw_transactions,
                block_info.timestamp,
                block_info.prev_block_hash,
                None,  # Difficulty not included in current implementation
            )
        except Exception as e:
            logger.error(f"Failed to parse block: {e}")
            raise ParserError(f"Block parsing failed: {e}")

    def _convert_to_ctransaction(self, tx_info: Any) -> CTransaction:
        """Convert Rust TransactionInfo to Python CTransaction."""
        try:
            # Convert inputs
            vin = [
                CTxIn(
                    COutPoint(x(input_info.prev_txid)[::-1], input_info.prev_vout),  # Create proper COutPoint
                    b"",  # Empty scriptSig
                    input_info.sequence,
                )
                for input_info in tx_info.inputs
            ]

            # Convert outputs
            vout = [
                CTxOut(nValue=output_info.value, scriptPubKey=CScript(bytes.fromhex(output_info.script_pubkey)))
                for output_info in tx_info.outputs
            ]

            # Create CTransaction
            ctx = CTransaction(vin, vout, nVersion=tx_info.version)
            return ctx
        except Exception as e:
            logger.error(f"Failed to convert transaction info: {e}")
            raise ParserError(f"Transaction conversion failed: {e}")

    def _convert_tx_info(self, tx_info: Any) -> Dict[str, Any]:
        """Convert TransactionInfo to dictionary format (for API responses)."""
        try:
            return {
                "txid": tx_info.txid,
                "version": tx_info.version,
                "inputs": [
                    {
                        "prev_txid": input_info.prev_txid,
                        "prev_vout": input_info.prev_vout,
                        "sequence": input_info.sequence,
                    }
                    for input_info in tx_info.inputs
                ],
                "outputs": [
                    {
                        "value": Decimal(str(output_info.value)) / Decimal("100000000"),
                        "script_pubkey": output_info.script_pubkey,
                        "is_op_return": output_info.is_op_return,
                    }
                    for output_info in tx_info.outputs
                ],
            }
        except Exception as e:
            logger.error(f"Failed to convert transaction info: {e}")
            raise ParserError(f"Transaction conversion failed: {e}")
