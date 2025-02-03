#!/usr/bin/env python3
import binascii
import json
import logging
import os
import sys
from typing import List, Optional, Tuple

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import config  # Import config directly, not from index_core
from index_core import arc4
from index_core import backend as backend_module
from index_core import script
from index_core.blocks import quick_filter_src20_transaction
from index_core.exceptions import DecodeError

try:
    from btc_stamps_parser import FastTransactionParser

    RUST_PARSER_AVAILABLE = True
    rust_parser = FastTransactionParser()
    logger.info("Rust parser is available")
    logger.info(f"Rust PREFIX: {rust_parser.get_prefix_hex()}")
    logger.info(f"Python PREFIX: {binascii.hexlify(config.PREFIX).decode('utf-8')}")
except ImportError:
    RUST_PARSER_AVAILABLE = False
    logger.warning("Rust parser is not available")


def debug_transaction(txid: str):
    """Debug a transaction's chunk creation and decryption process."""
    logger.info(f"Debugging transaction: {txid}")

    # Initialize the backend
    b = backend_module.Backend()

    # Fetch the raw transaction
    try:
        raw_tx = b.getrawtransaction(txid)
        logger.info(f"Raw transaction fetched, length: {len(raw_tx)}")
    except Exception as e:
        logger.error(f"Failed to fetch transaction: {e}")
        return

    # Deserialize the transaction
    try:
        ctx = b.deserialize(raw_tx)
        logger.info(f"Transaction deserialized, {len(ctx.vout)} outputs")
    except Exception as e:
        logger.error(f"Failed to deserialize transaction: {e}")
        return

    # Check if the transaction should be included according to Python implementation
    try:
        should_include_python = quick_filter_src20_transaction(ctx)
        logger.info(f"Python implementation: should_include = {should_include_python}")
    except Exception as e:
        logger.error(f"Error in Python filter: {e}")
        should_include_python = False

    # If Rust parser is available, check if the transaction should be included
    if RUST_PARSER_AVAILABLE:
        try:
            tx_info = rust_parser.deserialize_transaction(raw_tx)
            logger.info(f"Rust implementation: should_include = {tx_info.should_include}")
            logger.info(f"Rust implementation: has_valid_pattern = {tx_info.has_valid_pattern}")
            logger.info(f"Rust implementation: has_valid_data = {tx_info.has_valid_data}")
            logger.info(f"Rust implementation: keyburn = {tx_info.keyburn}")
        except Exception as e:
            logger.error(f"Error in Rust parser: {e}")

    # Process each output
    for idx, vout in enumerate(ctx.vout):
        logger.info(f"Output #{idx}: value={vout.nValue}")

        try:
            asm = script.get_asm(vout.scriptPubKey)
            logger.info(f"  ASM: {asm}")

            # Check for OP_CHECKMULTISIG
            if asm[-1] == "OP_CHECKMULTISIG":
                logger.info(f"  Output #{idx} has OP_CHECKMULTISIG")

                # Get pubkeys and keyburn
                try:
                    pubkeys, signatures_required, keyburn = script.get_checkmultisig(asm)
                    logger.info(f"  Pubkeys: {pubkeys}")
                    logger.info(f"  Signatures required: {signatures_required}")
                    logger.info(f"  Keyburn: {keyburn}")

                    # Create chunk from pubkeys
                    chunk = b"".join(pubkey[1:-1] for pubkey in pubkeys)
                    logger.info(f"  Python chunk: {binascii.hexlify(chunk).decode('utf-8')}")

                    # Decrypt chunk
                    input_hash = ctx.vin[0].prevout.hash[::-1]
                    logger.info(f"  Input hash: {binascii.hexlify(input_hash).decode('utf-8')}")

                    key = arc4.init_arc4(input_hash)
                    decrypted_chunk = arc4.arc4_decrypt_chunk(chunk, key)
                    logger.info(f"  Python decrypted chunk: {binascii.hexlify(decrypted_chunk).decode('utf-8')}")

                    # Check for PREFIX at position 2
                    if len(decrypted_chunk) >= 2 + len(config.PREFIX):
                        prefix_found = decrypted_chunk[2 : 2 + len(config.PREFIX)] == config.PREFIX
                        logger.info(f"  PREFIX found at position 2: {prefix_found}")
                        logger.info(f"  Expected PREFIX: {binascii.hexlify(config.PREFIX).decode('utf-8')}")
                        logger.info(
                            f"  Found at position 2: {binascii.hexlify(decrypted_chunk[2:2+len(config.PREFIX)]).decode('utf-8')}"
                        )
                    else:
                        logger.info(f"  Decrypted chunk too short for PREFIX check")

                    # Check for PREFIX at other positions
                    for pos in range(len(decrypted_chunk) - len(config.PREFIX) + 1):
                        if decrypted_chunk[pos : pos + len(config.PREFIX)] == config.PREFIX:
                            logger.info(f"  PREFIX found at position {pos}: {binascii.hexlify(config.PREFIX).decode('utf-8')}")

                    # If Rust parser is available, compare with Rust implementation
                    if RUST_PARSER_AVAILABLE:
                        logger.info("  Comparing with Rust implementation:")
                        try:
                            # Get the output info
                            if idx < len(tx_info.outputs):
                                output_info = tx_info.outputs[idx]
                                logger.info(
                                    f"  Rust output #{idx}: has_op_checkmultisig={output_info.has_op_checkmultisig}, keyburn={output_info.keyburn}"
                                )

                                # Debug the output using the Rust parser
                                debug_info = rust_parser.debug_output(txid, idx)
                                logger.info(f"  Rust debug info: {debug_info}")
                            else:
                                logger.warning(f"  Output #{idx} not found in Rust parser results")
                        except Exception as e:
                            logger.error(f"  Error in Rust parser: {e}")
                except Exception as e:
                    logger.error(f"  Error processing OP_CHECKMULTISIG: {e}")

            # Check for P2WSH
            elif len(asm) > 1 and asm[0] == 0 and len(asm[1]) == 32:
                logger.info(f"  Output #{idx} has P2WSH pattern")

                # Get pubkeys
                try:
                    pubkeys = script.get_p2wsh(asm)
                    logger.info(f"  P2WSH pubkeys: {pubkeys}")
                except Exception as e:
                    logger.error(f"  Error processing P2WSH: {e}")
        except Exception as e:
            logger.error(f"  Error processing output #{idx}: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <txid>")
        sys.exit(1)

    txid = sys.argv[1]
    debug_transaction(txid)
