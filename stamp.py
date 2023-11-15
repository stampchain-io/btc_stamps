import logging
import json
import base64
from datetime import datetime
import hashlib

import config

logger = logging.getLogger(__name__)


def purgue_block_db(db, block_index):
    """Purgue block transactions from the database."""
    cursor = db.cursor()
    db.ping(reconnect=True)
    cursor.execute('''
                   DELETE FROM transactions
                   WHERE block_index = %s
                   ''', (block_index,))
    cursor.execute('''
                    DELETE FROM blocks
                    WHERE block_index = %s
                    ''', (block_index,))
    cursor.execute('''
                   DELETE FROM StampTableV4
                   WHERE block_index = %s
                    ''', (block_index,))
    cursor.execute("COMMIT")
    cursor.close()


def is_prev_block_parsed(db, block_index):
    block_fields = config.BLOCK_FIELDS_POSITION
    db.ping(reconnect=True)
    cursor = db.cursor()
    cursor.execute('''
                   SELECT * FROM blocks
                   WHERE block_index = %s
                   ''', (block_index - 1,))
    block = cursor.fetchone()
    if block[block_fields['indexed']] == 1:
        return True
    else:
        purgue_block_db(db, block_index - 1)
        return False


def get_stamps_without_validation(db, block_index):
    cursor = db.cursor()
    cursor.execute('''
                    SELECT * FROM transactions
                    WHERE block_index = %s
                    AND data IS NOT NULL
                    ''', (block_index,))
    stamps = cursor.fetchall()
    # logger.warning("stamps: {}".format(stamps))
    return stamps


def base62_encode(num):
    characters = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    base = len(characters)
    if num == 0:
        return characters[0]
    result = []
    while num:
        num, rem = divmod(num, base)
        result.append(characters[rem])
    return ''.join(reversed(result))


def create_base62_hash(str1, str2, length=20):
    if not 12 <= length <= 20:
        raise ValueError("Length must be between 12 and 20 characters")
    combined_str = str1 + "|" + str2
    hash_bytes = hashlib.sha256(combined_str.encode()).digest()
    hash_int = int.from_bytes(hash_bytes, byteorder='big')
    base62_hash = base62_encode(hash_int)
    return base62_hash[:length]


def get_cpid(stamp, tx_index, tx_hash):
    return stamp.get('cpid', create_base62_hash(tx_hash, str(tx_index), 20))


def clean_and_load_json(json_string):
    try:
        return json.loads(json_string)
    except json.JSONDecodeError:
        json_string = json_string.replace("'", '"')
        json_string = json_string.replace("None", "null")
        return json.loads(json_string)


def decode_base64_json(base64_string):
    try:
        decoded_data = base64.b64decode(base64_string)
        json_string = decoded_data.decode('utf-8')
        return json.loads(json_string)
    except Exception as e:
        print(f"Error decoding json: {e}")
        return None


def get_src_data(stamp):
    if 'p' in stamp and stamp.get('p') == 'src-20':
        return stamp
    else:
        return decode_base64_json(stamp.get('description').split(':')[1])


def parse_stamps_to_stamp_table(db, stamps):
    tx_fields = config.TXS_FIELDS_POSITION
    with db:
        cursor = db.cursor()
        for stamp_tx in stamps:
            stamp = clean_and_load_json(stamp_tx[tx_fields['data']])
            src_data = get_src_data(stamp)
            tx_index = stamp_tx[tx_fields['tx_index']]
            tx_hash = stamp_tx[tx_fields['tx_hash']]
            block_index = stamp_tx[tx_fields['block_index']]
            ident = src_data is not None and 'p' in src_data and (src_data.get('p') == 'src-20' or src_data.get('p') == 'src-721') and src_data.get('p').upper() or 'STAMP'
            parsed = {
                "stamp": None,
                "block_index": block_index,
                "cpid": get_cpid(stamp, tx_index, tx_hash),
                "asset_longname": stamp.get('asset_longname'),
                "creator": stamp.get('issuer', stamp_tx[tx_fields['source']]),
                "divisible": stamp.get('divisible'),
                "keyburn": None,  # TODO: add keyburn
                "locked": stamp.get('locked'),
                "message_index": stamp.get('message_index'),
                "stamp_base64": stamp.get('description'),
                "stamp_mimetype": None,  # TODO: add stamp_mimetype
                "stamp_url": None,  # TODO: add stamp_url
                "supply": stamp.get('quantity'),
                "timestamp": datetime.utcfromtimestamp(
                    stamp_tx[tx_fields['block_time']]
                ).strftime('%Y-%m-%d %H:%M:%S'),
                "tx_hash": tx_hash,
                "tx_index": tx_index,
                "src_data": json.dumps(get_src_data(stamp)),
                "ident": ident,
                "creator_name": None,  # TODO: add creator_name
                "stamp_gen": None,  # TODO: add stamp_gen,
            }
            cursor.execute('''
                           INSERT INTO StampTableV4(
                                stamp, block_index, cpid, asset_longname,
                                creator, divisible, keyburn, locked,
                                message_index, stamp_base64,
                                stamp_mimetype, stamp_url, supply, timestamp,
                                tx_hash, tx_index, src_data, ident,
                                creator_name, stamp_gen
                                ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                                %s,%s,%s,%s,%s,%s,%s,%s)
                           ''', (
                                parsed['stamp'], parsed['block_index'],
                                parsed['cpid'], parsed['asset_longname'],
                                parsed['creator'],
                                parsed['divisible'], parsed['keyburn'],
                                parsed['locked'], parsed['message_index'],
                                parsed['stamp_base64'],
                                parsed['stamp_mimetype'], parsed['stamp_url'],
                                parsed['supply'], parsed['timestamp'],
                                parsed['tx_hash'], parsed['tx_index'],
                                parsed['src_data'], parsed['ident'],
                                parsed['creator_name'], parsed['stamp_gen']
                           ))
        cursor.execute("COMMIT")


def update_parsed_block(block_index, db):
    db.ping(reconnect=True)
    cursor = db.cursor()
    cursor.execute('''
                    UPDATE blocks SET indexed = 1
                    WHERE block_index = %s
                    ''', (block_index,))
    cursor.execute("COMMIT")


def update_stamp_table(db, block_index):
    db.ping(reconnect=True)
    stamps_without_validation = get_stamps_without_validation(db, block_index)
    parse_stamps_to_stamp_table(db, stamps_without_validation)
    update_parsed_block(block_index=block_index, db=db)

# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
