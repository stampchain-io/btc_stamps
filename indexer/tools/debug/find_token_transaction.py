"""
Debug script to find the missing transaction for token "10.10"
sent to address "bc1q8hyz22x03y9hv2xty8x0sh0njh92adujg3fva3" in block 865003.

This script searches for transactions in block 865003 and analyzes why a specific
transaction isn't being processed correctly.
"""

import json
import logging
import os
import sys
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Add src to path
sys.path.insert(0, ".")

# Load environment variables
from dotenv import load_dotenv

load_dotenv()

from src.config import BTC_SRC20_OLGA_BLOCK
from src.index_core import arc4, backend, blocks, script, util
from src.index_core.backend import Backend


def scan_block_for_address(block_index, target_address):
    """Scan all transactions in a block for a specific address"""
    logger.info(f"Scanning block {block_index} for transactions involving address {target_address}")

    # Create a backend instance
    bitcoin_backend = Backend()

    # Get block hash
    block_hash = bitcoin_backend.getblockhash(block_index)
    logger.info(f"Block hash: {block_hash}")

    # Get full block data
    block_data = bitcoin_backend.getblock(block_hash, 2)  # Verbosity level 2 includes tx data

    # Track all transactions involving the address
    matching_txs = []

    # Process each transaction
    for tx in block_data["tx"]:
        tx_hash = tx["txid"]
        has_address = False

        # Check inputs
        for vin in tx["vin"]:
            if "prevout" in vin and "scriptPubKey" in vin["prevout"]:
                if "addresses" in vin["prevout"]["scriptPubKey"]:
                    addresses = vin["prevout"]["scriptPubKey"]["addresses"]
                    if target_address in addresses:
                        has_address = True
                        logger.info(f"Found target address in input of tx {tx_hash}")

        # Check outputs
        for vout in tx["vout"]:
            if "scriptPubKey" in vout and "addresses" in vout["scriptPubKey"]:
                addresses = vout["scriptPubKey"]["addresses"]
                if target_address in addresses:
                    has_address = True
                    logger.info(f"Found target address in output of tx {tx_hash}")

        if has_address:
            matching_txs.append(tx_hash)
            # Analyze the transaction in detail
            detailed_analysis(tx_hash, block_index)

    logger.info(f"Found {len(matching_txs)} transactions involving address {target_address}")
    logger.info(f"Transaction hashes: {matching_txs}")
    return matching_txs


def analyze_all_transactions(block_index):
    """Analyze all transactions in a block to find potential SRC-20 tokens"""
    logger.info(f"Analyzing all transactions in block {block_index} for SRC-20 tokens")

    # Create a backend instance
    bitcoin_backend = Backend()

    # Get block hash
    block_hash = bitcoin_backend.getblockhash(block_index)

    # Get full block data
    block_data = bitcoin_backend.getblock(block_hash, 2)  # Verbosity level 2 includes tx data

    # Save original CURRENT_BLOCK_INDEX
    original_block_index = util.CURRENT_BLOCK_INDEX
    util.CURRENT_BLOCK_INDEX = block_index

    # Track potential SRC-20 transactions
    potential_src20_txs = []

    # Process each transaction
    for tx in block_data["tx"]:
        tx_hash = tx["txid"]
        tx_hex = tx["hex"]

        # Test the quick filter function
        try:
            parsed_tx = bitcoin_backend.deserialize(tx_hex)
            should_include = blocks.quick_filter_src20_transaction(parsed_tx)

            if should_include:
                logger.info(f"Transaction {tx_hash} passed quick filter")
                potential_src20_txs.append(tx_hash)

            # Analyze all outputs for potential OP_RETURN data
            for idx, vout in enumerate(parsed_tx.vout):
                try:
                    script_asm = script.get_asm(vout.scriptPubKey)
                    if script_asm and len(script_asm) > 1 and script_asm[-1] == "OP_RETURN":
                        logger.info(f"Found OP_RETURN in tx {tx_hash} output {idx}")
                        if len(script_asm) > 2:
                            data = script.process_op_return(script_asm)
                            if data:
                                try:
                                    data_str = data.decode("utf-8", errors="ignore")
                                    logger.info(f"OP_RETURN data: {data_str}")
                                    # Look for 10.10 token identifier
                                    if "10.10" in data_str:
                                        logger.info(f"Found potential 10.10 token transaction: {tx_hash}")
                                        detailed_analysis(tx_hash, block_index)
                                except:
                                    logger.info(f"OP_RETURN data (hex): {data.hex()}")
                except Exception as e:
                    logger.error(f"Error analyzing script for {tx_hash} output {idx}: {e}")

        except Exception as e:
            logger.error(f"Error analyzing transaction {tx_hash}: {e}")

    # Restore original block index
    util.CURRENT_BLOCK_INDEX = original_block_index

    logger.info(f"Found {len(potential_src20_txs)} potential SRC-20 transactions in block {block_index}")
    return potential_src20_txs


def detailed_analysis(tx_hash, block_index):
    """Perform detailed analysis of a specific transaction"""
    logger.info(f"\n===== Detailed analysis of transaction {tx_hash} =====")

    # Create a backend instance
    bitcoin_backend = Backend()

    # Save original CURRENT_BLOCK_INDEX
    original_block_index = util.CURRENT_BLOCK_INDEX

    try:
        # Set the current block index for the test
        util.CURRENT_BLOCK_INDEX = block_index

        # Get transaction hex
        tx_hex = bitcoin_backend.getrawtransaction(tx_hash)
        if not tx_hex:
            logger.error(f"Could not get transaction {tx_hash}")
            return

        # Deserialize transaction
        tx = bitcoin_backend.deserialize(tx_hex)

        # Test quick_filter_src20_transaction
        should_include = blocks.quick_filter_src20_transaction(tx)
        logger.info(f"Quick filter result: should_include={should_include}")

        # Get transaction info
        transaction_info = blocks.get_tx_info(tx_hex, block_index=block_index, db=None, stamp_issuance=None)

        if transaction_info:
            logger.info(f"Source: {transaction_info.source}")
            logger.info(f"Destinations: {transaction_info.destinations}")
            logger.info(f"Data: {transaction_info.data}")
            logger.info(f"Keyburn: {transaction_info.keyburn}")
            logger.info(f"Is OP_RETURN: {transaction_info.is_op_return}")

            # Try to decode the data if present
            if transaction_info.data:
                try:
                    data_str = transaction_info.data.decode("utf-8", errors="ignore")
                    logger.info(f"Decoded data: {data_str}")

                    # Check if it's a JSON string
                    try:
                        json_data = json.loads(data_str)
                        logger.info(f"JSON data: {json.dumps(json_data, indent=2)}")

                        # Look for SRC-20 info
                        if "p" in json_data and json_data["p"] == "src-20":
                            logger.info(f"This is an SRC-20 transaction")
                            logger.info(f"Operation: {json_data.get('op')}")
                            logger.info(f"Token: {json_data.get('tick')}")
                            logger.info(f"Amount: {json_data.get('amt')}")

                            # Check if this is our missing 10.10 token
                            if json_data.get("tick") == "10.10":
                                logger.info(f"FOUND THE MISSING 10.10 TOKEN TRANSACTION!")
                    except json.JSONDecodeError:
                        logger.info("Data is not a JSON string")
                except:
                    logger.info(f"Data appears to be binary: {transaction_info.data.hex()}")
        else:
            logger.error(f"get_tx_info returned None for {tx_hash}")

        # Analyze transaction directly
        logger.info("\nAnalyzing transaction structure:")
        for idx, vout in enumerate(tx.vout):
            logger.info(f"Output {idx} - Value: {vout.nValue}")
            script_asm = script.get_asm(vout.scriptPubKey)
            logger.info(f"  Script ASM: {script_asm}")

            if script_asm and len(script_asm) > 1:
                if script_asm[-1] == "OP_RETURN":
                    logger.info(f"  This is an OP_RETURN output")
                    if len(script_asm) > 2:
                        data = script.process_op_return(script_asm)
                        if data:
                            try:
                                data_str = data.decode("utf-8", errors="ignore")
                                logger.info(f"  OP_RETURN data: {data_str}")
                            except:
                                logger.info(f"  OP_RETURN data (hex): {data.hex()}")
                elif script_asm[-1] == "OP_CHECKMULTISIG":
                    logger.info(f"  This is a MULTISIG output")
                    try:
                        pubkeys, n, kb = script.get_checkmultisig(script_asm)
                        logger.info(f"  Pubkeys count: {len(pubkeys)}")
                        logger.info(f"  Keyburn: {kb}")

                        if kb == 1:
                            logger.info(f"  This is a potential SRC-20 multisig transaction")
                            chunk = b"".join(pubkey[1:-1] for pubkey in pubkeys)
                            logger.info(f"  Chunk size: {len(chunk)} bytes")

                            # Try to decrypt
                            try:
                                key = arc4.init_arc4(tx.vin[0].prevout.hash[::-1])
                                decrypted_chunk = arc4.arc4_decrypt_chunk(chunk, key)
                                logger.info(f"  Decrypted chunk size: {len(decrypted_chunk)} bytes")

                                # Check for SRC-20 prefix
                                from src.config import PREFIX

                                prefix_position = 2  # Standard position after length bytes
                                if (
                                    len(decrypted_chunk) >= prefix_position + len(PREFIX)
                                    and decrypted_chunk[prefix_position : prefix_position + len(PREFIX)] == PREFIX
                                ):
                                    logger.info(f"  Found SRC-20 prefix at expected position")

                                    # Extract the data
                                    chunk_length = int.from_bytes(decrypted_chunk[:2], byteorder="big")
                                    logger.info(f"  Data length prefix: {chunk_length}")

                                    if len(decrypted_chunk) >= 2 + chunk_length:
                                        data_chunk = decrypted_chunk[2 + len(PREFIX) : 2 + chunk_length]
                                        try:
                                            data_str = data_chunk.decode("utf-8", errors="ignore")
                                            logger.info(f"  Decoded data: {data_str}")

                                            # Check if it's a JSON string
                                            try:
                                                json_data = json.loads(data_str)
                                                logger.info(f"  JSON data: {json.dumps(json_data, indent=2)}")

                                                # Check if this is our missing 10.10 token
                                                if "tick" in json_data and json_data["tick"] == "10.10":
                                                    logger.info(f"  FOUND THE MISSING 10.10 TOKEN TRANSACTION!")
                                            except json.JSONDecodeError:
                                                logger.info("  Data is not a JSON string")
                                        except:
                                            logger.info(f"  Data appears to be binary: {data_chunk.hex()}")
                                    else:
                                        logger.info(f"  Data chunk is too short")
                                else:
                                    logger.info(f"  SRC-20 prefix not found at expected position")
                                    if len(decrypted_chunk) >= 10:
                                        logger.info(f"  First 10 bytes: {decrypted_chunk[:10].hex()}")
                            except Exception as e:
                                logger.error(f"  Error decrypting chunk: {e}")
                    except Exception as e:
                        logger.error(f"  Error analyzing MULTISIG: {e}")

    except Exception as e:
        logger.error(f"Error in detailed_analysis for {tx_hash}: {e}")

    finally:
        # Restore original block index
        util.CURRENT_BLOCK_INDEX = original_block_index


def main():
    """Main function that scans for missing transactions"""
    logger.info("Starting debug_missing_transaction.py")

    # Block 865003 is after the OLGA cutoff
    block_index = 865003
    logger.info(f"Analyzing block {block_index}")
    logger.info(f"BTC_SRC20_OLGA_BLOCK is set to {BTC_SRC20_OLGA_BLOCK}")

    # Target address from missing ledger entry
    target_address = "bc1q8hyz22x03y9hv2xty8x0sh0njh92adujg3fva3"

    # Option 1: Find transactions involving the target address
    matching_txs = scan_block_for_address(block_index, target_address)

    # Option 2: If no direct matches, analyze all transactions in the block
    if not matching_txs:
        logger.info("No direct matches found, analyzing all transactions in the block")
        potential_src20_txs = analyze_all_transactions(block_index)

    logger.info("Analysis complete")


if __name__ == "__main__":
    main()
