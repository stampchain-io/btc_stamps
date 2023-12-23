"""
initialize database.

Sieve blockchain for Stamp transactions, and add them to the database.
"""

import sys
import time
import binascii
import decimal
import logging
import http
import bitcoin as bitcoinlib
from bitcoin.core.script import CScriptInvalidError
from bitcoin.wallet import CBitcoinAddress
import pymysql as mysql

import config
import src.exceptions as exceptions
import src.util as util
import check
import src.script as script
import src.backend as backend
import src.arc4 as arc4
import src.log as log
from xcprequest import (
    get_all_tx_by_block,
    get_all_dispensers_by_block,
    get_all_dispenses_by_block,
    parse_issuances_and_sends_from_block,
    parse_dispensers_from_block,
    parse_dispenses_from_block,
    filter_sends_by_tx_hash,
    filter_issuances_by_tx_hash,
    filter_dispensers_by_tx_hash,
)
from stamp import (
    is_prev_block_parsed,
    purge_block_db,
    parse_tx_to_stamp_table,
    update_parsed_block,
)

from send import (
    parse_tx_to_send_table,
    parse_issuance_to_send_table,
    parse_tx_to_dispenser_table,
)

from src20 import (
    update_src20_balances,
)

from src.exceptions import DecodeError, BTCOnlyError

D = decimal.Decimal
logger = logging.getLogger(__name__)
log.set_logger(logger)  

def parse_block(db, block_index, block_time,
                previous_ledger_hash=None, ledger_hash=None,
                previous_txlist_hash=None, txlist_hash=None,
                previous_messages_hash=None):
    """Parse the block, return hash of new ledger, txlist and messages.
    The unused arguments `ledger_hash` and `txlist_hash` are for the test suite.
    """

    assert block_index == util.CURRENT_BLOCK_INDEX

    cursor = db.cursor()
    db.ping(reconnect=True)
    cursor.execute('''SELECT * FROM transactions \
                      WHERE block_index=%s ORDER BY tx_index''',
                   (block_index,))
    txes = cursor.fetchall()
    logger.warning("TX LENGTH FOR BLOCK {} BEFORE PARSING: {}".format(block_index,len(txes)))

    txlist = []
    for tx in txes:
        # print("tx", tx) # DEBUG
        try:
            # parse_tx(db, tx)

            # adding this block so we can add items that don't decode # was below in data field
            if tx[config.TXS_FIELDS_POSITION['data']] is not None:
                # data = binascii.hexlify(tx[config.TXS_FIELDS_POSITION['data']]) # .encode('UTF-8')).decode('UTF-8')
                data = tx[config.TXS_FIELDS_POSITION['data']]
                print("decoding data", data)
            else:
                data = ''
            
            txlist.append('{}{}{}{}{}{}'.format(tx[config.TXS_FIELDS_POSITION['tx_index']],
                                                tx[config.TXS_FIELDS_POSITION['tx_hash']],
                                                tx[config.TXS_FIELDS_POSITION['block_index']],
                                                tx[config.TXS_FIELDS_POSITION['block_hash']],
                                                tx[config.TXS_FIELDS_POSITION['block_time']],
                                                data))
        except exceptions.ParseTransactionError as e:
            logger.warn('ParseTransactionError for tx %s: %s' % (tx[config.TXS_FIELDS_POSITION['tx_index']], e))
            raise e

    cursor.close()

    # Calculate consensus hashes.
    # TODO: need to update these functions to use MySQL - these appear to be part of the block reorg checks - needs to be done before deprecating sqlite 
    new_txlist_hash, found_txlist_hash = check.consensus_hash(db, 'txlist_hash', previous_txlist_hash, txlist)
    new_ledger_hash, found_ledger_hash = check.consensus_hash(db, 'ledger_hash', previous_ledger_hash, util.BLOCK_LEDGER)
    new_messages_hash, found_messages_hash = check.consensus_hash(db, 'messages_hash', previous_messages_hash, util.BLOCK_MESSAGES)
    return new_ledger_hash, new_txlist_hash, new_messages_hash, found_messages_hash


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


def get_tx_info(tx_hex, block_parser=None, block_index=None, db=None, stamp_issuance=None):
    """Get the transaction info.
        Returns normalized None data for DecodeError and BTCOnlyError."""
    try:
        if not block_index:
            block_index = util.CURRENT_BLOCK_INDEX
        return get_tx_info2(
            tx_hex, block_parser=block_parser,
            p2sh_support=True, p2sh_is_segwit=False, stamp_issuance=stamp_issuance
        )
    except DecodeError as e:
        return b'', None, None, None, None, None, None, None
    except BTCOnlyError as e:
        return b'', None, None, None, None, None, None, None


def get_tx_info2(
    tx_hex, block_parser=None, p2sh_support=False, p2sh_is_segwit=False, stamp_issuance=None
):
    """Get multisig transaction info.
    The destinations, if they exists, always comes before the data output; the
    change, if it exists, always comes after.
    Updating to include keyburn check on all transactions, not just src-20
    This is parsing every single transaction, not just those that are stamps/src-20
    """

    # Decode transaction binary.
    ctx = backend.deserialize(tx_hex)
    # deserialize does this: bitcoinlib.core.CTransaction.deserialize(binascii.unhexlify(tx_hex))
    pubkeys_compiled = []

    # Ignore coinbase transactions.
    if ctx.is_coinbase():
        raise DecodeError('coinbase transaction')

    destinations, btc_amount, fee, data, keyburn, is_op_return = [], 0, 0, b'', None, None

    if stamp_issuance:
        source = str(stamp_issuance['source'])
        destination = str(stamp_issuance['issuer'])
        data = str(stamp_issuance)

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
                pubkeys, signatures_required, keyburn_vout = script.get_checkmultisig(asm) # this is all the pubkeys from the loop
                if keyburn_vout is not None: # if one of the vouts have keyburn we set keyburn for the whole trx. the last vout is not keyburn
                    keyburn = keyburn_vout
                pubkeys_compiled += pubkeys
                # print("pubkeys compiled: ", pubkeys_compiled)
                # stripped_pubkeys = [pubkey[1:-1] for pubkey in pubkeys]
            except:
                # print("ctx: ", ctx)
                raise DecodeError('unrecognised output type')
        elif asm[-1] == 'OP_CHECKSIG':
            pass # FIXME: not certain if we need to check keyburn on these
                # see 'A14845889080100805000'
                #   0: OP_DUP
                #   1: OP_HASH160
                #   3: OP_EQUALVERIFY
                #   4: OP_CHECKSIG
        elif asm[0] == 'OP_RETURN':
            is_op_return = True
            pass #Just ignore.
    
    if pubkeys_compiled:  # this is the combination of the two pubkeys which hold the data
        chunk = b''
        for pubkey in pubkeys_compiled:
            chunk += pubkey[1:-1]       # Skip sign byte and nonce byte. ( this does the concatenation as well)
        try:
            new_destination, new_data = decode_checkmultisig(ctx, chunk) # this only decodes src-20 type trx
        except:
            if stamp_issuance:
                # returning since we parsed and got keyburn
                return source, destination, btc_amount, round(fee), data, ctx, keyburn, is_op_return
            else:
                raise DecodeError('unrecognized output type')
        assert new_destination is not None and new_data is not None  # removing this might not get a dest for cp trx?
        if new_data is not None:
            data += new_data
            destinations = (str(new_destination))

    source = None

    if stamp_issuance:
        return source, destination, btc_amount, round(fee), data, ctx, keyburn, is_op_return

    if not data:
        raise BTCOnlyError('no data and not unspendable', ctx)

    vin = ctx.vin[0]

    prev_tx_hash = vin.prevout.hash
    prev_tx_index = vin.prevout.n

    # Get the full transaction data for the previous transaction.
    if block_parser:
        prev_tx = block_parser.read_raw_transaction(prev_tx_hash[::-1])
        prev_ctx = backend.deserialize(prev_tx['__data__'])
    else:
        prev_tx = backend.getrawtransaction(util.ib2h(prev_tx_hash))
        # prev_tx = backend.getrawtransaction(prev_tx_hash[::-1])
        prev_ctx = backend.deserialize(prev_tx)

    # Get the output being spent by the input.
    prev_vout = prev_ctx.vout[prev_tx_index]
    prev_vout_script_pubkey = prev_vout.scriptPubKey

    # Decode the address associated with the output.
    # print("prev_vout.scriptPubKey: ", prev_vout_script_pubkey, "\n")
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

    # this is detecting keyburn for CP as well :) 
    # print("source =", source, "destinations =", destinations, "btc_amount =", btc_amount, "fee =", round(fee), "data =", data, "keyburn", keyburn, "\n")
    return source, destinations, btc_amount, round(fee), data, ctx, keyburn, is_op_return


def decode_checkmultisig(ctx, chunk):
    key = arc4.init_arc4(ctx.vin[0].prevout.hash[::-1])
    chunk = arc4.arc4_decrypt_chunk(chunk, key) # this is a different method since we are stripping the nonce/sign beforehand
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

# counterparty decoding for multisig
# def decode_checkmultisig(asm, ctx):
#     pubkeys, signatures_required = script.get_checkmultisig(asm)
#     chunk = b''
#     for pubkey in pubkeys[:-1]:     # (No data in last pubkey.)
#         chunk += pubkey[1:-1]       # Skip sign byte and nonce byte.
#     chunk = arc4_decrypt(chunk, ctx)
#     if chunk[1:len(config.PREFIX) + 1] == config.PREFIX:        # Data
#         # Padding byte in each output (instead of just in the last one) so that encoding methods may be mixed. Also, it’s just not very much data.
#         chunk_length = chunk[0]
#         chunk = chunk[1:chunk_length + 1]
#         destination, data = None, chunk[len(config.PREFIX):]
#     else:                                                       # Destination
#         pubkeyhashes = [script.pubkey_to_pubkeyhash(pubkey) for pubkey in pubkeys]
#         destination, data = script.construct_array(signatures_required, pubkeyhashes, len(pubkeyhashes)), None

def decode_p2w(script_pubkey):  # This is used for stamps
    try:
        bech32 = bitcoinlib.bech32.CBech32Data.from_bytes(0, script_pubkey[2:22])
        return str(bech32), None
    except TypeError:
        raise DecodeError('bech32 decoding error')


def reinitialize(db, block_index=None):
    ''' Not yet implemented for stamps need to swap to mysql and figure out what tables to drop! '''

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


def list_tx(db, block_hash, block_index, block_time, tx_hash, tx_index, tx_hex=None, stamp_issuance=None, stamp_send=None):
    assert type(tx_hash) is str
    cursor = db.cursor()
    # check if the incoming tx_hash from txhash_list is already in the trx table
    cursor.execute('''SELECT * FROM transactions WHERE tx_hash = %s''', (tx_hash,)) # this will include all CP transactinos as well ofc
    transactions = cursor.fetchall()
    if transactions:
        return tx_index

    # Get the important details about each transaction.
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
    ) = get_tx_info(tx_hex, db=db, stamp_issuance=stamp_issuance)

    assert block_index == util.CURRENT_BLOCK_INDEX

    if source and (data or destination) or stamp_issuance or stamp_send:
        if stamp_issuance is not None:
            data = str(stamp_issuance)
            source = str(stamp_issuance['source'])
            destination = str(stamp_issuance['issuer'])
        if stamp_send is not None:
            data = str(stamp_send)
            source = str(stamp_send[0]['source'])
            destination = ','.join(send['destination'] for send in stamp_send)
        logger.info('Saving to MySQL transactions: {}\nDATA:{}\nKEYBURN: {}\nOP_RETURN: {}'.format(tx_hash, data, keyburn, is_op_return))
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
        return tx_index + 1, source, destination, btc_amount, fee, data, decoded_tx, keyburn, is_op_return
    else:
        logger.getChild('list_tx.skip').debug('Skipping transaction: {}'.format(tx_hash))

    return tx_index, None, None, None, None, None, None, None, None


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

            block_data_from_xcp = get_all_tx_by_block(block_index=block_index)
            parsed_block_data = parse_issuances_and_sends_from_block(
                block_data=block_data_from_xcp,
                db=db
            )
            stamp_issuances = parsed_block_data['issuances']
            stamp_sends = parsed_block_data['sends']
            block_dispensers_from_xcp = get_all_dispensers_by_block(
                block_index=block_index
            )
            parsed_stamp_dispensers = parse_dispensers_from_block(
                dispensers=block_dispensers_from_xcp,
                db=db
            )
            stamp_dispensers = parsed_stamp_dispensers['dispensers']
            stamp_sends += parsed_stamp_dispensers['sends']
            block_dispenses_from_xcp = get_all_dispenses_by_block(
                block_index=block_index
            )
            stamp_dispenses = parse_dispenses_from_block(
                dispenses=block_dispenses_from_xcp,
                db=db
            )
            stamp_sends += stamp_dispenses
            logger.warning(
                f"""
                XCP Block {block_index}
                - {len(stamp_issuances)} issuances
                - {len(stamp_sends)} sends
                - {len(stamp_dispensers)} dispensers
                - {len(stamp_dispenses)} dispenses
                """
            )
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
                                ) VALUES(%s,%s,FROM_UNIXTIME(%s),%s,%s,%s,%s,%s)'''
            args = (block_index, block_hash, block_time, previous_block_hash, float(cblock.difficulty), new_ledger_hash, new_txlist_hash, new_messages_hash)

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
                stamp_send = filter_sends_by_tx_hash(stamp_sends, tx_hash)
                stamp_dispenser = filter_dispensers_by_tx_hash(
                    stamp_dispensers, tx_hash
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
                    stamp_issuance=stamp_issuance,
                    stamp_send=stamp_send,
                )
                if (stamp_send is None):
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
                else:
                    parse_tx_to_send_table(
                        db=db,
                        cursor=block_cursor,
                        sends=stamp_send,
                        tx={
                            "tx_index": tx_index,
                        }
                    )
                    if (stamp_dispenser is not None):
                        parse_tx_to_dispenser_table(
                            db=db,
                            cursor=block_cursor,
                            dispenser=stamp_dispenser,
                            tx={
                                "tx_index": tx_index,
                            }
                        )
            if valid_src20_in_block:
                update_src20_balances(db, block_index, block_time, valid_src20_in_block)

            try:
                db.commit()
                update_parsed_block(db, block_index)
            except Exception as e:
                print("Error message:", e)
                db.rollback()
                db.close()
                sys.exit()

            logger.warning('Block: %s (%ss, hashes: L:%s / TX:%s / M:%s%s)' % (
                str(block_index), "{:.2f}".format(time.time() - start_time, 3),
                new_ledger_hash[-5:], new_txlist_hash[-5:], new_messages_hash[-5:],
                (' [overwrote %s]' % found_messages_hash) if found_messages_hash and found_messages_hash != new_messages_hash else ''))
            block_count = backend.getblockcount()
            block_index += 1
