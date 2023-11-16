import logging
import json
import base64
import pybase64
from datetime import datetime
import hashlib
import magic
import subprocess

import config
from xcprequest import parse_base64_from_description
from bitcoin.core.script import CScript, OP_RETURN
from src721 import create_src721_mint_svg, get_src721_svg_string

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
                   DELETE FROM StampTableV4
                   WHERE block_index >= %s
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
        return json.loads(json_string)


def decode_base64_json(base64_string):
    try:
        decoded_data = base64.b64decode(base64_string)
        json_string = decoded_data.decode('utf-8')
        return json.loads(json_string)
    except Exception as e:
        print(f"Error decoding json: {e}")
        return None


def decode_base64_with_repair(base64_string):
    ''' original function which attemts to add padding to "fix" the base64.
    This was resulting in invalid/corrupted images. '''
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
    if 'description' not in stamp:
        if 'p' in stamp or 'P' in stamp and stamp.get('p').upper() == 'SRC-20':
            return stamp, None
        elif 'p' in stamp or 'P' in stamp and stamp.get('p').upper() == 'SRC-721':
            # TODO: add src-721 decoding and details here
            return stamp, None
    else:
        stamp_description = stamp.get('description')
        base64_string, stamp_mimetype = parse_base64_from_description(
            stamp_description
        )
        # if decoded base64 string is src-721 or src-20 return the json
        decoded_base64 = decode_base64(base64_string, block_index)
        return decoded_base64, stamp_mimetype
        # return decode_base64_json(stamp.get('description').split(':')[1])


def check_custom_suffix(bytestring_img_data):
    ''' for items that aren't part of the magic module that we want to include '''
    if bytestring_img_data[:3] == b'BMN':
        return True
    else:
        return None


def get_file_suffix(bytestring_img_data, block_index):
    print(block_index, config.BMN_BLOCKSTART)
    if block_index > config.BMN_BLOCKSTART:
        if check_custom_suffix(bytestring_img_data):
            return 'bmn'
    try:
        json.loads(bytestring_img_data.decode('utf-8'))
        return 'json'
    except (json.JSONDecodeError, UnicodeDecodeError):
        # If it failed to decode as UTF-8 text, pass it to magic to determine the file type
        if block_index > 797200: # after this block we attempt to strip whitespace from the beginning of the binary data to catch Mikes A12333916315059997842
            file_type = magic.from_buffer(bytestring_img_data.lstrip(), mime=True)
        else:
            file_type = magic.from_buffer(bytestring_img_data, mime=True)
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
    for vout in transaction["vout"]:
        script_pub_key = vout["scriptPubKey"]
        asm = script_pub_key["asm"]
        if "OP_CHECKMULTISIG" in asm:
            for burnkey in config.BURNKEYS:
                if burnkey in asm:
                    return True
    return False


def is_json_string(s):
    try:
        json.loads(s)
        return True
    except json.JSONDecodeError:
        return False


def parse_stamps_to_stamp_table(db, stamps):
    tx_fields = config.TXS_FIELDS_POSITION
    with db:
        cursor = db.cursor()
        for stamp_tx in stamps:
            stamp_base64 = None
            block_index = stamp_tx[tx_fields['block_index']]
            tx_index = stamp_tx[tx_fields['tx_index']]
            tx_hash = stamp_tx[tx_fields['tx_hash']]
            stamp = clean_and_load_json(stamp_tx[tx_fields['data']])
            src_data, stamp_mimetype = get_src_or_img_data(stamp, block_index)
            cpid, stamp_hash = get_cpid(stamp, block_index, tx_hash)
            if type(src_data) is bytes:
                src_data = src_data.decode('utf-8')
                
            if type(src_data) is str and is_json_string(src_data):
                # TODO: invalidate src-20 on CP after block CP_SRC20_BLOCK_END
                if isinstance(json.loads(src_data), dict):
                    src_data = {k.lower(): v for k, v in json.loads(src_data).items()}
                ident = False
                if src_data and src_data.get('p') and src_data.get('p').upper() in ['SRC-721', 'SRC-20']:
                    ident = src_data['p'].upper()
                    file_suffix = 'json'
                else:
                    ident = 'UNKNOWN'
                    continue # TODO: Determine if this we don't want save to StampTableV4 if not 721/20 JSON?
            else:
                # we are assuming if the src_data does not decode to a json string it's a base64 string perhaps add more checks
                stamp_base64 = src_data
                ident = 'STAMP'
                src_data is None
                try:
                    file_suffix = get_file_suffix(stamp_base64, block_index)
                    print(f"file_suffix: {file_suffix}") #DEBUG
                except Exception as e:
                    print(f"Error: {e}")
                    raise
                try: 
                    pass
                    # TODO: this is super redundant since we parse the transaction previously and are hitting bitcoin core again here
                    # decoded_tx = get_decoded_tx_with_retries(tx_hash)
                except:
                    print(f"ERROR: Failed to get decoded transaction for {tx_hash} after retries. Exiting.")
                    raise
            
            # TODO: more validation if this is a valid btc_stamp
           
            # need to check keyburn for src-721 or they are not valid

            if ident == 'SRC-721':
                op_val = src_data.get("op", None).upper()
                if 'symbol' in src_data:
                    src_data['tick'] = src_data.pop('symbol')
                if op_val == "MINT":
                    svg_output = create_src721_mint_svg(src_data, db)
                    file_suffix = 'svg'
                elif op_val == "DEPLOY":
                    deploy_description = src_data.get("description", None)
                    deploy_name = src_data.get("name", None)
                    svg_output = get_src721_svg_string(deploy_name, deploy_description)
                    file_suffix = 'svg'
                else:
                    svg_output = get_src721_svg_string("SRC-721", "stampchain.io")
                    file_suffix = 'svg'

            file_suffix = "svg" if file_suffix == "svg+xml" else file_suffix
            # if file_suffix in ["plain", "octet-stream", "js", "css", "x-empty", "json"]: # these are not btc_stamps
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
                "keyburn": None,  # TODO: add keyburn -- should check while we are parsing through the transactions
                "locked": stamp.get('locked'),
                "message_index": stamp.get('message_index'),
                "stamp_base64": stamp_base64,
                "stamp_mimetype": stamp_mimetype,
                "stamp_url": None,  # TODO: add stamp_url
                "supply": stamp.get('quantity'),
                "timestamp": datetime.utcfromtimestamp(
                    stamp_tx[tx_fields['block_time']]
                ).strftime('%Y-%m-%d %H:%M:%S'),
                "tx_hash": tx_hash,
                "tx_index": tx_index,
                "src_data": json.dumps(src_data),
                "stamp_gen": None,  # TODO: add stamp_gen,
                "stamp_hash": stamp_hash,
            }
            cursor.execute('''
                           INSERT INTO StampTableV4(
                                stamp, block_index, cpid, asset_longname,
                                creator, divisible, keyburn, locked,
                                message_index, stamp_base64,
                                stamp_mimetype, stamp_url, supply, timestamp,
                                tx_hash, tx_index, src_data, ident,
                                creator_name, stamp_gen, stamp_hash
                                ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                                %s,%s,%s,%s,%s,%s,%s,%s,%s)
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
                                parsed['stamp_hash'],
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
