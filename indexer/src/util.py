import logging
logger = logging.getLogger(__name__)
import binascii
import re
import hashlib
import collections
import threading

import config

CP_BLOCK_COUNT = None

CURRENT_BLOCK_INDEX = None # resolves to blocks.last_db_index(db)

BLOCK_LEDGER = []
BLOCK_MESSAGES = []

def chunkify(l, n):
    """
    Splits a list into smaller chunks of size n.

    Args:
        l (list): The list to be chunked.
        n (int): The size of each chunk.

    Returns:
        list: A list of smaller chunks.
    """
    n = max(1, n)
    return [l[i:i + n] for i in range(0, len(l), n)]


def dhash(text):
    """
    Calculate the double hash of the given text.

    Args:
        text (str or bytes): The input text to be hashed.

    Returns:
        bytes: The double hash of the input text as bytes.
    """
    if not isinstance(text, bytes):
        text = bytes(str(text), 'utf-8')

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
        text = bytes(str(text), 'utf-8')

    return binascii.hexlify(hashlib.sha256(text).digest()).decode('utf-8')

# def shash_string(previous_hash, new_data):
#     hash_obj = hashlib.sha256()
#     hash_obj.update(previous_hash.encode('utf-8'))
#     hash_obj.update(new_data.encode('utf-8'))
#     return hash_obj.hexdigest()


### Protocol Changes ###
def enabled(change_name, block_index=None):
    """Return True if protocol change is enabled."""
    if config.REGTEST:
        return True # All changes are always enabled on REGTEST

    if config.TESTNET:
        index_name = 'testnet_block_index'
    else:
        index_name = 'block_index'
    
    # we are hard coding all protocol changes to be enabled here for now 
    enable_block_index =  0 # PROTOCOL_CHANGES[change_name][index_name]

    if not block_index:
        block_index = CURRENT_BLOCK_INDEX

    if block_index >= enable_block_index:
        return True
    else:
        return False


class DictCache:
    """Threadsafe FIFO dict cache"""
    def __init__(self, size=100):
        if int(size) < 1 :
            raise AttributeError('size < 1 or not a number')
        self.size = size
        self.dict = collections.OrderedDict()
        self.lock = threading.Lock()

    def __getitem__(self,key):
        with self.lock:
            return self.dict[key]

    def __setitem__(self,key,value):
        with self.lock:
            while len(self.dict) >= self.size:
                self.dict.popitem(last=False)
            self.dict[key] = value

    def __delitem__(self,key):
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


URL_USERNAMEPASS_REGEX = re.compile('.+://(.+)@')


def clean_url_for_log(url):
    m = URL_USERNAMEPASS_REGEX.match(url)
    if m and m.group(1):
        url = url.replace(m.group(1), 'XXXXXXXX')

    return url


def b2h(b):
    return binascii.hexlify(b).decode('utf-8')


def inverse_hash(hashstring):
    hashstring = hashstring[::-1]
    return ''.join([hashstring[i:i+2][::-1] for i in range(0, len(hashstring), 2)])


def ib2h(b):
    return inverse_hash(b2h(b))
