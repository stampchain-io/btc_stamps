import time
import decimal
import sys
import json
import logging
logger = logging.getLogger(__name__)
import inspect
import requests
from datetime import datetime
from dateutil.tz import tzlocal
from operator import itemgetter
import fractions
import warnings
import binascii
import re
import hashlib
import sha3
import bitcoin as bitcoinlib
import os
import collections
import threading
import random
import itertools

import src.exceptions as exceptions
import config
# from exceptions import DecodeError

D = decimal.Decimal
B26_DIGITS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'

# subasset contain only characters a-zA-Z0-9.-_@!
SUBASSET_DIGITS = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_@!'
SUBASSET_REVERSE = {'a':1,'b':2,'c':3,'d':4,'e':5,'f':6,'g':7,'h':8,'i':9,'j':10,'k':11,'l':12,'m':13,'n':14,
                    'o':15,'p':16,'q':17,'r':18,'s':19,'t':20,'u':21,'v':22,'w':23,'x':24,'y':25,'z':26,
                    'A':27,'B':28,'C':29,'D':30,'E':31,'F':32,'G':33,'H':34,'I':35,'J':36,'K':37,'L':38,'M':39,
                    'N':40,'O':41,'P':42,'Q':43,'R':44,'S':45,'T':46,'U':47,'V':48,'W':49,'X':50,'Y':51,'Z':52,
                    '0':53,'1':54,'2':55,'3':56,'4':57,'5':58,'6':59,'7':60,'8':61,'9':62,'.':63,'-':64,'_':65,'@':66,'!':67}

# Obsolete in Python 3.4, with enum module.
BET_TYPE_NAME = {0: 'BullCFD', 1: 'BearCFD', 2: 'Equal', 3: 'NotEqual'}
BET_TYPE_ID = {'BullCFD': 0, 'BearCFD': 1, 'Equal': 2, 'NotEqual': 3}

json_dump = lambda x: json.dumps(x, sort_keys=True, indent=4)
json_print = lambda x: print(json_dump(x))

BLOCK_LEDGER = []

CURRENT_BLOCK_INDEX = None # resolves to blocks.last_db_index(db)

CURR_DIR = os.path.dirname(os.path.realpath(__file__))
# with open(CURR_DIR + '/../protocol_changes.json') as f:
#     PROTOCOL_CHANGES = json.load(f)

class RPCError (Exception): pass

# TODO: Move to `util_test.py`.
# TODO: This doesn’t timeout properly. (If server hangs, then unhangs, no result.)
def api(method, params):
    """Poll API via JSON-RPC."""
    headers = {'content-type': 'application/json'}
    payload = {
        "method": method,
        "params": params,
        "jsonrpc": "2.0",
        "id": 0,
    }

    response = requests.post(config.RPC, data=json.dumps(payload), headers=headers)
    if response == None:
        raise RPCError('Cannot communicate with {} server.'.format(config.STAMPS_NAME))
    elif response.status_code != 200:
        if response.status_code == 500:
            raise RPCError('Malformed API call.')
        else:
            raise RPCError(str(response.status_code) + ' ' + response.reason)

    response_json = response.json()
    if 'error' not in response_json.keys() or response_json['error'] == None:
        try:
            return response_json['result']
        except KeyError:
            raise RPCError(response_json)
    else:
        raise RPCError('{} ({})'.format(response_json['error']['message'], response_json['error']['code']))

def chunkify(l, n):
    n = max(1, n)
    return [l[i:i + n] for i in range(0, len(l), n)]

def flat(z):
    return [x for x in z]

def py34TupleAppend(first_elem, t):
    # Had to do it this way to support python 3.4, if we start
    # using the 3.5 runtime this can be replaced by:
    #  (first_elem, *t)

    l = list(t)
    l.insert(0, first_elem)
    return tuple(l)

def accumulate(l):
    it = itertools.groupby(l, itemgetter(0))
    for key, subiter in it:
       yield key, sum(item[1] for item in subiter)

def date_passed(date):
    """Check if the date has already passed."""
    return date <= int(time.time())

def price (numerator, denominator):
    """Return price as Fraction or Decimal."""
    if CURRENT_BLOCK_INDEX >= 294500 or config.TESTNET or config.REGTEST: # Protocol change.
        return fractions.Fraction(numerator, denominator)
    else:
        numerator = D(numerator)
        denominator = D(denominator)
        return D(numerator / denominator)

def last_message(db):
    """Return latest message from the db."""
    cursor = db.cursor()
    messages = list(cursor.execute('''SELECT * FROM messages WHERE message_index = (SELECT MAX(message_index) from messages)'''))
    if messages:
        assert len(messages) == 1
        last_message = messages[0]
    else:
        raise exceptions.DatabaseError('No messages found.')
    cursor.close()
    return last_message

def generate_asset_id(asset_name, block_index):
    """Create asset_id from asset_name."""
    if asset_name == config.BTC: return 0
    elif asset_name == config.XCP: return 1

    if len(asset_name) < 4:
        raise exceptions.AssetNameError('too short')

    # Numeric asset names.
    if enabled('numeric_asset_names'):  # Protocol change.
        if asset_name[0] == 'A':
            # Must be numeric.
            try:
                asset_id = int(asset_name[1:])
            except ValueError:
                raise exceptions.AssetNameError('non‐numeric asset name starts with ‘A’')

            # Number must be in range.
            if not (26**12 + 1 <= asset_id <= 2**64 - 1):
                raise exceptions.AssetNameError('numeric asset name not in range')

            return asset_id
        elif len(asset_name) >= 13:
            raise exceptions.AssetNameError('long asset names must be numeric')

    if asset_name[0] == 'A': raise exceptions.AssetNameError('non‐numeric asset name starts with ‘A’')

    # Convert the Base 26 string to an integer.
    n = 0
    for c in asset_name:
        n *= 26
        if c not in B26_DIGITS:
            raise exceptions.AssetNameError('invalid character:', c)
        digit = B26_DIGITS.index(c)
        n += digit
    asset_id = n

    if asset_id < 26**3:
        raise exceptions.AssetNameError('too short')

    return asset_id

def generate_random_asset ():
    return 'A' + str(random.randint(26**12 + 1, 2**64 - 1))

def parse_options_from_string(string):
    """Parse options integer from string, if exists."""
    string_list = string.split(" ")
    if len(string_list) == 2:
        try:
            options = int(string_list.pop())
        except:
            raise exceptions.OptionsError('options not an integer')
        return options
    else:
        return False

def validate_address_options(options):
    """Ensure the options are all valid and in range."""
    if (options > config.MAX_INT) or (options < 0):
        raise exceptions.OptionsError('options integer overflow')
    elif options > config.ADDRESS_OPTION_MAX_VALUE:
        raise exceptions.OptionsError('options out of range')
    elif not active_options(config.ADDRESS_OPTION_MAX_VALUE, options):
        raise exceptions.OptionsError('options not possible')

def active_options(config, options):
    """Checks if options active in some given config."""
    return config & options == options





class GetURLError (Exception): pass
def get_url(url, abort_on_error=False, is_json=True, fetch_timeout=5):
    """Fetch URL using requests.get."""
    try:
        r = requests.get(url, timeout=fetch_timeout)
    except Exception as e:
        raise GetURLError("Got get_url request error: %s" % e)
    else:
        if r.status_code != 200 and abort_on_error:
            raise GetURLError("Bad status code returned: '%s'. result body: '%s'." % (r.status_code, r.text))
        result = json.loads(r.text) if is_json else r.text
    return result


def dhash(text):
    if not isinstance(text, bytes):
        text = bytes(str(text), 'utf-8')

    return hashlib.sha256(hashlib.sha256(text).digest()).digest()


def dhash_string(text):
    return binascii.hexlify(dhash(text)).decode()


# Why on Earth does `binascii.hexlify()` return bytes?!
def hexlify(x):
    """Return the hexadecimal representation of the binary data. Decode from ASCII to UTF-8."""
    return binascii.hexlify(x).decode('ascii')
def unhexlify(hex_string):
    return binascii.unhexlify(bytes(hex_string, 'utf-8'))

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
