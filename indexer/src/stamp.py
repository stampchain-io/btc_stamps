import logging
import json
import base64
import pybase64
import magic
import subprocess
import zlib
import msgpack
import traceback
from datetime import datetime
from decimal import Decimal

import src.log as log
from src.exceptions import DataConversionError, InvalidInputDataError, SerializationError
from src.xcprequest import parse_base64_from_description
from src.database import get_next_stamp_number, check_reissue
from src.util import ( 
    create_base62_hash, 
    check_valid_base64_string, 
    is_json_string, 
    convert_to_dict_or_string
)
from src.files import store_files
from src.src721 import validate_src721_and_process
from src.src20 import (
    check_format,
    build_src20_svg_string,
)
from config import (
    BMN_BLOCKSTART,
    STOP_BASE64_REPAIR,
    CP_P2WSH_BLOCK_START,
    CP_SRC20_BLOCK_END,
    STRIP_WHITESPACE,
    SUPPORTED_SUB_PROTOCOLS,
    MIME_TYPES,
    DOMAINNAME,
    INVALID_BTC_STAMP_SUFFIX,
)

logger = logging.getLogger(__name__)
log.set_logger(logger)


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

    is_valid_base64_string = True

    if block_index >= CP_P2WSH_BLOCK_START:
        is_valid_base64_string = check_valid_base64_string(base64_string)
        if not is_valid_base64_string:
            logger.info(f"EXCLUSION: BASE64 DECODE_FAIL invalid string: {base64_string}")
            return None, None

    if block_index <= STOP_BASE64_REPAIR:
        image_data = decode_base64_with_repair(base64_string)
        if image_data == None:
            is_valid_base64_string = None
        return image_data, is_valid_base64_string
    try:
        image_data = base64.b64decode(base64_string)
        return image_data, is_valid_base64_string
    except Exception as e1:
        try:
            image_data = pybase64.b64decode(base64_string)
            return image_data, is_valid_base64_string
        except Exception as e2:
            try:
                # Note: base64 cli returns success on MAC when on linux it returns an error code. 
                # this will be ok in the docker containers, but a potential problem
                # will need to verify that there are no instances where this is su
                command = f'printf "%s" "{base64_string}" | base64 -d 2>&1'
                image_data = subprocess.run(command, shell=True, capture_output=True, text=True, check=True, stdout=subprocess.PIPE).stdout
                return image_data, is_valid_base64_string
            except Exception as e3:
                # If all decoding attempts fail, print an error message and return None
                logger.info(f"EXCLUSION: BASE64 DECODE_FAIL base64 image string: {e1}, {e2}, {e3}")
                return None, None


def decode_base64_with_repair(base64_string):
    ''' original function which attempts to add padding to "fix" the base64 string. This was resulting in invalid/corrupted images. '''
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
    if block_index > BMN_BLOCKSTART:
        if check_custom_suffix(bytestring_data):
            return 'bmn'
    try:
        json.loads(bytestring_data.decode('utf-8'))
        return 'json'
    except (json.JSONDecodeError, UnicodeDecodeError):
        # If it failed to decode as UTF-8 text, pass it to magic to determine the file type
        if block_index > STRIP_WHITESPACE: # after this block we attempt to strip whitespace from the beginning of the binary data to catch Mikes A12333916315059997842
            file_type = magic.from_buffer(bytestring_data.lstrip(), mime=True)
        else:
            file_type = magic.from_buffer(bytestring_data, mime=True)
        return file_type.split('/')[-1]


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
    if decoded_data and decoded_data.get('p') and decoded_data.get('p').upper() in SUPPORTED_SUB_PROTOCOLS:
        ident = decoded_data['p'].upper()
        file_suffix = 'json'
    else:
        file_suffix = None
        ident = 'UNKNOWN'
    return ident, file_suffix


def zlib_decompress(compressed_data, block_index):
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
        # DEBUG: msgpack support for all stamps
        # uncompressed_file_suffix = get_file_suffix(uncompressed_data, block_index)
        # if uncompressed_file_suffix == 'plain':
        #     print("found plaintext - check for json string")
        #     # may need to do msgpack here. 
        #     if (type(uncompressed_data) is str and is_json_string(uncompressed_data)):
        #         print("found json string")

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
    else:
        try:
            if decoded_data and type(decoded_data) is str:
                decoded_data_bytestring = decoded_data.encode('utf-8')
                file_suffix = get_file_suffix(decoded_data_bytestring, block_index)
                ident = 'STAMP'
            elif decoded_data and type(decoded_data) is bytes:
                file_suffix = get_file_suffix(decoded_data, block_index)
                if file_suffix in ['zlib']:
                    ident, file_suffix, decoded_data = zlib_decompress(decoded_data, block_index)
                else:
                    ident = 'STAMP'
            else:
                file_suffix = None
                ident = 'UNKNOWN'
        except Exception as e:
            logger.error(f"Error: {e}\n{traceback.format_exc()}")
            raise
    return ident, file_suffix, decoded_data


def parse_stamp(db, tx_hash, source, destination, btc_amount, fee, data, decoded_tx, keyburn, 
                            tx_index, block_index, block_time, is_op_return,  valid_stamps_in_block, p2wsh_data):
    """
    Parses a transaction and extracts stamp-related information to be stored in the stamp table.

    Args:
        db (object): The database connection object.
        tx_hash (str): The hash of the transaction.
        source (str): The source address of the transaction.
        destination (str): The destination address of the transaction.
        btc_amount (float): The amount of BTC in the transaction.
        fee (float): The transaction fee.
        data (str): The data associated with the transaction.
        decoded_tx (str): The decoded transaction.
        keyburn (int): The keyburn value.
        tx_index (int): The index of the transaction.
        block_index (int): The index of the block containing the transaction.
        block_time (int): The timestamp of the block containing the transaction.
        is_op_return (bool): Indicates if the transaction is an OP_RETURN transaction.
        valid_stamps_in_block (list): A list to store valid stamps in the block.
        processed_src20_in_block (list): A list to store valid SRC-20 stamps in the block.

    Returns:
        None

    Raises:
        Exception: If an unexpected condition occurs during stamp processing.

    """
    file_suffix = filename = src_data = is_reissue = file_obj_md5 = is_btc_stamp = ident = is_valid_base64 = is_cursed = stamp_results = src20_dict = prevalidated_src20 = None
    valid_stamp = {}
    try:
        if not data:
            raise ValueError("Input data is empty or None")
        stamp = convert_to_dict_or_string(data, output_format='dict')
    except (DataConversionError, InvalidInputDataError, ValueError) as e:
        print(f"Invalid SRC-20 JSON {e}")
        return (None,) * 4
    
    decoded_base64, stamp_base64, stamp_mimetype, is_valid_base64  = get_src_or_img_from_data(stamp, block_index)
    (cpid, stamp_hash) = get_cpid(stamp, block_index, tx_hash)
    if p2wsh_data is not None and block_index >= CP_P2WSH_BLOCK_START:
        stamp_base64 = base64.b64encode(p2wsh_data).decode()
        decoded_base64, is_valid_base64 = decode_base64(stamp_base64, block_index)
        # decoded_base64 = p2wsh_data # bytestring
        (ident, file_suffix, decoded_base64) = check_decoded_data_fetch_ident(decoded_base64, block_index, ident)
        is_op_return = None # reset this because p2wsh typically have op_return tx
    elif decoded_base64 is not None:
        (ident, file_suffix, decoded_base64) = check_decoded_data_fetch_ident(decoded_base64, block_index, ident)
    else:    
        ident, file_suffix = 'UNKNOWN', None

    file_suffix = "svg" if file_suffix == "svg+xml" else file_suffix

    is_src20 = ident == 'SRC-20' and keyburn == 1

    valid_cp_src20 = is_src20 and cpid and block_index < CP_SRC20_BLOCK_END and stamp.get('quantity') == 0
    valid_src20 = valid_cp_src20 or (is_src20 and not cpid)
    valid_src721 = (
        ident == 'SRC-721'
        and (keyburn == 1 or (p2wsh_data is not None and block_index >= CP_P2WSH_BLOCK_START))
        and stamp.get('quantity') <= 1 # A407879294639844200 is 0 qty
    )

    if valid_src20:
        src20_dict = check_format(decoded_base64, tx_hash)
        if src20_dict is not None:
            is_btc_stamp = 1
            decoded_base64 = build_src20_svg_string(db, src20_dict)
            file_suffix = 'svg'
        else:
            return (None,) * 4
        
    if valid_src721:
        src_data = decoded_base64
        is_btc_stamp = 1
        (svg_output, file_suffix) = validate_src721_and_process(src_data, valid_stamps_in_block, db)
        decoded_base64 = svg_output
        file_suffix = 'svg'


    if (
        ident != 'UNKNOWN' and stamp.get('asset_longname') is None
        and cpid and cpid.startswith('A') and not is_op_return
        and file_suffix not in INVALID_BTC_STAMP_SUFFIX
    ):
        is_btc_stamp = 1
        is_btc_stamp, is_reissue = check_reissue(db, cpid, is_btc_stamp, valid_stamps_in_block)
    elif stamp.get('asset_longname') is not None:
        stamp['cpid'] = stamp.get('asset_longname')
        is_cursed = 1
        is_btc_stamp = None
    elif ( # CURSED 
        cpid and (file_suffix in INVALID_BTC_STAMP_SUFFIX or
        not cpid.startswith('A') or is_op_return)
    ):
        is_btc_stamp = None
        is_cursed = 1
        is_btc_stamp, is_reissue = check_reissue(db, cpid, is_btc_stamp, valid_stamps_in_block)
        if is_reissue:
            return (None,) * 4

    if is_op_return:
        is_btc_stamp = None
        is_cursed = 1
    
    if is_btc_stamp:
        stamp_number = get_next_stamp_number(db, 'stamp')
    elif is_cursed:
        stamp_number = get_next_stamp_number(db, 'cursed')
    else:
        stamp_number = None
        if is_reissue:
            return
        else:
            stamp_number = None # need to save these in the db do detect invalid reissuances of prior stamp: trx

    if cpid and is_btc_stamp:
        valid_stamp = {
            'stamp': stamp_number,
            'tx_hash': tx_hash,
            'cpid': cpid,
            'is_btc_stamp': is_btc_stamp,
            'is_valid_base64': is_valid_base64,
            'stamp_base64': stamp_base64,
            'is_cursed': is_cursed,
            'src_data': src_data,
        }

    if valid_src20 and not is_reissue:
        src20_dict.update({
            'stamp:': stamp_number,
            'creator': source,
            'tx_hash': tx_hash,
            'tx_index': tx_index,
            'block_index': block_index,
            'block_time': block_time,
            'destination': destination
        })
        prevalidated_src20 = src20_dict

    # Set MIME type based on file_suffix
    if not stamp_mimetype and file_suffix in MIME_TYPES:
        stamp_mimetype = MIME_TYPES[file_suffix]

    # Store files if conditions are met
    if ident in SUPPORTED_SUB_PROTOCOLS or file_suffix:
        if isinstance(decoded_base64, str):
            decoded_base64 = decoded_base64.encode('utf-8')
        filename = f"{tx_hash}.{file_suffix}"
        file_obj_md5 = store_files(db, filename, decoded_base64, stamp_mimetype)

    # All stamps including cursed
    parsed_stamp = {
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
        "stamp_url": 'https://' + DOMAINNAME + '/stamps/' + filename if file_suffix is not None and filename is not None else None,
        "supply": stamp.get('quantity'),
        "block_time": datetime.utcfromtimestamp(
            block_time
        ).strftime('%Y-%m-%d %H:%M:%S'),
        "tx_hash": tx_hash,
        "tx_index": tx_index,
        "src_data": src_data,
        "stamp_hash": stamp_hash,
        "is_btc_stamp": is_btc_stamp,
        "is_cursed": is_cursed,
        "is_reissue": is_reissue,
        "file_hash": file_obj_md5,
        "is_valid_base64": is_valid_base64,
    }  # NOTE:: we may want to insert and update on this table in the case of a reindex where we don't want to remove data....
    # filtered_parsed = {k: v for k, v in parsed.items() if k != 'stamp_base64'}
    # logger.warning(f"parsed: {json.dumps(filtered_parsed, indent=4, separators=(', ', ': '), ensure_ascii=False)}")
    stamp_results = True
    # NOTE: parsed_stamp includes cursed stamps and non-numbered stamps
    # valid_stamp is is_btc_stamp only
    return stamp_results, parsed_stamp, valid_stamp, prevalidated_src20
