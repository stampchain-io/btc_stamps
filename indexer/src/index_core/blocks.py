"""
initialize database.

Sieve blockchain for Stamp transactions, and add them to the database.
"""

import concurrent.futures
import decimal
import http
import logging
import sys
import time
from collections import namedtuple
from typing import List

import pymysql as mysql
from bitcoin.core.script import CScriptInvalidError
from pymysql.connections import Connection

# import cProfile
# import pstats
import config
import index_core.arc4 as arc4
import index_core.backend as backend
import index_core.check as check
import index_core.log as log
import index_core.script as script
import index_core.server as server
import index_core.util as util
from index_core.database import (
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
from index_core.exceptions import BlockAlreadyExistsError, BlockUpdateError, BTCOnlyError, DatabaseInsertError, DecodeError
from index_core.models import StampData, ValidStamp
from index_core.parser import RUST_PARSER_AVAILABLE, Parser
from index_core.src20 import Src20Dict  # FIXME: move to models for consistency
from index_core.src20 import (
    clear_zero_balances,
    parse_src20,
    process_balance_updates,
    update_src20_balances,
    validate_src20_ledger_hash,
)
from index_core.src101 import Src101Dict  # FIXME: move to models for consistency
from index_core.src101 import parse_src101, update_src101_owners
from index_core.stamp import parse_stamp
from index_core.xcprequest import fetch_cp_concurrent, filter_issuances_by_tx_hash, get_xcp_assets_by_cpids
from index_core.zmq_utils import ZMQNotifier

D = decimal.Decimal
logger = logging.getLogger(__name__)
log.set_logger(logger)
skip_logger = logging.getLogger("list_tx.skip")

# Initialize Rust parser if available
_parser = None
if RUST_PARSER_AVAILABLE:
    try:
        _parser = Parser()
        logger.info("Using high-performance Rust parser")
    except Exception as e:
        logger.warning(f"Failed to initialize Rust parser: {e}. Falling back to Python parser")

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

    def process_transaction_results(self, tx_results):
        logger.debug(f"Processing {len(tx_results)} transaction results")
        for result in tx_results:
            logger.debug(f"Processing transaction: {result.tx_hash}")
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
            logger.debug(f"Created StampData for tx: {result.tx_hash}")

            _, stamp_data, valid_stamp, prevalidated_src = parse_stamp(
                stamp_data=stamp_data,
                db=self.db,
                valid_stamps_in_block=self.valid_stamps_in_block,
            )
            logger.debug(
                f"Parsed stamp data for tx: {result.tx_hash}, prevalidated_src exists: {prevalidated_src is not None}"
            )

            if stamp_data:
                self.parsed_stamps.append(stamp_data)
                self.collection_operations.append((stamp_data, config.LEGACY_COLLECTIONS))
                logger.debug(f"Added stamp data for tx: {result.tx_hash}")
            if valid_stamp:
                self.valid_stamps_in_block.append(valid_stamp)
                logger.debug(f"Added valid stamp for tx: {result.tx_hash}")
            if prevalidated_src and stamp_data and stamp_data.pval_src20:
                logger.debug(f"Processing SRC20 for tx: {result.tx_hash}")
                _, src20_dict = parse_src20(self.db, prevalidated_src, self.processed_src20_in_block)
                logger.debug(f"SRC20 dict created: {src20_dict}")
                self.processed_src20_in_block.append(src20_dict)
            if prevalidated_src and stamp_data and stamp_data.pval_src101:
                logger.debug(f"Processing SRC101 for tx: {result.tx_hash}")
                _, src101_dict = parse_src101(
                    self.db, prevalidated_src, self.processed_src101_in_block, stamp_data.block_index
                )
                logger.debug(f"SRC101 dict created: {src101_dict}")
                self.processed_src101_in_block.append(src101_dict)

        if self.parsed_stamps:
            logger.debug(f"Inserting {len(self.parsed_stamps)} stamps into table")
            insert_into_stamp_table(self.db, self.parsed_stamps)

            if self.collection_operations:
                logger.debug(f"Processing {len(self.collection_operations)} collection operations")
                for stamp, collections in self.collection_operations:
                    stamp.match_and_insert_collection_data(collections, self.db)

    def finalize_block(self, block_index, block_time, txhash_list):
        try:
            if self.processed_src20_in_block:
                logger.debug(f"Finalizing block {block_index} with {len(self.processed_src20_in_block)} SRC20 transactions")
                logger.debug(f"First SRC20 transaction: {self.processed_src20_in_block[0]}")

                # First insert the transactions
                insert_into_src20_tables(self.db, self.processed_src20_in_block)
                logger.debug("Successfully inserted SRC20 transactions")

                # Then update balances
                balance_updates = update_src20_balances(self.db, block_index, block_time, self.processed_src20_in_block)
                logger.debug(f"Balance updates completed: {balance_updates}")

                valid_src20_str = process_balance_updates(balance_updates)
                logger.debug(f"Processed balance updates: {valid_src20_str[:100]}...")
            else:
                valid_src20_str = ""

            src101_count = 0
            if self.processed_src101_in_block:
                logger.debug(f"Processing {len(self.processed_src101_in_block)} SRC101 transactions")
                insert_into_src101_tables(self.db, self.processed_src101_in_block)
                update_src101_owners(self.db, block_index, self.processed_src101_in_block)
                src101_count = len(self.processed_src101_in_block)

            if block_index > config.BTC_SRC20_GENESIS_BLOCK and block_index % 100 == 0:
                clear_zero_balances(self.db)

            new_ledger_hash, new_txlist_hash, new_messages_hash = create_check_hashes(
                self.db, block_index, self.valid_stamps_in_block, valid_src20_str, txhash_list
            )

            if valid_src20_str:
                validate_src20_ledger_hash(block_index, new_ledger_hash, valid_src20_str)

            stamps_in_block = len(self.valid_stamps_in_block)
            src20_in_block = len(self.processed_src20_in_block)
            return new_ledger_hash, new_txlist_hash, new_messages_hash, stamps_in_block, src20_in_block, src101_count
        except Exception as e:
            logger.error(f"Error in finalize_block: {e}", exc_info=True)
            raise

    def insert_transactions(self, tx_results):
        insert_transactions(self.db, tx_results)


def process_vout(ctx, block_index, stamp_issuance=None):
    """
    Process all the out values of a transaction.

    Args:
        ctx (TransactionContext): The transaction context.
        block_index (int): The index of the block.
        stamp_issuance (bool, optional): Flag indicating if the transaction is a stamp issuance.

    Returns:
        vOutInfo: A named tuple containing information about the outputs.
    """
    pubkeys_compiled = []
    keyburn = None
    is_op_return, is_olga = None, None
    p2wsh_data_chunks = []
    fee = 0

    if ctx.is_coinbase():
        raise DecodeError("coinbase transaction")

    for idx, vout in enumerate(ctx.vout):
        fee -= vout.nValue
        try:
            asm = script.get_asm(vout.scriptPubKey)
        except CScriptInvalidError as e:
            raise DecodeError(e)
        if asm[-1] == "OP_CHECKMULTISIG":
            try:
                pubkeys, signatures_required, keyburn_vout = script.get_checkmultisig(asm)
                if keyburn_vout is not None:
                    keyburn = keyburn_vout
                pubkeys_compiled += pubkeys
                # stripped_pubkeys = [pubkey[1:-1] for pubkey in pubkeys]
            except Exception as e:
                raise DecodeError(f"unrecognised output type {e}")
        elif asm[-1] == "OP_CHECKSIG":
            pass  # FIXME: not certain if we need to check keyburn on OP_CHECKSIG
            # see 'A14845889080100805000'
            #   0: OP_DUP
            #   1: OP_HASH160
            #   3: OP_EQUALVERIFY
            #   4: OP_CHECKSIG
        elif asm[0] == "OP_RETURN":
            is_op_return = True
        elif stamp_issuance is not None and asm[0] == 0 and len(asm[1]) == 32:
            # Pay-to-Witness-Script-Hash (P2WSH) on CPID transactions
            pubkeys = script.get_p2wsh(asm)
            pubkeys_compiled += pubkeys
            is_olga = True
        elif asm[0] == 0 and len(asm[1]) == 32:
            # Pay-to-Witness-Script-Hash (P2WSH) on SRC-20 transactions
            if block_index >= config.BTC_SRC20_OLGA_BLOCK:
                if idx > 0:
                    data_bytes = asm[1]
                    p2wsh_data_chunks.append(data_bytes)
                    is_olga = True
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

        ctx = backend.deserialize(tx_hex)
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
                    else:
                        p2wsh_data = None
                else:
                    # Data length is not sufficient
                    p2wsh_data = None
            else:
                p2wsh_data = None

        # SRC-20 via MULTISIG
        # This prioritizes P2WSH over CHECKMULTISIG in a mixed transaction
        # To be deprecated in a future block height over P2WSH for all SRC-20 transactions
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
        prev_tx = backend.getrawtransaction(util.ib2h(prev_tx_hash))
        prev_ctx = backend.deserialize(prev_tx)

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
               If the chunk does not match the expected format, returns (None, None).

    Raises:
        DecodeError: If the decoded data length does not match the expected length.
    """
    key = arc4.init_arc4(ctx.vin[0].prevout.hash[::-1])
    chunk = arc4.arc4_decrypt_chunk(chunk, key)  # this is a different method since we are stripping the nonce/sign beforehand
    if chunk[2 : 2 + len(config.PREFIX)] == config.PREFIX:
        chunk_length = chunk[:2].hex()  # the expected length of the string from the first 2 bytes
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
        tx_hex = backend.getrawtransaction(tx_hash, verbose=False, skip_missing=False, current_block=block_index)

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
            "Saving to MySQL transactions: {} DATA: {} KEYBURN: {} OP_RETURN: {}".format(tx_hash, data, keyburn, is_op_return)
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
    """
    Commits the changes to the database, updates the parsed block, and increments the block index.
    Updates stats when:
    - At tip: Every block with SRC20 transactions
    - During bulk: Every 1000 blocks as a safety net

    Args:
        db: The database connection object.
        block_index: The current block index.
        block_tip: The current blockchain tip.
        src20_in_block: Number of SRC20 transactions in this block.

    Returns:
        int: The next block index to process.
    """
    try:
        # Update stats if:
        # 1. We're at the tip AND (it's a normal block OR has SRC20 transactions)
        # 2. Every 1000 blocks during bulk indexing (as a safety net)
        should_update_stats = block_index >= config.BTC_SRC20_GENESIS_BLOCK and (
            (
                block_index == block_tip and (block_index % 100 == 0 or src20_in_block > 0)
            )  # At tip with SRC20 or every 100th block
            or (block_tip - block_index > 100 and block_index % 1000 == 0)  # Bulk safety net
        )

        if should_update_stats:
            logger.warning(f"Updating token stats at block {block_index} (src20_txs: {src20_in_block})")
            update_src20_token_stats(db)

        db.commit()
        update_parsed_block(db, block_index)
        block_index += 1
        return block_index
    except Exception as e:
        print("Error message:", e)
        db.rollback()
        db.close()
        sys.exit(f"Critical database error encountered: {e}")


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
        block_tip: int = backend.getblockcount()

        # Calculate progress based on CP genesis block to current tip
        blocks_to_process = block_tip - config.CP_STAMP_GENESIS_BLOCK
        blocks_processed = block_index - config.CP_STAMP_GENESIS_BLOCK

        # Ensure we don't show progress before genesis block
        if block_index < config.CP_STAMP_GENESIS_BLOCK:
            current_progress = 0.0
        else:
            current_progress = min(1.0, blocks_processed / blocks_to_process if blocks_to_process > 0 else 0)

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
    stamp_issuance = filter_issuances_by_tx_hash(stamp_issuances, tx_hash)

    tx_hex = raw_transactions[tx_hash]
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


def quick_filter_src20_transaction(tx_hex):
    """
    Quick pre-filter to check if a transaction might be a SRC-20 transaction.
    Only checks for multisig and p2wsh patterns.

    Returns:
        bool: True if transaction might be a SRC-20, False if definitely not
    """
    try:
        ctx = backend.deserialize(tx_hex)

        # Check outputs for SRC-20 patterns
        for vout in ctx.vout:
            script = bytes(vout.scriptPubKey)

            # Check for P2WSH pattern (0x00 + 32 bytes)
            if len(script) == 34 and script[0] == 0x00:
                return True

            # Check for potential multisig pattern with OP_CHECKMULTISIG
            # OP_CHECKMULTISIG opcode is 0xAE
            if len(script) > 2 and script[-1] == 0xAE:
                return True

        return False

    except Exception as e:
        # If we can't decode, better to include it than miss it
        logger.debug(f"Error in quick filter: {e}")
        return True


def filter_block_transactions(block_data, stamp_issuances=None):
    """
    Filter transactions from a block based on genesis status.
    Uses Rust parser for efficient batch processing if available.
    Before BTC_SRC20_GENESIS_BLOCK, only returns stamp issuance transactions.
    After BTC_SRC20_GENESIS_BLOCK:
    - Always includes stamp issuance transactions
    - Quick filters other transactions for SRC-20 patterns in parallel
    Always returns full tx_hash_list for message hash calculation.
    Maintains original transaction order.

    Args:
        block_data: The block data from backend.get_tx_list
        stamp_issuances: Optional list of stamp issuances already fetched for this block
    """
    tx_hash_list = []
    raw_transactions = {}

    # Get all transactions from block
    all_txs = block_data["tx"]

    # Store all tx hashes for message hash calculation (maintain original order)
    tx_hash_list = [tx["txid"] for tx in all_txs]

    # Get set of issuance transactions if any
    issuance_tx_hashes = {issuance["tx_hash"] for issuance in stamp_issuances} if stamp_issuances else set()

    # Before SRC20 genesis, only get stamp issuance transactions
    if util.CURRENT_BLOCK_INDEX < config.BTC_SRC20_GENESIS_BLOCK:
        # Only process issuance transactions (in order)
        for tx in all_txs:
            if tx["txid"] in issuance_tx_hashes:
                raw_transactions[tx["txid"]] = tx["hex"]
    else:
        # After genesis block:
        # 1. First add all stamp issuance transactions (in order)
        for tx in all_txs:
            if tx["txid"] in issuance_tx_hashes:
                raw_transactions[tx["txid"]] = tx["hex"]

        # 2. Quick filter remaining transactions
        non_issuance_txs = [tx for tx in all_txs if tx["txid"] not in issuance_tx_hashes]

        if non_issuance_txs:
            if RUST_PARSER_AVAILABLE and _parser is not None:
                try:
                    # Log transaction hex strings
                    logger.debug(f"Parsing transactions: {[tx['hex'] for tx in non_issuance_txs]}")

                    # Use Rust parser for parallel filtering
                    tx_hexes = [tx["hex"] for tx in non_issuance_txs]
                    parsed_txs = _parser.batch_parse_transactions(tx_hexes)

                    # Add transactions that passed filtering
                    for tx, ctx in zip(non_issuance_txs, parsed_txs):
                        # Use the same filtering logic as quick_filter_src20_transaction
                        for out in ctx.vout:
                            script_bytes = bytes(out.scriptPubKey)
                            # Check for P2WSH pattern (0x00 + 32 bytes)
                            if len(script_bytes) == 34 and script_bytes[0] == 0x00:
                                raw_transactions[tx["txid"]] = tx["hex"]
                                break
                            # Check for OP_CHECKMULTISIG (0xAE)
                            if len(script_bytes) > 2 and script_bytes[-1] == 0xAE:
                                raw_transactions[tx["txid"]] = tx["hex"]
                                break

                except Exception as e:
                    logger.warning(f"Rust batch parsing failed: {e}. Falling back to Python implementation")
                    # Fall through to original implementation

            if not RUST_PARSER_AVAILABLE or _parser is None:
                # Original implementation with ThreadPoolExecutor
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    futures = [executor.submit(quick_filter_src20_transaction, tx["hex"]) for tx in non_issuance_txs]
                    for tx, future in zip(non_issuance_txs, futures):
                        try:
                            if future.result():
                                raw_transactions[tx["txid"]] = tx["hex"]
                        except Exception as e:
                            logger.debug(f"Error in parallel filtering for tx {tx['txid']}: {e}")
                            raw_transactions[tx["txid"]] = tx["hex"]

    return tx_hash_list, raw_transactions


def check_db_connection(db):
    """Check if database connection is alive and reconnect if needed."""
    max_retries = 3
    retry_delay = 5  # seconds

    for attempt in range(max_retries):
        try:
            # First try to ping the connection
            db.ping(reconnect=True)
            return db
        except Exception as e:
            logger.warning(f"Database connection check failed (attempt {attempt + 1}/{max_retries}): {e}")

            # Close the connection if it exists
            try:
                if not db._closed:
                    db.close()
            except (AttributeError, mysql.Error) as e:
                logger.debug(f"Error during database cleanup: {e}")
                pass

            if attempt < max_retries - 1:
                logger.info(f"Waiting {retry_delay} seconds before retry...")
                time.sleep(retry_delay)

                try:
                    from index_core.server import initialize_db

                    new_db = initialize_db()
                    logger.info("Successfully reconnected to database")
                    return new_db
                except Exception as reconnect_error:
                    logger.error(f"Failed to reconnect to database: {reconnect_error}")
                    # Continue to next retry
            else:
                logger.error("Max retries reached for database reconnection")
                raise Exception("Failed to establish database connection after max retries")


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


def follow(db):
    """
    Continuously follows the blockchain, parsing and indexing new blocks
    for SRC-20 transactions and to gather details about CP trx such as
    keyburn status.
    """
    initialize(db)
    rebuild_balances(db)
    rebuild_owners(db)
    update_src20_token_stats(db)

    # Get index of last block.
    if util.CURRENT_BLOCK_INDEX == 0:
        logger.warning("New database.")
        block_index = config.BLOCK_FIRST
    else:
        block_index = util.CURRENT_BLOCK_INDEX + 1

    logger.info("Resuming parsing.")
    tx_index = next_tx_index(db)

    # Add ZMQ initialization here
    zmq_notifier = None
    zmq_enabled = False
    try:
        zmq_notifier = ZMQNotifier()
        zmq_enabled = zmq_notifier.check_zmq_ports()
        if zmq_enabled:
            logger.info("ZMQ notifications enabled")
    except Exception as e:
        logger.warning(f"Failed to initialize ZMQ: {e}")

    stamp_issuances_list = None
    executor = None
    consecutive_errors = 0
    max_consecutive_errors = 5
    error_cooldown = 10  # seconds
    last_keepalive = time.time()
    KEEPALIVE_INTERVAL = 60  # Send keepalive every minute

    def send_keepalive(db):
        """Send a lightweight query to keep the connection alive"""
        try:
            with db.cursor() as cursor:
                cursor.execute("SELECT 1")
            return True
        except Exception as e:
            logger.warning(f"Keepalive query failed: {e}")
            return False

    try:
        executor = concurrent.futures.ThreadPoolExecutor()
        update_cpids_future = None
        update_cpids_last_run_block = 0

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
                    block_tip = backend.getblockcount()
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

                    # Remove CPID update from here since we do it in the idle block

                    if stamp_issuances_list and (stamp_issuances_list[block_index] or stamp_issuances_list[block_index] == []):
                        stamp_issuances = stamp_issuances_list[block_index]
                    else:
                        try:
                            if server.shutdown_flag.is_set():
                                logger.info("Shutdown flag detected before CP fetch, breaking...")
                                break

                            if block_index + 1 == block_tip:
                                indicator = True
                            else:
                                indicator = None

                            stamp_issuances_list = fetch_cp_concurrent(block_index, block_tip, indicator=indicator)

                            if server.shutdown_flag.is_set():
                                logger.info("Shutdown flag detected after CP fetch, breaking...")
                                break

                            stamp_issuances = stamp_issuances_list[block_index]
                        except KeyboardInterrupt:
                            logger.info("Received keyboard interrupt during CP fetch.")
                            server.shutdown_flag.set()
                            break
                        except Exception as e:
                            logger.error(f"Error during CP fetch: {e}")
                            if not config.FORCE:
                                raise

                    if block_tip - block_index < 100:
                        requires_rollback = False
                        while True:
                            if block_index == config.BLOCK_FIRST:
                                break
                            logger.info(f"Checking that block {block_index} is not orphan.")
                            current_hash = backend.getblockhash(block_index)
                            block_header = backend.getblockheader(current_hash)
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
                            logger.warning(f"Rolling back to block {block_index} to avoid problems.")
                            purge_block_db(db, block_index)
                            rebuild_balances(db)
                            rebuild_owners(db)
                            update_src20_token_stats(db)
                            requires_rollback = False
                            stamp_issuances_list = None
                            time.sleep(60)  # delay waiting for CP to catch up
                            continue

                    block_hash = backend.getblockhash(block_index)

                    # Get full block data from backend
                    txhash_list_full, raw_transactions_full, block_time, previous_block_hash, difficulty = backend.get_tx_list(
                        block_hash
                    )

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

                    block_processor = BlockProcessor(db)
                    block_processor.insert_transactions(tx_results)
                    block_processor.process_transaction_results(tx_results)

                    new_ledger_hash, new_txlist_hash, new_messages_hash, stamps_in_block, src20_in_block, src101_in_block = (
                        block_processor.finalize_block(block_index, block_time, txhash_list)
                    )

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

                else:
                    if server.shutdown_flag.is_set():
                        break

                    # Check database connection before waiting
                    db = check_db_connection(db)

                    # Update CPIDs if needed (every 50 blocks)
                    if (block_index % 50 == 0) and (block_index != update_cpids_last_run_block):
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
                    else:
                        logger.info(f"Not time yet for update_cpids_async. Current block: {block_index}")

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
                                        block_tip = backend.getblockcount()
                                        break
                                continue
                        except Exception as e:
                            logger.warning(f"ZMQ notification failed, falling back to polling: {e}")
                            zmq_enabled = False
                            if zmq_notifier:
                                zmq_notifier.cleanup()

                    # Only reach here if ZMQ is disabled or failed
                    if not zmq_enabled:
                        logger.info("Using RPC polling for new blocks")

                        # Send keepalive if needed
                        if time.time() - last_keepalive > KEEPALIVE_INTERVAL:
                            if not send_keepalive(db):
                                db = check_db_connection(db)
                            last_keepalive = time.time()

                        time.sleep(config.BACKEND_POLL_INTERVAL)
                        block_tip = backend.getblockcount()

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
                db.rollback()
                # Short sleep before retry
                if not server.shutdown_flag.is_set():
                    time.sleep(5)

    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt in follow().")
    except Exception as e:
        logger.error(f"An unexpected error occurred in follow(): {e}")
        raise
    finally:
        logger.info("Starting cleanup in follow()...")
        if zmq_notifier:
            logger.info("Cleaning up ZMQ resources...")
            zmq_notifier.cleanup()
        if executor:
            logger.info("Shutting down executor...")
            try:
                executor.shutdown(wait=True, timeout=10)
            except TypeError:
                executor.shutdown(wait=True)
        try:
            logger.info("Committing final transactions...")
            db.commit()
        except Exception as e:
            logger.error(f"Error during final commit: {e}")
        try:
            logger.info("Closing database connection...")
            db.close()
        except Exception as e:
            logger.error(f"Error closing database: {e}")
        logger.info("Cleanup complete in follow().")
        logging.shutdown()
