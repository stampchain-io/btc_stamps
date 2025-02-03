import binascii
import json
import logging
import os
import sys
from typing import List, Optional, Tuple

from bitcoin.core import CScript, CTransaction

import config
import index_core.script as script
from index_core.arc4 import arc4_decrypt_chunk, init_arc4
from index_core.backend import Backend
from index_core.blocks import quick_filter_src20_transaction

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def analyze_transaction(txid: str) -> None:
    """Analyze a transaction in detail."""
    backend = Backend()
    tx_hex = backend.getrawtransaction(txid)
    ctx = backend.deserialize(tx_hex)

    logger.info(f"Transaction ID: {txid}")
    logger.info(f"Inputs: {len(ctx.vin)}")
    logger.info(f"Outputs: {len(ctx.vout)}")

    # Check if the transaction passes the quick filter
    filter_result = quick_filter_src20_transaction(ctx)
    logger.info(f"Quick filter result: {filter_result}")

    # Analyze each output
    for idx, vout in enumerate(ctx.vout):
        script_bytes = bytes.fromhex(vout.scriptPubKey.hex())
        logger.info(f"Output #{idx}: {vout.nValue/100000000} BTC")
        logger.info(f"  Script: {vout.scriptPubKey.hex()}")

        # Check for P2WSH pattern
        if len(script_bytes) == 34 and script_bytes[0] == 0x00 and len(script_bytes[1:]) == 32:
            logger.info(f"  Output #{idx} has P2WSH pattern")

        # Check for multisig pattern
        if len(script_bytes) > 2 and script_bytes[-1] == 0xAE:
            logger.info(f"  Output #{idx} has potential multisig pattern")

            try:
                asm = script.get_asm(vout.scriptPubKey)
                logger.info(f"  ASM: {asm}")

                if asm[-1] == "OP_CHECKMULTISIG":
                    logger.info(f"  Output #{idx} has OP_CHECKMULTISIG")

                    try:
                        pubkeys, signatures_required, keyburn = script.get_checkmultisig(asm)
                        logger.info(f"  Signatures required: {signatures_required}")
                        logger.info(f"  Pubkeys: {[binascii.hexlify(pk).decode('utf-8') for pk in pubkeys]}")
                        logger.info(f"  Keyburn: {keyburn}")

                        # Check if the last pubkey is a burnkey
                        last_pubkey = binascii.hexlify(pubkeys[-1]).decode("utf-8")
                        logger.info(f"  Last pubkey: {last_pubkey}")
                        logger.info(f"  Is burnkey: {last_pubkey in config.BURNKEYS}")

                        # Try to decrypt the data
                        if keyburn == 1:
                            chunk = b"".join(pubkey for pubkey in pubkeys)
                            logger.info(f"  Chunk length: {len(chunk)}")

                            key = init_arc4(ctx.vin[0].prevout.hash[::-1])
                            decrypted_chunk = arc4_decrypt_chunk(chunk, key)
                            logger.info(f"  Decrypted chunk: {binascii.hexlify(decrypted_chunk).decode('utf-8')}")

                            # Check for PREFIX
                            if decrypted_chunk[2 : 2 + len(config.PREFIX)] == config.PREFIX:
                                logger.info(f"  Found PREFIX: {config.PREFIX}")

                                # Extract data
                                chunk_length = decrypted_chunk[:2].hex()
                                data = decrypted_chunk[len(config.PREFIX) + 2 :].rstrip(b"\x00")
                                data_length = len(decrypted_chunk[2:].rstrip(b"\x00"))

                                logger.info(f"  Chunk length (hex): {chunk_length}")
                                logger.info(f"  Data length: {data_length}")
                                logger.info(f"  Expected length: {int(chunk_length, 16)}")

                                try:
                                    # Try to decode as JSON
                                    json_data = json.loads(data)
                                    logger.info(f"  JSON data: {json.dumps(json_data, indent=2)}")

                                    # Check for SRC-20 fields
                                    if "p" in json_data and json_data["p"] == "src-20":
                                        logger.info("  This is an SRC-20 transaction")
                                        logger.info(f"  Operation: {json_data.get('op', 'unknown')}")
                                        logger.info(f"  Tick: {json_data.get('tick', 'unknown')}")
                                        logger.info(f"  Amount: {json_data.get('amt', 'unknown')}")
                                except json.JSONDecodeError:
                                    logger.info(f"  Data is not valid JSON: {data}")
                            else:
                                logger.info(
                                    f"  PREFIX not found. Expected: {config.PREFIX}, Found: {decrypted_chunk[2:2+len(config.PREFIX)]}"
                                )
                    except Exception as e:
                        logger.error(f"  Error processing multisig: {e}")
            except Exception as e:
                logger.error(f"  Error getting ASM: {e}")

    # Check Rust parser behavior
    try:
        from btc_stamps_parser import FastTransactionParser

        parser = FastTransactionParser()

        # Test batch parsing with just this transaction
        result = parser.batch_parse_transactions([tx_hex])
        logger.info(f"Rust parser result: {len(result)} transactions passed filtering")

        if len(result) > 0:
            logger.info("Transaction passed Rust filtering")
        else:
            logger.info("Transaction did NOT pass Rust filtering")
    except ImportError:
        logger.warning("Rust parser not available")
    except Exception as e:
        logger.error(f"Error with Rust parser: {e}")


def main():
    # Initialize backend
    backend = Backend()

    # Transaction ID to analyze
    tx_id = "50aeb77245a9483a5b077e4e7506c331dc2f628c22046e7d2b4c6ad6c6236ae1"

    # Get transaction hex
    tx_hex = backend.getrawtransaction(tx_id)
    print(f"Transaction hex length: {len(tx_hex)}")

    # Deserialize transaction
    ctx = backend.deserialize(tx_hex)

    # Analyze with Python implementation
    python_result = quick_filter_src20_transaction(ctx)
    print(f"\nPython filter result: {python_result}")

    # Print transaction details
    print(f"\nTransaction details:")
    print(f"Inputs: {len(ctx.vin)}")
    print(f"Outputs: {len(ctx.vout)}")

    # Print output details
    print(f"\nOutput details:")
    for i, vout in enumerate(ctx.vout):
        print(f"Output #{i}: {vout.nValue/100000000} BTC, Script: {vout.scriptPubKey.hex()}")

        # Check for P2WSH pattern
        script_bytes = bytes.fromhex(vout.scriptPubKey.hex())
        if len(script_bytes) == 34 and script_bytes[0] == 0x00 and len(script_bytes[1:]) == 32:
            print(f"  - Output #{i} has P2WSH pattern")

        # Check for multisig pattern
        if len(script_bytes) > 2 and script_bytes[-1] == 0xAE:
            print(f"  - Output #{i} has potential multisig pattern")

            # Check if the last byte of the second-to-last pubkey is 0x02 (keyburn)
            if len(script_bytes) >= 33 and script_bytes[-34] == 0x02:
                print(f"  - Output #{i} has potential keyburn (0x02 pattern)")

    # Now analyze with Rust implementation if available
    if backend._parser is not None:
        print("\nAnalyzing with Rust implementation:")
        try:
            # Use the batch_parse_transactions method directly
            rust_results = backend._parser.batch_parse_transactions([tx_hex])
            print(f"Rust parser returned {len(rust_results)} results")

            # Check if our transaction was included
            if len(rust_results) > 0:
                print("Transaction was included by Rust parser")
            else:
                print("Transaction was NOT included by Rust parser")

                # Debug the Rust filtering logic
                print("\nDebugging Rust filtering logic:")
                print("1. Checking for P2WSH pattern in outputs:")
                for i, vout in enumerate(ctx.vout):
                    script_bytes = bytes.fromhex(vout.scriptPubKey.hex())
                    if len(script_bytes) == 34 and script_bytes[0] == 0x00 and len(script_bytes[1:]) == 32:
                        if i > 0:  # P2WSH must not be first output
                            print(f"  - Output #{i} has valid P2WSH pattern")

                print("\n2. Checking for multisig pattern and keyburn:")
                for i, vout in enumerate(ctx.vout):
                    script_bytes = bytes.fromhex(vout.scriptPubKey.hex())
                    if len(script_bytes) > 2 and script_bytes[-1] == 0xAE:
                        print(f"  - Output #{i} has potential multisig pattern")

                        # In Rust, we check if the last pubkey starts with 0x02020202... or 0x03030303...
                        # Let's check the script bytes for this pattern
                        if b"\x02\x02\x02\x02\x02" in script_bytes or b"\x03\x03\x03\x03\x03" in script_bytes:
                            print(f"  - Output #{i} has keyburn pattern (0x0202... or 0x0303...)")

        except Exception as e:
            print(f"Error using Rust parser: {e}")
    else:
        print("\nRust parser not available")


if __name__ == "__main__":
    main()
