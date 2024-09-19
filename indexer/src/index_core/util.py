import ast
import binascii
import collections
import decimal
import hashlib
import json
import logging
import re
import threading
import unicodedata
from binascii import unhexlify
from bitcoinlib import encoding
from ecdsa import SECP256k1, VerifyingKey

from bitcoinlib import encoding
from ecdsa import SECP256k1, VerifyingKey

import config
from index_core.exceptions import DataConversionError, InvalidInputDataError, SerializationError

logger = logging.getLogger(__name__)
D = decimal.Decimal

CP_BLOCK_COUNT = None

CURRENT_BLOCK_INDEX = None  # resolves to database.last_db_index(db)


def chunkify(lst, n):
    """
    Splits a list into smaller chunks of size n.

    Args:
        lst (list): The list to be chunked.
        n (int): The size of each chunk.

    Returns:
        list: A list of smaller chunks.
    """
    n = max(1, n)
    return [lst[i : i + n] for i in range(0, len(lst), n)]


def dhash(text):
    """
    Calculate the double hash of the given text.

    Args:
        text (str or bytes): The input text to be hashed.

    Returns:
        bytes: The double hash of the input text as bytes.
    """
    if not isinstance(text, bytes):
        text = bytes(str(text), "utf-8")

    return hashlib.sha256(hashlib.sha256(text).digest()).digest()


def dhash_string(text):
    """
    Calculate the double hash of the given data and return it as a hex string.

    Args:
        data (bytes): The input data to calculate the dhash from.

    Returns:
        str: The double hash value represented as a hex string.
    """
    return binascii.hexlify(dhash(text)).decode()


def shash_string(text):
    """
    Calculate the single hash of the given data and return it as a hex string.

    Args:
        data (bytes): The input data to calculate the shash from.

    Returns:
        str: The single hash value represented as a hex string.
    """
    if not isinstance(text, bytes):
        text = bytes(str(text), "utf-8")

    return binascii.hexlify(hashlib.sha256(text).digest()).decode("utf-8")


# def shash_string(previous_hash, new_data):
#     hash_obj = hashlib.sha256()
#     hash_obj.update(previous_hash.encode('utf-8'))
#     hash_obj.update(new_data.encode('utf-8'))
#     return hash_obj.hexdigest()


# Protocol Changes
def enabled(change_name, block_index=None):
    """Return True if protocol change is enabled."""
    if config.REGTEST:
        return True  # All changes are always enabled on REGTEST

    # if config.TESTNET:
    #     index_name = 'testnet_block_index'
    # else:
    #     index_name = 'block_index'

    # we are hard coding all protocol changes to be enabled here for now
    enable_block_index = 0  # PROTOCOL_CHANGES[change_name][index_name]

    if not block_index:
        block_index = CURRENT_BLOCK_INDEX

    if block_index >= enable_block_index:
        return True
    else:
        return False


class DictCache:
    """Threadsafe FIFO dict cache"""

    def __init__(self, size=100):
        if int(size) < 1:
            raise AttributeError("size < 1 or not a number")
        self.size = size
        self.dict = collections.OrderedDict()
        self.lock = threading.Lock()

    def __getitem__(self, key):
        with self.lock:
            return self.dict[key]

    def __setitem__(self, key, value):
        with self.lock:
            while len(self.dict) >= self.size:
                self.dict.popitem(last=False)
            self.dict[key] = value

    def __delitem__(self, key):
        with self.lock:
            del self.dict[key]

    def __len__(self):
        with self.lock:
            return len(self.dict)

    def __contains__(self, key):
        with self.lock:
            return key in self.dict

    def refresh(self, key):
        with self.lock:
            self.dict.move_to_end(key, last=True)


URL_USERNAMEPASS_REGEX = re.compile(".+://(.+)@")


def clean_url_for_log(url):
    m = URL_USERNAMEPASS_REGEX.match(url)
    if m and m.group(1):
        url = url.replace(m.group(1), "XXXXXXXX")

    return url


def b2h(b):
    return binascii.hexlify(b).decode("utf-8")


def inverse_hash(hashstring):
    hashstring = hashstring[::-1]
    return "".join([hashstring[i : i + 2][::-1] for i in range(0, len(hashstring), 2)])


def ib2h(b):
    return inverse_hash(b2h(b))


def hex_decode(hexstring):
    try:
        return bytes.fromhex(hexstring).decode("utf-8")
    except Exception:
        return None

def is_valid_pubkey_hex(pubkey_hex):
    try:
        if len(pubkey_hex) != 66:
            return False
        if not (pubkey_hex.startswith("02") or pubkey_hex.startswith("03")):
            return False
        pubkey_bytes = unhexlify(pubkey_hex)
        VerifyingKey.from_string(pubkey_bytes, curve=SECP256k1)
        return True
    except Exception as e:
        return False

def is_valid_pubkey_hex(pubkey_hex):
    try:
        if len(pubkey_hex) != 66:
            return False
        if not (pubkey_hex.startswith("02") or pubkey_hex.startswith("03")):
            return False
        pubkey_bytes = unhexlify(pubkey_hex)
        VerifyingKey.from_string(pubkey_bytes, curve=SECP256k1)
        return True
    except Exception as e:
        return False


def check_valid_eth_address(address: str):
    if not address.startswith("0x"):
        return False

    if len(address) != 42:
        return False

    if not re.match(r"^0x[0-9a-fA-F]{40}$", address):
        return False

    return True


def check_valid_bitcoin_address(address: str):
    try:
        if address.startswith("bc1") or address.startswith("tb1"):
            encoding.addr_bech32_to_pubkeyhash(address)
        else:
            encoding.addr_base58_to_pubkeyhash(address)
        return True
    except Exception as e:
        return False


def check_valid_tx_hash(tx_hash: str) -> bool:
    match = re.fullmatch(r"[0-9a-fA-F]{64}", tx_hash)
    return match is not None


special_characters_pattern = (
    r"[`~!@#$%\^\-\+&\*\(\)_\=＝\=|{}\":;',\\\[\]\.·<>\/\?~！@#￥……&*（）——|{}【】《》'；：“”‘。，、？\s]"
)

def check_contains_special(text):
    special_categories = {"Zs", "Cf"}
    match = re.search(special_characters_pattern, text)
    return any(unicodedata.category(char) in special_categories for char in text) or text.isspace() or match is not None

def check_valid_base64_string(base64_string):
    if base64_string is not None and re.fullmatch(r"^[A-Za-z0-9+/]+={0,2}$", base64_string) and len(base64_string) % 4 == 0:
        return True
    else:
        return False


def base62_encode(num):
    chars = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    base = len(chars)
    if num == 0:
        return chars[0]
    result = []
    while num:
        num, rem = divmod(num, base)
        result.append(chars[rem])
    return "".join(reversed(result))


def create_base62_hash(str1, str2, length=20):
    if not 12 <= length <= 20:
        raise ValueError("Length must be between 12 and 20 characters")
    combined_str = str1 + "|" + str2
    hash_bytes = hashlib.sha256(combined_str.encode()).digest()
    hash_int = int.from_bytes(hash_bytes, byteorder="big")
    base62_hash = base62_encode(hash_int)
    return base62_hash[:length]


def escape_non_ascii_characters(text):
    """
    Encodes non-ASCII characters in the given text using unicode_escape encoding and then decodes it using utf-8 encoding.

    Args:
        text (str): The text to encode.

    Returns:
        str: The encoded and decoded text.
    """
    return text.encode("unicode_escape").decode("utf-8")


def decode_unicode_escapes(text):
    """
    Decodes Unicode escape sequences in the given text back to their corresponding Unicode characters.

    Args:
        text (str): The text containing Unicode escape sequences.

    Returns:
        str: The text with Unicode escape sequences converted back to Unicode characters.
    """
    return text.encode("utf-8").decode("unicode_escape")


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
    json_string = json_string.replace("'", " ")
    json_string = json_string.replace("\\x00", "")  # remove null bytes
    return json_string


def convert_decimal_to_string(obj):
    if isinstance(obj, D):
        return str(obj)
    raise TypeError


def convert_to_dict_or_string(input_data, output_format="dict"):
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

    if isinstance(input_data, bytes):
        try:
            input_data = json.loads(input_data, parse_float=D)
        except json.JSONDecodeError:
            input_data = repr(input_data)[2:-1]

    if isinstance(input_data, str):
        try:
            return json.loads(input_data, parse_float=D)
        except json.JSONDecodeError:
            try:
                input_data = ast.literal_eval(input_data)
            except (ValueError, SyntaxError):
                raise DataConversionError("Invalid string representation of a dictionary")

    if not isinstance(input_data, dict):
        raise InvalidInputDataError("input_data is not a dictionary, string, or bytes")

    if output_format == "dict":
        return input_data
    elif output_format == "string":
        try:
            json_string = json.dumps(input_data, ensure_ascii=False, default=convert_decimal_to_string)
            return clean_json_string(json_string)
        except Exception as e:
            raise SerializationError(f"An error occurred during JSON serialization: {e}")
    else:
        raise DataConversionError("Invalid output format: {}".format(output_format))
