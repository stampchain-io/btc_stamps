#!/usr/bin/env python
"""
Debug specific transactions to compare Python and Rust implementations.

This script analyzes specific transactions and compares the results between
Python and Rust implementations to help debug discrepancies.
"""

import argparse
import binascii
import logging
import os
import sys

# Add the src directory to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "src")))

import config
import index_core.arc4 as arc4
import index_core.backend as backend
from index_core.transaction_utils import quick_filter_src20_transaction

# Configure logging
logging.basicConfig(level=logging.DEBUG if os.environ.get("RUST_LOG") == "debug" else logging.INFO)
logger = logging.getLogger(__name__)


def analyze_transaction(txid, verbose=False):
    """Analyze a transaction and compare Python and Rust implementations."""
    b = backend.Backend()

    # Get the transaction hex
    tx_hex = b.getrawtransaction(txid)
    logger.info(f"Transaction {txid} hex length: {len(tx_hex)}")

    # Deserialize with Python
    ctx = b.deserialize(tx_hex)

    # Check if the transaction should be included using Python implementation
    py_should_include = quick_filter_src20_transaction(ctx)
    logger.info(f"Python implementation: Transaction {txid} should_include = {py_should_include}")

    # If verbose, print more details about the transaction
    if verbose:
        logger.info(f"Transaction {txid} has {len(ctx.vout)} outputs")
        for i, vout in enumerate(ctx.vout):
            logger.info(f"Output {i}: value={vout.nValue}, script_len={len(vout.scriptPubKey)}")

        # For multisig outputs, try to decode and print the data
        for i, vout in enumerate(ctx.vout):
            if hasattr(vout, "is_multisig") and vout.is_multisig():
                logger.info(f"Output {i} is multisig")
                pubkeys = vout.get_multisig_pubkeys()
                if pubkeys:
                    logger.info(f"Output {i} has {len(pubkeys)} pubkeys")

                    # Print each pubkey in hex
                    for j, pk in enumerate(pubkeys):
                        logger.info(f"Output {i} pubkey {j}: {binascii.hexlify(pk).decode()}")
                        logger.info(f"Output {i} pubkey {j} length: {len(pk)}")
                        logger.info(
                            f"Output {i} pubkey {j} without first and last byte: {binascii.hexlify(pk[1:-1]).decode()}"
                        )

                    # Create chunk from pubkeys (removing first and last byte from each pubkey)
                    chunk = b"".join([pk[1:-1] for pk in pubkeys])
                    logger.info(f"Output {i} chunk: {binascii.hexlify(chunk).decode()}")
                    logger.info(f"Output {i} chunk length: {len(chunk)}")

                    # Try to decrypt the chunk
                    if ctx.vin and ctx.vin[0].prevout and ctx.vin[0].prevout.hash:
                        input_hash = ctx.vin[0].prevout.hash[::-1]
                        logger.info(f"Input hash: {binascii.hexlify(input_hash).decode()}")
                        key = arc4.init_arc4(input_hash)
                        decrypted = arc4.arc4_decrypt_chunk(chunk, key)
                        logger.info(f"Output {i} decrypted: {binascii.hexlify(decrypted).decode()}")
                        logger.info(f"Output {i} decrypted length: {len(decrypted)}")

                        # Print each byte of the decrypted chunk
                        logger.info(f"Output {i} decrypted bytes:")
                        for j, byte in enumerate(decrypted):
                            ascii_char = chr(byte) if 32 <= byte <= 126 else "."
                            logger.info(f"  Byte {j}: 0x{byte:02x} (ASCII: {ascii_char})")

                        # Check for PREFIX
                        if len(decrypted) >= 2 + len(config.PREFIX):
                            prefix_start = 2  # Skip the first 2 bytes (length prefix)
                            prefix_end = prefix_start + len(config.PREFIX)
                            chunk_prefix = decrypted[prefix_start:prefix_end]
                            logger.info(
                                f"Output {i} expected PREFIX: {binascii.hexlify(config.PREFIX).decode()}, found at position 2: {binascii.hexlify(chunk_prefix).decode()}"
                            )

                            # Check if PREFIX matches
                            if chunk_prefix == config.PREFIX:
                                logger.info(f"Output {i} PREFIX matches at position 2")
                            else:
                                logger.info(f"Output {i} PREFIX does not match at position 2")

                            # Check for PREFIX anywhere in the decrypted chunk
                            found = False
                            for start_pos in range(len(decrypted) - len(config.PREFIX) + 1):
                                test_prefix = decrypted[start_pos : start_pos + len(config.PREFIX)]
                                if test_prefix == config.PREFIX:
                                    logger.info(
                                        f"Output {i} PREFIX found at position {start_pos}: {binascii.hexlify(test_prefix).decode()}"
                                    )
                                    found = True
                                    break

                            if not found:
                                logger.info(f"Output {i} PREFIX not found anywhere in the decrypted chunk")

    # Check if Rust parser is available
    if hasattr(b, "_parser") and b._parser is not None:
        # Access the Rust parser directly
        rust_parser = b._parser._parser

        # Print the PREFIX value from Rust
        rust_prefix_hex = rust_parser.get_prefix_hex()
        logger.info(f"Rust PREFIX: {rust_prefix_hex}")
        logger.info(f"Python PREFIX: {binascii.hexlify(config.PREFIX).decode()}")

        # Parse the transaction with the Rust parser directly
        tx_info = rust_parser.deserialize_transaction(tx_hex)

        # Check if the transaction should be included using Rust implementation
        rust_should_include = tx_info.should_include
        logger.info(f"Rust implementation: Transaction {txid} should_include = {rust_should_include}")

        # If verbose, print more details about the transaction
        if verbose:
            logger.info(
                f"Rust transaction info: has_valid_pattern={tx_info.has_valid_pattern}, has_valid_data={tx_info.has_valid_data}, keyburn={tx_info.keyburn}"
            )
            logger.info(f"Rust transaction has {len(tx_info.outputs)} outputs")
            for i, output in enumerate(tx_info.outputs):
                logger.info(
                    f"Output {i}: value={output.value}, has_op_checkmultisig={output.has_op_checkmultisig}, keyburn={output.keyburn}"
                )

                # If this is a multisig output with keyburn, get more details
                if output.has_op_checkmultisig and output.keyburn > 0:
                    # Add a custom method to the Rust parser to get the decrypted chunk for debugging
                    if hasattr(rust_parser, "debug_output"):
                        debug_info = rust_parser.debug_output(txid, i)
                        if debug_info:
                            logger.info(f"Rust debug for output {i}:")
                            logger.info(f"  Chunk: {debug_info.get('chunk', 'N/A')}")
                            logger.info(f"  Decrypted chunk: {debug_info.get('decrypted_chunk', 'N/A')}")
                            logger.info(f"  PREFIX position: {debug_info.get('prefix_position', 'Not found')}")
                            logger.info(f"  Has valid data: {debug_info.get('has_valid_data', False)}")

                    # Manually recreate the Python decryption process for comparison
                    if ctx.vin and ctx.vin[0].prevout and ctx.vin[0].prevout.hash:
                        input_hash = ctx.vin[0].prevout.hash[::-1]
                        logger.info(f"Manual verification for output {i}:")
                        logger.info(f"  Input hash: {binascii.hexlify(input_hash).decode()}")

                        # Get pubkeys from the Python implementation
                        if hasattr(ctx.vout[i], "is_multisig") and ctx.vout[i].is_multisig():
                            pubkeys = ctx.vout[i].get_multisig_pubkeys()
                            chunk = b"".join([pk[1:-1] for pk in pubkeys])
                            logger.info(f"  Chunk from Python: {binascii.hexlify(chunk).decode()}")

                            # Decrypt using Python implementation
                            key = arc4.init_arc4(input_hash)
                            decrypted = arc4.arc4_decrypt_chunk(chunk, key)
                            logger.info(f"  Decrypted with Python: {binascii.hexlify(decrypted).decode()}")

                            # Check for PREFIX at position 2
                            if len(decrypted) >= 2 + len(config.PREFIX):
                                prefix_at_pos_2 = decrypted[2 : 2 + len(config.PREFIX)]
                                logger.info(f"  PREFIX at position 2: {binascii.hexlify(prefix_at_pos_2).decode()}")
                                logger.info(f"  Expected PREFIX: {binascii.hexlify(config.PREFIX).decode()}")
                                logger.info(f"  Match at position 2: {prefix_at_pos_2 == config.PREFIX}")

        # Compare the results
        if py_should_include == rust_should_include:
            logger.info(f"✅ Both implementations agree: should_include = {py_should_include}")
        else:
            logger.error(f"❌ Implementations disagree: Python = {py_should_include}, Rust = {rust_should_include}")
    else:
        logger.warning("Rust parser not available. Make sure to build it with 'poetry run maturin develop'")


def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Debug specific transactions")
    parser.add_argument("--txids", nargs="+", help="Transaction IDs to analyze")
    parser.add_argument("--verbose", action="store_true", help="Print verbose output")
    args = parser.parse_args()

    # Default transaction IDs if none provided
    txids = args.txids or [
        "e2aa459ebfe0ba3625c917143452678a3e80636489fe0ec8cc7e9651cfd4ddb2",
        "359aefd7bf0bbd8398ee5c8c0f206799b78b158578f0f98e1e06bf58e70008dc",
    ]

    # Analyze each transaction
    for txid in txids:
        logger.info(f"Analyzing transaction {txid}")
        analyze_transaction(txid, args.verbose)
        logger.info("-" * 80)


if __name__ == "__main__":
    main()
