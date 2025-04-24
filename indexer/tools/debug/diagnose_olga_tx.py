#!/usr/bin/env python
"""
Diagnostic script to understand why OLGA transactions aren't being properly processed.
This script provides detailed information about each transaction in block 865003.
"""

import logging
import os
import sys
from pathlib import Path

# Set logging to DEBUG level to see all details
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
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

from btc_stamps_parser import FastTransactionParser

from src.config import BTC_SRC20_OLGA_BLOCK, PREFIX
from src.index_core import arc4, blocks, script
from src.index_core.backend import Backend

# Transactions from block 865003 as reported in the MySQL query
EXPECTED_TX_HASHES = [
    "c8c3831f6354831f1f14ee8f979c2b114d883c85653aae1c2d286ad351dfc30c",
    "8a68d7a9cf316014bc9f9a61583eced0dbf90db08e542639921ce235cd55f82e",
    "943200a9525381c5f128f1b889d0dd0c6a648f131b104b5db095fa82b5dd3304",
    "711ef8be4c0076b267e96afffd71907fd9388ea08e6d93564008e91a040e8d0c",
    "5e7d66b0b1d3bc28d8ed9211262592d44b601f148686a93cc372fc7e5a3bab71",
    "71aa8481fd179b56cbc125a95dad1c24e3146895f3d2dbe60875f549c1359fe7",
    "e70cfa82f5979405e715420af5533bfb8f8a99ec66177b4d6fc1ea790875c99c",
    "1e20a653c0824c10ed9401953927bef16cfaf43411f7d45165b88e252d8a9f48",
    "b7fc8ca93c23d2b0ef4c210147ec56df426139f85c6496db575ffe3c41beedea",
    "0fea78019487990814cfaba4c9b3fd861f70b3190886a659eaedc0bdc221d0ed",
    "3368bd06d79cc3a66a01d55cf81112e92affcb64022d7f1c78fafcad824ea426",
    "8730c7f8940706be7de6c28466b348703c8ddd48bf9a409a483265b7ded07d8e",
]


def analyze_with_rust_parser(tx_hash, tx_hex):
    """Analyze transaction with Rust parser."""
    parser = FastTransactionParser()
    tx_info = parser.deserialize_transaction(tx_hex)

    logger.info(f"=== RUST PARSER ANALYSIS for {tx_hash} ===")
    logger.info(f"Should include: {tx_info.should_include}")
    logger.info(f"Has valid pattern: {tx_info.has_valid_pattern}")
    logger.info(f"Has valid data: {tx_info.has_valid_data}")
    logger.info(f"Keyburn: {tx_info.keyburn}")
    logger.info(f"Number of inputs: {len(tx_info.inputs)}")
    logger.info(f"Number of outputs: {len(tx_info.outputs)}")

    # Analyze each output
    for i, output in enumerate(tx_info.outputs):
        logger.info(f"Output {i}:")
        logger.info(f"  - Value: {output.value}")
        logger.info(f"  - Script hex: {output.script_hex[:20]}...")
        logger.info(f"  - Has OP_CHECKMULTISIG: {output.has_op_checkmultisig}")
        logger.info(f"  - Keyburn: {output.keyburn}")

    return tx_info


def analyze_with_python(tx_hash, tx_hex, block_index):
    """Analyze transaction with Python implementation."""
    backend = Backend()
    ctx = backend.deserialize(tx_hex)

    logger.info(f"=== PYTHON ANALYSIS for {tx_hash} ===")
    logger.info(f"Transaction has {len(ctx.vout)} outputs")

    # Log details about each output
    for idx, vout in enumerate(ctx.vout):
        script_bytes = bytes(vout.scriptPubKey)
        logger.info(f"Output {idx}:")
        logger.info(f"  - Script bytes length: {len(script_bytes)}")
        logger.info(f"  - Script bytes prefix: {script_bytes[:5].hex()}")

        try:
            asm = script.get_asm(vout.scriptPubKey)
            logger.info(f"  - ASM: {asm}")

            # Check for P2WSH pattern
            if isinstance(asm[0], int) and asm[0] == 0 and len(asm[1]) == 32:
                logger.info(f"  - FOUND P2WSH PATTERN at output {idx}")
                logger.info(f"  - Witness data: {asm[1].hex()}")

            # Check for CHECKMULTISIG
            if asm[-1] == "OP_CHECKMULTISIG":
                logger.info(f"  - FOUND OP_CHECKMULTISIG at output {idx}")
                try:
                    pubkeys, sigs_req, kb = script.get_checkmultisig(asm)
                    logger.info(f"  - Pubkeys: {len(pubkeys)}")
                    logger.info(f"  - Keyburn: {kb}")

                    # Try to decode data (for diagnostic purposes)
                    if kb == 1:
                        chunk = b"".join(pubkey[1:-1] for pubkey in pubkeys)
                        logger.info(f"  - Chunk: {chunk.hex()[:20]}...")

                        if len(ctx.vin) > 0:
                            key = arc4.init_arc4(ctx.vin[0].prevout.hash[::-1])
                            decrypted = arc4.arc4_decrypt_chunk(chunk, key)
                            logger.info(f"  - Decrypted chunk: {decrypted.hex()[:20]}...")

                            if len(decrypted) >= 2 + len(PREFIX):
                                expected_prefix = PREFIX.hex()
                                actual_prefix = decrypted[2 : 2 + len(PREFIX)].hex()
                                logger.info(f"  - Expected PREFIX: {expected_prefix}")
                                logger.info(f"  - Actual prefix: {actual_prefix}")

                                if decrypted[2 : 2 + len(PREFIX)] == PREFIX:
                                    logger.info(f"  - PREFIX MATCH!")
                                else:
                                    logger.info(f"  - PREFIX MISMATCH")
                except Exception as e:
                    logger.error(f"  - Error decoding CHECKMULTISIG: {e}")
        except Exception as e:
            logger.error(f"  - Error processing script: {e}")

    # Process with process_vout
    try:
        vout_info = blocks.process_vout(ctx, block_index)
        logger.info(f"process_vout results:")
        logger.info(f"  - is_olga: {vout_info.is_olga}")
        logger.info(f"  - keyburn: {vout_info.keyburn}")
        logger.info(f"  - p2wsh_data_chunks: {len(vout_info.p2wsh_data_chunks)} chunks")

        if vout_info.p2wsh_data_chunks:
            for i, chunk in enumerate(vout_info.p2wsh_data_chunks):
                logger.info(f"  - Chunk {i}: {chunk.hex()[:20]}...")
    except Exception as e:
        logger.error(f"Error in process_vout: {e}")

    # Finally, try the complete process_tx function
    try:
        tx_result = blocks.process_tx(None, tx_hash, block_index, None, {tx_hash: tx_hex})
        if tx_result:
            logger.info(f"process_tx returned a result")
            logger.info(f"  - source: {tx_result.source}")
            logger.info(f"  - destination: {tx_result.destination}")
            logger.info(f"  - data: {tx_result.data}")
            logger.info(f"  - keyburn: {tx_result.keyburn}")
            logger.info(f"  - is_op_return: {tx_result.is_op_return}")
            logger.info(f"  - p2wsh_data: {tx_result.p2wsh_data}")
        else:
            logger.error(f"process_tx returned None")
    except Exception as e:
        logger.error(f"Error in process_tx: {e}")


def compare_tx_analysis(tx_hash, tx_hex, block_index):
    """Compare analysis from both Rust and Python implementations."""
    logger.info(f"\n\n========= ANALYZING TRANSACTION {tx_hash} =========\n")

    # Check if we modified blocks.py correctly
    # Check quick_filter_src20_transaction function in Python
    try:
        ctx = Backend().deserialize(tx_hex)
        python_include = blocks.quick_filter_src20_transaction(ctx)
        logger.info(f"Python quick_filter result: {python_include}")
    except Exception as e:
        logger.error(f"Error in Python quick_filter: {e}")

    # Analyze with Rust parser
    rust_info = analyze_with_rust_parser(tx_hash, tx_hex)

    # Analyze with Python
    analyze_with_python(tx_hash, tx_hex, block_index)

    # Compare results
    logger.info("\n=== COMPARISON ===")
    logger.info(f"Rust should_include: {rust_info.should_include}")
    logger.info(f"Python quick_filter: {python_include}")

    return rust_info.should_include == python_include


def analyze_all_expected_txs():
    """Analyze all expected transactions from block 865003."""
    backend = Backend()
    block_index = 865003  # The block with the expected transactions

    # Get block data
    block_hash = backend.getblockhash(block_index)
    if not block_hash:
        logger.error(f"Could not get block hash for {block_index}")
        return

    logger.info(f"Analyzing block {block_index} with hash {block_hash}")
    logger.info(f"OLGA block: {BTC_SRC20_OLGA_BLOCK}")
    logger.info(f"PREFIX: {PREFIX.hex()}")

    # Get all transactions
    mismatched = []

    # Focus on just the expected transactions
    for tx_hash in EXPECTED_TX_HASHES:
        try:
            tx_hex = backend.getrawtransaction(tx_hash)
            if not tx_hex:
                logger.error(f"Could not get transaction {tx_hash}")
                continue

            result_match = compare_tx_analysis(tx_hash, tx_hex, block_index)
            if not result_match:
                mismatched.append(tx_hash)
        except Exception as e:
            logger.error(f"Error processing {tx_hash}: {e}")

    # Summary
    logger.info("\n\n=== SUMMARY ===")
    logger.info(f"Analyzed {len(EXPECTED_TX_HASHES)} expected transactions")
    if mismatched:
        logger.error(f"Found {len(mismatched)} transactions with mismatched results: {mismatched}")
    else:
        logger.info("All transactions have matching results between Rust and Python implementations")


if __name__ == "__main__":
    analyze_all_expected_txs()
