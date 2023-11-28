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
from src721 import validate_src721_and_process
from src20 import check_format, build_src20_svg_string
import traceback
from src.aws import check_existing_and_upload_to_s3
from whitelist import is_tx_in_whitelist, is_to_include, is_to_exclude

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
    

def get_creator_name(block_cursor, address):
    block_cursor.execute(f'''
        SELECT creator FROM creator
        WHERE address = %s 
    ''', (address,))
    return block_cursor.fetchone()


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
    cpid = stamp.get('cpid', None)
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
                # Note: base64 cli returns success on MAC when on linux it returns an error code. 
                # this will be ok in the docker containers, but a potential problem
                # will need to verify that there are no instances where this is su
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


def is_json_string(s):
    try:
        s = s.strip()  # DEBUG: This was for one src-721 that was currently in production. need to review/test reparse. 
        s = s.rstrip('\r\n')  
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
def get_stamp_key(tx_hash):
    url = f"https://stampchain.io/api/stamps?tx_hash={tx_hash}"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()  # Return the response as a JSON object
    else:
        return None  # Return None if the request was not successful


def parse_tx_to_stamp_table(db, block_cursor, tx_hash, source, destination, btc_amount, fee, data, decoded_tx, keyburn, 
                            tx_index, block_index, block_time, is_op_return,  processed_in_block):
    (file_suffix, filename, src_data, is_reissue, file_obj_md5, src_20_dict, src_20_string, is_btc_stamp) = (
        None, None, None, None, None, None, None, None
    )
    if data is None or data == '':
        return
    stamp = convert_to_json(data)
    decoded_base64, stamp_base64, stamp_mimetype = get_src_or_img_data(stamp, block_index)
    (cpid, stamp_hash) = get_cpid(stamp, block_index, tx_hash)
    (ident, file_suffix, decoded_base64) = check_decoded_data(decoded_base64, block_index)
    file_suffix = "svg" if file_suffix == "svg+xml" else file_suffix

    creator_name = get_creator_name(block_cursor, source)

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
        and stamp.get('quantity') <= 1 # A407879294639844200 is 0 qty
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
        # TODO: add a list of src721 tx to build for each block like we do with dupe on block below.
        (svg_output, file_suffix) = validate_src721_and_process(src_data, db)
        decoded_base64 = svg_output
        file_suffix = 'svg'

    # DEBUG / VALIDATION ONLY - REMOVE AFTER VALIDATION
    is_whitelisted = None
    if is_op_return:
        is_whitelisted = is_tx_in_whitelist(tx_hash)
    # -------- remove above

    if (
        ident != 'UNKNOWN' and stamp.get('asset_longname') is None
        and cpid.startswith('A') and file_suffix not in config.INVALID_BTC_STAMP_SUFFIX
        and (not is_op_return or (is_op_return and is_whitelisted))
        or (file_suffix == 'json' and (valid_src20 or valid_src721))
    ):
        is_btc_stamp = 1

    reissue_result = None
    if cpid:
        block_cursor.execute(f'''
            SELECT * FROM {config.STAMP_TABLE}
            WHERE cpid = %s AND is_btc_stamp = 1
        ''', (cpid,))
        reissue_result = block_cursor.fetchone()
    if reissue_result:
        is_btc_stamp = None # invalid reissuance
        is_reissue = 1
    else:
        duplicate_on_block = next(
            (
                item for item in processed_in_block
                if item["cpid"] == cpid and item["is_btc_stamp"] == 1
            ),
            None
        )
        if duplicate_on_block is not None:
            is_btc_stamp = None # invalid reissuance
            is_reissue = 1

        processed_stamps_dict = {
            'tx_hash': tx_hash,
            'cpid': cpid,
            'is_btc_stamp': is_btc_stamp
        }
        processed_in_block.append(processed_stamps_dict)

    stamp_number = get_next_stamp_number(db) if is_btc_stamp else None

    if not stamp_mimetype and file_suffix in config.MIME_TYPES:
        stamp_mimetype = config.MIME_TYPES[file_suffix]

    if (
        ident in config.SUPPORTED_SUB_PROTOCOLS
        or file_suffix in config.MIME_TYPES
    ):
        if type(decoded_base64) is str:
            decoded_base64 = decoded_base64.encode('utf-8')
        filename = f"{tx_hash}.{file_suffix}"
        file_obj_md5 = store_files(filename, decoded_base64, stamp_mimetype)

    # DEBUG: this is for debugging / validation only against stampchain prod api
    if is_to_include(tx_hash):
        stamp_number = None
        is_btc_stamp = None
    api_stamp_num = None
    api_tx_hash = None

    #  debug_stamp_api = get_stamp_key(tx_hash)
    #  if debug_stamp_api is None and debug_stamp_api[0] is None and is_btc_stamp == 1:
    #      api_stamp_num = debug_stamp_api[0].get('stamp')
    #  elif debug_stamp_api:
    #      api_tx_hash = debug_stamp_api[0].get('tx_hash')
    #      api_stamp_num = debug_stamp_api[0].get('stamp')
    if is_to_exclude(tx_hash):
        stamp_number = api_stamp_num
        is_btc_stamp = 1 # temporarily add this to the db to keep numbers in sync

    logger.warning(f'''
        block_index: {block_index}
        cpid: {cpid}
        stamp_number: {stamp_number}
        api_stamp_num: {api_stamp_num}
        ident: {ident}
        keyburn: {keyburn}
        creator_name: {creator_name}
        file_suffix: {file_suffix}
        is valid src20 in cp: {valid_cp_src20}
        is valid src 20: {valid_src20}
        is valid src 721: {valid_src721}
        is bitcoin stamp: {is_btc_stamp}
        is_reissue: {is_reissue}
        stamp_mimetype: {stamp_mimetype}
        file_hash: {file_obj_md5}
        tx_hash: {tx_hash}
        api_tx_hash: {api_tx_hash}
        is_op_return: {is_op_return}
        is_whitelisted: {is_whitelisted}
        src_data: {src_data}
        src_string: {src_20_string}
        is_reissue: {is_reissue}
    ''')

    # DEBUG: Validation against stampchain API numbers. May want to validate against akash records instead
    #  if api_stamp_num != stamp_number:
    #      print("we found a mismatch - api:", api_stamp_num, "vs:", stamp_number)
    #      input("Press Enter to continue...")
    #  if is_btc_stamp and api_tx_hash != tx_hash:
    #      print("we found a mismatch - api:", api_tx_hash, "vs:", tx_hash)
    #      input("Press Enter to continue...")


    parsed = {
        "stamp": stamp_number,
        "block_index": block_index,
        "cpid": cpid if cpid is not None else stamp_hash,
        "creator_name": creator_name,
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
                src_data if src_data is not None and (valid_src20 or valid_src721) else json.dumps(src_20_string)
            ),
        "stamp_hash": stamp_hash,
        "is_btc_stamp": is_btc_stamp,
        "is_reissue": is_reissue,
        "file_hash": file_obj_md5
    }  # NOTE:: we may want to insert and update on this table in the case of a reindex where we don't want to remove data....
    # logger.warning(f"parsed: {json.dumps(parsed, indent=4, separators=(', ', ': '), ensure_ascii=False)}")
    block_cursor.execute(f'''
                    INSERT INTO {config.STAMP_TABLE}(
                        stamp, block_index, cpid, asset_longname,
                        creator, divisible, keyburn, locked,
                        message_index, stamp_base64,
                        stamp_mimetype, stamp_url, supply, timestamp,
                        tx_hash, tx_index, src_data, ident,
                        creator_name, stamp_hash,
                        is_btc_stamp, is_reissue, file_hash
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
                        parsed['creator_name'],
                        parsed['stamp_hash'], parsed['is_btc_stamp'],
                        parsed['is_reissue'], parsed['file_hash']
                    ))


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
        print("uploading to aws")  # FIXME: there may be cases where we want both aws and disk storage
        check_existing_and_upload_to_s3(
            filename, mime_type, file_obj, file_obj_md5
        )
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
        cwd = os.path.abspath(os.getcwd())
        base_directory = os.path.join(cwd, "files")
        os.makedirs(base_directory, mode=0o777, exist_ok=True)
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
