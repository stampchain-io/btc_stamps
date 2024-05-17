import logging
import base64
import pybase64
import subprocess  # nosec
import json

from index_core.exceptions import DataConversionError, InvalidInputDataError
from index_core.models import ValidStamp, StampData
import index_core.log as log
from index_core.xcprequest import parse_base64_from_description
from index_core.database import get_next_stamp_number, check_reissue
from index_core.util import (
    check_valid_base64_string,
    convert_to_dict_or_string
)
from index_core.files import store_files
from config import (
    STOP_BASE64_REPAIR,
    CP_P2WSH_FEAT_BLOCK_START,
)

logger = logging.getLogger(__name__)
log.set_logger(logger)


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

    if block_index >= CP_P2WSH_FEAT_BLOCK_START:
        is_valid_base64_string = check_valid_base64_string(base64_string)
        if not is_valid_base64_string:
            logger.info(f"EXCLUSION: BASE64 DECODE_FAIL invalid string: {base64_string}")
            return None, None

    if block_index <= STOP_BASE64_REPAIR:
        image_data = decode_base64_with_repair(base64_string)
        if image_data is None:
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
                command = ['bash', '-c', f'printf "%s" "{base64_string}" | base64 -d']
                image_data = subprocess.run(command, capture_output=True, text=True, check=True).stdout  # nosec
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
            - stamp_mimetype (str or None): The MIME type of the stamp in the description.
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
        decoded_base64, is_valid_base64 = decode_base64(
            base64_string, block_index
        )
        return decoded_base64, base64_string, stamp_mimetype, is_valid_base64


def encode_and_store_file(db, tx_hash, file_suffix, decoded_base64, stamp_mimetype):
    """
    Encodes the decoded_base64 string to utf-8 (if it's a string or a dict), constructs the filename,
    and stores the file.

    Args:
        db: The database connection object.
        tx_hash (str): The transaction hash.
        file_suffix (str): The file suffix.
        decoded_base64 (bytes, str, or dict): The decoded base64 data.
        stamp_mimetype (str): The MIME type of the stamp.

    Returns:
        The result of the file storage operation.
    """
    if file_suffix:
        if isinstance(decoded_base64, dict):
            decoded_base64 = json.dumps(decoded_base64)
        if isinstance(decoded_base64, str):
            decoded_base64 = decoded_base64.encode('utf-8')
        filename = f"{tx_hash}.{file_suffix}"
        logger.info(decoded_base64)
        return store_files(db, filename, decoded_base64, stamp_mimetype)
    return None, None


def create_valid_stamp_dict(stamp_number: int, tx_hash: str, cpid: str, is_btc_stamp: bool,
                            is_valid_base64: bool, stamp_base64: str, is_cursed: bool,
                            src_data: str) -> ValidStamp:
    """
    Prepares the valid_stamp dictionary with the provided parameters.

    Args:
        stamp_number (int): The stamp number.
        tx_hash (str): The transaction hash.
        cpid (str): The CPID of the stamp.
        is_btc_stamp (bool): Indicates if the stamp is a BTC stamp.
        is_valid_base64 (bool): Indicates if the base64 data is valid.
        stamp_base64 (str): The base64 encoded stamp data.
        is_cursed (bool): Indicates if the stamp is cursed.
        src_data (str): The source data of the stamp.

    Returns:
        ValidStamp: The prepared valid_stamp dictionary.
    """
    return ValidStamp(
        stamp_number=stamp_number,
        tx_hash=tx_hash,
        cpid=cpid,
        is_btc_stamp=is_btc_stamp,
        is_valid_base64=is_valid_base64,
        stamp_base64=stamp_base64,
        is_cursed=is_cursed,
        src_data=src_data,
    )


def append_stamp_data_to_src20_dict(stamp_data: StampData, src20_dict):
    src20_dict.update({
        'stamp:': stamp_data.stamp,
        'creator': stamp_data.creator,
        'tx_hash': stamp_data.tx_hash,
        'tx_index': stamp_data.tx_index,
        'block_index': stamp_data.block_index,
        'block_time': stamp_data.block_time,
        'destination': stamp_data.destination
    })
    return src20_dict


def parse_stamp(*, stamp_data: StampData, db, valid_stamps_in_block: list[ValidStamp]):
    """
    Parses a transaction and extracts stamp-related information to be stored in the stamp table.

    Args:
        stamp_data (StampData): An instance of StampData containing all necessary transaction information.

    Returns:
        None

    Raises:
        Exception: If an unexpected condition occurs during stamp processing.

    """
    stamp_results = src20_dict = prevalidated_src20 = None
    valid_stamp: ValidStamp = {}
    try:
        stamp_data.process_and_store_stamp_data(
            get_src_or_img_from_data, convert_to_dict_or_string, encode_and_store_file, check_reissue, decode_base64, db, valid_stamps_in_block)
    except (DataConversionError, InvalidInputDataError, ValueError) as e:
        logger.warning(f"Invalid Stamp Data: {e}")
        return (None,) * 4

    if stamp_data.is_btc_stamp:
        stamp_data.stamp = get_next_stamp_number(db, 'stamp')
    elif stamp_data.is_cursed:
        stamp_data.stamp = get_next_stamp_number(db, 'cursed')
    else:
        stamp_data.stamp = None

    if stamp_data.cpid and stamp_data.is_btc_stamp:
        valid_stamp = create_valid_stamp_dict(
            stamp_data.stamp, stamp_data.tx_hash, stamp_data.cpid, stamp_data.is_btc_stamp, stamp_data.is_valid_base64, stamp_data.stamp_base64, stamp_data.is_cursed, stamp_data.src_data)

    if stamp_data.pval_src20:
        src20_dict = stamp_data.src20_dict
        prevalidated_src20 = append_stamp_data_to_src20_dict(stamp_data, src20_dict)

    stamp_results = True
    return stamp_results, stamp_data, valid_stamp, prevalidated_src20
