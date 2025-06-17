"""
Transaction processing utilities extracted from blocks.py

This module contains functions for processing Bitcoin transactions,
particularly for Bitcoin Stamps and SRC-20 tokens. These functions
handle transaction parsing, validation, and data extraction.

Functions:
    process_vout(): Process transaction outputs for stamp data
    get_tx_info(): Extract comprehensive transaction information
    decode_checkmultisig(): Decode CHECKMULTISIG script data
    list_tx(): List transaction data for block processing
    process_tx(): Process individual transactions with stamp issuances
    quick_filter_src20_transaction(): Fast filtering for SRC-20 transactions
"""

import logging
from collections import namedtuple

import config
import index_core.arc4 as arc4
import index_core.script as script
import index_core.util as util
from exceptions import DecodeError
from index_core.backend import Backend
from index_core.fetch_utils import find_issuance_by_tx_hash

# Module logger
logger = logging.getLogger(__name__)

# Backend instance for transaction operations
backend_instance = Backend()

# Transaction result structure - matches original blocks.py
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

# vOut information structure
vOutInfo = namedtuple(
    "vOutInfo",
    [
        "pubkeys_compiled",
        "keyburn",
        "is_op_return",
        "fee",
        "is_olga",
        "p2wsh_data_chunks",
    ],
)


def process_vout(ctx, block_index, stamp_issuance=None):
    """
    Process the vout of a transaction to extract relevant data.

    Args:
        ctx: The transaction context.
        block_index (int): The block index.
        stamp_issuance: The stamp issuance data (optional).

    Returns:
        vOutInfo: A named tuple containing the extracted data.
    """
    pubkeys_compiled = []
    keyburn = 0
    is_op_return = None
    fee = 0
    p2wsh_data_chunks = []

    # Check if this is a OLGA block
    is_olga = block_index >= config.BTC_SRC20_OLGA_BLOCK

    for vout in ctx.vout:
        asm = script.get_asm(vout.scriptPubKey)

        # Check for OP_RETURN
        if len(asm) >= 1 and asm[0] == "OP_RETURN":
            is_op_return = True

        # Check for CHECKMULTISIG
        pubkeys_list, sigs_required, keyburn_amount = script.get_checkmultisig(asm)
        if pubkeys_list:
            pubkeys_compiled.extend(pubkeys_list)
            keyburn += keyburn_amount

        # Check for P2WSH and collect data chunks if stamp issuance
        if stamp_issuance and stamp_issuance.get("p2wsh_data_required", False):
            p2wsh_chunks = script.get_p2wsh(asm)
            if p2wsh_chunks:
                p2wsh_data_chunks.extend(p2wsh_chunks)

        fee += vout.nValue

    return vOutInfo(
        pubkeys_compiled=pubkeys_compiled,
        keyburn=keyburn,
        is_op_return=is_op_return,
        fee=fee,
        is_olga=is_olga,
        p2wsh_data_chunks=p2wsh_data_chunks,
    )


def get_tx_info(tx_hex, block_index=None, db=None, stamp_issuance=None):
    """
    Extract transaction information for Bitcoin Stamps processing.

    Args:
        tx_hex (str): The transaction hex.
        block_index (int, optional): The block index.
        db: Database connection (optional).
        stamp_issuance: Stamp issuance data (optional).

    Returns:
        TransactionInfo or None: Transaction information or None if not relevant.
    """
    try:
        ctx = backend_instance.deserialize(tx_hex)
    except Exception as e:
        raise DecodeError(f"Transaction deserialization failed: {e}")

    # Process vout to get transaction data
    vout_info = process_vout(ctx, block_index or 0, stamp_issuance)

    # Skip if no relevant data found
    if not vout_info.pubkeys_compiled and not vout_info.p2wsh_data_chunks and not vout_info.is_op_return:
        return None

    # Extract basic transaction info
    tx_hash = util.ib2h(ctx.hash)
    source = None
    destination = None
    btc_amount = 0
    data = None

    # Process first input for source
    if ctx.vin:
        try:
            # Get source address from first input
            vin = ctx.vin[0]
            if hasattr(vin, "prevout"):
                source_tx = backend_instance.getrawtransaction(util.ib2h(vin.prevout.hash))
                source_ctx = backend_instance.deserialize(source_tx)
                if vin.prevout.n < len(source_ctx.vout):
                    source_script = source_ctx.vout[vin.prevout.n].scriptPubKey
                    source = util.decode_address(source_script)
        except Exception:
            # Source extraction failed, continue without source
            pass

    # Process multisig data if present
    if vout_info.pubkeys_compiled:
        try:
            # Find the CHECKMULTISIG chunk
            for vout in ctx.vout:
                asm = script.get_asm(vout.scriptPubKey)
                pubkeys_list, sigs_required, keyburn_amount = script.get_checkmultisig(asm)
                if pubkeys_list:
                    # Try to decode the data
                    for chunk in pubkeys_list:
                        try:
                            destination, btc_amount, data = decode_checkmultisig(ctx, chunk)
                            break
                        except DecodeError:
                            continue
                    break
        except Exception:
            # CHECKMULTISIG processing failed
            pass

    # Process P2WSH data if present
    if vout_info.p2wsh_data_chunks:
        try:
            # Combine P2WSH data chunks
            combined_data = b"".join(vout_info.p2wsh_data_chunks)
            if combined_data.startswith(config.PREFIX):
                data = combined_data[len(config.PREFIX) :]
        except Exception:
            # P2WSH processing failed
            pass

    # Create transaction info structure
    TransactionInfo = namedtuple(
        "TransactionInfo",
        [
            "source",
            "destination",
            "btc_amount",
            "fee",
            "data",
            "keyburn",
            "tx_hash",
            "op",
            "tx_index",
            "supported",
            "tx_hex",
        ],
    )

    return TransactionInfo(
        source=source,
        destination=destination,
        btc_amount=btc_amount,
        fee=vout_info.fee,
        data=data,
        keyburn=vout_info.keyburn,
        tx_hash=tx_hash,
        op=None,  # Operation type determined later
        tx_index=None,  # Transaction index determined later
        supported=True,
        tx_hex=tx_hex,
    )


def decode_checkmultisig(ctx, chunk):
    """
    Decode CHECKMULTISIG script data.

    Args:
        ctx: Transaction context.
        chunk (bytes): The data chunk to decode.

    Returns:
        tuple: (destination, nvalue, data)

    Raises:
        DecodeError: If decoding fails.
    """
    if len(chunk) < len(config.PREFIX) + 1 + 32:
        raise DecodeError("Insufficient chunk length")

    if not chunk.startswith(config.PREFIX):
        raise DecodeError("Invalid prefix")

    # Extract components
    offset = len(config.PREFIX)
    address_length = chunk[offset]
    offset += 1

    if len(chunk) < offset + address_length + 4:
        raise DecodeError("Insufficient data for address and value")

    # Extract address
    address_bytes = chunk[offset : offset + address_length]
    offset += address_length

    # Extract value (4 bytes, big-endian)
    nvalue_bytes = chunk[offset : offset + 4]
    nvalue = int.from_bytes(nvalue_bytes, byteorder="big")
    offset += 4

    # Extract encrypted data
    encrypted_data = chunk[offset:]

    # Decrypt data using ARC4
    try:
        # Check if transaction has inputs
        if not ctx.vin:
            raise DecodeError("Transaction has no inputs for ARC4 key")

        # Use first input hash as key
        key_hash = ctx.vin[0].prevout.hash
        arc4_key = arc4.init_arc4(key_hash)
        decrypted_data = arc4.arc4_decrypt_chunk(encrypted_data, arc4_key)
    except Exception as e:
        raise DecodeError(f"ARC4 decryption failed: {e}")

    # Decode destination address
    try:
        destination = util.decode_address(address_bytes)
    except Exception as e:
        raise DecodeError(f"Address decoding failed: {e}")

    return destination, nvalue, decrypted_data


def list_tx(db, block_index, tx_hash, tx_hex=None, stamp_issuance=None):
    """
    List transaction data for block processing.

    Args:
        db: Database connection.
        block_index (int): Block index.
        tx_hash (str): Transaction hash.
        tx_hex (str, optional): Transaction hex.
        stamp_issuance: Stamp issuance data (optional).

    Returns:
        tuple or Generator: Transaction data or generator of None values.
    """
    if not isinstance(tx_hash, str):
        raise TypeError("tx_hash must be a string")

    # Get transaction hex if not provided
    if tx_hex is None:
        logger.debug(f"Fetching raw transaction for tx_hash: {tx_hash}")
        tx_hex = backend_instance.getrawtransaction(tx_hash, verbose=False, skip_missing=False, current_block=block_index)

    # Parse transaction to get context
    try:
        ctx = backend_instance.deserialize(tx_hex)
    except Exception as e:
        logger.error(f"Failed to deserialize transaction {tx_hash}: {e}")
        return tuple(None for _ in range(11))

    # Process vout to get initial transaction data
    vout_info = process_vout(ctx, block_index, stamp_issuance)

    # Initialize return values
    source = None
    prev_tx_hash = None
    destination = None
    destination_nvalue = None
    btc_amount = 0
    fee = vout_info.fee
    data = None
    decoded_tx = ctx
    keyburn = vout_info.keyburn
    is_op_return = vout_info.is_op_return
    p2wsh_data = None

    # Extract source from first input
    if ctx.vin:
        try:
            vin = ctx.vin[0]
            if hasattr(vin, "prevout"):
                prev_tx_hash = util.ib2h(vin.prevout.hash)
                source_tx = backend_instance.getrawtransaction(prev_tx_hash)
                source_ctx = backend_instance.deserialize(source_tx)
                if vin.prevout.n < len(source_ctx.vout):
                    source_script = source_ctx.vout[vin.prevout.n].scriptPubKey
                    source = util.decode_address(source_script)
        except Exception as e:
            logger.debug(f"Failed to extract source for {tx_hash}: {e}")

    # Process CHECKMULTISIG if present
    if vout_info.pubkeys_compiled:
        for pubkey in vout_info.pubkeys_compiled:
            try:
                destination, destination_nvalue, data = decode_checkmultisig(ctx, pubkey)
                if destination:
                    break
            except DecodeError:
                continue

    # Process P2WSH data if present
    if vout_info.p2wsh_data_chunks:
        combined_data = b"".join(vout_info.p2wsh_data_chunks)
        if combined_data.startswith(config.PREFIX):
            p2wsh_data = combined_data[len(config.PREFIX) :]
            data = p2wsh_data

    # Check block index (matching original behavior)
    if hasattr(util, "CURRENT_BLOCK_INDEX") and util.CURRENT_BLOCK_INDEX is not None:
        if block_index != util.CURRENT_BLOCK_INDEX:
            raise ValueError(
                f"block_index does not match util.CURRENT_BLOCK_INDEX: {block_index} != {util.CURRENT_BLOCK_INDEX}"
            )

    # Handle stamp issuance override (matching original)
    if stamp_issuance is not None:
        source = str(stamp_issuance.get("source", source) or source)
        destination = str(stamp_issuance.get("issuer", destination) or destination)
        data = str(stamp_issuance)

    # Check if we have enough data to process
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
        return tuple(None for _ in range(11))


def process_tx(db, tx_hash, block_index, stamp_issuances, raw_transactions):
    """
    Process individual transaction with stamp issuances.

    Args:
        db: Database connection.
        tx_hash (str): Transaction hash.
        block_index (int): Block index.
        stamp_issuances: List of stamp issuances.
        raw_transactions (dict): Raw transaction data.

    Returns:
        TxResult: Transaction processing result.
    """
    try:
        # Find matching issuance
        issuance = None
        if isinstance(stamp_issuances, list):
            issuance = find_issuance_by_tx_hash(stamp_issuances, tx_hash)

        # Get transaction hex
        tx_hex = raw_transactions.get(tx_hash)

        # Process transaction
        tx_data = list_tx(db, block_index, tx_hash, tx_hex, issuance)

        # Convert generator to tuple if necessary (maintaining original behavior)
        if hasattr(tx_data, "__iter__") and not isinstance(tx_data, (tuple, list)):
            tx_data = tuple(tx_data)

        # Check if tx_data is a valid tuple with 11 elements
        if not isinstance(tx_data, tuple) or len(tx_data) != 11:
            logger.error(
                f"Unexpected tx_data format for {tx_hash}: type={type(tx_data)}, len={len(tx_data) if hasattr(tx_data, '__len__') else 'N/A'}"
            )
            raise ValueError("Invalid tx_data format")

        # Map the original list_tx return values to TxResult
        # tx_data order: source, prev_tx_hash, destination, destination_nvalue,
        # btc_amount, fee, data, decoded_tx, keyburn, is_op_return, p2wsh_data
        return TxResult(
            tx_index=None,  # tx_index (field 0)
            source=tx_data[0],  # source (field 1)
            prev_tx_hash=tx_data[1],  # prev_tx_hash (field 2)
            destination=tx_data[2],  # destination (field 3)
            destination_nvalue=tx_data[3],  # destination_nvalue (field 4)
            btc_amount=tx_data[4],  # btc_amount (field 5)
            fee=tx_data[5],  # fee (field 6)
            data=tx_data[6],  # data (field 7)
            decoded_tx=tx_data[7],  # decoded_tx (field 8)
            keyburn=tx_data[8],  # keyburn (field 9)
            is_op_return=tx_data[9],  # is_op_return (field 10)
            tx_hash=tx_hash,  # tx_hash (field 11)
            block_index=block_index,  # block_index (field 12)
            block_hash=None,  # block_hash (field 13)
            block_time=None,  # block_time (field 14)
            p2wsh_data=tx_data[10],  # p2wsh_data (field 15)
        )
    except IndexError as e:
        logger.error(f"Failed to process transaction {tx_hash} - IndexError: {e}", exc_info=True)
        return TxResult(
            tx_index=None,
            source=None,
            prev_tx_hash=None,
            destination=None,
            destination_nvalue=None,
            btc_amount=None,
            fee=None,
            data=None,
            decoded_tx=None,
            keyburn=None,
            is_op_return=None,
            tx_hash=tx_hash,
            block_index=block_index,
            block_hash=None,
            block_time=None,
            p2wsh_data=None,
        )
    except Exception as e:
        logger.error(f"Failed to process transaction {tx_hash}: {e}")
        return TxResult(
            tx_index=None,
            source=None,
            prev_tx_hash=None,
            destination=None,
            destination_nvalue=None,
            btc_amount=None,
            fee=None,
            data=None,
            decoded_tx=None,
            keyburn=None,
            is_op_return=None,
            tx_hash=tx_hash,
            block_index=block_index,
            block_hash=None,
            block_time=None,
            p2wsh_data=None,
        )


def quick_filter_src20_transaction(ctx):
    """
    Quickly filter transactions to identify potential SRC-20 transactions.

    Args:
        ctx: Transaction context (CTransaction or dict).

    Returns:
        bool: True if transaction should be included for SRC-20 processing.
    """
    try:
        # Handle both CTransaction objects and dict contexts
        if hasattr(ctx, "vout"):
            vouts = ctx.vout
        elif isinstance(ctx, dict) and "vout" in ctx:
            vouts = ctx["vout"]
        else:
            return False

        # Check for P2WSH outputs first (faster check)
        p2wsh_data_chunks = []
        for vout in vouts:
            if hasattr(vout, "scriptPubKey"):
                script_pubkey = vout.scriptPubKey
            elif isinstance(vout, dict) and "scriptPubKey" in vout:
                script_pubkey = vout["scriptPubKey"]
            else:
                continue

            asm = script.get_asm(script_pubkey)

            # Check for P2WSH pattern (OP_0 followed by 32-byte hash)
            if len(asm) == 2 and asm[0] == "OP_0" and len(asm[1]) == 64:
                p2wsh_chunks = script.get_p2wsh(asm)
                if p2wsh_chunks:
                    p2wsh_data_chunks.extend(p2wsh_chunks)

        # If we found P2WSH data, this is likely an SRC-20 transaction
        if p2wsh_data_chunks:
            return True

        # Check for CHECKMULTISIG outputs with keyburn
        for vout in vouts:
            if hasattr(vout, "scriptPubKey"):
                script_pubkey = vout.scriptPubKey
            elif isinstance(vout, dict) and "scriptPubKey" in vout:
                script_pubkey = vout["scriptPubKey"]
            else:
                continue

            asm = script.get_asm(script_pubkey)
            pubkeys_list, sigs_required, keyburn_amount = script.get_checkmultisig(asm)

            if pubkeys_list and keyburn_amount > 0:
                # Check if any pubkey contains valid data
                for pubkey in pubkeys_list:
                    try:
                        # Try to decrypt and check for PREFIX
                        if hasattr(ctx, "vin") and ctx.vin:
                            key_hash = ctx.vin[0].prevout.hash
                        elif isinstance(ctx, dict) and "vin" in ctx and ctx["vin"]:
                            key_hash = ctx["vin"][0]["prevout"]["hash"]
                        else:
                            continue

                        arc4_key = arc4.init_arc4(key_hash)
                        decrypted = arc4.arc4_decrypt_chunk(pubkey, arc4_key)

                        if decrypted.startswith(config.PREFIX):
                            return True
                    except Exception:
                        # Decryption failed, try next pubkey
                        continue

        return False

    except Exception as e:
        logger.debug(f"Error in quick_filter_src20_transaction: {e}")
        return False
