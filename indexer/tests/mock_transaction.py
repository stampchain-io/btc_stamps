"""
Mock transaction processing module for testing.

This module provides mock implementations of transaction processing
functions for use in test cases only. It is not part of the actual
indexer codebase and should only be used for testing purposes.

Note: In a real implementation, these functions would be part of the
main codebase in src/index_core/transaction.py, but since they're only
needed for testing, we keep them separate to avoid polluting the
actual codebase with test-specific code.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from index_core.backend import Backend

logger = logging.getLogger(__name__)


def process_transactions(tx_hashes: List[str], output_file: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Mock implementation of process_transactions for testing.

    Args:
        tx_hashes: List of transaction hashes to process
        output_file: Optional path to save the results as JSON

    Returns:
        List of processed transaction details
    """
    logger.info(f"[MOCK] Processing {len(tx_hashes)} transactions")

    backend = Backend()
    results = []

    for tx_hash in tx_hashes:
        try:
            # Get the raw transaction data
            tx_hex = backend.getrawtransaction(tx_hash)

            # In a real implementation, we would parse the transaction here
            # For this example, we'll just create a simple result
            tx_info = {
                "txid": tx_hash,
                "hex": tx_hex,
                "size": len(tx_hex) // 2,  # Hex string is twice the byte size
            }

            results.append(tx_info)

        except Exception as e:
            logger.error(f"Error processing transaction {tx_hash}: {e}")
            # Continue processing other transactions instead of stopping

    logger.info(f"[MOCK] Processed {len(results)} out of {len(tx_hashes)} transactions")

    # Save results to file if requested
    if output_file:
        with open(output_file, "w") as f:
            json.dump(results, f, indent=2)

    return results
