import os
from bitcoinrpc.authproxy import AuthServiceProxy, JSONRPCException
import regex
import logging
import src.util as util
from requests.auth import HTTPBasicAuth
import boto3

logger = logging.getLogger(__name__)

# env vars to be set in docker, or locally if connecting to a local btc and/or cp_node
RPC_USER = os.environ.get("RPC_USER", 'rpc')
RPC_PASSWORD = os.environ.get("RPC_PASSWORD", 'rpc')
RPC_IP = os.environ.get("RPC_IP", '127.0.0.1')
RPC_PORT = os.environ.get("RPC_PORT", '8332')

CP_RPC_URL = os.environ.get("CP_RPC_URL", "https://public.coindaddy.io:4001/api/rest/") # 'http://127.0.0.1:4000/api/'
CP_RPC_USER = os.environ.get("CP_RPC_USER", "rpc")
CP_RPC_PASSWORD = os.environ.get("CP_RPC_PASSWORD", "1234")
CP_AUTH = HTTPBasicAuth(CP_RPC_USER, CP_RPC_PASSWORD)

AWS_ACCESS_KEY_ID=os.environ.get("AWS_ACCESS_KEY_ID", None)
AWS_SECRET_ACCESS_KEY=os.environ.get("AWS_SECRET_ACCESS_KEY", None)

AWS_S3_CLIENT = boto3.client(
    's3',
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    )

AWS_CLOUDFRONT_DISTRIBUTION_ID = os.environ.get('AWS_CLOUDFRONT_DISTRIBUTION_ID', None)
AWS_S3_BUCKETNAME = os.environ.get('AWS_S3_BUCKETNAME', None)
AWS_S3_IMAGE_DIR = os.environ.get('AWS_S3_IMAGE_DIR', None)
S3_OBJECTS = []

BLOCKS_TO_KEEP = int(os.environ.get("BLOCKS_TO_KEEP", 0))

# Define for Quicknode or simiilar remote nodes which use a token
QUICKNODE_URL = os.environ.get("QUICKNODE_URL", None)
RPC_TOKEN = os.environ.get("RPC_TOKEN", None)
if QUICKNODE_URL and RPC_TOKEN:
    RPC_URL = f"https://{RPC_USER}:{RPC_PASSWORD}@{QUICKNODE_URL}/{RPC_TOKEN}"
else:
    RPC_URL = f"http://{RPC_USER}:{RPC_PASSWORD}@{RPC_IP}:{RPC_PORT}"

RPC_CONNECTION = AuthServiceProxy(RPC_URL)

RAW_TRANSACTIONS_CACHE_SIZE = 20000
RPC_BATCH_SIZE = 20     # A 1 MB block can hold about 4200 transactions.
RPC_BATCH_NUM_WORKERS = 5  # 20

raw_transactions_cache = util.DictCache(size=RAW_TRANSACTIONS_CACHE_SIZE)  # used in getrawtransaction_batch()

STAMP_TABLE = "StampTableV4"
DOMAINNAME = os.environ.get("DOMAINNAME", "stampchain.io")
SUPPORTED_SUB_PROTOCOLS = ['SRC-721', 'SRC-20']
INVALID_BTC_STAMP_SUFFIX = ['plain', 'octet-stream', 'js', 'css', 'x-empty', 'json']

STAMP_PREFIX_HEX = "7374616d703a" # (lowercase stamp:)

CP_STAMP_GENESIS_BLOCK = 779652 # block height of first valid stamp transaction on counterparty
BTC_STAMP_GENESIS_BLOCK = 793068 # block height of first stamp (src-20) transaction on btc

CP_SRC20_BLOCK_START = 788041 # This initial start of SRC-20 on Counterparty
CP_SRC20_BLOCK_END = 796000 # The last SRC-20 on CP  - IGNORE ALL SRC-20 on CP AFTER THIS BLOCK

CP_SRC720_BLOCK_START = 799434

FIRST_KEYBURN_BLOCK = 784978

BMN_BLOCKSTART = 815130 # This is the block where we start looking for BMN audio files

BYTE_LENGTH_PREFIX_SIZE = 2 # 2 bytes for byte length prefix after block 790370

TESTNET = None
REGTEST = None

BURNKEYS = [
    "022222222222222222222222222222222222222222222222222222222222222222",
    "033333333333333333333333333333333333333333333333333333333333333333",
    "020202020202020202020202020202020202020202020202020202020202020202",
    "030303030303030303030303030303030303030303030303030303030303030302",
    "030303030303030303030303030303030303030303030303030303030303030303"
]

# TODO: These will be used as part of the check AFTER we decode the base64 and save the image to disk
MIME_TYPES = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "svg": "image/svg+xml",
    "tif": "image/tiff",
    "jfif": "image/jpeg",
    "jpe": "image/jpeg",
    "pbm": "image/x-portable-bitmap",
    "pgm": "image/x-portable-graymap",
    "ppm": "image/x-portable-pixmap",
    "pnm": "image/x-portable-anymap",
    "apng": "image/apng",
    "bmp": "image/bmp",
    "webp": "image/webp",
    "heif": "image/heif",
    "heic": "image/heic",
    "avif": "image/avif",
    "ico": "image/x-icon",
    "tiff": "image/tiff",
    "svgz": "image/svg+xml",
    "wmf": "image/wmf",
    "emf": "image/emf",
    "pcx": "image/pcx",
    "djvu": "image/vnd.djvu",
    "djv": "image/vnd.djvu",
    "html": "text/html"
    # "eps": "image/eps",
    # "pdf": "application/pdf"
}

BLOCK_FIELDS_POSITION = {
    'block_index': 0,
    'block_hash': 1,
    'block_time': 2,
    'previous_block_hash': 3,
    'difficulty': 4,
    'ledger_hash': 5,
    'txlist_hash': 6,
    'messages_hash': 7,
    'indexed': 8
}

TXS_FIELDS_POSITION = {
    'tx_index': 0,
    'tx_hash': 1,
    'block_index': 2,
    'block_hash': 3,
    'block_time': 4,
    'source': 5,
    'destination': 6,
    'btc_amount': 7,
    'fee': 8,
    'data': 9,
    'supported': 10,
    'keyburn': 11,
    'is_btc_stamp': 12,
}


TICK_PATTERN_LIST = {
    regex.compile(r'((\p{Emoji_Presentation})|(\p{Emoji_Modifier_Base}\p{Emoji_Modifier}?))|[\p{Punctuation}\p{Symbol}\w~!@#$%^&*()_=<>?]')
}



UNIT = 100000000        # The same across assets.


# Versions
VERSION_MAJOR = 0
VERSION_MINOR = 1
VERSION_REVISION = 2
VERSION_STRING = str(VERSION_MAJOR) + '.' + str(VERSION_MINOR) + '.' + str(VERSION_REVISION)


# Counterparty protocol
TXTYPE_FORMAT = '>I'
SHORT_TXTYPE_FORMAT = 'B'

TWO_WEEKS = 2 * 7 * 24 * 3600
MAX_EXPIRATION = 4 * 2016   # Two months

MEMPOOL_BLOCK_HASH = 'mempool'
MEMPOOL_BLOCK_INDEX = 9999999


# SQLite3
MAX_INT = 2**63 - 1


# Bitcoin Core
OP_RETURN_MAX_SIZE = 80  # bytes


# Currency agnosticism
BTC = 'BTC'
XCP = 'XCP'

BTC_NAME = 'Bitcoin'
STAMPS_NAME = 'btc_stamps'
APP_NAME = STAMPS_NAME.lower()


DEFAULT_BACKEND_PORT_REGTEST = 28332
DEFAULT_BACKEND_PORT_TESTNET = 18332
DEFAULT_BACKEND_PORT = 8332

DEFAULT_INDEXD_PORT_REGTEST = 28432
DEFAULT_INDEXD_PORT_TESTNET = 18432
DEFAULT_INDEXD_PORT = 8432

ADDRESSVERSION_TESTNET = b'\x6f'
P2SH_ADDRESSVERSION_TESTNET = b'\xc4'
PRIVATEKEY_VERSION_TESTNET = b'\xef'
ADDRESSVERSION_MAINNET = b'\x00'
P2SH_ADDRESSVERSION_MAINNET = b'\x05'
PRIVATEKEY_VERSION_MAINNET = b'\x80'
ADDRESSVERSION_REGTEST = b'\x6f'
P2SH_ADDRESSVERSION_REGTEST = b'\xc4'
PRIVATEKEY_VERSION_REGTEST = b'\xef'
MAGIC_BYTES_TESTNET = b'\xfa\xbf\xb5\xda'   # For bip-0010
MAGIC_BYTES_MAINNET = b'\xf9\xbe\xb4\xd9'   # For bip-0010
MAGIC_BYTES_REGTEST = b'\xda\xb5\xbf\xfa'

BLOCK_FIRST_TESTNET = 310000
BLOCK_FIRST_TESTNET_HASH = '000000001f605ec6ee8d2c0d21bf3d3ded0a31ca837acc98893876213828989d'
BURN_START_TESTNET = 310000
BURN_END_TESTNET = 4017708              # Fifty years, at ten minutes per block.

BLOCK_FIRST_MAINNET = CP_STAMP_GENESIS_BLOCK #791243 # 791510  # 791243  # 796000  # 790249  # 779650
BLOCK_FIRST_MAINNET_HASH = '000000000000000000058ea4f7bf747a78475f137fd8ff5f22b8db1f6dc1a8c2'
# FIRST MAINNET BLOCK WITH BTCSTAMPS: 793487 TX 50aeb77245a9483a5b077e4e7506c331dc2f628c22046e7d2b4c6ad6c6236ae1
BURN_START_MAINNET = 278310
BURN_END_MAINNET = 283810

BLOCK_FIRST_REGTEST = 0
BLOCK_FIRST_REGTEST_HASH = '0f9188f13cb7b2c71f2a335e3a4fc328bf5beb436012afca590b1a11466e2206'
BURN_START_REGTEST = 101
BURN_END_REGTEST = 150000000

# Protocol defaults
# NOTE: If the DUST_SIZE constants are changed, they MUST also be changed in counterblockd/lib/config.py as well
DEFAULT_REGULAR_DUST_SIZE = 546          # TODO: Revisit when dust size is adjusted in bitcoin core
DEFAULT_MULTISIG_DUST_SIZE = 7800        # <https://bitcointalk.org/index.php?topic=528023.msg7469941#msg7469941>
DEFAULT_OP_RETURN_VALUE = 0
DEFAULT_FEE_PER_KB_ESTIMATE_SMART = 1024
DEFAULT_FEE_PER_KB = 25000               # sane/low default, also used as minimum when estimated fee is used

# UI defaults
DEFAULT_FEE_FRACTION_REQUIRED = .009   # 0.90%
DEFAULT_FEE_FRACTION_PROVIDED = .01    # 1.00%


DEFAULT_REQUESTS_TIMEOUT = 20   # 20 seconds
DEFAULT_RPC_BATCH_SIZE = 20     # A 1 MB block can hold about 4200 transactions.

# Custom exit codes
EXITCODE_UPDATE_REQUIRED = 5


DEFAULT_CHECK_ASSET_CONSERVATION = True

BACKEND_RAW_TRANSACTIONS_CACHE_SIZE = 20000
BACKEND_RPC_BATCH_NUM_WORKERS = 6

UNDOLOG_MAX_PAST_BLOCKS = 100  # the number of past blocks that we store undolog history

ADDRESS_OPTION_REQUIRE_MEMO = 1
ADDRESS_OPTION_MAX_VALUE = ADDRESS_OPTION_REQUIRE_MEMO  # Or list of all the address options

API_LIMIT_ROWS = 1000

MEMPOOL_TXCOUNT_UPDATE_LIMIT = 60000
