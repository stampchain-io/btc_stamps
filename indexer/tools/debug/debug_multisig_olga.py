#!/usr/bin/env python
"""
Debug script to examine how multisig transactions are handled after the BTC_SRC20_OLGA_BLOCK cutoff.
Specifically focusing on the transactions in block 865003 that are in the database but not being processed.
"""

import binascii
import json
import logging
import os
import sys
from decimal import Decimal
from pathlib import Path

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

from btc_stamps_parser import FastTransactionParser

from src.config import BTC_SRC20_OLGA_BLOCK
from src.index_core import arc4, blocks, script
from src.index_core.backend import Backend

# Transactions from block 865003
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


def analyze_transaction_format(tx_hash, tx_hex, block_index):
    """Analyze if a transaction is using OLGA (P2WSH) or multisig format."""
    logger.info(f"\n===== Analyzing transaction {tx_hash} =====")

    # Use the Rust parser to check if it should be included
    try:
        parser = FastTransactionParser()
        tx_info = parser.deserialize_transaction(tx_hex)

        should_include = tx_info.should_include
        logger.info(f"Rust parser should_include: {should_include}")

        # Analyze each output using blocks module
        backend = Backend()
        ctx = backend.deserialize(tx_hex)

        # Check each output for multisig or P2WSH
        multisig_outputs = []
        p2wsh_outputs = []

        for idx, vout in enumerate(ctx.vout):
            try:
                asm = script.get_asm(vout.scriptPubKey)
                logger.info(f"Output #{idx} script type: {asm[-1] if len(asm) > 0 else 'Empty'}")

                if len(asm) > 0 and asm[-1] == "OP_CHECKMULTISIG":
                    try:
                        pubkeys, signatures_required, keyburn_vout = script.get_checkmultisig(asm)
                        key_count = len(pubkeys) if pubkeys else 0
                        multisig_outputs.append({"index": idx, "pubkeys": key_count, "keyburn": keyburn_vout})

                        # Extract data from multisig
                        if pubkeys:
                            chunk = b"".join(pubkey[1:-1] for pubkey in pubkeys)
                            logger.info(f"Multisig data chunk length: {len(chunk)}")

                            # Decrypt chunk to check for SRC-20 data
                            try:
                                # Get input hash for decryption
                                if len(ctx.vin) > 0:
                                    input_hash = ctx.vin[0].prevout.hash[::-1]
                                    key = arc4.init_arc4(input_hash)
                                    decrypted_chunk = arc4.arc4_decrypt_chunk(chunk, key)

                                    # Show first few bytes of decrypted data
                                    logger.info(f"Decrypted data starts with: {decrypted_chunk[:50]}")

                                    try:
                                        # Try to decode as UTF-8 and check for SRC-20 pattern
                                        data_str = decrypted_chunk.decode("utf-8", errors="replace")
                                        if "SRC-20" in data_str or "src-20" in data_str.lower():
                                            logger.info(f"Contains SRC-20 data: {data_str[:100]}")
                                    except Exception as e:
                                        logger.warning(f"Error decoding data: {e}")
                            except Exception as e:
                                logger.warning(f"Error decrypting multisig data: {e}")

                    except Exception as e:
                        logger.warning(f"Error processing multisig: {e}")

                elif asm[0] == 0 and len(asm[1]) == 32:
                    # P2WSH format
                    p2wsh_outputs.append({"index": idx, "data_len": len(asm[1])})
                    logger.info(f"P2WSH output at index {idx}")

                    # If at index > 0, this would be checked for data
                    if idx > 0 and block_index >= BTC_SRC20_OLGA_BLOCK:
                        data_bytes = asm[1]
                        logger.info(f"P2WSH data chunk length: {len(data_bytes)}")
                        logger.info(f"P2WSH data starts with: {binascii.hexlify(data_bytes[:20])}")

            except Exception as e:
                logger.error(f"Error analyzing output {idx}: {e}")

        # Summary
        logger.info(f"Summary for {tx_hash}:")
        logger.info(f"- Multisig outputs: {len(multisig_outputs)}")
        for out in multisig_outputs:
            logger.info(f"  - Output #{out['index']}: {out['pubkeys']} pubkeys, keyburn={out['keyburn']}")

        logger.info(f"- P2WSH outputs: {len(p2wsh_outputs)}")
        for out in p2wsh_outputs:
            logger.info(f"  - Output #{out['index']}: data_len={out['data_len']}")

        # Check which type this transaction is primarily using
        if len(multisig_outputs) > 0 and len(p2wsh_outputs) == 0:
            logger.info("CONCLUSION: This is a MULTISIG transaction")
            return "MULTISIG", should_include
        elif len(p2wsh_outputs) > 0 and len(multisig_outputs) == 0:
            logger.info("CONCLUSION: This is a P2WSH (OLGA) transaction")
            return "P2WSH", should_include
        elif len(p2wsh_outputs) > 0 and len(multisig_outputs) > 0:
            logger.info("CONCLUSION: This is a HYBRID transaction (both MULTISIG and P2WSH)")
            return "HYBRID", should_include
        else:
            logger.info("CONCLUSION: This is neither a MULTISIG nor P2WSH transaction")
            return "OTHER", should_include

    except Exception as e:
        logger.error(f"Error analyzing transaction {tx_hash}: {e}")
        return "ERROR", False


def main():
    """Main function that analyzes transactions."""
    block_index = 865003  # Block height after BTC_SRC20_OLGA_BLOCK
    logger.info(f"Analyzing transactions from block {block_index}")
    logger.info(f"BTC_SRC20_OLGA_BLOCK is set to {BTC_SRC20_OLGA_BLOCK}")

    backend = Backend()

    # Track counts
    format_counts = {"MULTISIG": 0, "P2WSH": 0, "HYBRID": 0, "OTHER": 0, "ERROR": 0}
    should_include_count = 0

    for tx_hash in EXPECTED_TX_HASHES:
        tx_hex = backend.getrawtransaction(tx_hash)

        if not tx_hex:
            logger.error(f"Could not get transaction {tx_hash}")
            continue

        format_type, should_include = analyze_transaction_format(tx_hash, tx_hex, block_index)
        format_counts[format_type] += 1

        if should_include:
            should_include_count += 1

    # Print summary
    logger.info("\n===== SUMMARY =====")
    logger.info(f"Analyzed {len(EXPECTED_TX_HASHES)} transactions from block {block_index}")
    logger.info(f"Transactions that should be included: {should_include_count}")
    logger.info("Transaction formats:")
    for format_type, count in format_counts.items():
        logger.info(f"- {format_type}: {count}")

    # Detection issue analysis
    if format_counts["MULTISIG"] > 0 and should_include_count > 0:
        logger.info("\n===== ISSUE ANALYSIS =====")
        logger.info("LIKELY ISSUE: Multisig transactions after BTC_SRC20_OLGA_BLOCK are not being processed")
        logger.info("SOLUTION: Ensure multisig transaction processing continues even after the OLGA cutoff")


if __name__ == "__main__":
    main()
