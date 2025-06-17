"""
Block validation utilities extracted from blocks.py

This module contains functions for validating blocks and their transactions,
including consensus hash calculation and transaction filtering.

Functions:
    create_check_hashes(): Calculate and update consensus hashes for block data
    validate_block_against_production(): Validate block against production database
    filter_block_transactions(): Filter transactions based on genesis status and patterns
"""

import logging
import os
import subprocess
import sys
from typing import List

import config
import index_core.check as check
import index_core.util as util
from index_core.database import update_block_hashes
from index_core.exceptions import BlockUpdateError
from index_core.models import ValidStamp
from index_core.node_health import is_shutdown_requested
from index_core.transaction_utils import backend_instance, quick_filter_src20_transaction

# Module logger
logger = logging.getLogger(__name__)


def create_check_hashes(
    db,
    block_index,
    valid_stamps_in_block: List[ValidStamp],
    processed_src20_in_block,
    txhash_list,
    previous_ledger_hash=None,
    previous_txlist_hash=None,
    previous_messages_hash=None,
):
    """
    Calculate and update the hashes for the given block data. This needs to be modified for a reparse.

    Args:
        db (Database): The database object.
        block_index (int): The index of the block.
        valid_stamps_in_block (list): The list of processed transactions in the block.
        processed_src20_in_block (list): The list of valid SRC20 tokens in the block.
        txhash_list (list): The list of transaction hashes in the block.
        previous_ledger_hash (str, optional): The hash of the previous ledger. Defaults to None.
        previous_txlist_hash (str, optional): The hash of the previous transaction list. Defaults to None.
        previous_messages_hash (str, optional): The hash of the previous messages. Defaults to None.

    Returns:
        tuple: A tuple containing the new transaction list hash, ledger hash, and messages hash.
    """
    # Filter out None values before sorting
    filtered_stamps = [stamp for stamp in valid_stamps_in_block if stamp is not None]
    sorted_valid_stamps = sorted(filtered_stamps, key=lambda x: x.get("stamp_number", ""))
    txlist_content = str(sorted_valid_stamps)
    new_txlist_hash, found_txlist_hash = check.consensus_hash(
        db, block_index, "txlist_hash", previous_txlist_hash, txlist_content
    )

    ledger_content = str(processed_src20_in_block)
    new_ledger_hash, found_ledger_hash = check.consensus_hash(
        db, block_index, "ledger_hash", previous_ledger_hash, ledger_content
    )

    messages_content = str(txhash_list)
    new_messages_hash, found_messages_hash = check.consensus_hash(
        db, block_index, "messages_hash", previous_messages_hash, messages_content
    )

    try:
        update_block_hashes(db, block_index, new_txlist_hash, new_ledger_hash, new_messages_hash)
    except BlockUpdateError as e:
        sys.exit(f"Exiting due to a critical update error: {e}")

    return new_ledger_hash, new_txlist_hash, new_messages_hash


def validate_block_against_production(block_index: int) -> bool:
    """Run the compare_tables script to validate against production."""
    if not config.DEBUG_VALIDATION:
        return True

    block_logger = logging.getLogger("validate_block")
    block_logger.info(f"Validating block {block_index} against production database...")

    try:
        script_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "tools", "compare_tables.py")

        # Check if script exists
        if not os.path.exists(script_path):
            block_logger.warning(f"Validation script not found: {script_path}")
            return True

        # Check shutdown flag before starting validation
        if is_shutdown_requested():
            block_logger.info("Skipping validation due to shutdown signal")
            return True

        process = subprocess.Popen([sys.executable, script_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        while True:
            try:
                # Use communicate with timeout to allow for interrupt checking
                stdout, stderr = process.communicate(timeout=1)
                break
            except subprocess.TimeoutExpired:
                # Check shutdown flag periodically
                if is_shutdown_requested():
                    block_logger.info("Terminating validation due to shutdown signal")
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    return True
                continue

        if process.returncode != 0:
            block_logger.error(f"Validation failed at block {block_index}")
            block_logger.error(f"Comparison output:\n{stdout}\n{stderr}")
            return False

        block_logger.info(f"Block {block_index} validation successful")
        return True

    except Exception as e:
        block_logger.error(f"Error running validation: {str(e)}")
        return True


def filter_block_transactions(block_data, stamp_issuances=None):
    """
    Filter transactions from a block based on genesis status.
    IMPORTANT: Always maintains complete tx_hash_list for hash calculation.
    Uses Rust parser for efficient batch processing if available.
    """
    logger.debug(f"Starting filter_block_transactions with {len(block_data['tx'])} transactions")

    # Initialize raw_transactions for filtered transactions
    raw_transactions = {}

    # Get all transactions from block
    all_txs = block_data["tx"]
    # CRITICAL: Create tx_hash_list with ALL transactions in original order for hash calculation
    tx_hash_list = [tx["txid"] for tx in all_txs]
    logger.debug(f"Created tx_hash_list with {len(tx_hash_list)} transactions for hash calculation")

    # Get set of issuance transactions if any
    issuance_tx_hashes = {issuance["tx_hash"] for issuance in stamp_issuances} if stamp_issuances else set()
    if issuance_tx_hashes:
        logger.debug(f"Found {len(issuance_tx_hashes)} stamp issuance transactions")

    # Before SRC20 genesis, only get stamp issuance transactions
    # Handle the case where CURRENT_BLOCK_INDEX is None
    current_block_index = util.CURRENT_BLOCK_INDEX or 0
    if current_block_index < config.BTC_SRC20_GENESIS_BLOCK:
        logger.debug("Pre-genesis block: processing only stamp issuances")
        # Only process issuance transactions (in order)
        for tx in all_txs:
            if tx["txid"] in issuance_tx_hashes:
                raw_transactions[tx["txid"]] = tx["hex"]
        logger.debug(f"Processed {len(raw_transactions)} pre-genesis transactions")
        return tx_hash_list, raw_transactions

    logger.debug("Post-genesis block: processing all potential transactions")
    # After genesis block:
    # 1. First add all stamp issuance transactions (in order)
    for tx in all_txs:
        if tx["txid"] in issuance_tx_hashes:
            raw_transactions[tx["txid"]] = tx["hex"]
            logger.debug(f"Added issuance transaction: {tx['txid']}")

    # 2. Process remaining transactions
    non_issuance_txs = [tx for tx in all_txs if tx["txid"] not in issuance_tx_hashes]
    logger.debug(f"Found {len(non_issuance_txs)} non-issuance transactions to filter")

    if non_issuance_txs:
        # Create a mapping of transaction ID to transaction object for easy lookup
        tx_id_to_tx = {tx["txid"]: tx for tx in non_issuance_txs}

        # Check if Rust parser is available and properly initialized
        if backend_instance._parser is not None:
            logger.debug("Using Rust parser for batch processing")

            # Create a list of transaction hexes in the same order as non_issuance_txs
            tx_hexes = [tx["hex"] for tx in non_issuance_txs]

            try:
                # Process transactions with Rust parser
                # Note: The Rust parser now only returns transactions that should be included
                parsed_txs = backend_instance._parser.batch_parse_transactions(tx_hexes)
                logger.debug(f"Rust parser returned {len(parsed_txs)} filtered results from {len(tx_hexes)} inputs")

                # Process each parsed transaction (all of which should be included)
                for parsed_tx in parsed_txs:
                    if parsed_tx is not None:
                        try:
                            # Try to get the txid from the parsed_tx object
                            # This should work with our EnhancedCTransaction class
                            tx_id = parsed_tx.txid

                            if tx_id in tx_id_to_tx:
                                raw_transactions[tx_id] = tx_id_to_tx[tx_id]["hex"]
                                logger.debug(f"Rust parser included transaction {tx_id}")
                            else:
                                logger.warning(f"Transaction {tx_id} returned by Rust parser not found in tx_id_to_tx")
                        except AttributeError as e:
                            logger.error(f"Transaction missing txid attribute: {e}")
                            # Skip this transaction
                            continue

            except Exception as e:
                logger.critical(f"Error in batch_parse_transactions: {e}, falling back to Python implementation")
                logger.exception(e)  # Log the full exception with traceback

                # Only use Python fallback if Rust parser completely fails
                for tx in non_issuance_txs:
                    try:
                        ctx = backend_instance.deserialize(tx["hex"])
                        filter_result = quick_filter_src20_transaction(ctx)

                        if filter_result:
                            raw_transactions[tx["txid"]] = tx["hex"]
                            logger.debug(f"Python fallback included transaction {tx['txid']}")
                    except Exception as e:
                        logger.error(f"Error processing transaction {tx['txid']}: {e}")
        else:
            # Use Python implementation if Rust parser is not available
            logger.debug("Using Python implementation for filtering")

            for tx in non_issuance_txs:
                try:
                    ctx = backend_instance.deserialize(tx["hex"])
                    filter_result = quick_filter_src20_transaction(ctx)

                    if filter_result:
                        raw_transactions[tx["txid"]] = tx["hex"]
                except Exception as e:
                    logger.error(f"Error processing transaction {tx['txid']}: {e}")

    logger.debug(f"Final transaction count: {len(raw_transactions)} filtered, {len(tx_hash_list)} total for hash")
    return tx_hash_list, raw_transactions
