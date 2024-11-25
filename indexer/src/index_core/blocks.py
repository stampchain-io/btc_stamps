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

from bitcoin.core.script import CScriptInvalidError
from bitcoin.wallet import CBitcoinAddress
from bitcoinlib.keys import pubkeyhash_to_addr
from pymysql.connections import Connection

# import cProfile
# import pstats
import config
import index_core.arc4 as arc4
import index_core.backend as backend
import index_core.check as check
import index_core.log as log
import index_core.script as script
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
    update_assets_in_db,
    update_block_hashes,
    update_parsed_block,
)
from index_core.exceptions import BlockAlreadyExistsError, BlockUpdateError, BTCOnlyError, DatabaseInsertError, DecodeError
from index_core.models import StampData, ValidStamp
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

D = decimal.Decimal
logger = logging.getLogger(__name__)
log.set_logger(logger)
skip_logger = logging.getLogger("list_tx.skip")

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

    def process_transaction_results(self, tx_results):
        for result in tx_results:
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
                self.parsed_stamps.append(stamp_data)  # includes cursed and prevalidated src20 on CP
            if valid_stamp:
                self.valid_stamps_in_block.append(valid_stamp)
            if prevalidated_src and stamp_data.pval_src20:
                _, src20_dict = parse_src20(self.db, prevalidated_src, self.processed_src20_in_block)
                self.processed_src20_in_block.append(src20_dict)
            if prevalidated_src and stamp_data.pval_src101:
                _, src101_dict = parse_src101(self.db, prevalidated_src, self.processed_src101_in_block, result.block_index)
                self.processed_src101_in_block.append(src101_dict)

        if self.parsed_stamps:
            insert_into_stamp_table(self.db, self.parsed_stamps)
            for stamp in self.parsed_stamps:
                stamp.match_and_insert_collection_data(config.LEGACY_COLLECTIONS, self.db)

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

        if valid_src20_str:
            validate_src20_ledger_hash(block_index, new_ledger_hash, valid_src20_str)

        stamps_in_block = len(self.valid_stamps_in_block)
        src20_in_block = len(self.processed_src20_in_block)
        return new_ledger_hash, new_txlist_hash, new_messages_hash, stamps_in_block, src20_in_block

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
                        destinations = decode_address(destination_pubkey)
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
        source = decode_address(prev_vout_script_pubkey)

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


def decode_address(script_pubkey):
    """
    Decode a Bitcoin address from a scriptPubKey. This supports taproot, etc

    Args:
        script_pubkey (bytes): The scriptPubKey to decode.

    Returns:
        str: The decoded Bitcoin address.

    Raises:
        ValueError: If the scriptPubKey format is unsupported.
    """
    try:
        # Attempt standard address decoding
        address = CBitcoinAddress.from_scriptPubKey(script_pubkey)
        return str(address)
    except Exception:
        # Handle other types of addresses
        if len(script_pubkey) == 34 and script_pubkey[0] == 0x51:  # Taproot check
            # Extract the witness program for Taproot
            witness_program = script_pubkey[2:]
            # Decode as Bech32m address
            if config.TESTNET:
                return pubkeyhash_to_addr(witness_program, prefix="tb", encoding="bech32", witver=1)
            else:
                return pubkeyhash_to_addr(witness_program, prefix="bc", encoding="bech32", witver=1)
        else:
            raise ValueError("Unsupported scriptPubKey format")


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
        destination = decode_address(script_pubkey)
        destination_nvalue = ctx.vout[0].nValue
        return str(destination), destination_nvalue, data
    else:
        return None, None, data


def list_tx(db, block_index: int, tx_hash: str, tx_hex=None, stamp_issuance=None):
    if not isinstance(tx_hash, str):
        raise TypeError("tx_hash must be a string")
    # NOTE: this is for future reparsing options
    # cursor = db.cursor()
    # cursor.execute('''SELECT * FROM transactions WHERE tx_hash = %s''', (tx_hash,)) # this will include all CP transactinos as well ofc
    # transactions = cursor.fetchall()
    # cursor.close()
    # if transactions:
    #     return tx_index

    if tx_hex is None:
        tx_hex = backend.getrawtransaction(tx_hash)

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
        logger.info(
            "Saving to MySQL transactions: {}\nDATA:{}\nKEYBURN: {}\nOP_RETURN: {}".format(
                tx_hash, data, keyburn, is_op_return
            )
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
        skip_logger.debug("Skipping transaction: {}".format(tx_hash))
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
        logger.error(e)
        sys.exit("Exiting due to a critical update error.")

    return new_ledger_hash, new_txlist_hash, new_messages_hash


def commit_and_update_block(db, block_index):
    """
    Commits the changes to the database, updates the parsed block, and increments the block index.

    Args:
        db: The database connection object.
        block_index: The current block index.

    Raises:
        Exception: If an error occurs during the commit or update process.

    Returns:
        None
    """
    try:
        db.commit()
        update_parsed_block(db, block_index)
        block_index += 1
        return block_index
    except Exception as e:
        print("Error message:", e)
        db.rollback()
        db.close()
        sys.exit()


def log_block_info(
    block_index: int,
    start_time: float,
    new_ledger_hash: str,
    new_txlist_hash: str,
    new_messages_hash: str,
    stamps_in_block: int,
    src20_in_block: int,
):
    """
    Logs the information of a block.

    Parameters:
    - block_index (int): The index of the block.
    - start_time (float): The start time of the block.
    - new_ledger_hash (str): The hash of the new ledger.
    - new_txlist_hash (str): The hash of the new transaction list.
    - new_messages_hash (str): The hash of the new messages.

    Returns:
    None
    """
    logger = logging.getLogger(__name__)
    logger.warning(
        "Block: %s (%ss, hashes: L:%s / TX:%s / M:%s / S:%s / S20:%s)"
        % (
            str(block_index),
            "{:.2f}".format(time.time() - start_time),
            new_ledger_hash[-5:] if new_ledger_hash else "N/A",
            new_txlist_hash[-5:],
            new_messages_hash[-5:],
            stamps_in_block,
            src20_in_block,
        )
    )


def process_tx(db, tx_hash, block_index, stamp_issuances, raw_transactions):
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


def follow(db):
    """
    Continuously follows the blockchain, parsing and indexing new blocks
    for SRC-20 transactions and to gather details about CP trx such as
    keyburn status.

    Args:
        db: The database connection object.

    Returns:
        None
    """

    # Check software version.
    check.cp_version()  # FIXME: need to add version checks for the endpoints and hash validations
    initialize(db)
    rebuild_balances(db)

    # Get index of last block.
    if util.CURRENT_BLOCK_INDEX == 0:
        logger.warning("New database.")
        block_index = config.BLOCK_FIRST
    else:
        block_index = util.CURRENT_BLOCK_INDEX + 1

    logger.info("Resuming parsing.")
    tx_index = next_tx_index(db)

    # a reorg can happen without the block count increasing, or even for that
    # matter, with the block count decreasing. This should only delay
    # processing of the new blocks a bit.
    try:
        block_tip = backend.getblockcount()
    except (
        ConnectionRefusedError,
        http.client.CannotSendRequest,
        backend.BackendRPCError,
    ) as e:
        if config.FORCE:
            time.sleep(config.BACKEND_POLL_INTERVAL)
        else:
            raise e

    stamp_issuances_list = None
    # profiler = cProfile.Profile()
    # should_profile = True

    executor = concurrent.futures.ThreadPoolExecutor()
    update_cpids_future = None
    update_cpids_last_run_block = None

    try:
        while True:
            start_time = time.time()

            try:
                block_tip = backend.getblockcount()
            except (
                ConnectionRefusedError,
                http.client.CannotSendRequest,
                backend.BackendRPCError,
            ) as e:
                if config.FORCE:
                    time.sleep(config.BACKEND_POLL_INTERVAL)
                    continue
                else:
                    raise e

            if block_index != config.BLOCK_FIRST and not is_prev_block_parsed(db, block_index):
                block_index -= 1

            if block_index <= block_tip:
                db.ping()

                if stamp_issuances_list and (stamp_issuances_list[block_index] or stamp_issuances_list[block_index] == []):
                    stamp_issuances = stamp_issuances_list[block_index]
                else:
                    if block_index + 1 == block_tip:
                        indicator = True
                    else:
                        indicator = None
                    stamp_issuances_list = fetch_cp_concurrent(block_index, block_tip, indicator=indicator)
                    stamp_issuances = stamp_issuances_list[block_index]

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
                        requires_rollback = False
                        stamp_issuances_list = None
                        time.sleep(60)  # delay waiting for CP to catch up
                        continue

                block_hash = backend.getblockhash(block_index)

                txhash_list, raw_transactions, block_time, previous_block_hash, difficulty = backend.get_tx_list(block_hash)
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
                    sys.exit(f"Exiting due to block already existing. {e}")
                except DatabaseInsertError as e:
                    logger.error(e)
                    sys.exit("Critical database error encountered. Exiting.")

                valid_stamps_in_block: List[ValidStamp] = []

                if not stamp_issuances_list[block_index] and block_index < config.CP_SRC20_GENESIS_BLOCK:
                    valid_src20_str = ""
                    new_ledger_hash, new_txlist_hash, new_messages_hash = create_check_hashes(
                        db,
                        block_index,
                        valid_stamps_in_block,
                        valid_src20_str,
                        txhash_list,
                    )

                    stamp_issuances_list.pop(block_index, None)
                    log_block_info(
                        block_index,
                        start_time,
                        new_ledger_hash,
                        new_txlist_hash,
                        new_messages_hash,
                        0,
                        0,
                    )
                    block_index = commit_and_update_block(db, block_index)
                    continue

                tx_results = []

                futures = []
                for tx_hash in txhash_list:
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

                new_ledger_hash, new_txlist_hash, new_messages_hash, stamps_in_block, src20_in_block = (
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
                )
                block_index = commit_and_update_block(db, block_index)

            else:
                logger.info(f"Block {block_index} is beyond the current block tip {block_tip}. Waiting for new blocks.")
                # every 50 blocks, update the supply/divisible/locked status of all unlocked CPIDs
                if (block_index % 50 == 0) and (block_index != update_cpids_last_run_block):
                    if update_cpids_future is None or update_cpids_future.done():
                        update_cpids_future = executor.submit(update_cpids_async, db)
                        update_cpids_last_run_block = block_index
                        logger.info(f"Submitted update_cpids_async task at block {block_index}.")
                    else:
                        logger.info("update_cpids_async is already running. Skipping submission.")
                else:
                    logger.info(f"Not time yet for update_cpids_async. Current block: {block_index}")
                time.sleep(30)  # TODO: Setup ZMQ triggers

        # if should_profile:
        #     profiler.disable()
        #     profiler.dump_stats("profile_results.prof")
        #     stats = pstats.Stats(profiler).sort_stats('cumulative')
        #     stats.print_stats()
        #     should_profile = False
    except KeyboardInterrupt:
        logger.info("Shutting down gracefully...")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
    finally:
        executor.shutdown(wait=True)
        logger.info("Executor has been shut down.")


def update_cpids_async(db):
    try:
        cpids = get_unlocked_cpids(db)
        if cpids:
            cpids_list = [cpid[0] for cpid in cpids]
            assets_details = get_xcp_assets_by_cpids(cpids_list, chunk_size=200, delay_between_chunks=6, max_workers=5)
            if assets_details:
                update_assets_in_db(db, assets_details, chunk_size=200, delay_between_chunks=6)
                logger.info("Successfully updated assets in the database.")
            else:
                logger.warning("No asset details were retrieved.")
        else:
            logger.info("No CPIDs to update.")
    except Exception as e:
        logger.error(f"Error in update_cpids_async: {e}")
