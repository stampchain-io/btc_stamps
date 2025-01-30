"""Fast Bitcoin transaction parser using Rust."""

import gc
import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import psutil
from bitcoin.core import COutPoint, CScript, CTransaction, CTxIn, CTxOut, x

try:
    from btc_stamps_parser import FastTransactionParser

    RUST_PARSER_AVAILABLE = True
except ImportError:
    RUST_PARSER_AVAILABLE = False
    logging.warning("Rust parser not available. Make sure to build it with 'poetry run maturin develop'")

# Configure garbage collection for better performance
gc.set_threshold(25000, 10, 10)  # Adjust primary threshold for less frequent collections

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
            self._process = psutil.Process()
            self._last_gc_time = 0
            self._memory_threshold = 85.0  # Memory threshold percentage
            self._chunk_size = 1000
            self._gc_chunk_interval = 5  # Number of chunks before GC
            logger.info("Initialized Rust parser backend with optimized GC settings")
        except Exception as e:
            logger.error(f"Failed to initialize Rust parser: {e}")
            raise ParserError(f"Parser initialization failed: {e}")

    def _should_collect_garbage(self, force_check: bool = False) -> bool:
        """
        Determine if garbage collection should be performed based on memory usage
        and time since last collection.
        """
        try:
            current_memory = self._process.memory_percent()
            if current_memory > self._memory_threshold or force_check:
                # Get generation counts before collection
                counts = gc.get_count()
                if counts[0] > 10000 or counts[1] > 1000 or counts[2] > 100:
                    return True
            return False
        except Exception as e:
            logger.warning(f"Memory check failed: {e}")
            return force_check

    def _perform_garbage_collection(self):
        """Perform optimized garbage collection."""
        try:
            # Get memory usage before collection
            mem_before = self._process.memory_percent()

            # Perform generational garbage collection
            gen2_count = gc.get_count()[2]
            if gen2_count > 100:
                # Full collection needed
                gc.collect()
            else:
                # Collect only younger generations
                gc.collect(0)
                if gc.get_count()[1] > 1000:
                    gc.collect(1)

            # Log memory change if significant
            mem_after = self._process.memory_percent()
            if mem_before - mem_after > 5.0:  # If we freed more than 5% of memory
                logger.debug(f"GC freed memory: {mem_before:.1f}% -> {mem_after:.1f}%")

        except Exception as e:
            logger.warning(f"Garbage collection error: {e}")
            gc.collect()  # Fallback to full collection

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
        """Parse multiple transactions in parallel with optimized memory management."""
        try:
            total_txs = len(tx_hexes)
            # Pre-allocate list with final size to avoid resizing overhead
            results: List[CTransaction] = [None] * total_txs  # type: ignore

            for i in range(0, total_txs, self._chunk_size):
                chunk = tx_hexes[i : i + self._chunk_size]
                end_idx = i + len(chunk)

                # Process chunk and assign directly to pre-allocated slice
                tx_infos = self._parser.batch_parse_transactions(chunk)
                # Use list comprehension instead of generator for faster execution
                results[i:end_idx] = [self._convert_to_ctransaction(tx_info) for tx_info in tx_infos]

                # Check if garbage collection is needed
                if i > 0 and (i % (self._chunk_size * self._gc_chunk_interval) == 0):
                    if self._should_collect_garbage(force_check=(i / total_txs > 0.5)):
                        self._perform_garbage_collection()

            return results
        except Exception as e:
            logger.error(f"Failed to batch parse transactions: {e}")
            raise ParserError(f"Batch transaction parsing failed: {e}")

    def parse_block(self, block_hex: str) -> Tuple[List[str], Dict[str, str], int, Optional[str], Optional[float]]:
        """Parse a block with optimized memory management."""
        try:
            block_info = self._parser.parse_block(block_hex)
            tx_hash_list = []
            raw_transactions = {}

            total_txs = len(block_info.transactions)
            for i in range(0, total_txs, self._chunk_size):
                chunk = block_info.transactions[i : i + self._chunk_size]
                for tx in chunk:
                    tx_hash_list.append(tx.txid)
                    raw_transactions[tx.txid] = tx.hex

                # Check if garbage collection is needed
                if i > 0 and (i % (self._chunk_size * self._gc_chunk_interval) == 0):
                    if self._should_collect_garbage(force_check=(i / total_txs > 0.5)):
                        self._perform_garbage_collection()

            return (
                tx_hash_list,
                raw_transactions,
                block_info.timestamp,
                block_info.prev_block_hash,
                None,
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
                    COutPoint(x(input_info.prev_txid)[::-1], input_info.prev_vout),
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
