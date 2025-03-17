"""
initialize database.

Sieve blockchain for Stamp transactions, and add them to the database.
"""

import concurrent.futures
import decimal
import http
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from collections import namedtuple
from typing import List

import pymysql as mysql
from bitcoin.core.script import CScriptInvalidError
from pymysql.connections import Connection

import config
import index_core.arc4 as arc4
import index_core.backend as backend
import index_core.check as check
import index_core.log as log
import index_core.script as script
import index_core.server as server
import index_core.util as util
from index_core.backend import Backend
from index_core.caching import cache_manager, clear_all_caches
from index_core.database import (
    check_db_connection,
    get_unlocked_cpids,
    initialize,
    insert_block,
    insert_into_src20_tables,
    insert_into_src101_tables,
    insert_into_stamp_table,
    insert_transactions,
    is_prev_block_parsed,
    next_tx_index,
    purge_block_db,
    rebuild_balances,
    rebuild_owners,
    update_assets_in_db,
    update_block_hashes,
    update_parsed_block,
    update_src20_token_stats,
)
from index_core.exceptions import (
    BlockAlreadyExistsError,
    BlockUpdateError,
    BTCOnlyError,
    DatabaseInsertError,
    DecodeError,
    LedgerMismatchError,
)
from index_core.fetch_utils import (
    CPBlocksPipeline,
    fetch_xcp_blocks_concurrent,
    find_issuance_by_tx_hash,
    get_xcp_assets_by_cpids,
    get_xcp_block_hash,
    verify_cp_block_hash,
)
from index_core.memory_manager import memory_manager
from index_core.models import StampData, ValidStamp
from index_core.profiling import Profiler
from index_core.src20 import (
    Src20Dict,
    clear_zero_balances,
    parse_src20,
    process_balance_updates,
    update_src20_balances,
    validate_src20_ledger_hash,
)
from index_core.src101 import Src101Dict, parse_src101, update_src101_owners
from index_core.stamp import parse_stamp
from index_core.zmq_utils import ZMQNotifier

D = decimal.Decimal
logger = logging.getLogger(__name__)
log.set_logger(logger)
skip_logger = logging.getLogger("list_tx.skip")
# Define how often to run garbage collection
GC_INTERVAL = 100

# Initialize backend instance - use the singleton
backend_instance = Backend()

TxResult = namedtuple(
    "TxResult",
    [
        "tx_index",
        "source",
        "prev_tx_hash",
        "destination",
        "destination_nvalue",
        "btc_amount",
        "fee",
        "data",
        "decoded_tx",
        "keyburn",
        "is_op_return",
        "tx_hash",
        "block_index",
        "block_hash",
        "block_time",
        "p2wsh_data",
    ],
)


class BlockProcessor:
    def __init__(self, db):
        self.db: Connection = db
        self.valid_stamps_in_block: List[ValidStamp] = []
        self.parsed_stamps: List[StampData] = []
        self.processed_src20_in_block: List[Src20Dict] = []
        self.processed_src101_in_block: List[Src101Dict] = []
        self.collection_operations = []
        self._lock = threading.Lock()

    def process_transaction_results(self, tx_results):
        """Process transaction results."""
        logger.debug(f"Processing {len(tx_results)} transaction results")

        # Then process each transaction for stamps
        for result in tx_results:
            try:

                stamp_data = StampData(
                    tx_hash=result.tx_hash,
                    source=result.source,
                    prev_tx_hash=result.prev_tx_hash,
                    destination=result.destination,
                    destination_nvalue=result.destination_nvalue,
                    btc_amount=result.btc_amount,
                    fee=result.fee,
                    data=result.data,
                    decoded_tx=result.decoded_tx,
                    keyburn=result.keyburn,
                    tx_index=result.tx_index,
                    block_index=result.block_index,
                    block_time=result.block_time,
                    is_op_return=result.is_op_return,
                    p2wsh_data=result.p2wsh_data,
                )

                _, stamp_data, valid_stamp, prevalidated_src = parse_stamp(
                    stamp_data=stamp_data,
                    db=self.db,
                    valid_stamps_in_block=self.valid_stamps_in_block,
                )

                if stamp_data:
                    with self._lock:
                        self.parsed_stamps.append(stamp_data)
                        self.collection_operations.append((stamp_data, config.LEGACY_COLLECTIONS))
                    logger.debug(f"Added stamp data for tx: {result.tx_hash}")
                if valid_stamp:
                    with self._lock:
                        self.valid_stamps_in_block.append(valid_stamp)

                if prevalidated_src and stamp_data and stamp_data.pval_src20:
                    logger.debug(f"\nProcessing SRC20 for tx: {result.tx_hash}")
                    _, src20_dict = parse_src20(self.db, prevalidated_src, self.processed_src20_in_block, self._lock)
                    logger.debug(f"SRC20 dict created: {src20_dict}")
                    with self._lock:
                        self.processed_src20_in_block.append(src20_dict)
                if prevalidated_src and stamp_data and stamp_data.pval_src101:
                    _, src101_dict = parse_src101(
                        self.db, prevalidated_src, self.processed_src101_in_block, stamp_data.block_index, self._lock
                    )
                    logger.debug(f"SRC101 dict created: {src101_dict}")
                    with self._lock:
                        self.processed_src101_in_block.append(src101_dict)
            except Exception as e:
                logger.error(f"Error in process_transaction_results for tx {result.tx_hash}: {e}", exc_info=True)
                raise

        if self.parsed_stamps:
            logger.debug(f"Inserting {len(self.parsed_stamps)} stamps into table")
            insert_into_stamp_table(self.db, self.parsed_stamps)

            if self.collection_operations:
                logger.debug(f"Processing {len(self.collection_operations)} collection operations")
                for stamp, collections in self.collection_operations:
                    try:
                        stamp.match_and_insert_collection_data(collections, self.db)
                    except Exception as e:
                        logger.error(f"Error in match_and_insert_collection_data: {e}", exc_info=True)
                        raise

    def finalize_block(self, block_index, block_time, txhash_list):
        if self.processed_src20_in_block:
            balance_updates = update_src20_balances(self.db, block_index, block_time, self.processed_src20_in_block)
            insert_into_src20_tables(self.db, self.processed_src20_in_block)
            valid_src20_str = process_balance_updates(balance_updates)
        else:
            valid_src20_str = ""

        if self.processed_src101_in_block:
            insert_into_src101_tables(self.db, self.processed_src101_in_block)
            update_src101_owners(self.db, block_index, self.processed_src101_in_block)

        if block_index > config.BTC_SRC20_GENESIS_BLOCK and block_index % 100 == 0:
            clear_zero_balances(self.db)

        new_ledger_hash, new_txlist_hash, new_messages_hash = create_check_hashes(
            self.db, block_index, self.valid_stamps_in_block, valid_src20_str, txhash_list
        )

        # Only validate ledger hash if both valid_src20_str and new_ledger_hash are non-empty
        if valid_src20_str and new_ledger_hash:
            if not validate_src20_ledger_hash(block_index, new_ledger_hash, valid_src20_str):
                # Only raise LedgerMismatchError if FORCE is not enabled
                if not config.FORCE:
                    raise LedgerMismatchError(block_index)
                else:
                    logger.warning(f"Ledger hash mismatch at block {block_index}. Continuing due to FORCE=True...")

        stamps_in_block = len(self.valid_stamps_in_block)
        src20_in_block = len(self.processed_src20_in_block)
        src101_in_block = len(self.processed_src101_in_block)
        return new_ledger_hash, new_txlist_hash, new_messages_hash, stamps_in_block, src20_in_block, src101_in_block

    def insert_transactions(self, tx_results):
        insert_transactions(self.db, tx_results)


def process_vout(ctx, block_index, stamp_issuance=None):
    """Process a decoded transaction's outputs, capturing relevant data and addresses.

    Args:
        ctx (ctx): The decoded transaction context.
        block_index (int): The block index.
        stamp_issuance (dict, optional): Stamp issuance information. Defaults to None.

    Returns:
        namedtuple: vOutInfo containing pubkeys_compiled, keyburn, is_op_return, fee, is_olga, p2wsh_data_chunks
    """
    # Get scripts
    vouts = ctx.vout
    keyburn = None
    is_op_return = None
    script_token_values = 0
    p2wsh_data_chunks = []
    is_olga = False

    pubkeys_compiled = []

    for idx, vout in enumerate(vouts):
        asm = script.get_asm(vout.scriptPubKey)
        n_value = vout.nValue
        script_token_values += n_value
        fee = script_token_values

        if asm[-1] == "OP_CHECKMULTISIG":
            # Multisig outputs encoded with SRC-20 data
            pubkeys, signatures_required, keyburn_vout = script.get_checkmultisig(asm)
            if keyburn_vout is not None:
                keyburn = keyburn_vout
            pubkeys_compiled += pubkeys
        elif asm[0] == "OP_RETURN":
            is_op_return = True
        elif stamp_issuance is not None and asm[0] == 0 and len(asm[1]) == 32:
            # Pay-to-Witness-Script-Hash (P2WSH) on CPID transactions
            pubkeys = script.get_p2wsh(asm)
            pubkeys_compiled += pubkeys
            is_olga = True
        elif asm[0] == 0 and len(asm[1]) == 32:
            # Pay-to-Witness-Script-Hash (P2WSH) on SRC-20 transactions
            # Only process outputs after the first one (idx > 0)
            if block_index >= config.BTC_SRC20_OLGA_BLOCK and idx > 0:
                data_bytes = asm[1]
                p2wsh_data_chunks.append(data_bytes)
                is_olga = True
                logger.debug(f"Found P2WSH output at index {idx} with bytes: {data_bytes.hex()[:20]}...")
    
    vOutInfo = namedtuple(
        "vOutInfo",
        ["pubkeys_compiled", "keyburn", "is_op_return", "fee", "is_olga", "p2wsh_data_chunks"],
    )

    return vOutInfo(pubkeys_compiled, keyburn, is_op_return, fee, is_olga, p2wsh_data_chunks)


def get_tx_info(tx_hex, block_index=None, db=None, stamp_issuance=None):
    """
    Get transaction information.

    Args:
        tx_hex (str): The hexadecimal representation of the transaction.
        block_index (int, optional): The index of the block.
        db (object, optional): The database object.
        stamp_issuance (bool, optional): Flag indicating if the transaction is a stamp issuance.

    Returns:
        TransactionInfo: A named tuple containing the transaction information.
    """
    TransactionInfo = namedtuple(
        "TransactionInfo",
        [
            "source",
            "prev_tx_hash",
            "destinations",
            "destination_nvalue",
            "btc_amount",
            "fee",
            "data",
            "ctx",
            "keyburn",
            "is_op_return",
            "p2wsh_data",
        ],
    )

    try:
        if not block_index:
            block_index = util.CURRENT_BLOCK_INDEX

        destinations, src_destination_nvalue, btc_amount, data, p2wsh_data = [], 0, 0, b"", b""

        ctx = backend_instance.deserialize(tx_hex)
        vout_info = process_vout(ctx, block_index, stamp_issuance=stamp_issuance)
        pubkeys_compiled = vout_info.pubkeys_compiled
        keyburn = vout_info.keyburn
        is_op_return = vout_info.is_op_return
        fee = vout_info.fee
        p2wsh_data_chunks = vout_info.p2wsh_data_chunks
        p2wsh_data = None

        if stamp_issuance is not None:
            # Process CP encoded stamp issuance P2WSH transactions
            if pubkeys_compiled and vout_info.is_olga:
                chunk = b"".join(pubkeys_compiled)
                pubkey_len = int.from_bytes(chunk[:2], byteorder="big")
                p2wsh_data = chunk[2 : 2 + pubkey_len]
            else:
                p2wsh_data = None
            return TransactionInfo(
                None,
                None,
                None,
                None,
                btc_amount,
                round(fee),
                None,
                None,
                keyburn,
                is_op_return,
                p2wsh_data,
            )

        # Handle P2WSH data chunks for SRC-20 transactions
        if p2wsh_data_chunks:
            p2wsh_data = b"".join(p2wsh_data_chunks).rstrip(b"\x00")  # Remove padding zeros

            if p2wsh_data and len(p2wsh_data) >= 2 + len(config.PREFIX):
                # Extract the length prefix (first 2 bytes)
                chunk_length = int.from_bytes(p2wsh_data[:2], byteorder="big")
                
                # Ensure that p2wsh_data has enough bytes
                if len(p2wsh_data) >= 2 + chunk_length:
                    # Extract the data chunk
                    data_chunk = p2wsh_data[2 : 2 + chunk_length]
                    
                    # Check for config.PREFIX at the start of data_chunk
                    if data_chunk.startswith(config.PREFIX):
                        data_chunk_without_prefix = data_chunk[len(config.PREFIX) :]
                        data = data_chunk_without_prefix
                        keyburn = 1  # setting to keyburn since this was a requirement of msig, and validates it later
                        p2wsh_data = None
                        destination_pubkey = ctx.vout[0].scriptPubKey
                        destinations = util.decode_address(destination_pubkey)
                        src_destination_nvalue = 0
                        if config.BTC_SRC101_OLGA_BLOCK != 0 and block_index >= config.BTC_SRC101_OLGA_BLOCK:
                            src_destination_nvalue = ctx.vout[0].nValue
                    else:
                        p2wsh_data = None
                else:
                    p2wsh_data = None
            else:
                p2wsh_data = None

        # SRC-20 via MULTISIG
        # This prioritizes P2WSH over CHECKMULTISIG in a mixed transaction
        # To be deprecated in a future block height over P2WSH for all SRC-20 transactions
        # Important: Continue to process MULTISIG data even if P2WSH data is present but invalid
        elif pubkeys_compiled:
            chunk = b"".join(pubkey[1:-1] for pubkey in pubkeys_compiled)
            try:
                src_destination, src_destination_nvalue, src_data = decode_checkmultisig(ctx, chunk)
            except Exception as e:
                raise DecodeError(f"unrecognized output type: {e}")
            if src_destination is None or src_data is None:
                raise ValueError("src20_destination and src20_data must not be None")
            if src_data:
                data += src_data
                destinations = str(src_destination)

        if not data:
            raise BTCOnlyError("no data, not a stamp", ctx)

        vin = ctx.vin[0]

        prev_tx_hash = vin.prevout.hash
        prev_tx_index = vin.prevout.n

        # Get the full transaction data for the previous transaction.
        # TODO: Can we batch process these for all calls from trx in the block
        prev_tx = backend_instance.getrawtransaction(util.ib2h(prev_tx_hash))
        prev_ctx = backend_instance.deserialize(prev_tx)

        # Get the output being spent by the input.
        prev_vout = prev_ctx.vout[prev_tx_index]
        prev_vout_script_pubkey = prev_vout.scriptPubKey

        # Decode the address associated with the output.
        source = util.decode_address(prev_vout_script_pubkey)

        return TransactionInfo(
            str(source),
            prev_tx_hash,
            destinations,
            src_destination_nvalue,
            btc_amount,
            round(fee),
            data,
            ctx,
            keyburn,
            is_op_return,
            None,
        )

    except (DecodeError, BTCOnlyError):
        return TransactionInfo(b"", None, None, None, None, None, None, None, None, None, None)


def decode_checkmultisig(ctx, chunk):
    """
    Decode a checkmultisig transaction chunk. Decoding in ARC4 and looking for the STAMP prefix
    This also validates the length of the string with the 2 byte data length prefix

    Args:
        ctx (Context): The context object containing transaction information.
        chunk (bytes): The chunk to be decoded.

    Returns:
        tuple: A tuple containing the destination address (str) and the decoded data (bytes).
               If the chunk does not match the expected format, returns (None, None, None).

    Raises:
        DecodeError: If the decoded data length does not match the expected length.
    """
    key = arc4.init_arc4(ctx.vin[0].prevout.hash[::-1])
    chunk = arc4.arc4_decrypt_chunk(chunk, key)
    if chunk[2 : 2 + len(config.PREFIX)] == config.PREFIX:
        chunk_length = chunk[:2].hex()
        data = chunk[len(config.PREFIX) + 2 :].rstrip(b"\x00")
        data_length = len(chunk[2:].rstrip(b"\x00"))
        if data_length != int(chunk_length, 16):
            raise DecodeError("invalid data length")

        script_pubkey = ctx.vout[0].scriptPubKey
        destination = util.decode_address(script_pubkey)
        destination_nvalue = ctx.vout[0].nValue
        return str(destination), destination_nvalue, data
    else:
        return None, None, data


def list_tx(db, block_index: int, tx_hash: str, tx_hex=None, stamp_issuance=None):

    if not isinstance(tx_hash, str):
        raise TypeError("tx_hash must be a string")

    if tx_hex is None:
        logger.debug(f"Fetching raw transaction for tx_hash: {tx_hash}")
        tx_hex = backend_instance.getrawtransaction(tx_hash, verbose=False, skip_missing=False, current_block=block_index)

    transaction_info = get_tx_info(tx_hex, block_index=block_index, db=db, stamp_issuance=stamp_issuance)
    source = getattr(transaction_info, "source", None)
    prev_tx_hash = getattr(transaction_info, "prev_tx_hash", None)
    destination = getattr(transaction_info, "destinations", None)
    destination_nvalue = getattr(transaction_info, "destination_nvalue", None)
    btc_amount = getattr(transaction_info, "btc_amount", None)
    fee = getattr(transaction_info, "fee", None)
    data = getattr(transaction_info, "data", None)
    decoded_tx = getattr(transaction_info, "ctx", None)
    keyburn = getattr(transaction_info, "keyburn", None)
    is_op_return = getattr(transaction_info, "is_op_return", None)
    p2wsh_data = getattr(transaction_info, "p2wsh_data", None)

    if block_index != util.CURRENT_BLOCK_INDEX:
        raise ValueError(f"block_index does not match util.CURRENT_BLOCK_INDEX: {block_index} != {util.CURRENT_BLOCK_INDEX}")

    if stamp_issuance is not None:
        source = str(stamp_issuance["source"])
        destination = str(stamp_issuance["issuer"])
        data = str(stamp_issuance)

    if source and (data or destination):
        logger.debug(
            "Processing transaction: {} DATA: {} KEYBURN: {} OP_RETURN: {}".format(tx_hash, data, keyburn, is_op_return)
        )

        return (
            source,
            prev_tx_hash,
            destination,
            destination_nvalue,
            btc_amount,
            fee,
            data,
            decoded_tx,
            keyburn,
            is_op_return,
            p2wsh_data,
        )

    else:
        # skip_logger.debug("Skipping transaction: {}".format(tx_hash))
        return (None for _ in range(11))


def create_check_hashes(
    db,
    block_index,
    valid_stamps_in_block: list[ValidStamp],
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
    sorted_valid_stamps = sorted(valid_stamps_in_block, key=lambda x: x.get("stamp_number", ""))
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


def commit_and_update_block(db, block_index, block_tip, src20_in_block=0):
    """Commit transaction and update block with proper error handling."""
    max_retries = 3
    retry_delay = 2  # seconds

    for attempt in range(max_retries):
        try:
            # Update SRC-20 token stats if:
            # 1. At tip with SRC20 transactions OR every 100th block
            # 2. During bulk sync, every 1000th block as safety net
            if block_index >= config.BTC_SRC20_GENESIS_BLOCK:
                should_update_stats = (block_index == block_tip and (block_index % 100 == 0 or src20_in_block > 0)) or (
                    block_tip - block_index > 100 and block_index % 1000 == 0
                )
                if should_update_stats:
                    logger.debug(f"Updating token stats at block {block_index} (src20_txs: {src20_in_block})")
                    update_src20_token_stats(db)

            db.commit()
            update_parsed_block(db, block_index)
            block_index += 1
            return block_index
        except Exception as e:
            logger.error(f"Error committing block {block_index} (attempt {attempt+1}/{max_retries}): {e}")
            db.rollback()

            if attempt < max_retries - 1:
                # Check and potentially reconnect the database before retrying
                try:
                    db = check_db_connection(db)
                    logger.info(f"Database connection checked/renewed, retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                except Exception as conn_err:
                    logger.critical(f"Failed to reconnect to database: {conn_err}")
                    raise
            else:
                logger.critical(f"Failed to commit block {block_index} after {max_retries} attempts")
                if config.FORCE:
                    logger.warning(f"FORCE mode enabled, continuing despite commit failure for block {block_index}")
                    block_index += 1
                    return block_index
                else:
                    raise


def log_block_info(
    block_index: int,
    start_time: float,
    new_ledger_hash: str,
    new_txlist_hash: str,
    new_messages_hash: str,
    stamps_in_block: int,
    src20_in_block: int,
    src101_in_block: int = 0,
) -> None:
    """
    Logs block information with highly stable ETA using weighted EMA and complexity factors.
    Skips first block of each batch in calculations due to CP overhead.
    """
    try:
        # Get current tip of the blockchain
        block_tip: int = backend_instance.getblockcount()

        # Calculate progress based on CP genesis block to current tip
        blocks_to_process = block_tip - config.CP_STAMP_GENESIS_BLOCK
        blocks_processed = block_index - config.CP_STAMP_GENESIS_BLOCK

        # Ensure we don't show progress before genesis block
        if block_index < config.CP_STAMP_GENESIS_BLOCK:
            current_progress = 0.0
        else:
            current_progress = min(1.0, blocks_processed / blocks_to_process if blocks_to_process > 0 else 0)

        # Log memory usage and cache stats every 100 blocks
        if block_index % 100 == 0:
            memory_manager.log_memory_usage(block_index)
            cache_manager.log_cache_stats()  # Use CacheManager's stats logging

        # Initialize tracking variables if not exists
        if not hasattr(log_block_info, "_state"):
            setattr(
                log_block_info,
                "_state",
                {
                    "times": [],  # Store last N block times
                    "window_size": 100,  # Reduced window for faster initial ETA
                    "last_eta_update": 0,
                    "last_eta": None,
                    "last_tip": block_tip,
                    "last_time": start_time,  # Track last block's time
                },
            )

        state = getattr(log_block_info, "_state")
        current_time = time.time() - state.get("last_time", start_time)  # Time since last block
        state["last_time"] = time.time()  # Update for next block

        # Detect if block tip has changed
        if block_tip != state["last_tip"]:
            logger.debug(f"Block tip changed from {state['last_tip']} to {block_tip}")
            state["last_tip"] = block_tip

        # Check if this is a CP fetch block (every 100 blocks)
        is_cp_fetch_block = (block_index % 100) == 0
        if is_cp_fetch_block:
            logger.debug(f"CP fetch block at {block_index}")

        # Only update times list if not a CP fetch block and time is reasonable
        if not is_cp_fetch_block and current_time < 10:  # Filter out outliers > 10s
            state["times"].append(current_time)
            if len(state["times"]) > state["window_size"]:
                state["times"].pop(0)

        # Calculate ETA using simple moving average
        if len(state["times"]) >= 5:  # Reduced minimum samples needed
            # Calculate average excluding highest 10% of times to handle outliers
            sorted_times = sorted(state["times"])
            cutoff = int(len(sorted_times) * 0.9)
            avg_time = sum(sorted_times[:cutoff]) / cutoff

            blocks_remaining = block_tip - block_index
            # Add time for remaining CP fetch blocks
            cp_fetches_remaining = blocks_remaining // 100  # CP fetch every 100 blocks
            est_seconds_remaining = (blocks_remaining * avg_time) + (cp_fetches_remaining * 5)  # Assume 5s per CP fetch

            # Convert to hours and minutes
            hours = int(est_seconds_remaining // 3600)
            minutes = int((est_seconds_remaining % 3600) // 60)

            # Update ETA only every 20 blocks or if significant change
            should_update = (
                state["last_eta"] is None
                or (block_index - state["last_eta_update"]) >= 20
                or abs(hours - state["last_eta"][0]) > 0
                or abs(minutes - state["last_eta"][1]) > 5
            )

            if should_update:
                state["last_eta"] = (hours, minutes)
                state["last_eta_update"] = block_index
            else:
                hours, minutes = state["last_eta"]

            eta = f"{hours}h {minutes:02d}m"
        else:
            eta = "calculating..."

        logger.block_status(  # type: ignore[attr-defined]
            "Block: %s/%s │ %ss │ ETA: %s │ Prog: %s%% │ [S:%s|20:%s|101:%s]"
            % (
                str(block_index),
                str(block_tip),
                "{:.2f}".format(current_time),
                eta,
                "{:.1f}".format(current_progress * 100),
                stamps_in_block,
                src20_in_block,
                src101_in_block,
            )
        )

    except Exception as e:
        logger.error(f"Error in log_block_info: {e}")
        logger.block_status(  # type: ignore[attr-defined]
            "Block: %s/%s │ %ss │ [S:%s|20:%s|101:%s]"
            % (
                str(block_index),
                str(block_tip),
                "{:.2f}".format(time.time() - start_time),
                stamps_in_block,
                src20_in_block,
                src101_in_block,
            )
        )


def process_tx(db, tx_hash, block_index, stamp_issuances, raw_transactions):
    """Process a single transaction and return its parsed information."""

    # Ensure stamp_issuances is a list before filtering
    if stamp_issuances is None:
        stamp_issuances = []
    elif not isinstance(stamp_issuances, list):
        logger.error(f"Invalid stamp_issuances type: {type(stamp_issuances)}")
        stamp_issuances = []

    stamp_issuance = find_issuance_by_tx_hash(stamp_issuances, tx_hash)

    tx_hex = raw_transactions[tx_hash]
    try:
        (
            source,
            prev_tx_hash,
            destination,
            destination_nvalue,
            btc_amount,
            fee,
            data,
            decoded_tx,
            keyburn,
            is_op_return,
            p2wsh_data,
        ) = list_tx(db, block_index, tx_hash, tx_hex, stamp_issuance=stamp_issuance)

        return TxResult(
            None,
            source,
            prev_tx_hash,
            destination,
            destination_nvalue,
            btc_amount,
            fee,
            data,
            decoded_tx,
            keyburn,
            is_op_return,
            tx_hash,
            block_index,
            None,
            None,
            p2wsh_data,
        )
    except Exception:  # Removed unused variable 'e'
        return TxResult(
            None, None, None, None, None, None, None, None, None, None, None, tx_hash, block_index, None, None, None
        )


def quick_filter_src20_transaction(ctx):
    """
    Quick pre-filter to check if a transaction might be a valid SRC-20 transaction.
    Must have either:
    1. One or more valid P2WSH outputs containing concatenated data with prefix: STAMP: (OLGA format)
    2. A multisig output with keyburn and data containing valid prefix STAMP:
    """
    tx_hash = ctx.GetHash()
    tx_hash_str = tx_hash.hex() if isinstance(tx_hash, bytes) else str(tx_hash)

    keyburn = None
    has_valid_pattern = False
    has_valid_data = False

    # First check for P2WSH pattern in all outputs - SRC-20 data may be split across multiple outputs
    try:
        vout_list = []
        # Handle different ctx types (CTransaction vs dict)
        if hasattr(ctx, "vout"):
            vout_list = ctx.vout
        elif isinstance(ctx, dict) and "vout" in ctx:
            vout_list = ctx["vout"]

        logger.debug(f"Transaction {tx_hash_str} has {len(vout_list)} outputs")
        
        # Collect all P2WSH data chunks across all outputs
        all_p2wsh_data_chunks = []
        
        for idx, vout in enumerate(vout_list):
            # Handle different vout types
            script_bytes = None
            if hasattr(vout, "scriptPubKey") and hasattr(vout.scriptPubKey, "hex"):
                script_bytes = bytes.fromhex(vout.scriptPubKey.hex())
            elif isinstance(vout, dict) and "scriptPubKey" in vout:
                if isinstance(vout["scriptPubKey"], dict) and "hex" in vout["scriptPubKey"]:
                    script_bytes = bytes.fromhex(vout["scriptPubKey"]["hex"])
                elif hasattr(vout["scriptPubKey"], "hex"):
                    script_bytes = bytes.fromhex(vout["scriptPubKey"].hex())

            if script_bytes is None:
                logger.debug(f"Could not get script_bytes for output {idx} in tx {tx_hash_str}")
                continue

            # Check for P2WSH pattern (0x00 + exactly 32 bytes)
            if len(script_bytes) >= 33 and script_bytes[0] == 0x00:
                if script_bytes[1] == 0x20:  # 0x20 is the value 32 in hex, indicates 32 bytes follow
                    data_bytes = script_bytes[2:34]  # Get the 32 bytes of data
                    all_p2wsh_data_chunks.append(data_bytes)
                    logger.debug(f"Transaction {tx_hash_str} has P2WSH data in output {idx}: {data_bytes.hex()[:20]}...")
                    has_valid_pattern = True
        
        # Additionally check for multisig pattern in all outputs
        for idx, vout in enumerate(vout_list):
            script_bytes = None
            if hasattr(vout, "scriptPubKey") and hasattr(vout.scriptPubKey, "hex"):
                script_bytes = bytes.fromhex(vout.scriptPubKey.hex())
            elif isinstance(vout, dict) and "scriptPubKey" in vout:
                if isinstance(vout["scriptPubKey"], dict) and "hex" in vout["scriptPubKey"]:
                    script_bytes = bytes.fromhex(vout["scriptPubKey"]["hex"])
                elif hasattr(vout["scriptPubKey"], "hex"):
                    script_bytes = bytes.fromhex(vout["scriptPubKey"].hex())
                    
            # Check for multisig pattern and keyburn
            if script_bytes and len(script_bytes) > 2 and script_bytes[-1] == 0xAE:
                logger.debug(f"Transaction {tx_hash_str} has potential multisig pattern at output {idx}")
                try:
                    asm = None
                    if hasattr(vout, "scriptPubKey"):
                        asm = script.get_asm(vout.scriptPubKey)
                    elif isinstance(vout, dict) and "scriptPubKey" in vout:
                        if isinstance(vout["scriptPubKey"], dict) and "asm" in vout["scriptPubKey"]:
                            asm = vout["scriptPubKey"]["asm"].split()
                        else:
                            asm = script.get_asm(vout["scriptPubKey"])

                    if asm is None:
                        logger.debug(f"Could not get ASM for output {idx} in tx {tx_hash_str}")
                        continue
                    
                    if asm[-1] == "OP_CHECKMULTISIG":
                        logger.debug(f"Transaction {tx_hash_str} has OP_CHECKMULTISIG at output {idx}")
                        pubkeys, _, kb = script.get_checkmultisig(asm)
                        logger.debug(f"Transaction {tx_hash_str} output {idx}: pubkeys={pubkeys}, kb={kb}")
                        if kb == 1:
                            keyburn = 1
                            logger.debug(f"Transaction {tx_hash_str} has keyburn=1 at output {idx}")
                            # Try to decode the data
                            chunk = b"".join(pubkey[1:-1] for pubkey in pubkeys)
                            logger.debug(f"Transaction {tx_hash_str} output {idx}: chunk={chunk.hex()}")
                            key = arc4.init_arc4(ctx.vin[0].prevout.hash[::-1])
                            chunk = arc4.arc4_decrypt_chunk(chunk, key)
                            logger.debug(f"Transaction {tx_hash_str} output {idx}: decrypted chunk={chunk.hex()}")
                            if len(chunk) >= 2 + len(config.PREFIX) and chunk[2 : 2 + len(config.PREFIX)] == config.PREFIX:
                                has_valid_data = True
                                logger.debug(f"Transaction {tx_hash_str} has valid SRC-20 data")
                                break  # Found valid data, no need to process other outputs
                            else:
                                logger.debug(
                                    f"Transaction {tx_hash_str} output {idx}: PREFIX not found. Expected: {config.PREFIX.hex()}, Found: {chunk[2 : 2 + len(config.PREFIX)].hex() if len(chunk) >= 2 + len(config.PREFIX) else 'too short'}"
                                )
                except Exception as e:
                    logger.debug(f"Error processing multisig at output {idx} in tx {tx_hash_str}: {e}")
        
        # Process combined P2WSH data if we have any chunks
        if all_p2wsh_data_chunks and has_valid_pattern and not has_valid_data:
            try:
                # Combine all P2WSH data chunks and check for valid SRC-20 data
                combined_data = b"".join(all_p2wsh_data_chunks).rstrip(b"\x00")  # Remove padding zeros
                logger.debug(f"Combined {len(all_p2wsh_data_chunks)} P2WSH chunks: {combined_data.hex()[:100]}...")
                
                # Check if combined data contains the STAMP: prefix
                if config.PREFIX in combined_data:
                    # Set keyburn to 1 since this was a requirement for P2WSH
                    keyburn = 1
                    has_valid_data = True
                    logger.debug(f"Transaction {tx_hash_str} combined P2WSH data contains STAMP: prefix")
                else:
                    # Also check if any individual chunk contains the prefix
                    for i, chunk in enumerate(all_p2wsh_data_chunks):
                        if config.PREFIX in chunk:
                            keyburn = 1
                            has_valid_data = True
                            logger.debug(f"Transaction {tx_hash_str} P2WSH chunk {i} contains STAMP: prefix")
                            break
            except Exception as e:
                logger.debug(f"Error processing combined P2WSH data for tx {tx_hash_str}: {e}")
                
    except Exception as e:
        logger.debug(f"Error in output processing for tx {tx_hash_str}: {e}")

    # Match the Rust implementation logic: include a transaction if it has either:
    # 1. A valid P2WSH pattern (OLGA format) with valid data
    # 2. A valid OP_CHECKMULTISIG with keyburn and valid data
    should_include = (has_valid_pattern and has_valid_data) or (has_valid_data and keyburn == 1)

    logger.debug(
        f"Transaction {tx_hash_str}: has_valid_pattern={has_valid_pattern}, has_valid_data={has_valid_data}, keyburn={keyburn}, should_include={should_include}"
    )

    return should_include


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





def calculate_rollback_depth(block_index: int, reason: str) -> int:
    """
    Calculate how many blocks to roll back based on the reason.

    Args:
        block_index: Current block index
        reason: Reason for the rollback

    Returns:
        int: Number of blocks to roll back (target will be block_index - depth)
    """
    if "Chain reorganization" in reason:
        # For chain reorgs, roll back 10 blocks to be safe
        return 10
    elif "Duplicate key" in reason or "transient" in reason:
        # For duplicate keys or transient errors, just roll back 1 block
        return 1
    else:
        # For unknown errors, roll back 3 blocks to be safe but not excessive
        return 3


def rollback_to_block(db: Connection, block_index: int, reason: str) -> int:
    """Roll back the database to a specific block index with full cleanup."""
    # Calculate rollback depth based on error type
    rollback_depth = calculate_rollback_depth(block_index, reason)
    target_block = max(block_index - rollback_depth, config.BLOCK_FIRST)

    logger.warning(f"ROLLBACK INITIATED: Rolling back {rollback_depth} blocks to {target_block} ({reason})")

    # Verify hashes at target block
    current_bitcoin_hash = backend_instance.getblockhash(target_block)
    if not verify_cp_block_hash(target_block, current_bitcoin_hash):
        logger.error("XCP node hasn't rolled back properly, finding common ancestor...")
        return find_common_ancestor_with_xcp(db, target_block - 1)

    try:
        # Perform the actual database rollback
        purge_block_db(db, target_block)

        # Clear all caches
        clear_all_caches()
        logger.info("Cleared all caches after rollback")

        # Rebuild critical database state
        logger.info("Rebuilding database state...")
        rebuild_balances(db)
        rebuild_owners(db)
        update_src20_token_stats(db)
        logger.info(f"Successfully rolled back to block {target_block}")

    except Exception as e:
        logger.critical(f"Critical error during rollback cleanup: {e}")
        if not config.FORCE:
            sys.exit("Exiting due to failed rollback cleanup")

    return target_block


def find_common_ancestor_with_xcp(db: Connection, start_index: int) -> int:
    """Find common ancestor with both Bitcoin chain and XCP node"""
    logger.info("Starting deep reorg detection with XCP verification...")

    while start_index >= config.BLOCK_FIRST:
        # Get Bitcoin chain data
        current_bitcoin_hash = backend_instance.getblockhash(start_index)
        block_header = backend_instance.getblockheader(current_bitcoin_hash)
        bitcoin_parent = block_header["previousblockhash"]

        # Get database data
        with db.cursor() as cursor:
            cursor.execute("SELECT block_hash FROM blocks WHERE block_index = %s", (start_index,))
            db_block = cursor.fetchone()

        if not db_block:
            logger.warning(f"No block found at index {start_index}, continuing...")
            start_index -= 1
            continue

        db_hash = db_block[0]

        # Verify Bitcoin chain consistency
        if db_hash != bitcoin_parent:
            logger.warning(f"Bitcoin parent mismatch at {start_index}, continuing rollback...")
            start_index -= 1
            continue

        # Verify XCP node consistency
        xcp_hash = get_xcp_block_hash(start_index)
        if xcp_hash != db_hash:
            logger.warning(f"XCP hash mismatch at {start_index}, continuing rollback...")
            start_index -= 1
            continue

        # Full match found
        logger.info(f"Found common ancestor at block {start_index}")
        return start_index

    return config.BLOCK_FIRST


def cleanup_resources(executor, zmq_notifier, update_cpids_future, db, cp_pipeline=None):
    """Helper function to clean up resources safely."""
    logger.info("Starting cleanup...")

    # Stop CP pipeline
    if cp_pipeline:
        logger.info("Stopping CP blocks pipeline...")
        try:
            cp_pipeline.stop()
        except Exception as e:
            logger.error(f"Error stopping CP pipeline: {e}")

    # Cancel any pending CPID updates
    if update_cpids_future and not update_cpids_future.done():
        logger.info("Cancelling pending CPID updates...")
        update_cpids_future.cancel()

    # Clean up ZMQ
    if zmq_notifier:
        logger.info("Cleaning up ZMQ resources...")
        try:
            zmq_notifier.cleanup()
        except Exception as e:
            logger.error(f"Error cleaning up ZMQ: {e}")

    # Clean up thread pool
    if executor:
        logger.info("Shutting down executor...")
        try:
            # Give threads a chance to complete
            executor.shutdown(wait=True)
        except (TypeError, Exception) as e:
            logger.error(f"Error shutting down executor: {e}")
            try:
                executor.shutdown(wait=False)
            except Exception:
                pass

    # Commit any pending transactions and close DB
    try:
        logger.info("Finalizing database operations...")
        if not db._closed:
            try:
                db.commit()
                logger.info("Final commit successful")
            except Exception as e:
                logger.error(f"Error during final commit: {e}")
                try:
                    db.rollback()
                except Exception:
                    pass
            finally:
                try:
                    db.close()
                    logger.info("Database connection closed")
                except Exception as e:
                    logger.error(f"Error closing database: {e}")
    except Exception as e:
        logger.error(f"Error during database cleanup: {e}")

    logger.info("Cleanup complete")
    logging.shutdown()


def signal_handler(sig, frame):
    """
    Handle SIGINT (Ctrl+C) gracefully.
    This handler is designed to be thread-safe and idempotent.
    """
    global profiler  # Add global reference to access profiler

    if server.shutdown_flag.is_set():
        # If flag is already set, force exit
        logger.warning("Received second interrupt, forcing exit...")
        if "profiler" in globals():
            profiler.end_block_profiling()  # End profiling before force exit
        sys.exit(1)

    logger.info("Received interrupt signal, initiating graceful shutdown...")
    if "profiler" in globals():
        profiler.end_block_profiling()  # End profiling on first interrupt
    server.shutdown_flag.set()


def follow(
    db,
    executor=None,
    zmq_enabled=True,
    cp_pipeline=True,
    update_cpids=True,
    single_block=False,
    reparse_mode=False,
):
    """
    Continuously follows the blockchain, parsing and indexing new blocks
    for SRC-20 transactions and to gather details about CP trx such as
    keyburn status.

    Args:
        db: Database connection
        executor: Optional ThreadPoolExecutor to use
        zmq_enabled: Whether to use ZMQ notifications
        cp_pipeline: Whether to use CP pipeline
        update_cpids: Whether to update CPIDs
        single_block: Whether to process just one block and exit
        reparse_mode: Whether running in reparse mode
    """
    # Set up signal handler early
    signal.signal(signal.SIGINT, signal_handler)

    # Initialize resources that need cleanup
    executor = executor or concurrent.futures.ThreadPoolExecutor()
    zmq_notifier = None
    update_cpids_future = None
    cp_pipeline_instance = None

    try:
        # Initial database setup
        if not reparse_mode:
            initialize(db)
            rebuild_balances(db)
            rebuild_owners(db)
            update_src20_token_stats(db)

        # Get index of last block and current tip
        block_tip = backend_instance.getblockcount()
        if util.CURRENT_BLOCK_INDEX == 0:
            logger.warning("New database.")
            block_index = config.BLOCK_FIRST
        else:
            block_index = util.CURRENT_BLOCK_INDEX + 1

        logger.info(f"Resuming parsing from block {block_index}, current tip: {block_tip}")
        tx_index = next_tx_index(db)

        # Initialize ZMQ if enabled
        if zmq_enabled:
            try:
                zmq_notifier = ZMQNotifier()
                zmq_enabled = zmq_notifier.check_zmq_ports()
                if zmq_enabled:
                    logger.info("ZMQ notifications enabled")
            except Exception as e:
                logger.warning(f"Failed to initialize ZMQ: {e}")
                zmq_enabled = False

        # Initialize profiler after setup but before processing
        global profiler
        profiler = Profiler()
        profiler.start_block_profiling()

        # Initialize CP blocks pipeline if enabled, using already fetched block_tip
        if cp_pipeline:
            cp_pipeline_instance = CPBlocksPipeline(max_queue_size=200)
            cp_pipeline_instance.start(block_index)
            stamp_issuances_list = {}  # Initialize empty dict, will be populated by pipeline

        consecutive_errors = 0
        max_consecutive_errors = 5
        error_cooldown = 10  # seconds
        last_keepalive = time.time()
        KEEPALIVE_INTERVAL = 60  # Send keepalive every minute
        update_cpids_last_run_block = 0

        # Track rollbacks to detect loops
        rollback_history = []
        MAX_ROLLBACKS = 3  # Maximum number of rollbacks allowed to the same block
        ROLLBACK_HISTORY_WINDOW = 10  # Number of recent rollbacks to track

        def check_rollback_loop(block_index):
            """Check if we're in a rollback loop for a specific block."""
            rollback_history.append(block_index)
            if len(rollback_history) > ROLLBACK_HISTORY_WINDOW:
                rollback_history.pop(0)

            # Count occurrences of this block index in recent history
            count = rollback_history.count(block_index)
            if count > MAX_ROLLBACKS:
                logger.error(f"Detected rollback loop at block {block_index} ({count} rollbacks)")
                return True
            return False

        def send_keepalive(db):
            """Send a lightweight query to keep the connection alive"""
            try:
                with db.cursor() as cursor:
                    cursor.execute("SELECT 1")
                return True
            except Exception as e:
                logger.warning(f"Keepalive query failed: {e}")
                return False

        def handle_ledger_mismatch(block_index):
            """Handle ledger hash mismatches based on configuration."""
            if not config.FORCE:  # If not in force mode, exit on mismatch
                logger.error(f"Ledger hash mismatch at block {block_index}. Exiting...")
                sys.exit(f"Ledger hash mismatch detected at block {block_index}")
            else:
                logger.warning(f"Ledger hash mismatch at block {block_index}. Continuing due to FORCE=True...")
                return True  # Continue processing

        while not server.shutdown_flag.is_set():
            start_time = time.time()

            # Check shutdown flag before starting new transaction
            if server.shutdown_flag.is_set():
                break

            try:
                # Check database connection before starting new block
                db = check_db_connection(db)

                db.begin()  # Start transaction for entire block

                # Get block tip with timeout
                try:
                    block_tip = backend_instance.getblockcount()
                    if single_block:
                        # In single block mode, only process one block
                        block_tip = block_index
                except (ConnectionRefusedError, http.client.CannotSendRequest, backend.BackendRPCError) as e:
                    if config.FORCE:
                        if server.shutdown_flag.is_set():
                            break
                        time.sleep(config.BACKEND_POLL_INTERVAL)
                        continue
                    else:
                        raise e

                if block_index != config.BLOCK_FIRST and not is_prev_block_parsed(db, block_index):
                    block_index -= 1

                if block_index <= block_tip:
                    logger.debug("Starting block processing after notification")
                    # Check shutdown flag before heavy operations
                    if server.shutdown_flag.is_set():
                        break

                    # Check database connection before operations
                    db = check_db_connection(db)

                    # Start profiling for this block
                    profiler.start_block_profiling()

                    # Try to get block from pipeline first
                    block_data = cp_pipeline_instance.get_block(block_index) if cp_pipeline_instance else None

                    if block_data:
                        stamp_issuances = block_data["issuances"]
                        stamp_issuances_list = {block_index: block_data}
                    else:
                        logger.warning(f"Block {block_index} not found in CP pipeline, falling back to direct fetch")
                        try:
                            if server.shutdown_flag.is_set():
                                logger.info("Shutdown flag detected before CP fetch, breaking...")
                                break

                            if block_index + 1 == block_tip:
                                indicator = True
                            else:
                                indicator = None

                            logger.info(f"Directly fetching block {block_index} from XCP API")
                            # Limit the fetch to at most 100 blocks instead of all the way to block_tip
                            max_fetch_blocks = 100
                            end_block = min(block_index + max_fetch_blocks - 1, block_tip)
                            stamp_issuances_list = fetch_xcp_blocks_concurrent(block_index, end_block, indicator=indicator)
                            logger.info(f"Successfully fetched {len(stamp_issuances_list)} blocks directly from XCP API")

                            if server.shutdown_flag.is_set():
                                logger.info("Shutdown flag detected after CP fetch, breaking...")
                                break

                            stamp_issuances = stamp_issuances_list[block_index]["issuances"]
                        except KeyboardInterrupt:
                            logger.info("Received keyboard interrupt during CP fetch.")
                            server.shutdown_flag.set()
                            break
                        except Exception as e:
                            logger.error(f"Error during CP fetch: {e}")
                            if not config.FORCE:
                                raise

                    if block_tip - block_index < 100 and not reparse_mode:
                        requires_rollback = False
                        while True:
                            if block_index == config.BLOCK_FIRST:
                                break
                            logger.info(f"Checking that block {block_index} is not orphan.")
                            current_hash = backend_instance.getblockhash(block_index)
                            block_header = backend_instance.getblockheader(current_hash)
                            backend_parent = block_header["previousblockhash"]
                            cursor = db.cursor()
                            block_query = """
                            SELECT * FROM blocks WHERE block_index = %s
                            """
                            cursor.execute(block_query, (block_index - 1,))
                            blocks = cursor.fetchall()
                            columns = [desc[0] for desc in cursor.description]
                            cursor.close()
                            blocks_dict = [dict(zip(columns, row)) for row in blocks]
                            if len(blocks_dict) != 1:
                                break
                            db_parent = blocks_dict[0]["block_hash"]

                            if not isinstance(db_parent, str):
                                raise TypeError("db_parent must be a string")
                            if not isinstance(backend_parent, str):
                                raise TypeError("backend_parent must be a string")
                            if db_parent == backend_parent:
                                break
                            else:
                                block_index -= 1
                                requires_rollback = True

                        if requires_rollback:
                            logger.warning(f"Blockchain reorganization at block {block_index}.")
                            block_index -= 1

                            if check_rollback_loop(block_index):
                                logger.error("Exiting due to rollback loop detection")
                                sys.exit(f"Detected rollback loop at block {block_index}")

                            block_index = rollback_to_block(db, block_index, "Chain reorganization detected")
                            if cp_pipeline_instance:
                                logger.info(f"Resetting CP pipeline after chain reorg to block {block_index}")
                                cp_pipeline_instance.reset(block_index)
                            stamp_issuances_list = None
                            time.sleep(60)  # delay waiting for CP to catch up
                            continue

                    block_hash = backend_instance.getblockhash(block_index)

                    # Get full block data from backend
                    txhash_list_full, raw_transactions_full, block_time, previous_block_hash, difficulty = (
                        backend_instance.get_tx_list(block_hash)
                    )

                    try:
                        # Try to get xcp_block_hash, fall back to block_hash if needed
                        if "xcp_block_hash" in stamp_issuances_list[block_index]:
                            xcp_hash = stamp_issuances_list[block_index]["xcp_block_hash"]
                        elif "block_hash" in stamp_issuances_list[block_index]:
                            xcp_hash = stamp_issuances_list[block_index]["block_hash"]
                            logger.debug(f"Using block_hash as xcp_block_hash for block {block_index}")
                        else:
                            raise KeyError("Neither xcp_block_hash nor block_hash found in block data")
                    except (KeyError, TypeError) as e:
                        logger.error(f"Error accessing block hash for block {block_index}: {e}")
                        # Handle the error appropriately

                    if xcp_hash != block_hash and not reparse_mode:
                        logger.critical(f"Hash mismatch at block {block_index}")
                        logger.critical(f"XCP: {xcp_hash}")
                        logger.critical(f"BTC: {block_hash}")
                        block_index = rollback_to_block(db, block_index - 2, "XCP/Bitcoin hash mismatch")
                        continue

                    # Filter transactions based on genesis status
                    block_data = {
                        "tx": [{"txid": tx_hash, "hex": raw_transactions_full[tx_hash]} for tx_hash in txhash_list_full]
                    }
                    txhash_list, raw_transactions = filter_block_transactions(block_data, stamp_issuances=stamp_issuances)

                    util.CURRENT_BLOCK_INDEX = block_index

                    try:
                        insert_block(
                            db,
                            block_index,
                            block_hash,
                            block_time,
                            previous_block_hash,
                            difficulty,
                        )
                    except BlockAlreadyExistsError as e:
                        logger.warning(e)
                        db.rollback()
                        sys.exit(f"Exiting due to block already existing. {e}")
                    except DatabaseInsertError as e:
                        logger.error(e)
                        db.rollback()
                        sys.exit("Critical database error encountered. Exiting.")

                    valid_stamps_in_block: List[ValidStamp] = []

                    if block_index < config.BTC_SRC20_GENESIS_BLOCK and not stamp_issuances_list[block_index]:
                        valid_src20_str = ""
                        new_ledger_hash, new_txlist_hash, new_messages_hash = create_check_hashes(
                            db,
                            block_index,
                            valid_stamps_in_block,
                            valid_src20_str,
                            txhash_list,
                        )

                        stamp_issuances_list.pop(block_index, None)
                        log_block_info(block_index, start_time, new_ledger_hash, new_txlist_hash, new_messages_hash, 0, 0, 0)
                        block_index = commit_and_update_block(db, block_index, block_tip, 0)
                        profiler.end_block_profiling()  # End profiling for this block
                        if single_block:
                            break
                        continue

                    tx_results = []

                    # Process transactions in parallel
                    futures = []
                    for tx_hash in raw_transactions:  # Only process transactions we have raw data for
                        future = executor.submit(
                            process_tx,
                            db,
                            tx_hash,
                            block_index,
                            stamp_issuances,
                            raw_transactions,
                        )
                        futures.append(future)

                    for future in concurrent.futures.as_completed(futures):
                        result = future.result()
                        if result.data is not None:
                            result = result._replace(
                                block_index=block_index,
                                block_hash=block_hash,
                                block_time=block_time,
                            )
                            tx_results.append(result)

                    tx_results = sorted(tx_results, key=lambda x: txhash_list.index(x.tx_hash))
                    # Assign tx_index after sorting
                    for i, result in enumerate(tx_results):
                        tx_results[i] = result._replace(tx_index=tx_index)
                        tx_index += 1

                    try:
                        block_processor = BlockProcessor(db)
                        block_processor.insert_transactions(tx_results)
                        block_processor.process_transaction_results(tx_results)

                        (
                            new_ledger_hash,
                            new_txlist_hash,
                            new_messages_hash,
                            stamps_in_block,
                            src20_in_block,
                            src101_in_block,
                        ) = block_processor.finalize_block(block_index, block_time, txhash_list)

                        stamp_issuances_list.pop(block_index, None)
                        log_block_info(
                            block_index,
                            start_time,
                            new_ledger_hash,
                            new_txlist_hash,
                            new_messages_hash,
                            stamps_in_block,
                            src20_in_block,
                            src101_in_block,
                        )
                        block_index = commit_and_update_block(db, block_index, block_tip, src20_in_block)
                        profiler.end_block_profiling()  # End profiling for this block

                        if single_block:
                            break

                    except LedgerMismatchError as e:
                        if not handle_ledger_mismatch(e.block_index):
                            db.rollback()
                            break
                        else:
                            # If handle_ledger_mismatch returns True (FORCE mode), continue processing
                            block_index = commit_and_update_block(db, block_index, block_tip, src20_in_block)
                            profiler.end_block_profiling()  # End profiling for this block

                    except Exception as e:
                        logger.error(f"Error processing block {block_index}: {e}")
                        if "Duplicate entry" in str(e):
                            logger.warning(f"Rolling back block {block_index} due to duplicate key error")
                            rollback_target = block_index - 1

                            # Check for rollback loop
                            if check_rollback_loop(rollback_target):
                                logger.error("Exiting due to rollback loop detection")
                                sys.exit(f"Detected rollback loop at block {rollback_target}")

                            block_index = rollback_to_block(
                                db, rollback_target, "Duplicate key error - transient database issue"
                            )
                            if cp_pipeline_instance:
                                logger.info(f"Resetting CP pipeline after duplicate key rollback to block {block_index}")
                                cp_pipeline_instance.reset(block_index)
                            stamp_issuances_list = None
                            continue

                        db.rollback()
                        # Short sleep before retry
                        if not server.shutdown_flag.is_set():
                            time.sleep(5)

                else:
                    if server.shutdown_flag.is_set():
                        logger.info("Shutdown flag detected, completing current block processing...")
                        # Ensure current block processing completes
                        block_processor.finalize_block(block_index, block_time, txhash_list)
                        db.commit()
                        logger.info("Current block processing completed successfully")
                        break

                    # Check database connection before waiting
                    db = check_db_connection(db)

                    # Update CPIDs if needed (every 50 blocks)
                    if update_cpids and (block_index % 50 == 0) and (block_index != update_cpids_last_run_block):
                        if update_cpids_future is None or update_cpids_future.done():
                            if update_cpids_future is not None and update_cpids_future.done():
                                try:
                                    # Check if the previous update had any errors
                                    update_cpids_future.result()
                                except Exception as e:
                                    logger.error(f"Previous CPID update failed: {e}")
                                    if not config.FORCE:
                                        raise

                            update_cpids_future = executor.submit(update_cpids_async, db)
                            update_cpids_last_run_block = block_index
                            logger.info(f"Submitted update_cpids_async task at block {block_index}.")
                        else:
                            logger.info("update_cpids_async is already running. Skipping submission.")

                    # Use ZMQ if enabled
                    if zmq_enabled:
                        try:
                            logger.info(f"Waiting for new blocks via ZMQ after block {block_index}")
                            while not server.shutdown_flag.is_set():
                                # Send keepalive if needed
                                if time.time() - last_keepalive > KEEPALIVE_INTERVAL:
                                    if not send_keepalive(db):
                                        db = check_db_connection(db)
                                    last_keepalive = time.time()

                                notification = zmq_notifier.wait_for_notification(min(5000, KEEPALIVE_INTERVAL * 1000))
                                if notification:
                                    topic, body, seq = notification
                                    topic_str = topic.decode("utf-8")
                                    if topic_str in ["hashblock", "rawblock"]:
                                        logger.info(f"Processing new block notification via ZMQ: {topic_str}")
                                        block_tip = backend_instance.getblockcount()

                                        # Add delay to allow Counterparty to catch up with Bitcoin
                                        delay_seconds = config.ZMQ_NOTIFICATION_DELAY
                                        logger.info(
                                            f"Delaying for {delay_seconds} seconds to allow Counterparty to process the new block"
                                        )
                                        time.sleep(delay_seconds)
                                        break
                                continue
                        except Exception as e:
                            logger.warning(f"ZMQ notification failed, falling back to polling: {e}")
                            zmq_enabled = False
                            if zmq_notifier:
                                zmq_notifier.cleanup()

                    # Only reach here if ZMQ is disabled or failed
                    if not zmq_enabled:

                        # Send keepalive if needed
                        if time.time() - last_keepalive > KEEPALIVE_INTERVAL:
                            if not send_keepalive(db):
                                db = check_db_connection(db)
                            last_keepalive = time.time()

                        time.sleep(config.BACKEND_POLL_INTERVAL)
                        block_tip = backend_instance.getblockcount()

                        # Try to re-enable ZMQ periodically
                        if block_index % 10 == 0:
                            try:
                                zmq_notifier = ZMQNotifier()
                                zmq_enabled = zmq_notifier.check_zmq_ports()
                                if zmq_enabled:
                                    logger.info("Successfully re-enabled ZMQ notifications")
                            except Exception as e:
                                logger.warning(f"Failed to re-initialize ZMQ: {e}")

                consecutive_errors = 0  # Reset error counter on successful iteration

            except (mysql.Error, mysql.OperationalError) as e:
                logger.error(f"Database error processing block {block_index}: {e}")
                db.rollback()

                # Check for duplicate key error
                if isinstance(e, mysql.Error) and e.args[0] == 1062:  # Duplicate key error
                    logger.warning(f"Rolling back block {block_index} due to duplicate key error")
                    rollback_target = block_index - 1

                    # Check for rollback loop
                    if check_rollback_loop(rollback_target):
                        logger.error("Exiting due to rollback loop detection")
                        sys.exit(f"Detected rollback loop at block {rollback_target}")

                    block_index = rollback_to_block(db, rollback_target, "Duplicate key error - transient database issue")
                    if cp_pipeline_instance:
                        logger.info(f"Resetting CP pipeline after duplicate key rollback to block {block_index}")
                        cp_pipeline_instance.reset(block_index)
                    stamp_issuances_list = None
                    continue

                consecutive_errors += 1

                if consecutive_errors >= max_consecutive_errors:
                    logger.error(f"Too many consecutive database errors ({consecutive_errors}). Taking a longer break...")
                    time.sleep(error_cooldown * 2)  # Double the cooldown
                    consecutive_errors = 0  # Reset counter after break
                else:
                    time.sleep(error_cooldown)

                # Try to reconnect to database
                try:
                    db = check_db_connection(db)
                except Exception as reconnect_error:
                    logger.error(f"Failed to reconnect to database: {reconnect_error}")
                    raise

            except Exception as e:
                logger.error(f"Error processing block {block_index}: {e}")
                if "Duplicate entry" in str(e):
                    logger.warning(f"Rolling back block {block_index} due to duplicate key error")
                    rollback_target = block_index - 1

                    # Check for rollback loop
                    if check_rollback_loop(rollback_target):
                        logger.error("Exiting due to rollback loop detection")
                        sys.exit(f"Detected rollback loop at block {rollback_target}")

                    block_index = rollback_to_block(db, rollback_target, "Duplicate key error - transient database issue")
                    if cp_pipeline_instance:
                        logger.info(f"Resetting CP pipeline after duplicate key rollback to block {block_index}")
                        cp_pipeline_instance.reset(block_index)
                    stamp_issuances_list = None
                    continue
                db.rollback()
                # Short sleep before retry
                if not server.shutdown_flag.is_set():
                    time.sleep(5)

            # Add validation check every 1000 blocks
            if config.DEBUG_VALIDATION and block_index % 1000 == 0:
                if not validate_block_against_production(block_index):
                    logger.error("Validation failed - terminating execution")
                    cleanup_resources(executor, zmq_notifier, update_cpids_future, db, cp_pipeline_instance)
                    sys.exit(1)

    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt in follow().")
    except Exception as e:
        logger.error(f"An unexpected error occurred in follow(): {e}")
        raise
    finally:
        # End profiling before cleanup
        if "profiler" in locals():
            profiler.end_block_profiling()

        # Stop CP pipeline
        if cp_pipeline_instance:
            cp_pipeline_instance.stop()

        cleanup_resources(executor, zmq_notifier, update_cpids_future, db, cp_pipeline_instance)


def validate_block_against_production(block_index: int) -> bool:
    """Run the compare_tables script to validate against production."""
    if not config.DEBUG_VALIDATION:
        return True

    logger = logging.getLogger("validate_block")
    logger.info(f"Validating block {block_index} against production database...")

    try:
        script_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "tools", "compare_tables.py")

        # Check shutdown flag before starting validation
        if server.shutdown_flag.is_set():
            logger.info("Skipping validation due to shutdown signal")
            return True

        process = subprocess.Popen([sys.executable, script_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        while True:
            try:
                # Use communicate with timeout to allow for interrupt checking
                stdout, stderr = process.communicate(timeout=1)
                break
            except subprocess.TimeoutExpired:
                # Check shutdown flag periodically
                if server.shutdown_flag.is_set():
                    logger.info("Terminating validation due to shutdown signal")
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    return True
                continue

        if process.returncode != 0:
            logger.error(f"Validation failed at block {block_index}")
            logger.error(f"Comparison output:\n{stdout}\n{stderr}")
            return False

        logger.info(f"Block {block_index} validation successful")
        return True

    except Exception as e:
        logger.error(f"Error running validation: {str(e)}")
        return True

def update_cpids_async(db):
    try:
        # Create a new database connection for this async task
        from index_core.server import initialize_db

        task_db = initialize_db()

        try:
            cpids = get_unlocked_cpids(task_db)
            if cpids:
                cpids_list = [cpid[0] for cpid in cpids]
                assets_details = get_xcp_assets_by_cpids(cpids_list, chunk_size=200, delay_between_chunks=6, max_workers=5)
                if assets_details:
                    update_assets_in_db(task_db, assets_details, chunk_size=200, delay_between_chunks=6)
                    logger.info("Successfully updated assets in the database.")
                else:
                    logger.warning("No asset details were retrieved.")
            else:
                logger.info("No CPIDs to update.")
        finally:
            task_db.close()

    except Exception as e:
        logger.error(f"Error in update_cpids_async: {e}")
        if not config.FORCE:
            raise