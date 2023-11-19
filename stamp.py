import logging
import json
import base64
import pybase64
from datetime import datetime
import hashlib
import magic
import subprocess
import ast

import config
from xcprequest import parse_base64_from_description
from bitcoin.core.script import CScript, OP_RETURN
from src721 import validate_src721_and_process
from src20 import check_format
import traceback
import src.script as script

logger = logging.getLogger(__name__)


def purge_block_db(db, block_index):
    """Purge block transactions from the database."""
    db.ping(reconnect=True)
    cursor = db.cursor()
    logger.warning(
        "Purging txs from database after block: {}"
        .format(block_index)
    )
    cursor.execute('''
                   DELETE FROM transactions
                   WHERE block_index >= %s
                   ''', (block_index,))
    logger.warning(
        "Purging blocks from database after block: {}"
        .format(block_index)
    )
    cursor.execute('''
                    DELETE FROM blocks
                    WHERE block_index >= %s
                    ''', (block_index,))
    logger.warning(
        "Purging stamps from database after block: {}"
        .format(block_index)
    )
    cursor.execute('''
                   DELETE FROM {}
                   WHERE block_index >= %s
                    '''.format(config.STAMP_TABLE), (block_index,))
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
        purge_block_db(db, block_index - 1)
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
    chars = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    base = len(chars)
    if num == 0:
        return chars[0]
    result = []
    while num:
        num, rem = divmod(num, base)
        result.append(chars[rem])
    return ''.join(reversed(result))


def create_base62_hash(str1, str2, length=20):
    if not 12 <= length <= 20:
        raise ValueError("Length must be between 12 and 20 characters")
    combined_str = str1 + "|" + str2
    hash_bytes = hashlib.sha256(combined_str.encode()).digest()
    hash_int = int.from_bytes(hash_bytes, byteorder='big')
    base62_hash = base62_encode(hash_int)
    return base62_hash[:length]


def get_cpid(stamp, block_index, tx_hash):
    cpid = stamp.get('cpid')
    return cpid, create_base62_hash(tx_hash, str(block_index), 20)


def clean_and_load_json(json_string):
    try:
        return json.loads(json_string)
    except json.JSONDecodeError:
        json_string = json_string.replace("'", '"')
        json_string = json_string.replace("None", "null")
        json_string = json_string.replace("\\x00", "") # remove null bytes
        return json.loads(json_string)

def convert_to_json(input_string):
    try:
        dictionary = ast.literal_eval(input_string)
        json_string = json.dumps(dictionary)
        return clean_and_load_json(json_string)
    except Exception as e:
        return f"An error occurred: {e}"
    
def decode_base64(base64_string, block_index):
    ''' validation on and after block 784550 - this will result in more invalid base64 strings since don't attempt repair of padding '''
    if block_index >= 784550:
        decode_base64_with_repair(base64_string)
        return
    try:
        image_data = base64.b64decode(base64_string)
        return image_data
    except Exception as e1:
        try:
            image_data = pybase64.b64decode(base64_string)
            return image_data
        except Exception as e2:
            try:
                # If decoding with pybase64 fails, try decoding with the base64 command line tool with and without newlines for the json strings
                command = f'printf "%s" "{base64_string}" | base64 -d 2>&1'
                if not base64_string.endswith('\n'):
                    command = f'printf "%s" "{base64_string}" | base64 -d 2>&1'
                image_data = subprocess.check_output(command, shell=True)
                return image_data
            except Exception as e3:
                # If all decoding attempts fail, print an error message and return None
                print(f"EXCLUSION: BASE64 DECODE_FAIL base64 image string: {e1}, {e2}, {e3}")
                # print(base64_string)
                return None


def decode_base64_with_repair(base64_string):
    ''' original function which attemts to add padding to "fix" the base64 string. This was resulting in invalid/corrupted images. '''
    try:
        missing_padding = len(base64_string) % 4
        if missing_padding:
            base64_string += '=' * (4 - missing_padding)

        image_data = base64.b64decode(base64_string)
        return image_data

    except Exception as e:
        print(f"EXCLUSION: Invalid base64 image string: {e}")
        # print(base64_string)
        return None


def decode_base64(base64_string, block_index):
    ''' validation on and after block 784550 - this will result in
    more invalid base64 strings since don't attempt repair of padding '''
    try:
        image_data = base64.b64decode(base64_string)
        return image_data
    except Exception as e1:
        try:
            image_data = pybase64.b64decode(base64_string)
            return image_data
        except Exception as e2:
            try:
                # If decoding with pybase64 fails,
                # try decoding with the base64 command line tool with
                # and without newlines for the json strings
                command = f'printf "%s" "{base64_string}" | base64 -d 2>&1'
                if not base64_string.endswith('\n'):
                    command = f'printf "%s" "{base64_string}" | base64 -d 2>&1'
                image_data = subprocess.check_output(command, shell=True)
                return image_data
            except Exception as e3:
                # If all decoding attempts fail,
                # print an error message and return None
                print(f"EXCLUSION: BASE64 DECODE_FAIL base64 image string: {e1}, {e2}, {e3}")
                # print(base64_string)
                return None


def get_src_or_img_data(stamp, block_index):
    # if this is src-20 on bitcoin we have already decoded
    # the string in the transaction table
    stamp_mimetype = None
    if 'description' not in stamp: # this was already decoded to json
        if 'p' in stamp or 'P' in stamp and stamp.get('p').upper() == 'SRC-20':
            return stamp, None
        elif 'p' in stamp or 'P' in stamp and stamp.get('p').upper() == 'SRC-721':
            # TODO: add src-721 decoding and details here
            return stamp, None
    else:
        stamp_description = stamp.get('description')
        #FIXME: stamp_mimetype may also be pulled in from the data json string as the stamp_mimetype key.
        # below will over-write that user-input value assuming the base64 decodes properly
        # we also may have text or random garbage in the description field to look out for
        base64_string, stamp_mimetype = parse_base64_from_description(
            stamp_description
        )
        decoded_base64 = decode_base64(base64_string, block_index)
        return decoded_base64, base64_string, stamp_mimetype


def check_custom_suffix(bytestring_data):
    ''' for items that aren't part of the magic module that we want to include '''
    if bytestring_data[:3] == b'BMN':
        return True
    else:
        return None


def get_file_suffix(bytestring_data, block_index):
    print(block_index, config.BMN_BLOCKSTART)
    if block_index > config.BMN_BLOCKSTART:
        if check_custom_suffix(bytestring_data):
            return 'bmn'
    try:
        json.loads(bytestring_data.decode('utf-8'))
        return 'json'
    except (json.JSONDecodeError, UnicodeDecodeError):
        # If it failed to decode as UTF-8 text, pass it to magic to determine the file type
        if block_index > 797200: # after this block we attempt to strip whitespace from the beginning of the binary data to catch Mikes A12333916315059997842
            file_type = magic.from_buffer(bytestring_data.lstrip(), mime=True)
        else:
            file_type = magic.from_buffer(bytestring_data, mime=True)
        return file_type.split('/')[-1]


def is_op_return(hex_pk_script):
    pk_script = bytes.fromhex(hex_pk_script)
    decoded_script = CScript(pk_script)

    if len(decoded_script) < 1:
        return False

    if decoded_script[0] == OP_RETURN:
        return True

    return False


def is_only_op_return(transaction):
    for outp in transaction['vout']:
        if 'scriptPubKey' in outp and not is_op_return(outp['scriptPubKey']['hex']):
            return False

    return True


def check_burnkeys_in_multisig(transaction):
    for vout in transaction.vout:
        asm = script.get_asm(vout.scriptPubKey)
        if "OP_CHECKMULTISIG" in asm:
            for burnkey in config.BURNKEYS:
                for item in asm:
                    if isinstance(item, bytes):
                        if item.hex() == burnkey:
                            return 1
    return None


def is_json_string(s):
    try:
        if s.startswith('{') and s.endswith('}'):
            json.loads(s)
            return True
        else:
            return False
    except json.JSONDecodeError:
        return False


def check_decoded_data(decoded_data, block_index):
    ''' this can come in as a json string or text (in the case of svg's)'''
    if type(decoded_data) is bytes:
        try:
            decoded_data = decoded_data.decode('utf-8') # this will fail if it's not a string (aka if it's a stamp image)
        except Exception as e:
            pass
    if (type(decoded_data) is str and is_json_string(decoded_data)): # or isinstance(decoded_data, dict):
        decoded_data = json.loads(decoded_data)
        decoded_data = {k.lower(): v for k, v in decoded_data.items()}
        if decoded_data and decoded_data.get('p') and decoded_data.get('p').upper() in config.SUPPORTED_SUB_PROTOCOLS:
            ident = decoded_data['p'].upper()
            file_suffix = 'json'
        else:
            ident = 'UNKNOWN'
    else:
        try:
            if decoded_data and type(decoded_data) is str:
                decoded_data_bytestring = decoded_data.encode('utf-8') # re-encode as bytestring for suffix check (for src-721/svg)
                file_suffix = get_file_suffix(decoded_data_bytestring, block_index)
                ident = 'STAMP'
            elif decoded_data and type(decoded_data) is bytes:
                file_suffix = get_file_suffix(decoded_data, block_index)
                ident = 'STAMP'
            else:
                file_suffix = None
                ident = 'UNKNOWN'
        except Exception as e:
            logger.error(f"Error: {e}\n{traceback.format_exc()}")
            raise
    return ident, file_suffix


def parse_stamps_to_stamp_table(db, stamps):
    tx_fields = config.TXS_FIELDS_POSITION
    with db:
        cursor = db.cursor()
        for stamp_tx in stamps:
            (file_suffix, filename, src_data) = None, None, None
            block_index = stamp_tx[tx_fields['block_index']]
            tx_index = stamp_tx[tx_fields['tx_index']]
            tx_hash = stamp_tx[tx_fields['tx_hash']]
            stamp = convert_to_json(stamp_tx[tx_fields['data']])
            decoded_base64, stamp_base64, stamp_mimetype = get_src_or_img_data(stamp, block_index) # still base64 here
            (cpid, stamp_hash) = get_cpid(stamp, block_index, tx_hash)
            keyburn = stamp_tx[tx_fields['keyburn']]
            (ident, file_suffix) = check_decoded_data(decoded_base64, block_index)
            file_suffix = "svg" if file_suffix == "svg+xml" else file_suffix

            valid_cp_src20 = (
                ident == 'SRC-20' and cpid and
                block_index < config.CP_SRC20_BLOCK_END
                and keyburn == 1
            )
            valid_src20 = (
                valid_cp_src20 or
                (
                    ident == 'SRC-20' and not cpid
                    and block_index >= config.CP_SRC20_BLOCK_END
                    and keyburn == 1
                )
            )
            valid_src721 = (
                ident == 'SRC-721'
                and keyburn == 1
                and stamp.get('quantity') == 1
            )

            if valid_src20 and check_format(decoded_base64):
                src_data = decoded_base64
            elif valid_src20 and not check_format(decoded_base64):
                continue

            if valid_src721:
                src_data = decoded_base64
                (svg_output, file_suffix) = validate_src721_and_process(src_data, db)

            if (file_suffix in config.INVALID_BTC_STAMP_SUFFIX or (
                not valid_src20 and not valid_src721
                and ident in config.SUPPORTED_SUB_PROTOCOLS
            )):
                is_btc_stamp = None
            elif ident != 'UNKNOWN' and stamp.get('asset_longname') is  None and \
                cpid.startswith('A') or \
                (file_suffix == 'json' and (valid_src20 or valid_src721)):
                processed_stamps_list = []
                is_btc_stamp = 1
                #TOD: functionalize these queries for cleanup. WIP
                cursor.execute(f'''
                    SELECT * FROM {config.STAMP_TABLE}
                    WHERE cpid = %s AND is_btc_stamp = 1
                ''', (cpid,))
                result = cursor.fetchone()
                if result:
                    is_btc_stamp = 'INVALID_REISSUE'
                else:
                    # query the processed_stamps_dict and find a matching cpid also with a is_btc_stamp = 1
                    duplicate_on_block = next((item for item in processed_stamps_list if item["cpid"] == cpid and item["is_btc_stamp"] == 1), None)
                    if duplicate_on_block is not None:
                        is_btc_stamp = 'INVALID_REISSUE' 
                
                if is_btc_stamp == 1:
                    processed_stamps_dict = {
                        'tx_hash': tx_hash,
                        'cpid': cpid,
                        'is_btc_stamp': is_btc_stamp
                    }
                    processed_stamps_list.append(processed_stamps_dict)
                else:
                    is_btc_stamp = None

            else:
                is_btc_stamp = None

            logger.warning(f'''
                block_index: {block_index}
                cpid: {cpid}
                ident: {ident}
                keyburn: {keyburn}
                file_suffix: {file_suffix}
                is valid src20 in cp: {valid_cp_src20}
                is valid src 20: {valid_src20}
                is valid src 721: {valid_src721}
                is bitcoin stamp: {is_btc_stamp}
            ''')
            filename = f"{tx_hash}.{file_suffix}"

            if not stamp_mimetype and file_suffix in config.MIME_TYPES:
                stamp_mimetype = config.MIME_TYPES[file_suffix]
            parsed = {
                "stamp": None,
                "block_index": block_index,
                "cpid": cpid if cpid is not None else stamp_hash,
                "creator_name": None,  # TODO: add creator_name
                "asset_longname": stamp.get('asset_longname'),
                "creator": stamp.get('issuer', stamp_tx[tx_fields['source']]),
                "divisible": stamp.get('divisible'),
                "ident": ident,
                "keyburn": keyburn,
                "locked": stamp.get('locked'),
                "message_index": stamp.get('message_index'),
                "stamp_base64": stamp_base64,
                "stamp_mimetype": stamp_mimetype,
                "stamp_url": 'https://' + config.DOMAINNAME + '/stamps/' + filename if file_suffix is not None else None,
                "supply": stamp.get('quantity'),
                "timestamp": datetime.utcfromtimestamp(
                    stamp_tx[tx_fields['block_time']]
                ).strftime('%Y-%m-%d %H:%M:%S'),
                "tx_hash": tx_hash,
                "tx_index": tx_index,
                "src_data": (
                    file_suffix == 'json' and src_data is not None and json.dumps(src_data) and (valid_src20 or valid_src721) or None
                ),
                "stamp_gen": None,  # TODO: add stamp_gen - might be able to remove this depending on how we handle numbering,
                "stamp_hash": stamp_hash,
                "is_btc_stamp": is_btc_stamp,
            } # NOTE:: we may want to insert and update on this table in the case of a reindex where we don't want to remove data....
            cursor.execute(f'''
                          INSERT INTO {config.STAMP_TABLE}(
                                stamp, block_index, cpid, asset_longname,
                                creator, divisible, keyburn, locked,
                                message_index, stamp_base64,
                                stamp_mimetype, stamp_url, supply, timestamp,
                                tx_hash, tx_index, src_data, ident,
                                creator_name, stamp_gen, stamp_hash,
                                is_btc_stamp
                                ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
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
                                parsed['creator_name'], parsed['stamp_gen'],
                                parsed['stamp_hash'], parsed['is_btc_stamp']
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
