"""
initialize database.

Sieve blockchain for Stamp transactions, and add them to the database.
"""

import sys
import time
import decimal
import logging
import http
import bitcoin as bitcoinlib
import pymysql as mysql
from bitcoin.core.script import CScriptInvalidError
from bitcoin.wallet import CBitcoinAddress
from bitcoinlib.keys import pubkeyhash_to_addr
from collections import namedtuple
import requests
import concurrent.futures

# import cProfile

import config
import src.exceptions as exceptions
import src.util as util
import check
import src.script as script
import src.backend as backend
import src.arc4 as arc4
import src.log as log
from xcprequest import filter_issuances_by_tx_hash, fetch_cp_concurrent
from stamp import (
    is_prev_block_parsed,
    purge_block_db,
    parse_tx_to_stamp_table,
    update_parsed_block,
    rebuild_balances
)

from src20 import (
    update_src20_balances,
    insert_into_src20_tables
)

from src.exceptions import DecodeError, BTCOnlyError

D = decimal.Decimal
logger = logging.getLogger(__name__)
log.set_logger(logger)  

TxResult = namedtuple('TxResult', ['tx_index', 'source', 'destination', 'btc_amount', 'fee', 'data', 'decoded_tx', 'keyburn', 'is_op_return', 'tx_hash', 'block_index', 'block_hash', 'block_time'])


def initialize(db):
    """initialize data, create and populate the database."""
    cursor = db.cursor() 

    cursor.execute('''
        SELECT MIN(block_index)
        FROM blocks
    ''')
    block_index = cursor.fetchone()[0]

    if block_index is not None and block_index != config.BLOCK_FIRST:
        raise exceptions.DatabaseError('First block in database is not block {}.'.format(config.BLOCK_FIRST))


    cursor.execute(
        '''DELETE FROM blocks WHERE block_index < {}'''
        .format(config.BLOCK_FIRST)
    )

    cursor.execute(
        '''DELETE FROM transactions WHERE block_index < {}'''
        .format(config.BLOCK_FIRST)
    )

    cursor.close()


def process_vout(ctx):
    """
    Process all the out values of a transaction.

    Args:
        ctx (TransactionContext): The transaction context.

    Returns:
        tuple: A tuple containing the following values:
            - pubkeys_compiled (list): A list of public keys.
            - keyburn (int or None): The keyburn value of the transaction.
            - is_op_return (bool or None): Indicates if the transaction is an OP_RETURN transaction.
            - fee (int): The updated fee after processing the vout values.
    """
    pubkeys_compiled = []
    keyburn = None
    is_op_return = None

    # Ignore coinbase transactions.
    if ctx.is_coinbase():
        raise DecodeError('coinbase transaction')

    # Fee is the input values minus output values.
    fee = 0

    for vout in ctx.vout:
        # asm is the bytestring of the vout values
        # Fee is the input values minus output values.
        fee -= vout.nValue
        # Ignore transactions with invalid script.
        try:
            asm = script.get_asm(vout.scriptPubKey)
        except CScriptInvalidError as e:
            raise DecodeError(e)
        if asm[-1] == 'OP_CHECKMULTISIG': # the last element in the asm list is OP_CHECKMULTISIG
            try:
                # NOTE: need to investigate signatures_required, signatures_possible
                pubkeys, signatures_required, keyburn_vout = script.get_checkmultisig(asm) # this is all the pubkeys from the loop
                if keyburn_vout is not None: # if one of the vouts have keyburn we set keyburn for the whole trx. the last vout is not keyburn
                    keyburn = keyburn_vout
                pubkeys_compiled += pubkeys
                # stripped_pubkeys = [pubkey[1:-1] for pubkey in pubkeys]
            except:
                raise DecodeError('unrecognised output type')
        elif asm[-1] == 'OP_CHECKSIG':
            pass # FIXME: not certain if we need to check keyburn on OP_CHECKSIG
                # see 'A14845889080100805000'
                #   0: OP_DUP
                #   1: OP_HASH160
                #   3: OP_EQUALVERIFY
                #   4: OP_CHECKSIG
        elif asm[0] == 'OP_RETURN':
            is_op_return = True

    vOutInfo = namedtuple('vOutInfo', ['pubkeys_compiled', 'keyburn', 'is_op_return', 'fee'])

    return vOutInfo(pubkeys_compiled, keyburn, is_op_return, fee)


def get_tx_info(tx_hex, block_index=None, db=None, stamp_issuance=None):
    """
    Get transaction information.

    Args:
        tx_hex (str): The hexadecimal representation of the transaction.
        block_index (int, optional): The index of the block. Defaults to None.
        db (object, optional): The database object. Defaults to None.
        stamp_issuance (bool, optional): Flag indicating if the transaction is a stamp issuance. Defaults to None.

    Returns:
        TransactionInfo: A named tuple containing the transaction information.

    Raises:
        DecodeError: If the output type is unrecognized.
        BTCOnlyError: If the transaction is not a stamp.

    Note:
        The destinations, if they exist, always come before the data output, and the change, if it exists, always comes after.
        Include keyburn check on all transactions, not just src-20.
        This function parses every transaction, not just stamps/src-20.
        Returns normalized None data for DecodeError and BTCOnlyError.
    """
 
    TransactionInfo = namedtuple('TransactionInfo', ['source', 'destinations', 'btc_amount', 'fee', 'data', 'ctx', 'keyburn', 'is_op_return'])

    try:
        if not block_index:
            block_index = util.CURRENT_BLOCK_INDEX
        
        destinations, btc_amount, data,  = [], 0, b''

        ctx = backend.deserialize(tx_hex)
        vout_info = process_vout(ctx)
        pubkeys_compiled = vout_info.pubkeys_compiled
        keyburn = getattr(vout_info, 'keyburn', None)
        is_op_return = getattr(vout_info, 'is_op_return', None)
        fee = getattr(vout_info, 'fee', None)

        if stamp_issuance is not None:
            # NOTE: rounding fee because of table data type need more precision? 
            return TransactionInfo(None, None, btc_amount, round(fee), None, None, keyburn, is_op_return)

        if pubkeys_compiled:  # this is the combination of the two pubkeys which hold the SRC-20 data
            chunk = b''
            for pubkey in pubkeys_compiled:
                chunk += pubkey[1:-1]       # Skip sign byte and nonce byte. ( this does the concatenation as well)
            try:
                src20_destination, src20_data = decode_checkmultisig(ctx, chunk) # this only decodes src-20 type trx
            except:
                raise DecodeError('unrecognized output type')
            assert src20_destination is not None and src20_data is not None
            if src20_data is not None:
                data += src20_data
                destinations = (str(src20_destination))

        if not data:
            raise BTCOnlyError('no data, not a stamp', ctx)

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

        return TransactionInfo(str(source), destinations, btc_amount, round(fee), data, ctx, keyburn, is_op_return)

    except (DecodeError, BTCOnlyError) as e:
        return TransactionInfo(b'', None, None, None, None, None, None, None)


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
    except Exception as e:
        # Handle other types of addresses
        if len(script_pubkey) == 34 and script_pubkey[0] == 0x51:  # Taproot check
            # Extract the witness program for Taproot
            witness_program = script_pubkey[2:]
            # Decode as Bech32m address
            return pubkeyhash_to_addr(witness_program, prefix='bc', encoding='bech32', witver=1)
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
    chunk = arc4.arc4_decrypt_chunk(chunk, key) # this is a different method since we are stripping the nonce/sign beforehand
    if chunk[2:2+len(config.PREFIX)] == config.PREFIX:
        chunk_length = chunk[:2].hex() # the expected length of the string from the first 2 bytes
        data = chunk[len(config.PREFIX) + 2:].rstrip(b'\x00')
        data_length = len(chunk[2:].rstrip(b'\x00'))
        if data_length != int(chunk_length, 16):
            raise DecodeError('invalid data length')

        script_pubkey = ctx.vout[0].scriptPubKey
        destination = decode_address(script_pubkey)

        return str(destination), data
    else:
        return None, data
            


def reinitialize(db, block_index=None):
    ''' Not yet implemented for stamps  '''

    """Drop all predefined tables and initialize the database once again."""
    cursor = db.cursor()

    # Delete all of the results of parsing (including the undolog) - removed since we aren't using any of these tables,
    # perhaps we purge from the src table here.. 

    # Create missing tables
    initialize(db)

    # warning and exit the program
    Exception("reinitialize() is not implemented yet")

    # clean consensus hashes if first block hash doesn't match with checkpoint.
    if config.TESTNET:
        checkpoints = check.CHECKPOINTS_TESTNET
    elif config.REGTEST:
        checkpoints = check.CHECKPOINTS_REGTEST
    else:
        checkpoints = check.CHECKPOINTS_MAINNET

    columns = [column['name'] for column in cursor.execute('''PRAGMA table_info(blocks)''')]
    for field in ['ledger_hash', 'txlist_hash']:
        if field in columns:
            sql = '''SELECT {} FROM blocks  WHERE block_index = ?'''.format(field)
            first_block = list(cursor.execute(sql, (config.BLOCK_FIRST,)))
            if first_block:
                first_hash = first_block[0][field]
                if first_hash != checkpoints[config.BLOCK_FIRST][field]:
                    logger.info('First hash changed. Cleaning {}.'.format(field))
                    cursor.execute('''UPDATE blocks SET {} = NULL'''.format(field))

    # For rollbacks, just delete new blocks and then reparse what’s left.
    if block_index:
        cursor.execute('''DELETE FROM transactions WHERE block_index > ?''', (block_index,))
        cursor.execute('''DELETE FROM blocks WHERE block_index > ?''', (block_index,))
    elif config.TESTNET or config.REGTEST:  # block_index NOT specified and we are running testnet
        # just blow away the consensus hashes with a full testnet reparse, as we could activate
        # new features retroactively, which could otherwise lead to ConsensusError exceptions being raised.
        logger.info("Testnet/regtest full reparse detected: Clearing all consensus hashes before performing reparse.")
        cursor.execute('''UPDATE blocks SET ledger_hash = NULL, txlist_hash = NULL, messages_hash = NULL''')

    cursor.close()


def reparse(db, block_index=None, quiet=False):
    """Reparse all transactions (atomically). If block_index is set, rollback
    to the end of that block.
    """
    Exception("reparse() is not implemented yet")

    # check.software_version()
    check.cp_version()
    reparse_start = time.time()

    reparsed = False

    cursor = db.cursor()

    if not reparsed:
        if block_index:
            logger.info("Could not roll back from undolog. Performing full reparse instead...")

        if quiet:
            root_logger = logging.getLogger()
            root_level = logger.getEffectiveLevel()

        with db:
            reinitialize(db, block_index)

            # Reparse all blocks, transactions.
            if quiet:
                root_logger.setLevel(logging.WARNING)

            previous_ledger_hash, previous_txlist_hash, previous_messages_hash = None, None, None
            cursor.execute('''SELECT * FROM blocks ORDER BY block_index''')
            for block in cursor.fetchall():
                util.CURRENT_BLOCK_INDEX = block['block_index']
                # will need to fetch txhash_list here to parse for consensus hashes in parse_block
                previous_ledger_hash, previous_txlist_hash, previous_messages_hash, previous_found_messages_hash = parse_block(
                                                                         db, block['block_index'], txhash_list=None,
                                                                         previous_ledger_hash=previous_ledger_hash,
                                                                         previous_txlist_hash=previous_txlist_hash,
                                                                         previous_messages_hash=previous_messages_hash)
                if quiet and block['block_index'] % 10 == 0:  # every 10 blocks print status
                    root_logger.setLevel(logging.INFO)
                logger.info('Block (re-parse): %s (hashes: L:%s / TX:%s / M:%s%s)' % (
                    block['block_index'], previous_ledger_hash[-5:], previous_txlist_hash[-5:], previous_messages_hash[-5:],
                    (' [overwrote %s]' % previous_found_messages_hash) if previous_found_messages_hash and previous_found_messages_hash != previous_messages_hash else ''))
                if quiet and block['block_index'] % 10 == 0:
                    root_logger.setLevel(logging.WARNING)

        if quiet:
            root_logger.setLevel(root_level)

    cursor.close()
    reparse_end = time.time()
    logger.info("Reparse took {:.3f} minutes.".format((reparse_end - reparse_start) / 60.0))


def insert_transactions(db, transactions):
    """
    Insert multiple transactions into the database.

    Args:
        db (DatabaseConnection): The database connection object.
        transactions (list): A list of namedtuples representing transactions.

    Returns:
        int: The index of the last inserted transaction.
    """
    assert util.CURRENT_BLOCK_INDEX is not None
    try:
        values = []
        for tx in transactions:
            values.append((
                tx.tx_index,
                tx.tx_hash,
                util.CURRENT_BLOCK_INDEX,
                tx.block_hash,
                tx.block_time,
                str(tx.source),
                str(tx.destination),
                tx.btc_amount,
                tx.fee,
                tx.data,
                tx.keyburn,
            ))
        with db.cursor() as cursor:
            cursor.executemany(
                '''INSERT INTO transactions (
                    tx_index,
                    tx_hash,
                    block_index,
                    block_hash,
                    block_time,
                    source,
                    destination,
                    btc_amount,
                    fee,
                    data,
                    keyburn
                ) VALUES (%s, %s, %s, %s, FROM_UNIXTIME(%s), %s, %s, %s, %s, %s, %s)''',
                (values)
            )
    except Exception as e:
        raise ValueError(f"Error occurred while inserting transactions: {e}")


def insert_transaction(db, tx_index, tx_hash, block_index, block_hash, block_time, source, destination, btc_amount, fee, data, keyburn):
    """
    Insert a transaction into the database.

    Args:
        db (DatabaseConnection): The database connection object.
        tx_index (int): The index of the transaction.
        tx_hash (str): The hash of the transaction.
        block_index (int): The index of the block containing the transaction.
        block_hash (str): The hash of the block containing the transaction.
        block_time (int): The timestamp of the block containing the transaction.
        source (str): The source address of the transaction.
        destination (str): The destination address of the transaction.
        btc_amount (float): The amount of BTC involved in the transaction.
        fee (float): The transaction fee.
        data (str): Additional data associated with the transaction.
        keyburn (str): The keyburn value of the transaction.

    Returns:
        int: The index of the inserted transaction.
    """
    assert block_index == util.CURRENT_BLOCK_INDEX
    try:
        cursor = db.cursor()
        cursor.execute(
            '''INSERT INTO transactions (
                tx_index,
                tx_hash,
                block_index,
                block_hash,
                block_time,
                source,
                destination,
                btc_amount,
                fee,
                data,
                keyburn
            ) VALUES (%s, %s, %s, %s, FROM_UNIXTIME(%s), %s, %s, %s, %s, %s, %s)''',
            (
                tx_index,
                tx_hash,
                block_index,
                block_hash,
                block_time,
                str(source),
                str(destination),
                btc_amount,
                fee,
                data,
                keyburn,
            )
        )
    except Exception as e:
        raise ValueError(f"Error occurred while inserting transaction: {e}")
    return tx_index + 1


def list_tx(db, block_index, tx_hash, tx_hex=None, stamp_issuance=None):
    assert type(tx_hash) is str
    # NOTE: this is for future reparsing options
    # cursor = db.cursor()
    # cursor.execute('''SELECT * FROM transactions WHERE tx_hash = %s''', (tx_hash,)) # this will include all CP transactinos as well ofc
    # transactions = cursor.fetchall()
    # cursor.close()
    # if transactions:
    #     return tx_index 
    
    if tx_hex is None:
        tx_hex = backend.getrawtransaction(tx_hash) # TODO: This is the call that is stalling the process the most
        
    transaction_info = get_tx_info(tx_hex, db=db, stamp_issuance=stamp_issuance)
    source = getattr(transaction_info, 'source', None)
    destination = getattr(transaction_info, 'destinations', None)
    btc_amount = getattr(transaction_info, 'btc_amount', None)
    fee = getattr(transaction_info, 'fee', None)
    data = getattr(transaction_info, 'data', None)
    decoded_tx = getattr(transaction_info, 'ctx', None)
    keyburn = getattr(transaction_info, 'keyburn', None)
    is_op_return = getattr(transaction_info, 'is_op_return', None)

    assert block_index == util.CURRENT_BLOCK_INDEX

    if stamp_issuance is not None:
        source = str(stamp_issuance['source'])
        destination = str(stamp_issuance['issuer'])
        data = str(stamp_issuance)

    if source and (data or destination):
        logger.info('Saving to MySQL transactions: {}\nDATA:{}\nKEYBURN: {}\nOP_RETURN: {}'.format(tx_hash, data, keyburn, is_op_return))

        # tx_index = insert_transaction(db, tx_index, tx_hash, block_index, block_hash, 
                            # block_time, source, destination, btc_amount, fee, data, keyburn)
        return source, destination, btc_amount, fee, data, decoded_tx, keyburn, is_op_return

    else:
        logger.getChild('list_tx.skip').debug('Skipping transaction: {}'.format(tx_hash))
        return  (None for _ in range(8))


def last_db_index(db):
    """
    Retrieve the last block index from the database.

    Args:
        db: The database connection object.

    Returns:
        The last block index as an integer.
    """
    field_position = config.BLOCK_FIELDS_POSITION
    cursor = db.cursor()

    try:
        cursor.execute('''SELECT * FROM blocks WHERE block_index = (SELECT MAX(block_index) from blocks)''')
        blocks = cursor.fetchall()
        try:
            last_index = blocks[0][field_position['block_index']]
        except IndexError:
            last_index = 0
    except  mysql.Error:
        last_index = 0
    finally:
        cursor.close()
    return last_index


def next_tx_index(db):
    """
    Return the index of the next incremental transaction # from transactions table.

    Parameters:
    db (object): The database object.

    Returns:
    int: The index of the next transaction.
    """
    cursor = db.cursor()

    cursor.execute('''SELECT tx_index FROM transactions WHERE tx_index = (SELECT MAX(tx_index) from transactions)''')
    txes = cursor.fetchall()
    if txes:
        assert len(txes) == 1
        tx_index = txes[0][0] + 1
    else:
        tx_index = 0

    cursor.close()

    return tx_index


def insert_block(db, block_index, block_hash, block_time, previous_block_hash, difficulty):
    """
    Insert a new block into the database, does not commit

    Args:
        db (object): The database connection object.
        block_index (int): The index of the block.
        block_hash (str): The hash of the block.
        block_time (int): The timestamp of the block.
        previous_block_hash (str): The hash of the previous block.
        difficulty (float): The difficulty of the block.

    Returns:
        None
    """
    cursor = db.cursor()
    logger.info('Inserting MySQL Block: {}'.format(block_index))
    block_query = '''INSERT INTO blocks(
                        block_index,
                        block_hash,
                        block_time,
                        previous_block_hash,
                        difficulty
                        ) VALUES(%s,%s,FROM_UNIXTIME(%s),%s,%s)'''
    args = (block_index, block_hash, block_time, previous_block_hash, float(difficulty))

    try:
        cursor.execute(block_query, args)
        cursor.close()
    except mysql.IntegrityError:
        print(f"block {block_index} already exists in mysql") # TODO: this may be ok if we are doing a reparse
        sys.exit()
    except Exception as e:
        print("Error executing query:", block_query)
        print("Arguments:", args)
        print("Error message:", e)
        sys.exit()


def update_block_hashes(db, block_index, txlist_hash, ledger_hash, messages_hash):
    """
    Update the hashes of a block in the MySQL database. This is for comparison across nodes. 
    So we can validate that each node has the same data.

    Args:
        db (MySQLConnection): The MySQL database connection.
        block_index (int): The index of the block to update.
        txlist_hash (str): The new transaction list hash.
        ledger_hash (str): The new ledger hash.
        messages_hash (str): The new messages hash.
    Returns:
        None
    """
    cursor = db.cursor()
    logger.info('Updating MySQL Block: {}'.format(block_index))
    block_query = '''UPDATE blocks SET
                        txlist_hash = %s,
                        ledger_hash = %s,
                        messages_hash = %s
                        WHERE block_index = %s'''

    args = (txlist_hash, ledger_hash, messages_hash, block_index)

    try:
        cursor.execute(block_query, args)
        cursor.close() 
    except Exception as e:
        print("Error executing query:", block_query)
        print("Arguments:", args)
        print("Error message:", e)
        sys.exit()


def create_check_hashes(db, block_index, valid_stamps_in_block, valid_src20_in_block, txhash_list,
                        previous_ledger_hash=None, previous_txlist_hash=None, previous_messages_hash=None):
    """
    Calculate and update the hashes for the given block data. This needs to be modified for a reparse.

    Args:
        db (Database): The database object.
        block_index (int): The index of the block.
        valid_stamps_in_block (list): The list of processed transactions in the block.
        valid_src20_in_block (list): The list of valid SRC20 tokens in the block.
        txhash_list (list): The list of transaction hashes in the block.
        previous_ledger_hash (str, optional): The hash of the previous ledger. Defaults to None.
        previous_txlist_hash (str, optional): The hash of the previous transaction list. Defaults to None.
        previous_messages_hash (str, optional): The hash of the previous messages. Defaults to None.

    Returns:
        tuple: A tuple containing the new transaction list hash, ledger hash, and messages hash.
    """
    txlist_content = str(valid_stamps_in_block)
    new_txlist_hash, found_txlist_hash = check.consensus_hash(db, 'txlist_hash', previous_txlist_hash, txlist_content) 
            
    ledger_content = str(valid_src20_in_block)
    new_ledger_hash, found_ledger_hash = check.consensus_hash(db, 'ledger_hash', previous_ledger_hash, ledger_content)
    
    messages_content = str(txhash_list)
    new_messages_hash, found_messages_hash = check.consensus_hash(db, 'messages_hash', previous_messages_hash, messages_content)
    
    update_block_hashes(db, block_index, new_txlist_hash, new_ledger_hash, new_messages_hash)
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


def log_block_info(block_index, start_time, new_ledger_hash, new_txlist_hash, new_messages_hash):
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
    logger.warning('Block: %s (%ss, hashes: L:%s / TX:%s / M:%s)' % (
        str(block_index), "{:.2f}".format(time.time() - start_time, 3),
        new_ledger_hash[-5:] if new_ledger_hash else 'N/A',
        new_txlist_hash[-5:], new_messages_hash[-5:]
    ))
    

def validate_src20_ledger_hash(block_index, ledger_hash, valid_src20_str):
    """
    Validates the SRC20 ledger hash for a given block index against remote API
    This is currently for OKX and will be to validate against stampscan.xyz as well

    Args:
        block_index (int): The index of the block.
        ledger_hash (str): The expected ledger hash.
        valid_src20_str (str): The valid SRC20 string.

    Returns:
        bool: True if the API ledger hash matches the ledger hash, False otherwise.

    Raises:
        ValueError: If the API ledger hash does not match the ledger hash.
        Exception: If failed to retrieve from the API after retries.
    """
    url = config.SRC_VALIDATION_API1 + str(block_index)
    max_retries = 10
    retry_count = 0

    while retry_count < max_retries:
        try:
            response = requests.get(url)
            if response.status_code == 200:
                api_ledger_hash = response.json()['data']['hash']
                if api_ledger_hash == ledger_hash:
                    return True
                else:
                    api_ledger_validation = response.json()['data']['balance_data']
                    if api_ledger_validation != valid_src20_str:
                        logger.warning("API ledger validation does not match ledger validation for block %s", block_index)
                        logger.warning("API ledger validation: %s", api_ledger_validation)
                        logger.warning("Ledger validation: %s", valid_src20_str)
                        mismatches = []
                        for api_entry, ledger_entry in zip(api_ledger_validation, valid_src20_str):
                            if api_entry != ledger_entry:
                                mismatches.append((api_entry, ledger_entry))
                        for mismatch in mismatches:
                            logger.warning("Mismatch found:")
                            logger.warning("API Ledger: %s", mismatch[0])
                            logger.warning("Ledger: %s", mismatch[1])
                        if not mismatches:
                            logger.warning("The strings match perfectly.")
                        else:
                            logger.warning("Total mismatches: %s", len(mismatches))
                    raise ValueError('API ledger hash does not match ledger hash')
            else:
                retry_count += 1
                time.sleep(1)
        except requests.exceptions.RequestException as e:
            retry_count += 1
            time.sleep(1)
    raise Exception(f'Failed to retrieve from the API after {max_retries} retries')


def process_balance_updates(balance_updates):
    """
    Process the balance updates and return a string representation of valid src20 entries.

    Args:
        balance_updates (list): A list of balance updates.

    Returns:
        str: A string representation of valid src20 entries.
    """

    valid_src20_list = []
    if balance_updates is not None:
        for src20 in balance_updates:
            creator = src20.get('address')
            if '\\' in src20['tick']:
                tick = src20['tick'].replace('\\u', '\\U')
                if len(tick) - 2 < 8:  # Adjusting for the length of '\\U'
                    tick = '\\U' + '0' * (10 - len(tick)) + tick[2:]
                tick = bytes(tick, "utf-8").decode("unicode_escape")
            else:
                tick = src20.get('tick')
            amt = src20.get('net_change') + src20.get('original_amt')
            amt = D(amt).normalize()
            if amt == int(amt):
                amt = int(amt)
            valid_src20_list.append(f"{tick},{creator},{amt}")
    valid_src20_list = sorted(valid_src20_list, key=lambda src20: (src20.split(',')[0] + '_' + src20.split(',')[1]))
    valid_src20_str = ';'.join(valid_src20_list)
    return valid_src20_str


def process_tx(db, tx_hash, block_index, stamp_issuances, raw_transactions):
    stamp_issuance = filter_issuances_by_tx_hash(stamp_issuances, tx_hash)
    
    tx_hex = raw_transactions[tx_hash]
    (
        source,
        destination,
        btc_amount,
        fee,
        data,
        decoded_tx,
        keyburn,
        is_op_return
    ) = list_tx(
        db,
        block_index,
        tx_hash,
        tx_hex,
        stamp_issuance=stamp_issuance
    )

    return TxResult(None, source, destination, btc_amount, fee, data, decoded_tx, keyburn, is_op_return, tx_hash, block_index, None, None)


def follow(db): 
    """
    Continuously follows the blockchain, parsing and indexing new blocks
    for src-20 transactions and to gather details about CP trx such as
    keyburn status. 

    Args:
        db: The database connection object.

    Returns:
        None
    """
    
    # Check software version.
    # check.software_version()
    check.cp_version() #FIXME: need to add version checks for the endpoints and hash validations
    initialize(db)
    rebuild_balances(db)

    # Get index of last block.
    if util.CURRENT_BLOCK_INDEX == 0:
        logger.warning('New database.')
        block_index = config.BLOCK_FIRST
    else:
        block_index = util.CURRENT_BLOCK_INDEX + 1

    logger.info('Resuming parsing.')
    tx_index = next_tx_index(db)

    # a reorg can happen without the block count increasing, or even for that
    # matter, with the block count decreasing. This should only delay
    # processing of the new blocks a bit.
    try:
        block_tip = backend.getblockcount()
    except (ConnectionRefusedError, http.client.CannotSendRequest, backend.BackendRPCError) as e:
        if config.FORCE:
            time.sleep(config.BACKEND_POLL_INTERVAL)
        else:
            raise e

    stamp_issuances_list = None
    # profiler = cProfile.Profile()
    # profiler.enable()

    while True:
        start_time = time.time()

        try:
            # for local nodes ad zmq here
            block_tip = backend.getblockcount()
        except (ConnectionRefusedError, http.client.CannotSendRequest, backend.BackendRPCError) as e:
            if config.FORCE:
                time.sleep(config.BACKEND_POLL_INTERVAL)
                continue
            else:
                raise e
        #  check if last block index was full indexed and if not delete it
        #  and set block_index to block_index - 1
        if (block_index != config.BLOCK_FIRST and
                not is_prev_block_parsed(db, block_index)):
            block_index -= 1

        if block_index <= block_tip:

            db.ping()  # check db connection and reinitialize if needed

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
                    logger.info(
                        f'Checking that block {block_index} is not orphan.'
                    )
                    # Backend parent hash.
                    current_hash = backend.getblockhash(block_index)
                    current_cblock = backend.getcblock(current_hash)
                    backend_parent = bitcoinlib.core.b2lx(
                        current_cblock.hashPrevBlock
                    )
                    cursor = db.cursor()
                    block_query = '''
                    SELECT * FROM blocks WHERE block_index = %s
                    '''
                    cursor.execute(block_query, (block_index - 1,))
                    blocks = cursor.fetchall()
                    columns = [desc[0] for desc in cursor.description]
                    cursor.close()
                    blocks_dict = [dict(zip(columns, row)) for row in blocks]
                    if len(blocks_dict) != 1:  # For empty DB.
                        break
                    db_parent = blocks_dict[0]['block_hash']

                    # Compare.
                    assert type(db_parent) is str
                    assert type(backend_parent) is str
                    if db_parent == backend_parent:
                        break
                    else:
                        block_index -= 1
                        requires_rollback = True

                # Rollback for reorganization.
                if requires_rollback:
                    # Record reorganization.
                    logger.warning(
                        'Blockchain reorganization at block {}.'
                        .format(block_index)
                    )
                    block_index -= 1
                    logger.warning(
                        'Rolling back to block {} to avoid problems.'
                        .format(block_index)
                    )
                    # Rollback.
                    purge_block_db(db, block_index)
                    rebuild_balances(db)
                    requires_rollback = False
                    stamp_issuances_list = None
                    continue

            # check.software_version() #FIXME: We may want to validate MySQL version here.
            block_hash = backend.getblockhash(block_index)
            cblock = backend.getcblock(block_hash)
            previous_block_hash = bitcoinlib.core.b2lx(cblock.hashPrevBlock)
            block_time = cblock.nTime
            txhash_list, raw_transactions = backend.get_tx_list(cblock)
            util.CURRENT_BLOCK_INDEX = block_index

            insert_block(db, block_index, block_hash, block_time, previous_block_hash, cblock.difficulty)
        
            valid_stamps_in_block= []
            valid_src20_in_block = []
            
            if not stamp_issuances_list[block_index] and block_index < config.CP_SRC20_BLOCK_START: # this could be moved to the first non cp src20 block
                valid_src20_str = ''
                new_ledger_hash, new_txlist_hash, new_messages_hash = create_check_hashes(
                        db,
                        block_index,
                        valid_stamps_in_block,
                        valid_src20_str,
                        txhash_list
                    )

                stamp_issuances_list.pop(block_index, None)
                log_block_info(block_index, start_time, new_ledger_hash, new_txlist_hash, new_messages_hash)
                block_index = commit_and_update_block(db, block_index)
                continue

            tx_results = []

            # with concurrent.futures.ThreadPoolExecutor() as executor:
            #     futures = [executor.submit(process_tx, db, tx_hash, block_index, stamp_issuances, raw_transactions) for tx_hash in txhash_list]

            #     for future in concurrent.futures.as_completed(futures):
            #         result = future.result()
            #         if result.data is not None:
            #             result = result._replace(tx_index=tx_index, block_index=block_index, block_hash=block_hash, block_time=block_time)
            #             tx_results.append(result)

            #     tx_results = sorted(tx_results, key=lambda x: txhash_list.index(x.tx_hash))

            #     for result in tx_results:
            #         result = result._replace(tx_index=tx_index)
            #         tx_index = tx_index + 1



            for tx_hash in txhash_list:
                result = process_tx(db, tx_hash, block_index, stamp_issuances, raw_transactions)
                if result.data is not None:
                    result = result._replace(tx_index=tx_index, block_index=block_index, block_hash=block_hash, block_time=block_time)
                    tx_results.append(result)
                    tx_index = tx_index + 1

            # tx_results = sorted(tx_results, key=lambda x: txhash_list.index(x.tx_hash))

            # for result in tx_results:
            #     result = result._replace(tx_index=tx_index)
            #     tx_index = tx_index + 1


        
            insert_transactions(db, tx_results)

            for result in tx_results:
                parse_tx_to_stamp_table(
                    db,
                    result.tx_hash,
                    result.source,
                    result.destination,
                    result.btc_amount,
                    result.fee,
                    result.data,
                    result.decoded_tx,
                    result.keyburn,
                    result.tx_index,
                    result.block_index,
                    result.block_time,
                    result.is_op_return,
                    valid_stamps_in_block,
                    valid_src20_in_block
                )
            if valid_src20_in_block:
                balance_updates = update_src20_balances(db, block_index, block_time, valid_src20_in_block)
                insert_into_src20_tables(db, valid_src20_in_block)
                valid_src20_str = process_balance_updates(balance_updates)
            else:
                valid_src20_str = ''

            new_ledger_hash, new_txlist_hash, new_messages_hash = create_check_hashes(
                db,
                block_index,
                valid_stamps_in_block,
                valid_src20_str,
                txhash_list
            )

            if valid_src20_str:
                validate_src20_ledger_hash(block_index, new_ledger_hash, valid_src20_str)

            stamp_issuances_list.pop(block_index, None)
            log_block_info(block_index, start_time, new_ledger_hash, new_txlist_hash, new_messages_hash)
            block_index = commit_and_update_block(db, block_index)

            # profiler.disable()
            # profiler.dump_stats("profile_results.prof")
            # sys.exit()