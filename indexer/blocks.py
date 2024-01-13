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

import config
import src.exceptions as exceptions
import src.util as util
import check
import src.script as script
import src.backend as backend
import src.arc4 as arc4
import src.log as log
from xcprequest import get_xcp_block_data, filter_issuances_by_tx_hash
from stamp import (
    is_prev_block_parsed,
    purge_block_db,
    parse_tx_to_stamp_table,
    update_parsed_block,
    rebuild_balances
)

from send import (
    parse_issuance_to_send_table,
    insert_into_sends_table,
    insert_into_dispenser_table,
)

from src20 import (
    update_src20_balances,
)

from src.exceptions import DecodeError, BTCOnlyError

D = decimal.Decimal
logger = logging.getLogger(__name__)
log.set_logger(logger)  


def initialize(db):
    """initialize data, create and populate the database."""
    cursor = db.cursor() 

    # Check if the block_index_idx index exists
    cursor.execute('''
        SHOW INDEX FROM blocks WHERE Key_name = 'block_index_idx'
    ''')
    result = cursor.fetchone()

    # Create the block_index_idx index if it does not exist
    if not result:
        cursor.execute('''
            CREATE INDEX block_index_idx ON blocks (block_index)
        ''')

    # Check if the index_hash_idx index exists
    cursor.execute('''
        SHOW INDEX FROM blocks WHERE Key_name = 'index_hash_idx'
    ''')
    result = cursor.fetchone()

    # Create the index_hash_idx index if it does not exist
    if not result:
        cursor.execute('''
            CREATE INDEX index_hash_idx ON blocks (block_index, block_hash)
        ''')

    # mysql_cursor.execute('''
    #     SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'blocks'
    # ''')
    # column_names = [row[0] for row in mysql_cursor.fetchall()]

    cursor.execute('''
        SELECT MIN(block_index)
        FROM blocks
    ''')
    block_index = cursor.fetchone()[0]

    if block_index is not None and block_index != config.BLOCK_FIRST:
        raise exceptions.DatabaseError('First block in database is not block {}.'.format(config.BLOCK_FIRST))

    # Check if the block_index_idx index exists
    cursor.execute('''
        SHOW INDEX FROM transactions WHERE Key_name = 'block_index_idx'
    ''')
    result = cursor.fetchone()

    # Create the block_index_idx index if it does not exist
    if not result:
        cursor.execute(
            '''CREATE INDEX block_index_idx ON transactions (block_index)'''
        )

    # Check if the tx_index_idx index exists
    cursor.execute('''
        SHOW INDEX FROM transactions WHERE Key_name = 'tx_index_idx'
    ''')
    result = cursor.fetchone()

    # Create the tx_index_idx index if it does not exist
    if not result:
        cursor.execute(
            '''CREATE INDEX tx_index_idx ON transactions (tx_index)'''
        )

    # Check if the tx_hash_idx index exists
    cursor.execute('''
        SHOW INDEX FROM transactions WHERE Key_name = 'tx_hash_idx'
    ''')
    result = cursor.fetchone()

    # Create the tx_hash_idx index if it does not exist
    if not result:
        cursor.execute(
            '''CREATE INDEX tx_hash_idx ON transactions (tx_hash)'''
        )

    # Check if the index_index_idx index exists
    cursor.execute('''
        SHOW INDEX FROM transactions WHERE Key_name = 'index_index_idx'
    ''')
    result = cursor.fetchone()

    # Create the index_index_idx index if it does not exist
    if not result:
        cursor.execute(
            '''CREATE INDEX index_index_idx ON transactions (block_index, tx_index)'''
        )

    # Check if the index_hash_index_idx index exists
    cursor.execute('''
        SHOW INDEX FROM transactions WHERE Key_name = 'index_hash_index_idx'
    ''')
    result = cursor.fetchone()

    # Create the index_hash_index_idx index if it does not exist
    if not result:
        cursor.execute(
            '''CREATE INDEX index_hash_index_idx ON transactions (tx_index, tx_hash, block_index)'''
        )

    cursor.execute(
        '''DELETE FROM blocks WHERE block_index < {}'''
        .format(config.BLOCK_FIRST)
    )

    cursor.execute(
        '''DELETE FROM transactions WHERE block_index < {}'''
        .format(config.BLOCK_FIRST)
    )

    cursor.close()


def process_vout(ctx, fee):
    pubkeys_compiled = []
    keyburn = None
    is_op_return = None

    # Ignore coinbase transactions.
    if ctx.is_coinbase():
        raise DecodeError('coinbase transaction')

    for vout in ctx.vout:
        # asm is the bytestring of the vout values
        # Fee is the input values minus output values.
        output_value = vout.nValue
        fee -= output_value
        # Ignore transactions with invalid script.
        try:
            asm = script.get_asm(vout.scriptPubKey)
        except CScriptInvalidError as e:
            raise DecodeError(e)
        if asm[-1] == 'OP_CHECKMULTISIG': # the last element in the asm list is OP_CHECKMULTISIG
            try:
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
            pass

    return pubkeys_compiled, keyburn, is_op_return, fee


def get_tx_info(tx_hex, block_index=None, db=None, stamp_issuance=None):
    """Get transaction information.
    The destinations, if they exist, always come before the data output, and the change, if it exists, always comes after.
    Include keyburn check on all transactions, not just src-20.
    This function parses every transaction, not just stamps/src-20.
    Returns normalized None data for DecodeError and BTCOnlyError.
    """
    try:
        if not block_index:
            block_index = util.CURRENT_BLOCK_INDEX
        
        destinations, btc_amount, fee, data, keyburn, is_op_return = [], 0, 0, b'', None, None

        ctx = backend.deserialize(tx_hex)
        pubkeys_compiled, keyburn, is_op_return, fee = process_vout(ctx, fee)
        
        if stamp_issuance is not None:
            # NOTE: rounding fee because of table data type need more precision? 
            return None, None, btc_amount, round(fee), None, None, keyburn, is_op_return

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

        return str(source), destinations, btc_amount, round(fee), data, ctx, keyburn, is_op_return

    except DecodeError as e:
        return b'', None, None, None, None, None, None, None
    except BTCOnlyError as e:
        return b'', None, None, None, None, None, None, None


def decode_address(script_pubkey):
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
            

def insert_sends_dispensers(db, block_hash, block_index, block_time, tx_index, stamp_sends=None, stamp_dispensers=None):
    """Inserts all sends and dispensers into the sends, dispenser and transaction database.
        NOTE: this inserts them all at the end of the transactions table so they will be out of sequence in the block  """
    try:
        if stamp_sends: # NOTE: not sure hos multiple destinations are handled here
            for stamp_send in stamp_sends:
                tx_index = insert_transaction(db, tx_index, stamp_send['tx_hash'], block_index,
                                              block_hash, block_time, stamp_send['source'], 
                                              stamp_send['destination'], None, None, str(stamp_send), None)
                parsed_send = {
                            'from': stamp_send.get('source'),
                            'to': stamp_send.get('destination'),
                            'cpid': stamp_send.get('cpid', None),
                            'tick': stamp_send.get('tick', None),
                            'memo': stamp_send.get('memo', "send"),
                            'quantity': stamp_send.get('quantity'),
                            'satoshirate': stamp_send.get('satoshirate', None),
                            'tx_hash': stamp_send.get('tx_hash'),
                            'tx_index': tx_index,
                            'block_index': stamp_send.get('block_index'),
                        }
                sends_cursor = db.cursor()
                insert_into_sends_table(
                    cursor=sends_cursor,
                    send=parsed_send
                )
                sends_cursor.close()
                
        if stamp_dispensers:
            for stamp_dispenser in stamp_dispensers:
                tx_index = insert_transaction(db, tx_index, stamp_dispenser['tx_hash'], block_index,
                                               block_hash, block_time, stamp_dispenser['source'], 
                                               None, None, None, str(stamp_send), None)

                stamp_dispenser['tx_index'] = tx_index
                dispenser_cursor = db.cursor()
                insert_into_dispenser_table(dispenser_cursor, stamp_dispenser)
                dispenser_cursor.close()
        return tx_index
    except Exception as e:
        raise e


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

    # Reparse from the undolog if possible
    # reparsed = reparse_from_undolog(db, block_index, quiet) - this would never be possible for stamps anyhow :)
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


def insert_transaction(db, tx_index, tx_hash, block_index, block_hash, block_time, source, destination, btc_amount, fee, data, keyburn):
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
        raise Exception(f"Error occurred while inserting transaction: {e}")
    finally:
        return tx_index + 1


def list_tx(db, block_hash, block_index, block_time, tx_hash, tx_index, tx_hex=None, stamp_issuance=None):
    assert type(tx_hash) is str
    # NOTE: removing this since the insert into tx table would fail if they already exists. may need to revise with reparsing.
    # cursor = db.cursor()
    # # check if the incoming tx_hash from txhash_list is already in the trx table
    # cursor.execute('''SELECT * FROM transactions WHERE tx_hash = %s''', (tx_hash,)) # this will include all CP transactinos as well ofc
    # transactions = cursor.fetchall()
    # cursor.close()
    # if transactions:
    #     # FIXME: for reparse this will be an issue since sends can create duplicate tx_hash
    #     # for now this is ok because this will alwasy return None w/o reparse option
    #     return tx_index 
    
    if tx_hex is None:
        tx_hex = backend.getrawtransaction(tx_hash) # TODO: This is the call that is stalling the process the most
    (
        source,
        destination,
        btc_amount,
        fee,
        data,
        decoded_tx,
        keyburn,
        is_op_return
    ) = get_tx_info(tx_hex, db=db, stamp_issuance=stamp_issuance) # this currently only gets source, dest for SRC-20

    assert block_index == util.CURRENT_BLOCK_INDEX

    if stamp_issuance is not None:
        source = str(stamp_issuance['source'])
        destination = str(stamp_issuance['issuer'])
        data = str(stamp_issuance)

    if source and (data or destination): # this is an src-20 trx
        logger.info('Saving to MySQL transactions: {}\nDATA:{}\nKEYBURN: {}\nOP_RETURN: {}'.format(tx_hash, data, keyburn, is_op_return))

        tx_index = insert_transaction(db, tx_index, tx_hash, block_index, block_hash, 
                            block_time, source, destination, btc_amount, fee, data, keyburn)
        return tx_index, source, destination, btc_amount, fee, data, decoded_tx, keyburn, is_op_return

    else:
        logger.getChild('list_tx.skip').debug('Skipping transaction: {}'.format(tx_hash))
        return tx_index, None, None, None, None, None, None, None, None


def last_db_index(db):
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


def get_next_tx_index(db):
    """Return index of next transaction."""
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


def purge_old_block_tx_db(db, block_index):
    """purge old transactions which are not related to stamps from the database."""
    if config.BLOCKS_TO_KEEP == 0:
        return
    cursor = db.cursor()
    db.ping(reconnect=True)
    last_block_to_keep = block_index - config.BLOCKS_TO_KEEP
    cursor.execute('''
                   DELETE FROM transactions
                   WHERE block_index < %s
                   AND data IS NULL
                   ''', (last_block_to_keep,))
    cursor.close()


def follow(db): 
    # Check software version.
    # check.software_version()
    check.cp_version()

    # initialize.
    initialize(db)

    # Get index of last block.
    if util.CURRENT_BLOCK_INDEX == 0:
        logger.warning('New database.')
        block_index = config.BLOCK_FIRST
    else:
        block_index = util.CURRENT_BLOCK_INDEX + 1

    logger.info('Resuming parsing.')
    # Get index of last transaction.
    tx_index = get_next_tx_index(db)


    # a reorg can happen without the block count increasing, or even for that
    # matter, with the block count decreasing. This should only delay
    # processing of the new blocks a bit.
    while True:
        start_time = time.time()
        # Get block count.
        # If the backend is unreachable and `config.FORCE` is set, just sleep
        # and try again repeatedly.
        try:
            block_count = backend.getblockcount()
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

        # Get new blocks.
        if block_index <= block_count:

            purge_old_block_tx_db(db, block_index)
            current_index = block_index

            stamp_issuances, stamp_sends, stamp_dispensers = get_xcp_block_data(block_index, db)

            if block_count - block_index < 100:
                requires_rollback = False
                while True:
                    if current_index == config.BLOCK_FIRST:
                        break
                    logger.info(
                        f'Checking that block {current_index} is not orphan.'
                    )
                    # Backend parent hash.
                    current_hash = backend.getblockhash(current_index)
                    current_cblock = backend.getcblock(current_hash)
                    backend_parent = bitcoinlib.core.b2lx(
                        current_cblock.hashPrevBlock
                    )
                    cursor = db.cursor()
                    block_query = '''
                    SELECT * FROM blocks WHERE block_index = %s
                    '''
                    cursor.execute(block_query, (current_index - 1,))
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
                        current_index -= 1
                        requires_rollback = True

                # Rollback for reorganization.
                if requires_rollback:
                    # Record reorganization.
                    logger.warning(
                        'Blockchain reorganization at block {}.'
                        .format(current_index)
                    )
                    current_index -= 1
                    logger.warning(
                        'Rolling back to block {} to avoid problems.'
                        .format(current_index)
                    )
                    # Rollback.
                    purge_block_db(db, current_index)
                    rebuild_balances(db)
                    requires_rollback = False
                    continue

            # check.software_version() #FIXME: We may want to validate MySQL version here.
            block_hash = backend.getblockhash(current_index)
            cblock = backend.getcblock(block_hash)
            previous_block_hash = bitcoinlib.core.b2lx(cblock.hashPrevBlock)
            block_time = cblock.nTime
            txhash_list, raw_transactions = backend.get_tx_list(cblock)
            block_cursor = db.cursor()
            util.CURRENT_BLOCK_INDEX = block_index

            logger.warning('Inserting MySQL Block: {}'.format(block_index))
            # new_ledger_hash, new_txlist_hash, new_messages_hash, found_messages_hash = parse_block(db, block_index, txhash_list) #txhash_list will be all btc trx in the block
            block_query = '''INSERT INTO blocks(
                                block_index,
                                block_hash,
                                block_time,
                                previous_block_hash,
                                difficulty
                                ) VALUES(%s,%s,FROM_UNIXTIME(%s),%s,%s)'''
            args = (block_index, block_hash, block_time, previous_block_hash, float(cblock.difficulty))

            try:
                block_cursor.execute(block_query, args)
            except mysql.IntegrityError:
                print(f"block {block_index} already exists in mysql") # TODO: this may be ok if we are doing a reparse
                sys.exit()
            except Exception as e:
                print("Error executing query:", block_query)
                print("Arguments:", args)
                print("Error message:", e)
                sys.exit()

            processed_in_block= []
            valid_src20_in_block = []

            for tx_hash in txhash_list:
                stamp_issuance = filter_issuances_by_tx_hash(
                    stamp_issuances, tx_hash
                )

                tx_hex = raw_transactions[tx_hash]
                (
                    tx_index,
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
                    block_hash,
                    block_index,
                    block_time,
                    tx_hash,
                    tx_index,
                    tx_hex,
                    stamp_issuance=stamp_issuance
                )
                # commits when the block is complete
                # parsing all trx in the block
                parse_tx_to_stamp_table(
                    db,
                    tx_hash,
                    source,
                    destination,
                    btc_amount,
                    fee,
                    data,
                    decoded_tx,
                    keyburn,
                    tx_index,
                    block_index,
                    block_time,
                    is_op_return,
                    processed_in_block,
                    valid_src20_in_block
                )
                if (stamp_issuance is not None):
                    parse_issuance_to_send_table(
                        db=db,
                        cursor=block_cursor,
                        issuance=stamp_issuance,
                        tx={
                            "tx_index": tx_index,
                            "block_index": block_index
                        }
                    )
  
            if valid_src20_in_block:
                update_src20_balances(db, block_index, block_time, valid_src20_in_block)

            previous_ledger_hash, previous_txlist_hash, previous_messages_hash = None, None, None

            txlist_content = str(valid_src20_in_block + processed_in_block)
            new_txlist_hash, found_txlist_hash = check.consensus_hash(db, 'txlist_hash', previous_txlist_hash, txlist_content) 
            
            ledger_content = str(stamp_sends + stamp_dispensers)
            new_ledger_hash, found_ledger_hash = check.consensus_hash(db, 'ledger_hash', previous_ledger_hash, ledger_content)
                
            # message hash for future use
            # new_messages_hash, found_messages_hash = None, None
            #  new_messages_hash, found_messages_hash = check.consensus_hash(db, 'messages_hash', previous_messages_hash, util.BLOCK_MESSAGES)

            if stamp_sends is not None or stamp_dispensers is not None:
                tx_index = insert_sends_dispensers(db, block_hash, block_index, block_time, tx_index, stamp_sends=stamp_sends, stamp_dispensers=stamp_dispensers)

            try:
                db.commit()
                update_parsed_block(db, block_index)
            except Exception as e:
                print("Error message:", e)
                db.rollback()
                db.close()
                sys.exit()

            logger.warning('Block: %s (%ss, hashes: L:%s / TX:%s)' % (
                str(block_index), "{:.2f}".format(time.time() - start_time, 3),
                new_ledger_hash[-5:], new_txlist_hash[-5:],))#new_messages_hash[-5:],
                # (' [overwrote %s]' % found_messages_hash) if found_messages_hash and found_messages_hash != new_messages_hash else ''))
            block_index += 1
