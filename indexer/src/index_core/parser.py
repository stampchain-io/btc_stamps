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


class EnhancedCTransaction:
    """
    Enhanced CTransaction wrapper that can store additional attributes.
    This is a wrapper around CTransaction that allows storing additional attributes
    while maintaining compatibility with the original CTransaction class.
    """

    def __init__(self, ctx, **kwargs):
        """
        Create a new EnhancedCTransaction instance.

        Args:
            ctx: A CTransaction instance
            **kwargs: Additional attributes to store

        Returns:
            An EnhancedCTransaction instance
        """
        if not isinstance(ctx, CTransaction):
            raise TypeError("EnhancedCTransaction must be created with a CTransaction instance")

        # Store the CTransaction instance
        self._ctx = ctx

        # Store additional attributes
        self._extra_attrs = kwargs

    def __getattr__(self, name):
        """
        Get an attribute from the CTransaction instance or _extra_attrs dictionary.

        Args:
            name: The name of the attribute

        Returns:
            The attribute value

        Raises:
            AttributeError: If the attribute doesn't exist
        """
        # First check in extra attributes
        if name in self._extra_attrs:
            return self._extra_attrs[name]

        # Then check in the CTransaction instance
        if hasattr(self._ctx, name):
            return getattr(self._ctx, name)

        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")


class ParserError(Exception):
    """Base exception for parser errors."""

    pass


class Parser:
    """Fast Bitcoin transaction parser using Rust."""

    # Singleton instance
    _instance = None

    def __new__(cls):
        """Ensure only one instance of Parser exists."""
        if cls._instance is None:
            cls._instance = super(Parser, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize the parser with Rust backend."""
        # Only initialize once
        if self._initialized:
            return

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
            self._initialized = True
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
            logger.debug(f"Starting batch parsing of {total_txs} transactions")

            # Use a smaller chunk size for very large batches
            adaptive_chunk_size = min(self._chunk_size, max(100, 10000 // (1 + (total_txs // 5000))))
            logger.debug(f"Using adaptive chunk size of {adaptive_chunk_size} for {total_txs} transactions")

            # Results will now be a list of transactions that should be included
            results = []

            for i in range(0, total_txs, adaptive_chunk_size):
                chunk = tx_hexes[i : i + adaptive_chunk_size]

                logger.debug(
                    f"Processing chunk {i//adaptive_chunk_size + 1}/{(total_txs + adaptive_chunk_size - 1)//adaptive_chunk_size} with {len(chunk)} transactions"
                )

                # Process chunk
                try:
                    # The Rust parser now only returns transactions that should be included
                    tx_infos = self._parser.batch_parse_transactions(chunk)
                    logger.debug(f"Rust parser returned {len(tx_infos)} filtered results for {len(chunk)} inputs in chunk")

                    # Convert TransactionInfo objects to CTransaction objects
                    for tx_info in tx_infos:
                        try:
                            # Convert to EnhancedCTransaction
                            ctx = self._convert_to_ctransaction(tx_info)
                            # Verify that txid attribute is accessible
                            _ = ctx.txid  # This should not raise an AttributeError
                            results.append(ctx)
                        except Exception as e:
                            logger.error(f"Error converting transaction: {e}")
                            # Continue with next transaction instead of failing the entire batch

                except Exception as e:
                    logger.error(f"Error processing chunk {i//adaptive_chunk_size + 1}: {e}")
                    # Continue with next chunk instead of failing the entire batch

                # Check if garbage collection is needed
                if i > 0 and (i % (adaptive_chunk_size * self._gc_chunk_interval) == 0):
                    if self._should_collect_garbage(force_check=(i / total_txs > 0.5)):
                        self._perform_garbage_collection()

            logger.debug(f"Completed batch parsing: {len(results)} transactions included out of {total_txs} processed")

            return results
        except Exception as e:
            logger.error(f"Failed to batch parse transactions: {e}")
            raise ParserError(f"Batch transaction parsing failed: {e}")

    def parse_block(self, block_hex: str) -> Tuple[List[str], Dict[str, str], int, Optional[str], Optional[float]]:
        """Parse a block with optimized memory management."""
        try:
            # The Rust parser now returns a tuple directly
            tx_hash_list, raw_transactions, timestamp, prev_block_hash, bits = self._parser.parse_block(block_hex)
            return (
                tx_hash_list,
                raw_transactions,
                timestamp,
                prev_block_hash,
                bits,  # This will be converted to float by the caller if needed
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

            # Create CTransaction with only the parameters it accepts
            ctx = CTransaction(vin, vout, nVersion=tx_info.version)

            # Now create the enhanced transaction with the original CTransaction
            # and add the extra attributes separately
            enhanced_ctx = EnhancedCTransaction(ctx)

            # Set extra attributes through the _extra_attrs dictionary
            enhanced_ctx._extra_attrs["txid"] = tx_info.txid
            enhanced_ctx._extra_attrs["should_include"] = tx_info.should_include
            enhanced_ctx._extra_attrs["has_valid_data"] = tx_info.has_valid_data
            enhanced_ctx._extra_attrs["keyburn"] = tx_info.keyburn

            return enhanced_ctx
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
