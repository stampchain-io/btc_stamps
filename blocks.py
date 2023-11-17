"""
Initialise database.

Sieve blockchain for Stamp transactions, and add them to the database.
"""

import sys
import time
import binascii
import struct
import decimal
import logging
import collections
import http
import bitcoin as bitcoinlib
from bitcoin.core.script import CScriptInvalidError
from bitcoin.core import CBlock
from bitcoin.wallet import CBitcoinAddress
import pymysql as mysql


import config
import src.exceptions as exceptions
import src.util as util
import check
import src.script as script
import src.backend as backend
import src.database as database
import src.arc4 as arc4
from xcprequest import (
    get_issuances_by_block,
    get_stamp_issuances,
    filter_issuances_by_tx_hash
)
from stamp import (
    update_stamp_table,
    is_prev_block_parsed,
    purge_block_db,
    check_burnkeys_in_multisig,
)


from src.exceptions import DecodeError, BTCOnlyError
import kickstart.utils as utils

D = decimal.Decimal
logger = logging.getLogger(__name__)
# CHANGED TO MYSQL


def parse_tx(db, tx):
    """Parse the transaction, return True for success."""
    cursor = db.cursor()
    try:
        with db:
            # Only one source and one destination allowed for now.

            # COMMENTING THESE TO ADD ALL INTO TRANSACTIONS TABLE
            # if len(tx['source'].split('-')) > 1:
            #     return
            # if tx['destination']:
            #     if len(tx['destination'].split('-')) > 1:
            #         return

            # return True
            if tx['data'] is not None:
                try:
                    print(tx['data']) # DEBUG
                    # TODO: check json string for src-20 transactions and populate StampTableVx directly
                    # need to check for compressed data here if we are dropping into srcx directly
                    print("we found a stamp transaction here in parse_tx")
                    # import data into the srcx mysql table based upon the names of the json keys
                    # print(tx['data'])
                    # mysql_cursor.execute
                    # tx_hash
                    # tx_index
                    # amt
                    # block_index
                    # c
                    # creator
                    # deci
                    # lim
                    # max
                    # op
                    # p
                    # stamp
                    # stamp_url
                    # tick
                    # ts
                    # stamp_gen

                    # message_type_id, message = message_type.unpack(tx['data'], tx['block_index'])
                except struct.error:    # Deterministically raised.
                    message_type_id = None
                    message = None
            else:
                message_type_id = None
                message = None

            return True
        
            # WRITE INTO THE STAMP TABLE HERE WITH THE IMG URL DECODING and Images string

            # parse the srcx json array and save into the db
            # item = {
            #     'tx_hash': tx_hash,
            #     'creator': creator,
            #     'tx_index': tx_index,
            #     'block_index': block_index,
            #     'constant': 1,
            #     'stamp': stamp,
            #     'stamp_url': stamp_url
            # }

            # Protocol change.
            rps_enabled = tx['block_index'] >= 308500 or config.TESTNET or config.REGTEST

            if message_type_id == send.ID:
                send.parse(db, tx, message)
            elif message_type_id == enhanced_send.ID and util.enabled('enhanced_sends', block_index=tx['block_index']):
                enhanced_send.parse(db, tx, message)

            else:
                cursor.execute('''UPDATE transactions \
                                           SET supported=? \
                                           WHERE tx_hash=?''',
                                        (False, tx['tx_hash']))
                if tx['block_index'] != config.MEMPOOL_BLOCK_INDEX:
                    logger.info('Unsupported transaction: hash {}; data {}'.format(tx['tx_hash'], tx['data']))
                cursor.close()
                return False

            # NOTE: for debugging (check asset conservation after every `N` transactions).
            # if not tx['tx_index'] % N:
            #     check.asset_conservation(db)

            return True

    # REMOVING THIS TO WRITE ALL TRX INTO TRANSACTIONS EVEN WHEN THEY DON"T DECODE    
    # except Exception as e:
    #     print('got tx herror ')
    #     raise exceptions.ParseTransactionError("%s" % e)
    finally:
        cursor.close()


def parse_block(db, block_index, block_time,
                previous_ledger_hash=None, ledger_hash=None,
                previous_txlist_hash=None, txlist_hash=None,
                previous_messages_hash=None):
    """Parse the block, return hash of new ledger, txlist and messages.
    The unused arguments `ledger_hash` and `txlist_hash` are for the test suite.
    """

    util.BLOCK_LEDGER = []
    database.BLOCK_MESSAGES = []
    assert block_index == util.CURRENT_BLOCK_INDEX

    cursor = db.cursor()
    db.ping(reconnect=True)
    cursor.execute('''SELECT * FROM transactions \
                      WHERE block_index=%s ORDER BY tx_index''',
                   (block_index,))
    txes = cursor.fetchall()
    logger.warning("TX LENGTH FOR BLOCK {} BEFORE PARSING: {}".format(block_index,len(txes)))
    time.sleep(2)
    txlist = []
    for tx in txes:
        # print("tx", tx) # DEBUG
        try:
            parse_tx(db, tx)
            # adding this block so we can add items that don't decode # was below in data field
            if tx['data'] is not None:
                data = binascii.hexlify(tx['data']).decode('UTF-8')
                print("decoding data", data)
            else:
                data = ''

            txlist.append('{}{}{}{}{}{}'.format(tx['tx_hash'], tx['source'], tx['destination'],
                                                tx['btc_amount'], tx['fee'],
                                                data))
        except exceptions.ParseTransactionError as e:
            logger.warn('ParseTransactionError for tx %s: %s' % (tx['tx_hash'], e))
            raise e

    cursor.close()

    # Calculate consensus hashes.
    # TODO: need to update these functions to use MySQL - these appear to be part of the block reorg checks - needs to be done before deprecating sqlite 
    new_txlist_hash, found_txlist_hash = check.consensus_hash(db, 'txlist_hash', previous_txlist_hash, txlist)
    new_ledger_hash, found_ledger_hash = check.consensus_hash(db, 'ledger_hash', previous_ledger_hash, util.BLOCK_LEDGER)
    new_messages_hash, found_messages_hash = check.consensus_hash(db, 'messages_hash', previous_messages_hash, database.BLOCK_MESSAGES)
    return new_ledger_hash, new_txlist_hash, new_messages_hash, found_messages_hash


def initialise(db):  # CHANGED TO MYSQL
    # print(db) # DEBUG
    """Initialise data, create and populate the database."""
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


def get_tx_info(tx_hex, block_parser=None, block_index=None, db=None):
    """Get the transaction info.
        Returns normalized None data for DecodeError and BTCOnlyError."""
    try:
        return _get_tx_info(tx_hex, block_parser, block_index)
    except DecodeError as e:
        return b'', None, None, None, None, None, None
    except BTCOnlyError as e:
        # # NOTE: For debugging, logger.debug('Could not decode: ' + str(e))
        return b'', None, None, None, None, None, None


def _get_tx_info(tx_hex, block_parser=None, block_index=None, p2sh_is_segwit=False):
    """
    Get the transaction info.
    Calls one of two subfunctions depending on signature type.
    """
    if not block_index:
        block_index = util.CURRENT_BLOCK_INDEX
    if util.enabled('p2sh_addresses', block_index=block_index):
        return get_tx_info3(
            tx_hex, block_parser=block_parser, p2sh_is_segwit=p2sh_is_segwit
        )
    elif util.enabled('multisig_addresses', block_index=block_index):
        return get_tx_info2(tx_hex, block_parser=block_parser)


def get_tx_info2(
    tx_hex, block_parser=None, p2sh_support=False, p2sh_is_segwit=False
):
    """Get multisig transaction info.
    The destinations, if they exists, always comes before the data output; the
    change, if it exists, always comes after.
    """

    # Decode transaction binary.
    ctx = backend.deserialize(tx_hex)
    # deserialize does this: bitcoinlib.core.CTransaction.deserialize(binascii.unhexlify(tx_hex))
    pubkeys = []
    pubkeys_compiled = []

    # Ignore coinbase transactions.
    if ctx.is_coinbase():
        raise DecodeError('coinbase transaction')

    # Get destinations and data outputs.
    destinations, btc_amount, fee, data = [], 0, 0, b''

    keyburn = check_burnkeys_in_multisig(ctx)
    logger.warning(f"key_burn in tx: {keyburn}")
    # vout_count = len(ctx.vout) # number of outputs
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
                pubkeys, signatures_required = script.get_checkmultisig(asm) # this is all the pubkeys from the loop
                # this will return pubkeys for CP transactions that have burnkeys in multisig output
                pubkeys_compiled += pubkeys
                # print("pubkeys compiled: ", pubkeys_compiled)
                # stripped_pubkeys = [pubkey[1:-1] for pubkey in pubkeys]
            except:
                # print("ctx: ", ctx)
                raise DecodeError('unrecognised output type')

    if pubkeys_compiled:  # this is the combination of the two pubkeys which hold the data
        chunk = b''
        for pubkey in pubkeys_compiled:
            chunk += pubkey[1:-1]       # Skip sign byte and nonce byte. ( this does the concatenation as well)
        try:
            new_destination, new_data = decode_checkmultisig(ctx, chunk)
        except:
            raise DecodeError('unrecognised output type')
        assert new_destination is not None and new_data is not None
        
        if new_data is not None:
            data += new_data
            destinations = (str(new_destination))

    # Get source
    source = None

    if not data:
        raise BTCOnlyError('no data and not unspendable', ctx)

    # Get the first input transaction.
    vin = ctx.vin[0]

    # Get the previous transaction hash and output index.
    prev_tx_hash = vin.prevout.hash
    prev_tx_index = vin.prevout.n

    # Get the full transaction data for the previous transaction.
    if block_parser:
        prev_tx = block_parser.read_raw_transaction(prev_tx_hash[::-1])
        prev_ctx = backend.deserialize(prev_tx['__data__'])
    else:
        prev_tx = backend.getrawtransaction(utils.ib2h(prev_tx_hash))
        # prev_tx = backend.getrawtransaction(prev_tx_hash[::-1])
        prev_ctx = backend.deserialize(prev_tx)

    # Get the output being spent by the input.
    prev_vout = prev_ctx.vout[prev_tx_index]
    prev_vout_script_pubkey = prev_vout.scriptPubKey

    # Decode the address associated with the output.
    # print("prev_vout.scriptPubKey: ", prev_vout_script_pubkey, "\n")
    # Decode the address associated with the output.
    try:
        source = str(CBitcoinAddress.from_scriptPubKey(prev_vout_script_pubkey)) #needed to add srt here or we get P2SHAddress('address') output - this is handled differently than destinations
    except Exception:
        pass
    if source is None:
        try:
            source = CBitcoinAddress(decode_p2w(prev_vout_script_pubkey)[0]) # not sure if the Cbitcoinaaddress is needed here
        except Exception:
            pass
    if source is None:
        try:
            source = CBitcoinAddress.from_taproot_scriptPubKey(prev_vout_script_pubkey)
        except Exception:
            pass
    if source is None:
        raise DecodeError('unknown source address type')
    # print("returning: sources, destinations, btc_amount, fee, data ", source, destinations, btc_amount, round(fee), data, "\n")
    return source, destinations, btc_amount, round(fee), data, ctx, keyburn


def get_tx_info3(tx_hex, block_parser=None, p2sh_is_segwit=False):
    return get_tx_info2(tx_hex, block_parser=block_parser, p2sh_support=True, p2sh_is_segwit=p2sh_is_segwit)


def arc4_decrypt(cyphertext, ctx):
    '''Un-obfuscate. Initialise key once per attempt.'''
    key = arc4.init_arc4(ctx.vin[0].prevout.hash[::-1])
    return key.decrypt(cyphertext)


def arc4_decrypt_chunk(cyphertext, key):
    '''Un-obfuscate. Initialise key once per attempt.'''
    # This  is modified  for stamps since in parse_stamp we were getting the key and then converting to a byte string in 2 steps. 
    return key.decrypt(cyphertext)


def get_opreturn(asm):
    if len(asm) == 2 and asm[0] == 'OP_RETURN':
        pubkeyhash = asm[1]
        if type(pubkeyhash) is bytes:
            return pubkeyhash
    raise DecodeError('invalid OP_RETURN')


def decode_scripthash(asm):
    destination = script.base58_check_encode(binascii.hexlify(asm[1]).decode('utf-8'), config.P2SH_ADDRESSVERSION)

    return destination, None


def decode_checksig(asm, ctx):
    pubkeyhash = script.get_checksig(asm)
    chunk = arc4_decrypt(pubkeyhash, ctx)
    if chunk[1:len(config.PREFIX) + 1] == config.PREFIX:        # Data
        # Padding byte in each output (instead of just in the last one) so that encoding methods may be mixed. Also, it’s just not very much data.
        chunk_length = chunk[0]
        chunk = chunk[1:chunk_length + 1]
        destination, data = None, chunk[len(config.PREFIX):]
    else:                                                       # Destination
        pubkeyhash = binascii.hexlify(pubkeyhash).decode('utf-8')
        destination, data = script.base58_check_encode(pubkeyhash, config.ADDRESSVERSION), None

    return destination, data


def decode_checkmultisig(ctx, chunk):
    key = arc4.init_arc4(ctx.vin[0].prevout.hash[::-1])
    chunk = arc4_decrypt_chunk(chunk, key) # this is a different method since we are stripping the nonce/sign beforehand
    if chunk[2:2+len(config.PREFIX)] == config.PREFIX:
        chunk_length = chunk[:2].hex() # the expected length of the string from the first 2 bytes
        data = chunk[len(config.PREFIX) + 2:].rstrip(b'\x00')
        data_length = len(chunk[2:].rstrip(b'\x00'))
        # print("data_length: ", data_length, "chunk_length: ", int(chunk_length, 16))
        if data_length != int(chunk_length, 16):
            raise DecodeError('invalid data length')

        # destination = CBitcoinAddress.from_scriptPubKey(ctx.vout[0].scriptPubKey) # this was not decoding all address types

        script_pubkey = ctx.vout[0].scriptPubKey
        # print("script_pubkey: ", script_pubkey)
        destination = None

        try:
            destination = CBitcoinAddress.from_scriptPubKey(script_pubkey)
        except Exception:
            pass
        if destination is None:
            try:
                destination = decode_p2w(script_pubkey)[0]
            except Exception:
                pass
        if destination is None:
            try:
                destination = CBitcoinAddress.from_taproot_scriptPubKey(script_pubkey)
            except Exception:
                pass
        if destination is None:
            raise DecodeError('unknown address type')

        return destination, data
    else:
        return None, data


def decode_p2w(script_pubkey):  # This is used for stamps
    try:
        bech32 = bitcoinlib.bech32.CBech32Data.from_bytes(0, script_pubkey[2:22])
        return str(bech32), None
    except TypeError:
        raise DecodeError('bech32 decoding error')


def reinitialise(db, block_index=None):
    ''' Not yet implemented for stamps need to swap to mysql and figure out what tables to drop! '''

    """Drop all predefined tables and initialise the database once again."""
    cursor = db.cursor()

    # Delete all of the results of parsing (including the undolog) - removed since we aren't using any of these tables,
    # perhaps we purge from the src table here.. 

    # Create missing tables
    initialise(db)

    # warning and exit the program
    Exception("reinitialise() is not implemented yet")

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
            reinitialise(db, block_index)

            # Reparse all blocks, transactions.
            if quiet:
                root_logger.setLevel(logging.WARNING)

            previous_ledger_hash, previous_txlist_hash, previous_messages_hash = None, None, None
            cursor.execute('''SELECT * FROM blocks ORDER BY block_index''')
            for block in cursor.fetchall():
                util.CURRENT_BLOCK_INDEX = block['block_index']
                previous_ledger_hash, previous_txlist_hash, previous_messages_hash, previous_found_messages_hash = parse_block(
                                                                         db, block['block_index'], block['block_time'],
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

    # on full reparse - vacuum the DB afterwards for better subsequent performance (especially on non-SSDs)
    if not block_index:
        database.vacuum(db)


def list_tx(db, block_hash, block_index, block_time, tx_hash, tx_index, tx_hex=None, stamp_issuance=None):
    assert type(tx_hash) is str
    cursor = db.cursor()

    # Edge case: confirmed tx_hash also in mempool
    # Leaving this for now on the sqlite table only since we aren't doing mempool on prod yet
    cursor.execute('''SELECT * FROM transactions WHERE tx_hash = %s''', (tx_hash,))
    transactions = cursor.fetchall()
    if transactions:
        return tx_index

    # Get the important details about each transaction.
    if tx_hex is None:
        tx_hex = backend.getrawtransaction(tx_hash) # TODO: This is the call that is stalling the process the most

    source, destination, btc_amount, fee, data, decoded_tx, keyburn = get_tx_info(tx_hex, db=db) # type: ignore

    # For mempool
    if block_hash == None:
        block_hash = config.MEMPOOL_BLOCK_HASH
        block_index = config.MEMPOOL_BLOCK_INDEX
    else:
        assert block_index == util.CURRENT_BLOCK_INDEX

    # if source and (data or destination == config.UNSPENDABLE or decoded_tx):
    if True: # we are writing all trx to the transactions table
        if stamp_issuance is not None:
            data = str(stamp_issuance)
            source = str(stamp_issuance['source'])
            destination = str(stamp_issuance['issuer'])
        logger.warning(f"keyburn before saving to db: {keyburn}")
        # logger.warning('Saving to MySQL transactions: {}\nDATA:{}'.format(tx_hash, data))
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
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)''',
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
        return tx_index + 1
    else:
        logger.getChild('list_tx.skip').debug('Skipping transaction: {}'.format(tx_hash))

    return tx_index


def last_db_index(db):
    field_position = config.BLOCK_FIELDS_POSITION
    cursor = db.cursor()
    
    try:
        # Get the last block index from the SQLite database.
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


class MempoolError(Exception):
    pass


def follow(db): 
    # Check software version.
    # check.software_version()

    # Initialise.
    initialise(db)

    # Get index of last block.
    if util.CURRENT_BLOCK_INDEX == 0:
        logger.warning('New database.')
        block_index = config.BLOCK_FIRST
    else:
        block_index = util.CURRENT_BLOCK_INDEX + 1

    logger.info('Resuming parsing.')
    # Get index of last transaction.
    tx_index = get_next_tx_index(db)
    not_supported = {}
    not_supported_sorted = collections.deque()
    cursor = db.cursor()

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
            print("block_count: ", block_count)

            purge_old_block_tx_db(db, block_index)
            current_index = block_index
            issuances = get_issuances_by_block(current_index)
            stamp_issuances = get_stamp_issuances(issuances)
            if block_count - block_index < 100:
                requires_rollback = False
                while True:
                    if current_index == config.BLOCK_FIRST:
                        break

                    logger.debug('Checking that block {} is not an orphan.'.format(current_index))
                    # Backend parent hash.
                    current_hash = backend.getblockhash(current_index)  # rpc call to the node
                    current_cblock = backend.getcblock(current_hash)    # rpc call to the node
                    backend_parent = bitcoinlib.core.b2lx(current_cblock.hashPrevBlock)

                    test_query = '''
                    SELECT * FROM blocks WHERE block_index = %s
                    '''
                    cursor.execute(test_query, (current_index - 1,))
                    blocks = cursor.fetchall()
                    columns = [desc[0] for desc in cursor.description]
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

                # Rollback for reorganisation.
                if requires_rollback:
                    # Record reorganisation.
                    logger.warning(
                        'Blockchain reorganisation at block {}.'
                        .format(current_index)
                    )
                    current_index -= 1
                    logger.warning(
                        'Rolling back to block {} to avoid problems.'
                        .format(current_index)
                    )
                    # Rollback.
                    purge_block_db(db, current_index)
                    requires_rollback = False
                    continue

            # check.software_version()
            block_hash = backend.getblockhash(current_index)
            block = backend.getblock(block_hash)
            cblock = backend.getcblock(block_hash)
            cblock_unhex = CBlock.deserialize(util.unhexlify(block))
            previous_block_hash = bitcoinlib.core.b2lx(cblock.hashPrevBlock) 
            previous_block_hash = bitcoinlib.core.b2lx(cblock.hashPrevBlock)
            block_time = cblock.nTime
            print(block_time)
            txhash_list, raw_transactions = backend.get_tx_list(cblock)

            with db, db.cursor() as block_cursor:
                util.CURRENT_BLOCK_INDEX = block_index

                logger.warning('Inserting MySQL Block: {}'.format(block_index))
                new_ledger_hash, new_txlist_hash, new_messages_hash, found_messages_hash = parse_block(db, block_index, block_time)
                block_query = '''INSERT INTO blocks(
                                    block_index,
                                    block_hash,
                                    block_time,
                                    previous_block_hash,
                                    difficulty,
                                    ledger_hash,
                                    txlist_hash,
                                    messages_hash
                                    ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)'''
                args = (block_index, block_hash, block_time, previous_block_hash, float(cblock.difficulty), new_ledger_hash, new_txlist_hash, new_messages_hash)

                try:
                    block_cursor.execute("START TRANSACTION")
                    block_cursor.execute(block_query, args)
                except mysql.IntegrityError:
                    print("block already exists in mysql")
                    sys.exit()
                except Exception as e:
                    print("Error executing query:", block_query)
                    print("Arguments:", args)
                    print("Error message:", e)
                    sys.exit()

                for tx_hash in txhash_list:
                    stamp_issuance = filter_issuances_by_tx_hash(stamp_issuances, tx_hash)
                    if tx_hash == "50aeb77245a9483a5b077e4e7506c331dc2f628c22046e7d2b4c6ad6c6236ae1":
                        print("found first src stamp in block follow db")
                    tx_hex = raw_transactions[tx_hash]
                    tx_index = list_tx(db, block_hash, block_index, block_time, tx_hash, tx_index, tx_hex, stamp_issuance=stamp_issuance)
                try:
                    block_cursor.execute("COMMIT")
                except Exception as e:
                    print("Error message:", e)
                    block_cursor.execute("ROLLBACK")
                    sys.exit()

            update_stamp_table(db, block_index)
            logger.warning('Block: %s (%ss, hashes: L:%s / TX:%s / M:%s%s)' % (
                str(block_index), "{:.2f}".format(time.time() - start_time, 3),
                new_ledger_hash[-5:], new_txlist_hash[-5:], new_messages_hash[-5:],
                (' [overwrote %s]' % found_messages_hash) if found_messages_hash and found_messages_hash != new_messages_hash else ''))
            block_count = backend.getblockcount()
            block_index += 1
