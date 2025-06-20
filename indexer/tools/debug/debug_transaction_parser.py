#!/usr/bin/env python
"""
Enhanced debug script for Bitcoin Stamps transaction parsing.

This script combines functionality from debug_rust_transaction.py and debug_rust_python.py
to provide comprehensive analysis of how transactions are processed by both
Python and Rust parsers, with detailed output for troubleshooting.
"""

import binascii
import json
import logging
import os
import re
import sys
from typing import Dict, Optional

from dotenv import load_dotenv

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Import necessary modules
import config  # Import config directly, not from index_core
from index_core import arc4, backend as backend_module, script
from index_core.fetch_utils import get_xcp_asset
from index_core.transaction_utils import quick_filter_src20_transaction

# Try to import Rust parser
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


def get_tx_hash_for_asset(asset_id: str) -> Optional[str]:
    """Get the issuance transaction hash for a given asset ID."""
    from index_core.node_health import initialize_node_health

    initialize_node_health()  # Ensure nodes are checked before fetching
    logger.info(f"Fetching asset details for {asset_id} to find issuance transaction...")
    asset_data = get_xcp_asset(asset_id)
    if asset_data:
        issuance_tx = asset_data.get("first_issuance", {}).get("tx_hash")
        if issuance_tx:
            logger.info(f"Found issuance transaction hash: {issuance_tx}")
            return issuance_tx
    logger.error(f"Could not find issuance transaction for asset {asset_id}")
    return None


def try_extract_json(data: bytes) -> Optional[Dict]:
    """Try to extract a JSON object from the given data."""
    try:
        # Look for JSON-like patterns
        json_pattern = re.compile(rb"({.*?})")
        matches = json_pattern.findall(data)

        for match in matches:
            try:
                return json.loads(match)
            except json.JSONDecodeError:
                continue

        # If no match was found with regex, try the entire string
        return json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def try_concatenate_outputs(outputs, verbose: bool = False) -> None:
    """Try to concatenate P2WSH outputs that might contain split data."""
    p2wsh_outputs = []
    p2wsh_data = bytearray()

    # First, collect all P2WSH outputs
    for idx, vout in enumerate(outputs):
        script_bytes = bytes(vout.scriptPubKey)
        if len(script_bytes) >= 34 and script_bytes[0] == 0x00 and script_bytes[1] == 0x20:
            p2wsh_outputs.append((idx, script_bytes[2:]))
            # Add to the combined data
            p2wsh_data.extend(script_bytes[2:])

    if len(p2wsh_outputs) <= 1:
        return  # No need to concatenate if only one or zero P2WSH outputs

    # Try to decode as UTF-8
    try:
        decoded = p2wsh_data.decode("utf-8", errors="replace")
        logger.info("\n=== Concatenated P2WSH Data ===")
        logger.info(f"Combined from outputs: {[idx for idx, _ in p2wsh_outputs]}")
        logger.info(f"Raw concatenated data: {decoded}")

        # Check for stamp: prefix
        if "stamp:" in decoded:
            logger.info("Found 'stamp:' prefix in concatenated data")

            # Try to extract JSON
            json_data = try_extract_json(p2wsh_data)
            if json_data:
                logger.info(f"Extracted JSON: {json.dumps(json_data, indent=2)}")

                # If it's an SRC-20 transaction, provide additional context
                if json_data.get("p") == "src-20":
                    logger.info("SRC-20 Transaction:")
                    logger.info(f"  Operation: {json_data.get('op', 'unknown')}")
                    logger.info(f"  Tick: {json_data.get('tick', 'unknown')}")
                    logger.info(f"  Amount: {json_data.get('amt', 'unknown')}")

        # Look for other protocol indicators
        elif any(pattern in decoded for pattern in ["src-20", "src-721", "src-1010", "OLGA"]):
            logger.info("Found protocol indicator in concatenated data")

            # Try to extract JSON
            json_data = try_extract_json(p2wsh_data)
            if json_data:
                logger.info(f"Extracted JSON: {json.dumps(json_data, indent=2)}")
    except UnicodeDecodeError:
        if verbose:
            logger.info("Could not decode concatenated data as UTF-8")
            logger.info(f"Hex representation: {binascii.hexlify(p2wsh_data).decode('utf-8')}")


def debug_transaction(txid: str, verbose: bool = False):
    """Debug a transaction's parsing, filtering, and data extraction with both Python and Rust."""
    logger.info(f"Debugging transaction: {txid}")

    # Set a debug environment variable to enable Rust debug logging if verbose
    if verbose and "RUST_LOG" not in os.environ:
        os.environ["RUST_LOG"] = "debug"

    # Initialize the backend
    b = backend_module.Backend()

    # Fetch the raw transaction
    try:
        raw_tx = b.getrawtransaction(txid)
        logger.info(f"Raw transaction fetched, length: {len(raw_tx)}")
    except Exception as e:
        logger.error(f"Failed to fetch transaction: {e}")
        return

    # Deserialize the transaction with Python
    try:
        ctx = b.deserialize(raw_tx)
        logger.info(f"Transaction deserialized with Python, {len(ctx.vout)} outputs")
    except Exception as e:
        logger.error(f"Failed to deserialize transaction with Python: {e}")
        return

    # Check if the transaction should be included according to Python implementation
    try:
        should_include_python = quick_filter_src20_transaction(ctx)
        logger.info(f"Python implementation: should_include = {should_include_python}")
    except Exception as e:
        logger.error(f"Error in Python filter: {e}")
        should_include_python = False

    # Test with Rust parser if available
    if RUST_PARSER_AVAILABLE:
        try:
            # Use the debug_p2wsh_detection method if verbose and available
            if verbose and hasattr(rust_parser, "debug_p2wsh_detection"):
                debug_output = rust_parser.debug_p2wsh_detection(raw_tx)
                logger.info("P2WSH Detection Debug Output:")
                for line in debug_output.split("\n"):
                    if line.strip():  # Only log non-empty lines
                        logger.info(f"  {line}")

            # Deserialize the transaction with Rust
            tx_info = rust_parser.deserialize_transaction(raw_tx)
            logger.info(f"Rust implementation: should_include = {tx_info.should_include}")
            logger.info(f"Rust implementation: has_valid_pattern = {tx_info.has_valid_pattern}")
            logger.info(f"Rust implementation: has_valid_data = {tx_info.has_valid_data}")
            logger.info(f"Rust implementation: keyburn = {tx_info.keyburn}")

            # Test batch processing
            if verbose:
                logger.info("Testing batch processing with Rust parser:")
                batch_result = rust_parser.batch_parse_transactions([raw_tx])
                logger.info(f"Batch processing returned {len(batch_result)} transactions")

                if batch_result:
                    logger.info(f"Included transaction hash: {batch_result[0].txid}")
        except Exception as e:
            logger.error(f"Error in Rust parser: {e}")

    # ========== Process each output with detailed analysis ==========
    for idx, vout in enumerate(ctx.vout):
        script_bytes = bytes(vout.scriptPubKey)
        logger.info(f"Output #{idx}: value={vout.nValue}, script_len={len(script_bytes)}")

        if verbose:
            logger.info(f"  Script hex: {vout.scriptPubKey.hex()}")
            if len(script_bytes) >= 5:
                logger.info(f"  First 5 bytes: {' '.join(f'0x{b:02x}' for b in script_bytes[:5])}")

        try:
            asm = script.get_asm(vout.scriptPubKey)
            logger.info(f"  ASM: {asm}")

            # Check for P2WSH pattern
            if len(asm) > 1 and asm[0] == 0 and len(asm[1]) == 32:
                logger.info(f"  Output #{idx} has P2WSH pattern")
                is_p2wsh = len(script_bytes) >= 34 and script_bytes[0] == 0x00 and script_bytes[1] == 0x20
                logger.info(f"  Is P2WSH format (len >= 34, starts with 0x00 0x20): {is_p2wsh}")

                # Get pubkeys
                try:
                    pubkeys = script.get_p2wsh(asm)
                    logger.info(f"  P2WSH pubkeys: {pubkeys}")

                    # Try to decode as string if it looks like data
                    for pubkey in pubkeys:
                        try:
                            decoded = pubkey.decode("utf-8", errors="replace")
                            if any(pattern in decoded for pattern in ["stamp:", "src-20", "src-721", "src-1010", "OLGA", "{"]):
                                logger.info(f"  Decoded P2WSH data: {decoded}")
                        except UnicodeDecodeError:
                            pass
                except Exception as e:
                    logger.error(f"  Error processing P2WSH: {e}")

            # Check for OP_CHECKMULTISIG
            elif asm[-1] == "OP_CHECKMULTISIG":
                logger.info(f"  Output #{idx} has OP_CHECKMULTISIG")

                # Get pubkeys and keyburn
                try:
                    pubkeys, signatures_required, keyburn = script.get_checkmultisig(asm)
                    logger.info(f"  Pubkeys: {len(pubkeys)}")
                    logger.info(f"  Signatures required: {signatures_required}")
                    logger.info(f"  Keyburn: {keyburn}")

                    if verbose:
                        for i, pubkey in enumerate(pubkeys):
                            logger.info(f"  Pubkey {i}: {binascii.hexlify(pubkey).decode('utf-8')}")

                    # Check if the last pubkey is a burnkey
                    last_pubkey = binascii.hexlify(pubkeys[-1]).decode("utf-8")
                    logger.info(f"  Last pubkey: {last_pubkey[:10]}...")
                    logger.info(f"  Is burnkey: {last_pubkey.startswith(('020202', '030303', '022222', '033333'))}")

                    # Create chunk from pubkeys
                    chunk = b"".join(pubkey[1:-1] for pubkey in pubkeys)
                    logger.info(f"  Python chunk length: {len(chunk)}")

                    if verbose:
                        logger.info(f"  Python chunk: {binascii.hexlify(chunk).decode('utf-8')}")

                    # Decrypt chunk
                    input_hash = ctx.vin[0].prevout.hash[::-1]
                    logger.info(f"  Input hash: {binascii.hexlify(input_hash).decode('utf-8')[:10]}...")

                    key = arc4.init_arc4(input_hash)
                    decrypted_chunk = arc4.arc4_decrypt_chunk(chunk, key)

                    if verbose:
                        logger.info(f"  Python decrypted chunk: {binascii.hexlify(decrypted_chunk).decode('utf-8')}")

                    # Check for PREFIX
                    if len(decrypted_chunk) >= 2 + len(config.PREFIX):
                        prefix_found = decrypted_chunk[2 : 2 + len(config.PREFIX)] == config.PREFIX
                        logger.info(f"  PREFIX found at position 2: {prefix_found}")
                        logger.info(f"  Expected PREFIX: {binascii.hexlify(config.PREFIX).decode('utf-8')}")
                        logger.info(
                            f"  Found at position 2: {binascii.hexlify(decrypted_chunk[2: 2 + len(config.PREFIX)]).decode('utf-8')}"
                        )

                        # Try to extract and decode data if PREFIX is found
                        if prefix_found:
                            try:
                                data = decrypted_chunk[2 + len(config.PREFIX) :].rstrip(b"\x00")
                                logger.info(f"  Extracted data: {data.decode('utf-8', errors='replace')}")

                                # Try to decode as JSON
                                try:
                                    json_data = json.loads(data)
                                    logger.info(f"  JSON data: {json.dumps(json_data, indent=2)}")
                                except json.JSONDecodeError:
                                    logger.info("  Data is not valid JSON")
                            except Exception as e:
                                logger.error(f"  Error extracting data: {e}")
                    else:
                        logger.info("  Decrypted chunk too short for PREFIX check")

                    # If Rust parser is available, get more output info
                    if RUST_PARSER_AVAILABLE:
                        logger.info("  Comparing with Rust implementation:")
                        try:
                            # Get the output info
                            if idx < len(tx_info.outputs):
                                output_info = tx_info.outputs[idx]
                                logger.info(
                                    f"  Rust output #{idx}: has_op_checkmultisig={output_info.has_op_checkmultisig}, keyburn={output_info.keyburn}"
                                )

                                # Debug the output using the Rust parser if method exists
                                if hasattr(rust_parser, "debug_output"):
                                    debug_info = rust_parser.debug_output(txid, idx)
                                    if debug_info:
                                        logger.info(f"  Rust debug info: {debug_info}")
                            else:
                                logger.warning(f"  Output #{idx} not found in Rust parser results")
                        except Exception as e:
                            logger.error(f"  Error in Rust parser: {e}")
                except Exception as e:
                    logger.error(f"  Error processing OP_CHECKMULTISIG: {e}")
        except Exception as e:
            logger.error(f"  Error processing output #{idx}: {e}")

    # Try to concatenate P2WSH outputs to analyze split data
    try_concatenate_outputs(ctx.vout, verbose)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Debug Bitcoin Stamps transaction parsing")
    parser.add_argument("tx_or_asset_id", help="Transaction ID or Asset ID (e.g., A123...) to analyze")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output")
    parser.add_argument("--env", "-e", help="Path to .env file", default=".env")

    args = parser.parse_args()

    # Load environment variables if .env file exists
    if os.path.exists(args.env):
        load_dotenv(args.env)
        logger.info(f"Loaded environment variables from {args.env}")

    identifier = args.tx_or_asset_id
    txid_to_debug = None

    # Check if the identifier is a potential asset ID
    if identifier.startswith("A") and identifier[1:].isdigit():
        txid_to_debug = get_tx_hash_for_asset(identifier)
        if not txid_to_debug:
            sys.exit(1)
    else:
        # Assume it's a txid
        txid_to_debug = identifier

    debug_transaction(txid_to_debug, args.verbose)
