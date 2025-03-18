#!/usr/bin/env python
"""
Compare how both the Rust and Python parsers handle the '10.10' transaction.
"""

import logging
import os
import sys

# Add the src directory to the path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "src")))

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

import config

# Import necessary modules
from index_core.backend import Backend
from index_core.blocks import quick_filter_src20_transaction


def analyze_with_rust_parser(backend: Backend, txid: str) -> dict:
    """Analyze the transaction with the Rust parser."""
    # Save current state
    original_setting = config.DISABLE_RUST_PARSER

    # Force Rust parser
    config.DISABLE_RUST_PARSER = False

    # Get transaction hex
    tx_hex = backend.getrawtransaction(txid)

    # Deserialize transaction using Rust parser
    ctx = backend.deserialize(tx_hex)

    # Check if it passes the quick filter
    filter_result = quick_filter_src20_transaction(ctx)

    # Restore original setting
    config.DISABLE_RUST_PARSER = original_setting

    return {
        "parser": "Rust",
        "tx_id": txid,
        "included": filter_result,
        "num_inputs": len(ctx.vin),
        "num_outputs": len(ctx.vout),
        "details": "Processed with Rust parser",
    }


def analyze_with_python_parser(backend: Backend, txid: str) -> dict:
    """Analyze the transaction with the Python parser."""
    # Save current state
    original_setting = config.DISABLE_RUST_PARSER

    # Force Python parser
    config.DISABLE_RUST_PARSER = True

    # Get transaction hex
    tx_hex = backend.getrawtransaction(txid)

    # Deserialize transaction using Python parser
    ctx = backend.deserialize(tx_hex)

    # Check if it passes the quick filter
    filter_result = quick_filter_src20_transaction(ctx)

    # Restore original setting
    config.DISABLE_RUST_PARSER = original_setting

    return {
        "parser": "Python",
        "tx_id": txid,
        "included": filter_result,
        "num_inputs": len(ctx.vin),
        "num_outputs": len(ctx.vout),
        "details": "Processed with Python parser",
    }


def main():
    """Main function."""
    # Initialize backend
    backend = Backend()

    # The '10.10' transaction hash
    txid = "572be558f1260117c134c1d4a770a443a713c778c4afdfe4139a8da15cb5d5ef"

    logger.info(f"Comparing parser results for transaction: {txid}")

    # Get original setting
    original_setting = config.DISABLE_RUST_PARSER
    logger.info(f"Original DISABLE_RUST_PARSER setting: {original_setting}")

    # Process with Rust parser
    try:
        rust_result = analyze_with_rust_parser(backend, txid)
        logger.info(f"Rust parser results: {rust_result}")
    except Exception as e:
        logger.error(f"Error with Rust parser: {str(e)}")
        rust_result = {"parser": "Rust", "error": str(e)}

    # Process with Python parser
    try:
        python_result = analyze_with_python_parser(backend, txid)
        logger.info(f"Python parser results: {python_result}")
    except Exception as e:
        logger.error(f"Error with Python parser: {str(e)}")
        python_result = {"parser": "Python", "error": str(e)}

    # Restore original setting
    config.DISABLE_RUST_PARSER = original_setting

    # Compare results
    if rust_result.get("included") == python_result.get("included"):
        logger.info("✅ Both parsers agree on whether to include this transaction!")
        logger.info(f"Transaction should be included: {rust_result.get('included')}")
    else:
        logger.info("❌ Parsers disagree on whether to include this transaction!")
        logger.info(f"Rust parser says include: {rust_result.get('included')}")
        logger.info(f"Python parser says include: {python_result.get('included')}")


if __name__ == "__main__":
    main()
