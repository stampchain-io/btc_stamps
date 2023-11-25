import logging
import json
import base64
import pybase64
from datetime import datetime
import hashlib
import magic
import subprocess
import ast
import requests
import os
import zlib
import msgpack
import io


import config
from xcprequest import parse_base64_from_description
from bitcoin.core.script import CScript, OP_RETURN
from src721 import validate_src721_and_process
from src20 import check_format, build_src20_svg_string
import traceback
import src.script as script
from src.aws import check_existing_and_upload_to_s3

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
    ''' method on and after block 784550 - this will result in more invalid base64 strings since don't attempt repair of padding '''
    if block_index <= 784550:
        image_data = decode_base64_with_repair(base64_string)
        return image_data
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


def get_src_or_img_data(stamp, block_index):
    # if this is src-20 on bitcoin we have already decoded
    # the string in the transaction table
    stamp_mimetype, decoded_base64, base64_string = None, None, None
    if 'description' not in stamp: # for src-20
        if 'p' in stamp or 'P' in stamp and stamp.get('p').upper() == 'SRC-20':
            return stamp, None, None # update mime/type when we start creating img
        elif 'p' in stamp or 'P' in stamp and stamp.get('p').upper() == 'SRC-721':
            # TODO: add src-721 decoding and details here
            return stamp, None, None # update mimetype when we start creating img
    else:
        stamp_description = stamp.get('description')
        if stamp_description is None:
            return None, None, None
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


def reformat_src_string(decoded_data):
    decoded_data = json.loads(decoded_data)
    decoded_data = {k.lower(): v for k, v in decoded_data.items()}
    if decoded_data and decoded_data.get('p') and decoded_data.get('p').upper() in config.SUPPORTED_SUB_PROTOCOLS:
        ident = decoded_data['p'].upper()
        file_suffix = 'json'
    else:
        file_suffix = None
        ident = 'UNKNOWN'
    return ident, file_suffix


def zlib_decompress(compressed_data):
    try:
        uncompressed_data = zlib.decompress(compressed_data) # suffix = plain /  Uncompressed data: b'\x85\xa1p\xa6src-20\xa2op\xa6deploy\xa4tick\xa4ordi\xa3max\xa821000000\xa3lim\xa41000'
        decoded_data = msgpack.unpackb(uncompressed_data) #  {'p': 'src-20', 'op': 'deploy', 'tick': 'kevin', 'max': '21000000', 'lim': '1000'}
        json_string = json.dumps(decoded_data)
        file_suffix = "json"
        ident, file_suffix = reformat_src_string(json_string)
        # FIXME: we will need to return the json_string to import into the srcx table or import from here
        return ident, file_suffix, json_string
    except zlib.error:
        print("EXCLUSION: Error decompressing zlib data")
        return 'UNKNOWN', 'zlib', compressed_data
    except msgpack.exceptions.ExtraData:
        print("EXCLUSION: Error decoding MessagePack data")
        return 'UNKNOWN', 'zlib', compressed_data
    except TypeError:
        print("EXCLUSION: The decoded data is not JSON-compatible")
        return 'UNKNOWN', 'zlib', compressed_data


def check_decoded_data(decoded_data, block_index):
    ''' this can come in as a json string or text (in the case of svg's)'''
    file_suffix = None
    if type(decoded_data) is bytes:
        try:
            decoded_data = decoded_data.decode('utf-8') 
        except Exception as e:
            pass
    if (type(decoded_data) is str and is_json_string(decoded_data)):
        ident, file_suffix = reformat_src_string(decoded_data)
        # FIXME: we will need to return the json_string to import into the srcx table or import from here
    else:
        try:
            if decoded_data and type(decoded_data) is str:
                decoded_data_bytestring = decoded_data.encode('utf-8')
                file_suffix = get_file_suffix(decoded_data_bytestring, block_index)
                ident = 'STAMP'
            elif decoded_data and type(decoded_data) is bytes:
                file_suffix = get_file_suffix(decoded_data, block_index)
                if file_suffix in ['zlib']:
                    ident, file_suffix, decoded_data = zlib_decompress(decoded_data)
                else:
                    ident = 'STAMP'
            else:
                file_suffix = None
                ident = 'UNKNOWN'
        except Exception as e:
            logger.error(f"Error: {e}\n{traceback.format_exc()}")
            raise
    return ident, file_suffix, decoded_data


# for debug / validation temporarily
def get_stamp_key(cpid):
    url = f"https://stampchain.io/api/stamps?cpid={cpid}"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()  # Return the response as a JSON object
    else:
        return None  # Return None if the request was not successful


def parse_tx_to_stamp_table(db, block_cursor, tx_hash, source, destination, btc_amount, fee, data, decoded_tx, keyburn, tx_index, block_index, block_time):
    (file_suffix, filename, src_data, is_reissue, file_obj_md5) = None, None, None, None, None
    if data is None or data == '':
        return
    stamp = convert_to_json(data)
    decoded_base64, stamp_base64, stamp_mimetype = get_src_or_img_data(stamp, block_index)
    (cpid, stamp_hash) = get_cpid(stamp, block_index, tx_hash)
    #FIXME: This is assuming decoded base64 is a bytestring (aka the image for src20/721 has been created)
    (ident, file_suffix, decoded_base64) = check_decoded_data(decoded_base64, block_index)
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

    if valid_src20:
        src_20_string = check_format(decoded_base64)
        src_20_dict = None
        if src_20_string:
            src_20_dict = decoded_base64
            is_btc_stamp = 1
            decoded_base64 = build_src20_svg_string(block_cursor, src_20_string)
            file_suffix = 'svg'
        elif valid_src20 and not src_20_dict:
            return

    if valid_src721:
        src_data = decoded_base64
        is_btc_stamp = 1
        (svg_output, file_suffix) = validate_src721_and_process(src_data, db)
        decoded_base64 = svg_output
        file_suffix = 'svg'

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
        block_cursor.execute(f'''
            SELECT * FROM {config.STAMP_TABLE}
            WHERE cpid = %s AND is_btc_stamp = 1
        ''', (cpid,))
        result = block_cursor.fetchone()
        if result:
            is_btc_stamp = 'INVALID_REISSUE'
            # reissunace of a stamp
            is_reissue = 1
        else:
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

    stamp_number = get_next_stamp_number(db) if is_btc_stamp else None

    if not stamp_mimetype and file_suffix in config.MIME_TYPES:
        stamp_mimetype = config.MIME_TYPES[file_suffix]

     # we won't try to save the file/image of a plaintext, etc. eg. cpid: ESTAMP
    if ident in config.SUPPORTED_SUB_PROTOCOLS or file_suffix in config.MIME_TYPES:
        filename = f"{tx_hash}.{file_suffix}"
        file_obj_md5 = store_files(filename, decoded_base64, stamp_mimetype)

    # debug / validation - add breakpoints to check if we are indexing correcly :) 
    debug_stamp_api = get_stamp_key(cpid)
    if debug_stamp_api is None and debug_stamp_api[0] is None and is_btc_stamp == 1:
        print("this is not a valid stamp, but we flagged as such")
    elif debug_stamp_api and is_btc_stamp is None:
        api_tx_hash = debug_stamp_api[0].get('tx_hash')
        api_stamp_num = debug_stamp_api[0].get('stamp')

        if tx_hash == api_tx_hash:
            print("this is a valid stamp, but we did not flag as such ", api_stamp_num)

    logger.warning(f'''
        block_index: {block_index}
        cpid: {cpid}
        stamp_number: {stamp_number}
        ident: {ident}
        keyburn: {keyburn}
        file_suffix: {file_suffix}
        is valid src20 in cp: {valid_cp_src20}
        is valid src 20: {valid_src20}
        is valid src 721: {valid_src721}
        is bitcoin stamp: {is_btc_stamp}
        is_reissue: {is_reissue}
        stamp_mimetype: {stamp_mimetype}
        file_hash: {file_obj_md5}
    ''')

    parsed = {
        "stamp": stamp_number,
        "block_index": block_index,
        "cpid": cpid if cpid is not None else stamp_hash,
        "creator_name": None,  # TODO: add creator_name - this is the issuer in CP, and source in BTC
        "asset_longname": stamp.get('asset_longname'),
        "creator": source,
        "divisible": stamp.get('divisible'),
        "ident": ident,
        "keyburn": keyburn,
        "locked": stamp.get('locked'),
        "message_index": stamp.get('message_index'),
        "stamp_base64": stamp_base64,
        "stamp_mimetype": stamp_mimetype,
        "stamp_url": 'https://' + config.DOMAINNAME + '/stamps/' + filename if file_suffix is not None and filename is not None else None,
        "supply": stamp.get('quantity'),
        "timestamp": datetime.utcfromtimestamp(
            block_time
        ).strftime('%Y-%m-%d %H:%M:%S'),
        "tx_hash": tx_hash,
        "tx_index": tx_index,
        "src_data": (
            file_suffix == 'json' and src_data is not None and json.dumps(src_data) and (valid_src20 or valid_src721) or None
        ),
        "stamp_gen": None,  # TODO: add stamp_gen - might be able to remove this column depending on how we handle numbering, this was temporary in prior indexing
        "stamp_hash": stamp_hash,
        "is_btc_stamp": is_btc_stamp,
        "is_reissue": is_reissue,
        "file_hash": file_obj_md5
    }  # NOTE:: we may want to insert and update on this table in the case of a reindex where we don't want to remove data....
    block_cursor.execute(f'''
                    INSERT INTO {config.STAMP_TABLE}(
                        stamp, block_index, cpid, asset_longname,
                        creator, divisible, keyburn, locked,
                        message_index, stamp_base64,
                        stamp_mimetype, stamp_url, supply, timestamp,
                        tx_hash, tx_index, src_data, ident,
                        creator_name, stamp_gen, stamp_hash,
                        is_btc_stamp, is_reissue
                        ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
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
                        parsed['stamp_hash'], parsed['is_btc_stamp'],
                        parsed['is_reissue']
                    ))
    #  cursor.execute("COMMIT") # commit with the parent block commit


def get_next_stamp_number(db):
    """Return index of next transaction."""
    cursor = db.cursor()

    cursor.execute(f'''
        SELECT stamp FROM {config.STAMP_TABLE}
        WHERE stamp = (SELECT MAX(stamp) from {config.STAMP_TABLE})
    ''')
    stamps = cursor.fetchall()
    if stamps:
        assert len(stamps) == 1
        stamp_number = stamps[0][0] + 1
    else:
        stamp_number = 0

    cursor.close()

    return stamp_number

def get_fileobj_and_md5(decoded_base64):
    if decoded_base64 is None:
        logger.warning("decoded_base64 is None")
        return None, None
    try:
        file_obj = io.BytesIO(decoded_base64)
        file_obj.seek(0)
        file_obj_md5 = hashlib.md5(file_obj.read()).hexdigest()
        return file_obj, file_obj_md5
    except Exception as e:
        logger.error(f"Error: {e}\n{traceback.format_exc()}")
        raise

def store_files(filename, decoded_base64, mime_type):
    file_obj, file_obj_md5 = get_fileobj_and_md5(decoded_base64)
    if config.AWS_SECRET_ACCESS_KEY and config.AWS_ACCESS_KEY_ID:
        print("uploading to aws") #FIXME: there may be cases where we want both aws and disk storage
        check_existing_and_upload_to_s3(filename, mime_type, file_obj, file_obj_md5)
    else:
        store_files_to_disk(filename, decoded_base64)
    return file_obj_md5


def store_files_to_disk(filename, decoded_base64):
    if decoded_base64 is None:
        logger.warning("decoded_base64 is None")
        return
    if filename is None:
        logger.warning("filename is None")
        return
    try:
        pwd = os.environ.get("PWD", '/usr/src/app')
        base_directory = os.path.join(pwd, "files")
        os.makedirs(base_directory, exist_ok=True)
        file_path = os.path.join(base_directory, filename)
        with open(file_path, "wb") as f:
            f.write(decoded_base64)
    except Exception as e:
        logger.error(f"Error: {e}\n{traceback.format_exc()}")
        raise


def update_parsed_block(block_index, db):
    db.ping(reconnect=True)
    cursor = db.cursor()
    cursor.execute('''
                    UPDATE blocks SET indexed = 1
                    WHERE block_index = %s
                    ''', (block_index,))
    cursor.execute("COMMIT")
