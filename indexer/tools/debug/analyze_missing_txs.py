#!/usr/bin/env python3
"""
Script to analyze missing transactions from StampTableV4.
"""

import binascii
import hashlib
import json
import logging
import sys
from typing import List

from index_core.backend import Backend
from index_core.transaction_utils import quick_filter_src20_transaction
from index_core.parser import Parser

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("analyze_missing_txs")

# The missing transactions
MISSING_TXS = [
    {
        "block": 795419,
        "txid": "e2aa459ebfe0ba3625c917143452678a3e80636489fe0ec8cc7e9651cfd4ddb2",
        "stamp": 67391,
        "ident": "SRC-20",
    },
    {
        "block": 795421,
        "txid": "359aefd7bf0bbd8398ee5c8c0f206799b78b158578f0f98e1e06bf58e70008dc",
        "stamp": 67392,
        "ident": "SRC-20",
    },
]


def get_txid_from_ctx(ctx):
    """Get transaction ID from a Python transaction object."""
    # This is how Python calculates the transaction ID
    tx_hash = hashlib.sha256(hashlib.sha256(ctx.serialize()).digest()).digest()
    return binascii.hexlify(tx_hash[::-1]).decode("utf-8")  # Reverse the bytes and convert to hex


def analyze_transaction(tx_id: str) -> None:
    """Analyze a transaction in detail."""
    logger.critical(f"Analyzing transaction: {tx_id}")

    # Define reversed_tx_id early to avoid reference errors
    reversed_tx_id = "".join(reversed([tx_id[i : i + 2] for i in range(0, len(tx_id), 2)]))
    logger.critical(f"Reversed byte order TX ID: {reversed_tx_id}")

    backend = Backend()
    tx_hex = backend.getrawtransaction(tx_id)
    ctx = backend.deserialize(tx_hex)

    # Calculate the transaction ID from the Python object
    calculated_txid = get_txid_from_ctx(ctx)
    logger.critical(f"Transaction ID: {tx_id}")
    logger.critical(f"Calculated Transaction ID: {calculated_txid}")
    logger.critical(f"Inputs: {len(ctx.vin)}")
    logger.critical(f"Outputs: {len(ctx.vout)}")

    # Check if the transaction passes the Python quick filter
    filter_result = quick_filter_src20_transaction(ctx)
    logger.critical(f"Python quick filter result: {filter_result}")

    # Analyze each output
    for idx, vout in enumerate(ctx.vout):
        script_bytes = bytes(vout.scriptPubKey)
        logger.critical(f"Output #{idx}: {vout.nValue/100000000} BTC")
        logger.critical(f"  Script: {vout.scriptPubKey.hex()}")
        logger.critical(f"  Script length: {len(script_bytes)} bytes")

        # Check for P2WSH pattern
        if len(script_bytes) == 34 and script_bytes[0] == 0x00 and len(script_bytes[1:]) == 32:
            logger.critical(f"  Output #{idx} has P2WSH pattern")

        # Check for multisig pattern
        if len(script_bytes) > 2 and script_bytes[-1] == 0xAE:
            logger.critical(f"  Output #{idx} has potential multisig pattern")

            # Try to extract ASM
            try:
                from index_core.script import get_asm, get_checkmultisig

                asm = get_asm(vout.scriptPubKey)
                logger.critical(f"  ASM: {asm}")

                if asm[-1] == "OP_CHECKMULTISIG":
                    logger.critical(f"  Output #{idx} has OP_CHECKMULTISIG")

                    try:
                        pubkeys, signatures_required, keyburn = get_checkmultisig(asm)
                        logger.critical(f"  Signatures required: {signatures_required}")
                        logger.critical(f"  Number of pubkeys: {len(pubkeys)}")
                        logger.critical(f"  Keyburn: {keyburn}")

                        # Check if the last pubkey is a burnkey
                        if pubkeys and len(pubkeys) > 0:
                            last_pubkey = pubkeys[-1].hex()
                            logger.critical(f"  Last pubkey: {last_pubkey}")

                            # Check for burnkey patterns
                            if (
                                last_pubkey.startswith("020202")
                                or last_pubkey.startswith("030303")
                                or last_pubkey.startswith("022222")
                                or last_pubkey.startswith("033333")
                            ):
                                logger.critical(f"  Last pubkey matches burnkey pattern")
                    except Exception as e:
                        logger.critical(f"  Error processing multisig: {e}")
            except Exception as e:
                logger.critical(f"  Error getting ASM: {e}")

    # Check Rust parser behavior
    try:
        logger.critical("Testing Rust implementation directly...")
        rust_results = backend._parser.batch_parse_transactions([tx_hex])
        logger.critical(f"Rust parser returned {len(rust_results)} results")
        rust_result = len(rust_results) > 0
        logger.critical(f"Rust filter result: {rust_result}")

        if not rust_result:
            logger.critical("Transaction was NOT included by Rust parser")

            # Check transaction ID byte order
            logger.critical(f"Reversed byte order TX ID: {reversed_tx_id}")

            # Try to debug the Rust filtering logic
            logger.critical("Debugging potential issues in Rust filtering logic:")

            # 1. Check if any output has a P2WSH pattern (not in first position)
            has_valid_p2wsh = False
            for i, vout in enumerate(ctx.vout):
                script_bytes = bytes(vout.scriptPubKey)
                if i > 0 and len(script_bytes) == 34 and script_bytes[0] == 0x00 and len(script_bytes[1:]) == 32:
                    has_valid_p2wsh = True
                    logger.critical(f"  - Output #{i} has valid P2WSH pattern")

            if not has_valid_p2wsh:
                logger.critical("  - No valid P2WSH pattern found in non-first outputs")

            # 2. Check for multisig pattern and keyburn
            has_valid_multisig = False
            has_keyburn = False
            for i, vout in enumerate(ctx.vout):
                script_bytes = bytes(vout.scriptPubKey)
                if len(script_bytes) > 2 and script_bytes[-1] == 0xAE:
                    has_valid_multisig = True
                    logger.critical(f"  - Output #{i} has potential multisig pattern")

                    # In Rust, we check if the last pubkey starts with 0x02020202... or 0x03030303...
                    script_hex = vout.scriptPubKey.hex()
                    if "020202" in script_hex or "030303" in script_hex or "022222" in script_hex or "033333" in script_hex:
                        has_keyburn = True
                        logger.critical(
                            f"  - Output #{i} has keyburn pattern (0x0202... or 0x0303... or 0x0222... or 0x0333...)"
                        )

            if not has_valid_multisig:
                logger.critical("  - No valid multisig pattern found")

            if not has_keyburn:
                logger.critical("  - No keyburn pattern found")

            # 3. Check the filtering logic conditions
            should_include = (has_valid_p2wsh and not has_keyburn) or (has_keyburn and not has_valid_p2wsh)
            logger.critical(f"  - Based on our understanding, should_include={should_include}")
            logger.critical(f"  - has_valid_p2wsh={has_valid_p2wsh}, has_keyburn={has_keyburn}")

        # Try to analyze the transaction with the Rust parser directly
        logger.critical("Analyzing transaction with Rust parser directly...")
        parser = Parser()

        # Try with both original and reversed transaction ID
        logger.critical("Testing with original transaction ID...")
        try:
            # Instead of trying to access txid directly, use our get_txid_from_ctx function
            tx_info = parser.deserialize_transaction(tx_hex)
            # The Rust parser returns a TransactionInfo object with a txid field
            if hasattr(tx_info, "txid"):
                logger.critical(f"Rust parser transaction ID: {tx_info.txid}")

                # Check if the transaction ID matches
                if tx_info.txid != tx_id:
                    logger.critical(f"Transaction ID mismatch: Rust parser returned {tx_info.txid}, expected {tx_id}")

                    # Check if it's a byte order issue
                    if tx_info.txid == reversed_tx_id:
                        logger.critical(f"Transaction ID is in reversed byte order")
            else:
                logger.critical("Rust parser did not return a txid field")
        except Exception as e:
            logger.critical(f"Error accessing Rust parser transaction ID: {e}")

        # Try to process the block directly
        logger.critical(f"Testing block processing for block {tx_id[:8]}...")
        try:
            # Get the block containing this transaction
            block_hash = backend.getblockhash(
                MISSING_TXS[0]["block"] if tx_id == MISSING_TXS[0]["txid"] else MISSING_TXS[1]["block"]
            )
            block_hex = backend.getblock(block_hash, 0)

            # Parse the block with the Rust parser
            tx_hash_list, raw_transactions, block_time, prev_block_hash, _ = parser.parse_block(block_hex)

            logger.critical(f"Block contains {len(tx_hash_list)} transactions")

            # Check if our transaction is in the list
            if tx_id in tx_hash_list:
                logger.critical(f"Transaction {tx_id} found in block at position {tx_hash_list.index(tx_id)}")
            else:
                logger.critical(f"Transaction {tx_id} NOT found in block tx_hash_list")

                # Check if reversed ID is in the list
                if reversed_tx_id in tx_hash_list:
                    logger.critical(
                        f"Reversed transaction ID {reversed_tx_id} found in block at position {tx_hash_list.index(reversed_tx_id)}"
                    )

            # Now try to filter the transactions
            logger.critical("Testing batch parsing of all transactions in the block...")
            tx_hexes = list(raw_transactions.values())
            filtered_txs = parser.batch_parse_transactions(tx_hexes)

            logger.critical(f"Filtered {len(filtered_txs)} of {len(tx_hexes)} transactions")

            # Check if our transaction is in the filtered list
            # Use a safer approach to get txids from filtered_txs
            tx_ids_in_filtered = []
            for tx in filtered_txs:
                if hasattr(tx, "txid"):
                    tx_ids_in_filtered.append(tx.txid)
                else:
                    # If txid is not available, log it
                    logger.critical(f"A filtered transaction does not have a txid attribute")

            if tx_id in tx_ids_in_filtered:
                logger.critical(
                    f"Transaction {tx_id} found in filtered transactions at position {tx_ids_in_filtered.index(tx_id)}"
                )
            else:
                logger.critical(f"Transaction {tx_id} NOT found in filtered transactions")

                # Check if reversed ID is in the filtered list
                if reversed_tx_id in tx_ids_in_filtered:
                    logger.critical(
                        f"Reversed transaction ID {reversed_tx_id} found in filtered transactions at position {tx_ids_in_filtered.index(reversed_tx_id)}"
                    )

        except Exception as e:
            logger.critical(f"Error processing block: {e}")

    except ImportError:
        logger.critical("Rust parser not available")
    except Exception as e:
        logger.critical(f"Error with Rust parser: {e}")


def analyze_block(block_index: int) -> None:
    """Analyze a specific block."""
    logger.critical(f"\n{'='*80}")
    logger.critical(f"Analyzing block {block_index}")
    logger.critical(f"{'='*80}\n")

    backend = Backend()
    parser = Parser()

    try:
        # Get the block
        block_hash = backend.getblockhash(block_index)
        block_hex = backend.getblock(block_hash, 0)

        # Parse the block with the Rust parser
        tx_hash_list, raw_transactions, block_time, prev_block_hash, _ = parser.parse_block(block_hex)

        logger.critical(f"Block contains {len(tx_hash_list)} transactions")

        # Find our missing transactions in this block
        missing_tx = next((tx for tx in MISSING_TXS if tx["block"] == block_index), None)
        if missing_tx:
            tx_id = missing_tx["txid"]
            # Define reversed_tx_id early to avoid reference errors
            reversed_tx_id = "".join(reversed([tx_id[i : i + 2] for i in range(0, len(tx_id), 2)]))

            logger.critical(f"Looking for missing transaction {tx_id} in block {block_index}")
            logger.critical(f"Reversed byte order TX ID: {reversed_tx_id}")

            # Check if our transaction is in the list
            if tx_id in tx_hash_list:
                logger.critical(f"Transaction {tx_id} found in block at position {tx_hash_list.index(tx_id)}")

                # Get the transaction hex
                tx_hex = raw_transactions[tx_id]

                # Deserialize with Python to check filtering
                ctx = backend.deserialize(tx_hex)
                filter_result = quick_filter_src20_transaction(ctx)
                logger.critical(f"Python quick filter result for transaction {tx_id}: {filter_result}")

            else:
                logger.critical(f"Transaction {tx_id} NOT found in block tx_hash_list")

                # Check if reversed ID is in the list
                if reversed_tx_id in tx_hash_list:
                    logger.critical(
                        f"Reversed transaction ID {reversed_tx_id} found in block at position {tx_hash_list.index(reversed_tx_id)}"
                    )

                    # Get the transaction hex
                    tx_hex = raw_transactions[reversed_tx_id]

                    # Deserialize with Python to check filtering
                    ctx = backend.deserialize(tx_hex)
                    filter_result = quick_filter_src20_transaction(ctx)
                    logger.critical(f"Python quick filter result for transaction {reversed_tx_id}: {filter_result}")

            # Now try to filter the transactions
            logger.critical("Testing batch parsing of all transactions in the block...")
            tx_hexes = list(raw_transactions.values())
            filtered_txs = parser.batch_parse_transactions(tx_hexes)

            logger.critical(f"Filtered {len(filtered_txs)} of {len(tx_hexes)} transactions")

            # Check if our transaction is in the filtered list
            # Use a safer approach to get txids from filtered_txs
            tx_ids_in_filtered = []
            for tx in filtered_txs:
                if hasattr(tx, "txid"):
                    tx_ids_in_filtered.append(tx.txid)
                else:
                    # If txid is not available, log it
                    logger.critical(f"A filtered transaction does not have a txid attribute")

            if tx_id in tx_ids_in_filtered:
                logger.critical(
                    f"Transaction {tx_id} found in filtered transactions at position {tx_ids_in_filtered.index(tx_id)}"
                )
            else:
                logger.critical(f"Transaction {tx_id} NOT found in filtered transactions")

                # Check if reversed ID is in the filtered list
                if reversed_tx_id in tx_ids_in_filtered:
                    logger.critical(
                        f"Reversed transaction ID {reversed_tx_id} found in filtered transactions at position {tx_ids_in_filtered.index(reversed_tx_id)}"
                    )

                # If not found, try to analyze why
                logger.critical(f"Analyzing why transaction {tx_id} was not included...")

                # Get the transaction hex
                if tx_id in raw_transactions:
                    tx_hex = raw_transactions[tx_id]
                elif reversed_tx_id in raw_transactions:
                    tx_hex = raw_transactions[reversed_tx_id]
                    logger.critical(f"Using reversed transaction ID {reversed_tx_id} to get transaction hex")
                else:
                    tx_hex = backend.getrawtransaction(tx_id)
                    logger.critical(f"Got transaction hex from RPC")

                # Analyze the transaction
                analyze_transaction(tx_id)

    except Exception as e:
        logger.critical(f"Error analyzing block {block_index}: {e}")


def main():
    """Main function to analyze missing transactions."""
    logger.critical("Starting analysis of missing transactions")

    # First analyze each transaction individually
    for tx_info in MISSING_TXS:
        logger.critical(f"\n{'='*80}")
        logger.critical(f"Analyzing transaction in block {tx_info['block']}: {tx_info['txid']}")
        logger.critical(f"Stamp ID: {tx_info['stamp']}, Identifier: {tx_info['ident']}")
        logger.critical(f"{'='*80}\n")

        analyze_transaction(tx_info["txid"])

    # Then analyze the blocks containing these transactions
    logger.critical("\n\nAnalyzing blocks containing missing transactions:")
    for tx_info in MISSING_TXS:
        analyze_block(tx_info["block"])


if __name__ == "__main__":
    main()
