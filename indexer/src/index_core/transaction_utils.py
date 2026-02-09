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
    calculate_total_inputs(): Calculate total input value for fee calculation
"""

import json
import logging
from collections import namedtuple

import config
import index_core.arc4 as arc4
import index_core.script as script
import index_core.util as util
from index_core.backend import Backend
from index_core.exceptions import BTCOnlyError, DecodeError
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
        "fee_rate_sat_vb",  # Added fee_rate_sat_vb field
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
        "fee_rate_sat_vb",
        "is_olga",
        "p2wsh_data_chunks",
    ],
)


def calculate_total_inputs(ctx):
    """
    Calculate the total value of all inputs in a transaction.

    Args:
        ctx: The decoded transaction context containing vin array

    Returns:
        int: Total input value in satoshis, or 0 if calculation fails

    Note:
        - Coinbase transactions (first transaction in block) have no real inputs, returns 0
        - Gracefully handles errors by returning 0 to preserve consensus behavior
        - Uses batch fetching for efficiency when multiple inputs exist
    """
    try:
        if not hasattr(ctx, "vin") or not ctx.vin:
            logger.debug("Transaction has no inputs")
            return 0

        # First pass: collect all transaction hashes we need to fetch
        tx_hashes_to_fetch = []
        input_refs = []  # Store (tx_hash, output_index) for each input

        for vin in ctx.vin:
            # Check for coinbase transaction (no previous output)
            if not hasattr(vin, "prevout") or not vin.prevout:
                logger.debug("Coinbase transaction detected, returning 0 fee")
                return 0

            # Check for null hash (coinbase indicator)
            if hasattr(vin.prevout, "hash") and vin.prevout.hash == b"\x00" * 32:
                logger.debug("Coinbase transaction detected (null hash), returning 0 fee")
                return 0

            prev_tx_hash = util.ib2h(vin.prevout.hash)
            prev_tx_index = vin.prevout.n

            tx_hashes_to_fetch.append(prev_tx_hash)
            input_refs.append((prev_tx_hash, prev_tx_index))

        # Batch fetch all previous transactions at once
        if not tx_hashes_to_fetch:
            return 0

        try:
            # Use batch fetching for efficiency
            prev_txs = backend_instance.getrawtransaction_batch(tx_hashes_to_fetch, verbose=False)

            total_input_value = 0

            # Process each input with its fetched transaction
            for tx_hash, output_index in input_refs:
                if tx_hash not in prev_txs or prev_txs[tx_hash] is None:
                    logger.debug(f"Could not fetch previous transaction {tx_hash}")
                    return 0

                # Deserialize and get the output value
                prev_ctx = backend_instance.deserialize(prev_txs[tx_hash])

                if output_index < len(prev_ctx.vout):
                    prev_vout = prev_ctx.vout[output_index]
                    total_input_value += prev_vout.nValue
                else:
                    logger.warning(f"Invalid output index {output_index} for transaction {tx_hash}")
                    return 0

            return total_input_value

        except Exception as e:
            logger.debug(f"Error in batch fetching previous transactions: {e}")
            return 0

    except Exception as e:
        logger.debug(f"Error calculating total inputs: {e}")
        return 0


def serialize_transaction(ctx):
    """
    Serialize a transaction to get its raw byte representation.

    Args:
        ctx: The decoded transaction context

    Returns:
        bytes: Serialized transaction bytes, or empty bytes if serialization fails

    Note:
        - Uses existing backend_instance.serialize() method
        - Gracefully handles errors by returning empty bytes
    """
    try:
        if not ctx:
            logger.debug("No transaction context provided")
            return b""

        # Use backend serialize method (opposite of deserialize)
        serialized_bytes = backend_instance.serialize(ctx)
        return serialized_bytes

    except Exception as e:
        logger.debug(f"Error serializing transaction: {e}")
        return b""


def has_witness_data(ctx):
    """
    Check if a transaction contains witness (SegWit) data.

    Args:
        ctx: The decoded transaction context

    Returns:
        bool: True if transaction has witness data, False otherwise

    Note:
        - SegWit transactions have witness data in their inputs
        - Legacy transactions do not have witness data
    """
    try:
        if not hasattr(ctx, "vin") or not ctx.vin:
            return False

        # Check if any input has witness data
        for vin in ctx.vin:
            if hasattr(vin, "scriptWitness") and vin.scriptWitness:
                # Check if witness has actual data (not just empty)
                if hasattr(vin.scriptWitness, "stack") and vin.scriptWitness.stack:
                    return True
                elif isinstance(vin.scriptWitness, list) and vin.scriptWitness:
                    return True
                elif isinstance(vin.scriptWitness, bytes) and vin.scriptWitness:
                    return True

        return False

    except Exception as e:
        logger.debug(f"Error checking witness data: {e}")
        return False


def calculate_legacy_size(ctx):
    """
    Calculate the size of a transaction as if it were a legacy (non-SegWit) transaction.

    Args:
        ctx: The decoded transaction context

    Returns:
        int: Transaction size in bytes, or 0 if calculation fails

    Note:
        - For legacy transactions, this is the actual size
        - For SegWit transactions, this excludes witness data
        - Used in virtual size calculation for SegWit transactions
    """
    try:
        # Serialize the transaction to get byte representation
        serialized_tx = serialize_transaction(ctx)
        if not serialized_tx:
            return 0

        # For legacy transactions, return the actual serialized size
        if not has_witness_data(ctx):
            return len(serialized_tx)

        # For SegWit transactions, we need to calculate size without witness data
        # This is more complex and would require reconstructing the transaction
        # without witness fields, which is not easily available in our current setup.
        #
        # TODO: Implement proper SegWit base size calculation by parsing the
        # transaction structure and excluding witness data. For now, we use
        # an approximation that may not be accurate for all transaction types.
        #
        # Estimate base size (without witness) as ~75% of total size
        # This approximation works reasonably well for typical P2WPKH transactions
        # but may be less accurate for complex scripts or multisig transactions.
        estimated_base_size = int(len(serialized_tx) * 0.75)

        return estimated_base_size

    except Exception as e:
        logger.debug(f"Error calculating legacy size: {e}")
        return 0


def calculate_segwit_weight(ctx):
    """
    Calculate the weight of a SegWit transaction according to BIP 141.

    Args:
        ctx: The decoded transaction context

    Returns:
        int: Transaction weight in weight units, or 0 if calculation fails

    Note:
        - Weight = (base_size * 4) + witness_size
        - Base size excludes witness data
        - Witness size includes only witness data
        - For legacy transactions, weight = size * 4
    """
    try:
        if not has_witness_data(ctx):
            # Legacy transaction: weight = size * 4
            legacy_size = calculate_legacy_size(ctx)
            return legacy_size * 4

        # SegWit transaction: weight = (base_size * 4) + witness_size
        base_size = calculate_legacy_size(ctx)

        # Get total serialized size (including witness)
        total_size = len(serialize_transaction(ctx))

        # Estimate witness size as the difference
        witness_size = total_size - base_size

        # Calculate weight according to BIP 141
        weight = (base_size * 4) + witness_size

        return weight

    except Exception as e:
        logger.debug(f"Error calculating SegWit weight: {e}")
        return 0


def calculate_virtual_size(ctx):
    """
    Calculate the virtual size (vsize) of a transaction.

    Args:
        ctx: The decoded transaction context

    Returns:
        int: Virtual size in virtual bytes (vbytes), or 0 if calculation fails

    Note:
        - For legacy transactions: vsize = size
        - For SegWit transactions: vsize = ceil(weight / 4)
        - Virtual size is used for fee rate calculations (sats/vB)
    """
    try:
        if not has_witness_data(ctx):
            # Legacy transaction: vsize = size
            return calculate_legacy_size(ctx)

        # SegWit transaction: vsize = ceil(weight / 4)
        weight = calculate_segwit_weight(ctx)
        if weight == 0:
            return 0

        # Use ceiling division to match Bitcoin Core behavior
        vsize = (weight + 3) // 4  # Equivalent to ceil(weight / 4)

        return vsize

    except Exception as e:
        logger.debug(f"Error calculating virtual size: {e}")
        return 0


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
    total_output_value = 0
    p2wsh_data_chunks = []
    is_olga = False

    pubkeys_compiled = []

    for idx, vout in enumerate(vouts):
        asm = script.get_asm(vout.scriptPubKey)
        n_value = vout.nValue
        total_output_value += n_value

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

    # Calculate actual transaction fee: inputs - outputs
    total_input_value = calculate_total_inputs(ctx)
    fee = total_input_value - total_output_value

    # Validate fee calculation
    if fee < 0:
        logger.warning(f"Negative fee calculated: inputs={total_input_value}, outputs={total_output_value}, setting fee=0")
        fee = 0
    elif fee > 1000000:  # 0.01 BTC = 1,000,000 satoshis (unusually high)
        logger.warning(f"Unusually high fee calculated: {fee} satoshis")

    # Calculate fee rate in sats/vB
    virtual_size = calculate_virtual_size(ctx)
    if virtual_size > 0 and fee > 0:
        fee_rate_sat_vb = round(fee / virtual_size, 2)  # Round to 2 decimal places
    else:
        fee_rate_sat_vb = 0.0

    vOutInfo = namedtuple(
        "vOutInfo",
        ["pubkeys_compiled", "keyburn", "is_op_return", "fee", "fee_rate_sat_vb", "is_olga", "p2wsh_data_chunks"],
    )

    return vOutInfo(pubkeys_compiled, keyburn, is_op_return, fee, fee_rate_sat_vb, is_olga, p2wsh_data_chunks)


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
        chunk_length_int = int(chunk[:2].hex(), 16)
        if len(chunk) < 2 + chunk_length_int:
            raise DecodeError("invalid data length")
        data = chunk[2 + len(config.PREFIX) : 2 + chunk_length_int]

        script_pubkey = ctx.vout[0].scriptPubKey
        destination = util.decode_address(script_pubkey)
        destination_nvalue = ctx.vout[0].nValue
        return str(destination), destination_nvalue, data
    else:
        return None, None, None


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
        # Use JSON serialization to preserve dict structure for later parsing
        data = json.dumps(stamp_issuance)

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
    """Process a single transaction and return its parsed information."""

    # DEBUG: Log critical transaction
    if tx_hash == "95dca4dc27e50e7b26174a0ded7af3b26527def625670d058ae09200eeb3d735":
        logger.error(f"🔍 DEBUG TX 95dca4dc: Starting process_tx in block {block_index}")
        logger.error(f"🔍 DEBUG TX 95dca4dc: stamp_issuances count = {len(stamp_issuances) if stamp_issuances else 0}")

    # Ensure stamp_issuances is a list before filtering
    if stamp_issuances is None:
        stamp_issuances = []
    elif not isinstance(stamp_issuances, list):
        logger.error(f"Invalid stamp_issuances type: {type(stamp_issuances)}")
        stamp_issuances = []

    stamp_issuance = find_issuance_by_tx_hash(stamp_issuances, tx_hash)

    # DEBUG: Log issuance lookup result
    if tx_hash == "95dca4dc27e50e7b26174a0ded7af3b26527def625670d058ae09200eeb3d735":
        if stamp_issuance:
            logger.error(f"🔍 DEBUG TX 95dca4dc: Found issuance! CPID = {stamp_issuance.get('cpid')}")
            logger.error(f"🔍 DEBUG TX 95dca4dc: Description = {stamp_issuance.get('description', '')[:100]}...")
        else:
            logger.error("🔍 DEBUG TX 95dca4dc: NO ISSUANCE FOUND!")

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

        # Calculate fee rate for this transaction
        fee_rate_sat_vb = 0.0
        if decoded_tx:
            try:
                virtual_size = calculate_virtual_size(decoded_tx)
                if virtual_size > 0 and fee and fee > 0:
                    fee_rate_sat_vb = round(fee / virtual_size, 2)
            except Exception as e:
                logger.debug(f"Error calculating fee rate for tx {tx_hash}: {e}")

        return TxResult(
            None,
            source,
            prev_tx_hash,
            destination,
            destination_nvalue,
            btc_amount,
            fee,
            fee_rate_sat_vb,
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
    except Exception:

        return TxResult(
            None, None, None, None, None, None, None, None, None, None, None, None, tx_hash, block_index, None, None, None
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
