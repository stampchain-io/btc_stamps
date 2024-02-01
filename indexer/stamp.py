import logging
import json
import base64
import pybase64
import hashlib
import magic
import subprocess
import ast
import requests
import os
import zlib
import msgpack
import io
from datetime import datetime
from decimal import Decimal

import config
import src.log as log
from xcprequest import parse_base64_from_description
from src721 import validate_src721_and_process
from src20 import (
    check_format,
    build_src20_svg_string,
    process_src20_trx,
)
import traceback
from src.aws import (
    check_existing_and_upload_to_s3,
)

logger = logging.getLogger(__name__)
log.set_logger(logger)  # set root logger


def purge_block_db(db, block_index):
    """Purge transactions from the database. This is for a reorg or
        where transactions were partially commited. 

    Args:
        db (Database): The database object.
        block_index (int): The block index from which to start purging.

    Returns:
        None
    """
    cursor = db.cursor()
    
    tables = [
        'transactions',
        'blocks',
        config.STAMP_TABLE,
        'SRC20',
        'SRC20Valid'
    ]

    for table in tables:
        logger.warning("Purging {} from database after block: {}".format(table, block_index))
        cursor.execute('''
                        DELETE FROM {}
                        WHERE block_index >= %s
                        '''.format(table), (block_index,))
        
    db.commit()
    cursor.close()


def is_prev_block_parsed(db, block_index):
    """
    Check if the previous block has been parsed and indexed.

    Args:
        db (DatabaseConnection): The database connection object.
        block_index (int): The index of the current block.

    Returns:
        bool: True if the previous block has been parsed and indexed, False otherwise.
    """
    block_fields = config.BLOCK_FIELDS_POSITION
    cursor = db.cursor()
    cursor.execute('''
                   SELECT * FROM blocks
                   WHERE block_index = %s
                   ''', (block_index - 1,))
    block = cursor.fetchone()
    cursor.close()
    if block[block_fields['indexed']] == 1:
        return True
    else:
        purge_block_db(db, block_index - 1)
        rebuild_balances(db)
        return False


def rebuild_balances(db):
    cursor = db.cursor()

    try:
        db.begin()  # Start a transaction

        query = """
        SELECT op, creator, destination, tick, tick_hash, amt, block_time, block_index
        FROM SRC20Valid
        WHERE op = 'TRANSFER' OR op = 'MINT'
        """
        cursor.execute(query)
        src20_valid_list = cursor.fetchall()

        query = """
        DELETE FROM balances
        """
        cursor.execute(query)

        logger.warning("Purging and rebuilding {} table".format('balances'))
        all_balances = {}
        for [op, creator, destination, tick, tick_hash, amt, block_time, block_index] in src20_valid_list:
            destination_id = tick + '_' + destination
            destination_amt = Decimal(0) if destination_id not in all_balances else all_balances[destination_id]['amt']
            destination_amt += amt

            all_balances[destination_id] = {
                'tick': tick,
                'tick_hash': tick_hash,
                'address': destination,
                'amt': destination_amt,
                'last_update': block_index,
                'block_time': block_time
            }

            if op == 'TRANSFER':
                creator_id = tick + '_' + creator
                creator_amt = Decimal(0) if creator_id not in all_balances else all_balances[creator_id]['amt']
                creator_amt -= amt
                all_balances[creator_id] = {
                    'tick': tick,
                    'tick_hash': tick_hash,
                    'address': creator,
                    'amt': creator_amt,
                    'last_update': block_index,
                    'block_time': block_time
                }

        logger.warning("Inserting {} balances".format(len(all_balances)))

        cursor.executemany('''INSERT INTO balances(id, tick, tick_hash, address, amt, last_update, block_time, p)
                            VALUES(%s,%s,%s,%s,%s,%s,%s,%s)''', [(key, value['tick'], value['tick_hash'], value['address'], value['amt'],
                            value['last_update'], value['block_time'], 'SRC-20') for key, value in all_balances.items()])


        db.commit() 

    except Exception as e:
        db.rollback()
        raise e

    finally:
        cursor.close()


def base62_encode(num):
    """
    Encodes a given number into a base62 string.

    Args:
        num (int): The number to be encoded.

    Returns:
        str: The base62 encoded string.
    """
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
    """
    Creates a base62 hash from two input strings.

    Args:
        str1 (str): The first input string.
        str2 (str): The second input string.
        length (int, optional): The desired length of the base62 hash. Must be between 12 and 20 characters. Defaults to 20.

    Returns:
        str: The base62 hash of the combined input strings, truncated to the specified length.
    
    Raises:
        ValueError: If the length is not between 12 and 20 characters.
    """
    if not 12 <= length <= 20:
        raise ValueError("Length must be between 12 and 20 characters")
    combined_str = str1 + "|" + str2
    hash_bytes = hashlib.sha256(combined_str.encode()).digest()
    hash_int = int.from_bytes(hash_bytes, byteorder='big')
    base62_hash = base62_encode(hash_int)
    return base62_hash[:length]


def get_cpid(stamp, block_index, tx_hash):
    """
    Get the CPID (Counterpart Identifier aka ASSET) for a given stamp.

    Args:
        stamp (dict): The stamp dictionary.
        block_index (int): The block index.
        tx_hash (str): The transaction hash.

    Returns:
        tuple: A tuple containing the CPID and the base62 hash.

    """
    cpid = stamp.get('cpid', None)
    return cpid, create_base62_hash(tx_hash, str(block_index), 20)


def clean_json_string(json_string):
    """
    Cleans a JSON string by replacing single quotes with spaces and removing null bytes.
    THis is so a proper string may be inserted into the Stamp Table. It is not used
    for inclusion or inclusion of src-20 tokens. 
    NOTE: this is only here because of the json data type on the Stamp Table 
    converting this to mediumblob will allow us to store malformed json strings
    which doesn't matter a whole lot because we do validation later in the SRC20 Tables. 

    Args:
        json_string (str): The JSON string to be cleaned.

    Returns:
        str: The cleaned JSON string.
    """
    json_string = json_string.replace("'", ' ')
    json_string = json_string.replace("\\x00", "") # remove null bytes
    return json_string


def convert_to_dict_or_string(input_data, output_format='dict'):
    """
    Convert the input data to a dictionary or a JSON string.
    Note this is not using encoding to convert the input string to utf-8 for example
    this is because utf-8 will not represent all of our character sets properly

    Args:
        input_data (str, bytes, dict): The input data to be converted.
        output_format (str, optional): The desired output format. Defaults to 'dict'.

    Returns:
        dict or str: The converted data in the specified output format.

    Raises:
        ValueError: If the input_data is a string representation of a dictionary but cannot be evaluated.
        Exception: If an error occurs during the conversion process.

    """

    def convert_decimal_to_string(obj):
        if isinstance(obj, Decimal):
            return str(obj)
        raise TypeError

    try:
        if isinstance(input_data, bytes):
            try:
                input_data = json.loads(input_data)
            except json.JSONDecodeError:
                # get a string representation of the bytes object
                input_data = repr(input_data)[2:-1]
                # utf8 conversion for src-20 tokens can make invalid ticks valid: 
                # .decode('utf-8') on c28966f1bf851874bb260c8d96122036700651c4ec414fca000ca8089da3176
                # original: ,"tick":"S\xd0\xa2AMP"  conversion to: ,"tick":"STAMP"
                # ie. input_data = input_data.decode('utf-8')
        if isinstance(input_data, str):
            # Check if input_data is a string representation of a dictionary
            try:
                input_data = ast.literal_eval(input_data)
            except ValueError:
                raise
 
        if isinstance(input_data, dict):
            # input_data is a dictionary, so convert it directly to a JSON string or return as a dictionary
            if output_format == 'dict':
                return input_data
            elif output_format == 'string':
                json_string = json.dumps(input_data, ensure_ascii=False, default=convert_decimal_to_string)
                return clean_json_string(json_string)
            else:
                return f"Invalid output format: {output_format}"
        else:
            return f"An error occurred: input_data is not a dictionary, string, or bytes"
    except Exception as e:
        return f"An error occurred: {e}"


def decode_base64(base64_string, block_index):
    ''' 
    Decode a base64 string into image data.
    
    Args:
        base64_string (str): The base64 encoded string to decode.
        block_index (int): The block index used for conditional decoding.
        
    Returns:
        tuple: A tuple containing the decoded image data and a boolean indicating success.
            - image_data (bytes): The decoded image data.
            - success (bool): True if decoding is successful, False otherwise.
    '''
    if block_index <= config.STOP_BASE64_REPAIR:
        image_data = decode_base64_with_repair(base64_string)
        return image_data, True
    try:
        image_data = base64.b64decode(base64_string)
        return image_data, True
    except Exception as e1:
        try:
            image_data = pybase64.b64decode(base64_string)
            return image_data, True
        except Exception as e2:
            try:
                # Note: base64 cli returns success on MAC when on linux it returns an error code. 
                # this will be ok in the docker containers, but a potential problem
                # will need to verify that there are no instances where this is su
                command = f'printf "%s" "{base64_string}" | base64 -d 2>&1'
                image_data = subprocess.run(command, shell=True, capture_output=True, text=True, check=True, stdout=subprocess.PIPE).stdout
                return image_data, True
            except Exception as e3:
                # If all decoding attempts fail, print an error message and return None
                logger.info(f"EXCLUSION: BASE64 DECODE_FAIL base64 image string: {e1}, {e2}, {e3}")
                return None, None


def decode_base64_with_repair(base64_string):
    ''' original function which attemts to add padding to "fix" the base64 string. This was resulting in invalid/corrupted images. '''
    try:
        missing_padding = len(base64_string) % 4
        if missing_padding:
            base64_string += '=' * (4 - missing_padding)

        image_data = base64.b64decode(base64_string)
        return image_data

    except Exception as e:
        logger.info(f"EXCLUSION: BASE64 DECODE_FAIL base64 image string: {e}")
        return None


def get_src_or_img_from_data(stamp, block_index):
    """
    Extracts the source or image data from the given stamp dictionary object.

    Args:
        stamp (dict): The stamp object.
        block_index (int): The block index.

    Returns:
        tuple: A tuple containing the extracted data in the following order:
            - decoded_base64 (str or None): The decoded base64 data.
            - base64_string (str or None): The original base64 string.
            - stamp_mimetype (str or None): The MIME type of the stamp.
            - is_valid_base64 (bool or None): Indicates if the base64 data is valid.
    """
    stamp_mimetype, decoded_base64, is_valid_base64 = None, None, None
    if 'description' not in stamp:
        if 'p' in stamp or 'P' in stamp and stamp.get('p').upper() == 'SRC-20':
            return stamp, None, None, 1
        elif 'p' in stamp or 'P' in stamp and stamp.get('p').upper() == 'SRC-721':
            return stamp, None, None, 1
    else:
        stamp_description = stamp.get('description')
        if stamp_description is None:
            return None, None, None, None
        base64_string, stamp_mimetype = parse_base64_from_description(
            stamp_description
        )
        decoded_base64, is_valid_base64 = decode_base64(base64_string, block_index)
        return decoded_base64, base64_string, stamp_mimetype, is_valid_base64


def check_custom_suffix(bytestring_data):
    ''' for items that aren't part of the magic module that we want to include '''
    if bytestring_data[:3] == b'BMN':
        return True
    else:
        return None


def get_file_suffix(bytestring_data, block_index):
    """
    Determines the file suffix based on the given bytestring data. The
    block index is used to determine the consensus change when we attempted
    repair on the base64 string for padding

    Args:
        bytestring_data (bytes): The bytestring data to analyze.
        block_index (int): The block index.

    Returns:
        str: The file suffix.

    Raises:
        None

    """
    if block_index > config.BMN_BLOCKSTART:
        if check_custom_suffix(bytestring_data):
            return 'bmn'
    try:
        json.loads(bytestring_data.decode('utf-8'))
        return 'json'
    except (json.JSONDecodeError, UnicodeDecodeError):
        # If it failed to decode as UTF-8 text, pass it to magic to determine the file type
        if block_index > config.STRIP_WHITESPACE: # after this block we attempt to strip whitespace from the beginning of the binary data to catch Mikes A12333916315059997842
            file_type = magic.from_buffer(bytestring_data.lstrip(), mime=True)
        else:
            file_type = magic.from_buffer(bytestring_data, mime=True)
        return file_type.split('/')[-1]


def is_json_string(s):
    """
    Check if a string is a valid JSON object.

    Args:
        s (str): The string to be checked.

    Returns:
        bool: True if the string is a valid JSON object, False otherwise.
    """
    try:
        s = s.strip() 
        s = s.rstrip('\r\n')  
        if s.startswith('{') and s.endswith('}'):
            json.loads(s)
            return True
        else:
            return False
    except json.JSONDecodeError:
        return False


def reformat_src_string_get_ident(decoded_data):
    """
    Reformat the source JSON string and extract the identifier and file suffix.

    This function takes a decoded data string as input and reformats it by converting all keys in the JSON object to lowercase.
    It then checks if the reformatted data has a key 'p' (protocol) that matches one of the supported sub-protocols defined in the 'config' module.
    If a match is found, it extracts the identifier from the 'p' key and sets the file suffix to 'json'. Otherwise, it sets the file suffix to None and the identifier to 'UNKNOWN'.

    Args:
        decoded_data (str): The decoded data string.

    Returns:
        tuple: A tuple containing the identifier and file suffix.
    """
    if not isinstance(decoded_data, dict):
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
    """
    Decompresses zlib-compressed data and returns the decompressed data as a JSON string.

    Args:
        compressed_data (bytes): The zlib-compressed data to decompress.

    Returns:
        tuple: A tuple containing the identifier, file suffix, and JSON string of the decompressed data.
            - identifier (str): The identifier of the decompressed data.
            - file_suffix (str): The file suffix indicating the format of the decompressed data.
            - json_string (str): The decompressed data as a JSON string.

    Raises:
        zlib.error: If there is an error decompressing the zlib data.
        msgpack.exceptions.ExtraData: If there is an error decoding the MessagePack data.
        TypeError: If the decoded data is not JSON-compatible.
    """
    try:
        uncompressed_data = zlib.decompress(compressed_data) # suffix = plain /  Uncompressed data: b'\x85\xa1p\xa6src-20\xa2op\xa6deploy\xa4tick\xa4ordi\xa3max\xa821000000\xa3lim\xa41000'
        decoded_data = msgpack.unpackb(uncompressed_data) #  {'p': 'src-20', 'op': 'deploy', 'tick': 'kevin', 'max': '21000000', 'lim': '1000'}
        json_string = json.dumps(decoded_data)
        file_suffix = "json"
        ident, file_suffix = reformat_src_string_get_ident(json_string)
        return ident, file_suffix, json_string
    except zlib.error:
        logger.info(f"EXCLUSION: Error decompressing zlib data")
        return 'UNKNOWN', 'zlib', compressed_data
    except msgpack.exceptions.ExtraData:
        logger.info(f"EXCLUSION: Error decoding MessagePack data")
        return 'UNKNOWN', 'zlib', compressed_data
    except TypeError:
        logger.info(f"EXCLUSION: The decoded data is not JSON-compatible")
        return 'UNKNOWN', 'zlib', compressed_data


def check_decoded_data_fetch_ident(decoded_data, block_index, ident):
    '''
    Check the decoded data and fetch the identifier and file suffix.

    Parameters:
        decoded_data (bytes or dict or str): The decoded data, which can be a bytes object, a dictionary, or a string.
        block_index (int): The block index.
        ident (str): The identifier.

    Returns:
        tuple: A tuple containing the identifier(STAMP, SRC-20/721), file suffix, and the decoded base64 data.
        If decoded base64 is a string it returns a dict

    Raises:
        Exception: If an error occurs during the process.

    '''

    ## FIXME: this is a nightmare! 

    if decoded_data is None:
        raise Exception("decoded_data is None")
    file_suffix = None
    if type(decoded_data) is bytes:
        try:
            decoded_data = decoded_data.decode('utf-8') 
        except Exception as e:
            pass
    if (type(decoded_data) is dict):
        ident, file_suffix = reformat_src_string_get_ident(decoded_data)
    elif (type(decoded_data) is str and is_json_string(decoded_data)):
        ident, file_suffix = reformat_src_string_get_ident(decoded_data)
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


def check_reissue(db, cpid, is_btc_stamp, valid_stamps_in_block):
    ''' 
    Validate if there was a prior valid stamp for the given cpid in the database or block and adjust is_btc_stamp and is_reissue.

    If stamp_base64 has changed and is not None, then this reissue is a new stamp with a new image. It is considered cursed
    as named stamp inclusions are cursed only to keep them from stamp numbering initially because of xcp fees.

    Parameters:
    - db: The database connection object.
    - cpid: The unique identifier for the stamp.
    - is_btc_stamp: A boolean indicating if the stamp is a BTC stamp.
    - valid_stamps_in_block: A list of stamps processed in the block.

    Returns:
    - is_btc_stamp: The adjusted value of is_btc_stamp after checking for reissue.
    - is_reissue: A boolean indicating if the stamp is a reissue.
    '''
    
    is_btc_stamp, is_reissue = check_reissue_in_block(valid_stamps_in_block, cpid, is_btc_stamp)
    if not is_reissue:
        is_btc_stamp, is_reissue = check_reissue_in_db(db, cpid, is_btc_stamp)

    return is_btc_stamp, is_reissue


def check_reissue_in_db(db, cpid, is_btc_stamp):
    """
    Check if there is a reissue in the database for a given cpid.

    Parameters:
    - db: The database connection object.
    - cpid: The unique identifier for the stamp.
    - is_btc_stamp: A boolean indicating if the stamp is a BTC stamp.
    - is_reissue: A boolean indicating if the stamp is a reissue.

    Returns:
    - is_btc_stamp: The updated value of is_btc_stamp.
    - is_reissue: The flag indicating if there is a reissue (1) or not (None).

    Note: This could be cached, but there are probably not a lot of updates on the same asset anyway.
    """
    is_reissue = None
    with db.cursor() as cursor:
        cursor.execute(f'''
            SELECT is_btc_stamp, is_valid_base64, stamp FROM {config.STAMP_TABLE}
            WHERE cpid = %s and is_valid_base64 is not null
            ORDER BY block_index DESC
            LIMIT 1
        ''', (cpid,))
        reissue_results = cursor.fetchall()
        if reissue_results:
            is_btc_stamp = None
            is_reissue = 1
            # prior_is_btc_stamp, prior_is_valid_base64, prior_stamp = reissue_results[0]
            # if prior_is_btc_stamp or prior_is_valid_base64: # and stamp >= 0: -- all reissuances of valid stamp: are not btc_stamps
            #     is_btc_stamp = None
            #     is_reissue = 1
            #     if current_stamp_base64 is not None and current_is_valid_base64 is not None and current_stamp_base64 != prior_stamp_base64 :
            #         is_cursed = 1
            #     return is_btc_stamp, is_reissue, is_cursed
            # else:
            #     is_reissue = 1
        return is_btc_stamp, is_reissue


def check_reissue_in_block(valid_stamps_in_block, cpid, is_btc_stamp):
    """
    Check if a reissue is present in the processed block.

    Args:
        valid_stamps_in_block (list): List of items processed in the block.
        cpid (str): CPID value to check.
        is_btc_stamp (int): Flag indicating if the item is a BTC stamp.
        is_reissue (int): Flag indicating if the item is a reissue.

    Returns:
        tuple: A tuple containing the updated values of is_btc_stamp and is_reissue.
    """
    is_reissue  = None
    if valid_stamps_in_block:
        for item in reversed(valid_stamps_in_block):
            if item["cpid"] == cpid and (item["is_btc_stamp"] or item["is_cursed)"]):
                is_btc_stamp = None 
                is_reissue = 1
                break
                # return is_btc_stamp, is_reissue
                # if (item["is_btc_stamp"] or item["is_valid_base64"]): # and item["stamp"] >= 0:
                #     is_btc_stamp = None 
                #     is_reissue = 1
                #     return is_btc_stamp, is_reissue
                # else:
                #     is_reissue = 1
    return is_btc_stamp, is_reissue



def parse_tx_to_stamp_table(db, tx_hash, source, destination, btc_amount, fee, data, decoded_tx, keyburn, 
                            tx_index, block_index, block_time, is_op_return,  valid_stamps_in_block, valid_src20_in_block):
    
    (file_suffix, filename, src_data, is_reissue, file_obj_md5, is_btc_stamp, ident, is_valid_base64, is_cursed) = (
        None, None, None, None, None, None, None, None, None)
    
    stamp_cursor = db.cursor()
    if data is None or data == '':
        return
    stamp = convert_to_dict_or_string(data, output_format='dict')
    if not isinstance(stamp, dict):
        return
    decoded_base64, stamp_base64, stamp_mimetype, is_valid_base64  = get_src_or_img_from_data(stamp, block_index)
    (cpid, stamp_hash) = get_cpid(stamp, block_index, tx_hash)
    if decoded_base64 is not None:
        (ident, file_suffix, decoded_base64) = check_decoded_data_fetch_ident(decoded_base64, block_index, ident)
        file_suffix = "svg" if file_suffix == "svg+xml" else file_suffix
    else:
        ident, file_suffix = 'UNKNOWN', None

    valid_cp_src20 = (
        ident == 'SRC-20' and cpid and
        block_index < config.CP_SRC20_BLOCK_END
        and keyburn == 1 and stamp.get('quantity') == 0
    )
    valid_src20 = (
        valid_cp_src20 or
        (
            ident == 'SRC-20' and not cpid
            and keyburn == 1
        )
    )
    valid_src721 = (
        ident == 'SRC-721'
        and keyburn == 1
        and stamp.get('quantity') <= 1 # A407879294639844200 is 0 qty
    )
    if valid_src20:
        src20_dict = check_format(decoded_base64, tx_hash)
        if src20_dict is not None:
            # src20_string = convert_to_dict_or_string(src20_dict, output_format='string')
            is_btc_stamp = 1
            decoded_base64 = build_src20_svg_string(stamp_cursor, src20_dict)
            file_suffix = 'svg'
        else:
            return
        
    if valid_src721:
        src_data = decoded_base64
        is_btc_stamp = 1
        # TODO: add a list of src721 tx to build for each block like we do with valid_stamps_in_block below.
        (svg_output, file_suffix) = validate_src721_and_process(src_data, stamp_cursor)
        decoded_base64 = svg_output
        file_suffix = 'svg'

    if (
        ident != 'UNKNOWN' and stamp.get('asset_longname') is None
        and file_suffix not in config.INVALID_BTC_STAMP_SUFFIX and 
        (cpid and cpid.startswith('A')) and not is_op_return
    ):
        is_btc_stamp = 1
        is_btc_stamp, is_reissue = check_reissue(db, cpid, is_btc_stamp, valid_stamps_in_block)
        # if (is_reissue and not is_btc_stamp) or (not is_btc_stamp and not is_valid_base64):
            # don't need to save these since we aren't tracking supply values now 
            # only the first asset with a valid stamp:base64 is valid
            # return  
    elif stamp.get('asset_longname') is not None:
        stamp['cpid'] = stamp.get('asset_longname')
        is_cursed = 1
        is_btc_stamp = None
    elif ( # CURSED 
        cpid and (file_suffix in config.INVALID_BTC_STAMP_SUFFIX or
        not cpid.startswith('A') or is_op_return) and is_valid_base64
    ):
        is_btc_stamp = None
        is_cursed = 1
        is_btc_stamp, is_reissue = check_reissue(db, cpid, is_btc_stamp, valid_stamps_in_block)
        if is_reissue:
            return
    # elif not is_valid_base64 and not is_btc_stamp:
        # return
    elif is_reissue:
        raise Exception("This should not happen")
    # else: 
    #     if ident == 'UNKNOWN': # need to save these
    #         return

    # cursed = named assets, op_return stamps, and invalid suffix stamps
    if is_op_return: # this appears to be redundant since we are checking in the initial if statement
        is_btc_stamp = None
        is_cursed = 1

    if is_btc_stamp:
        stamp_number = get_next_stamp_number(db)
    elif is_cursed:
        stamp_number = get_next_cursed_number(db) # this includes reissued items and op_return
    else:
        stamp_number = None
    
    # what happens for reissues of a non_stamp - they get repeated in the db.

    if cpid and (is_btc_stamp):
        processed_stamps_dict = {
            'stamp': stamp_number,
            'tx_hash': tx_hash,
            'cpid': cpid,
            'is_btc_stamp': is_btc_stamp,
            'is_valid_base64': is_valid_base64,
            'stamp_base64': stamp_base64,
            'is_cursed': is_cursed,
        }
        valid_stamps_in_block.append(processed_stamps_dict)

    if valid_src20 and not is_reissue:
        process_src20_trx(db, src20_dict, source, tx_hash, tx_index, block_index, block_time, destination,
                valid_src20_in_block)

    if not stamp_mimetype and file_suffix in config.MIME_TYPES:
        stamp_mimetype = config.MIME_TYPES[file_suffix]

    if (
        ident in config.SUPPORTED_SUB_PROTOCOLS
        or file_suffix # in config.MIME_TYPES
    ):
        if type(decoded_base64) is str:
            decoded_base64 = decoded_base64.encode('utf-8')
        filename = f"{tx_hash}.{file_suffix}"
        file_obj_md5 = store_files(db, filename, decoded_base64, stamp_mimetype)

    parsed = {
        "stamp": stamp_number,
        "block_index": block_index,
        "cpid": cpid if cpid is not None else stamp_hash,
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
        "block_time": datetime.utcfromtimestamp(
            block_time
        ).strftime('%Y-%m-%d %H:%M:%S'),
        "tx_hash": tx_hash,
        "tx_index": tx_index,
        "src_data": src_data,
        "stamp_hash": stamp_hash,
        "is_btc_stamp": is_btc_stamp,
        "is_reissue": is_reissue,
        "file_hash": file_obj_md5,
        "is_valid_base64": is_valid_base64,
    }  # NOTE:: we may want to insert and update on this table in the case of a reindex where we don't want to remove data....
    # filtered_parsed = {k: v for k, v in parsed.items() if k != 'stamp_base64'}
    # logger.warning(f"parsed: {json.dumps(filtered_parsed, indent=4, separators=(', ', ': '), ensure_ascii=False)}")
    insert_into_stamp_table(stamp_cursor, parsed)


def insert_into_stamp_table(stamp_cursor, parsed):
    stamp_cursor.execute(f'''
        INSERT INTO {config.STAMP_TABLE}(
            stamp, block_index, cpid, asset_longname,
            creator, divisible, keyburn, locked,
            message_index, stamp_base64,
            stamp_mimetype, stamp_url, supply, block_time,
            tx_hash, tx_index, ident, src_data,
            stamp_hash, is_btc_stamp, is_reissue,
            file_hash, is_valid_base64
        ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    ''', (
        parsed['stamp'], parsed['block_index'],
        parsed['cpid'], parsed['asset_longname'],
        parsed['creator'],
        parsed['divisible'], parsed['keyburn'],
        parsed['locked'], parsed['message_index'],
        parsed['stamp_base64'],
        parsed['stamp_mimetype'], parsed['stamp_url'],
        parsed['supply'], parsed['block_time'],
        parsed['tx_hash'], parsed['tx_index'],
        parsed['ident'], parsed['src_data'],
        parsed['stamp_hash'], parsed['is_btc_stamp'],
        parsed['is_reissue'], parsed['file_hash'],
        parsed['is_valid_base64']
    ))
    stamp_cursor.close()


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


def get_next_cursed_number(db):
    """Return index of next transaction."""
    cursor = db.cursor()

    cursor.execute(f'''
        SELECT stamp FROM {config.STAMP_TABLE}
        WHERE stamp = (SELECT MIN(stamp) from {config.STAMP_TABLE})
    ''')
    cursed = cursor.fetchall()
    if cursed:
        assert len(cursed) == 1
        cursed_number = cursed[0][0] - 1
    else:
        cursed_number = 0

    cursor.close()

    return cursed_number


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


def store_files(db, filename, decoded_base64, mime_type):
    file_obj, file_obj_md5 = get_fileobj_and_md5(decoded_base64)
    if (config.AWS_SECRET_ACCESS_KEY and config.AWS_ACCESS_KEY_ID and
        config.AWS_S3_BUCKETNAME and config.AWS_S3_IMAGE_DIR):
        logger.info(f"uploading {filename} to aws")  # FIXME: there may be cases where we want both aws and disk storage
        check_existing_and_upload_to_s3(
            db, filename, mime_type, file_obj, file_obj_md5
        )
    else:
        store_files_to_disk(filename, decoded_base64)
    return file_obj_md5


def store_files_to_disk(filename, decoded_base64):
    if decoded_base64 is None:
        logger.info(f"decoded_base64 is None")
        return
    if filename is None:
        logger.info(f"filename is None")
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


def update_parsed_block(db, block_index,):
    cursor = db.cursor()
    cursor.execute('''
                    UPDATE blocks SET indexed = 1
                    WHERE block_index = %s
                    ''', (block_index,))
    db.commit()
    cursor.close()