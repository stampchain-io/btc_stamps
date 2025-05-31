import logging
import os
import re
from typing import TYPE_CHECKING, Dict, List, Optional, Union

if TYPE_CHECKING:
    import boto3
    from requests.auth import HTTPBasicAuth
else:
    try:
        import boto3
    except ImportError:
        boto3 = None  # type: ignore
    try:
        from requests.auth import HTTPBasicAuth
    except ImportError:
        HTTPBasicAuth = None  # type: ignore

from exceptions import ConfigurationError

logger = logging.getLogger(__name__)

# Cache size configurations
BACKEND_RAW_TRANSACTIONS_CACHE_SIZE = int(os.environ.get("BACKEND_RAW_TRANSACTIONS_CACHE_SIZE", "200000"))
DESERIALIZED_TX_CACHE_SIZE = int(os.environ.get("DESERIALIZED_TX_CACHE_SIZE", "150000"))  # Increased from 100000
DESERIALIZED_TX_CACHE_SIZE = int(os.environ.get("DESERIALIZED_TX_CACHE_SIZE", "150000"))  # Increased from 100000
RUST_PARSER_MAX_CACHE_MB = int(os.environ.get("RUST_PARSER_MAX_CACHE_MB", "250"))  # 250MB for raw transaction data
RUST_PARSER_ENTRIES = int(os.environ.get("RUST_PARSER_ENTRIES", "20000"))  # Match Python cache size

# Cache sizes with memory usage estimates
BALANCE_CACHE_SIZE = int(os.environ.get("BALANCE_CACHE_SIZE", "1000"))  # Reduced from 10000, Active balance tracking
# Cache sizes with memory usage estimates
BALANCE_CACHE_SIZE = int(os.environ.get("BALANCE_CACHE_SIZE", "1000"))  # Reduced from 10000, Active balance tracking
DEPLOYMENT_CACHE_SIZE = int(os.environ.get("DEPLOYMENT_CACHE_SIZE", "1000"))  # Deployment info (~0.5MB memory)
TOTAL_MINTED_CACHE_SIZE = int(os.environ.get("TOTAL_MINTED_CACHE_SIZE", "2000"))
SUBASSET_CACHE_SIZE = int(os.environ.get("SUBASSET_CACHE_SIZE", "1500"))
ADDRESS_CACHE_SIZE = int(os.environ.get("ADDRESS_CACHE_SIZE", "15000"))
SRC721_SUBASSET_CACHE_SIZE = int(os.environ.get("SRC721_SUBASSET_CACHE_SIZE", "256"))  # SRC-721 specific subasset cache

# Block and stamp cache sizes
BLOCK_CACHE_SIZE = int(os.environ.get("BLOCK_CACHE_SIZE", "2"))
STAMP_CACHE_SIZE = int(os.environ.get("STAMP_CACHE_SIZE", "2"))
COLLECTION_CACHE_SIZE = int(os.environ.get("COLLECTION_CACHE_SIZE", str(SUBASSET_CACHE_SIZE)))
PRICE_CACHE_SIZE = int(os.environ.get("PRICE_CACHE_SIZE", str(DEPLOYMENT_CACHE_SIZE)))
SRC101_DEPLOY_CACHE_SIZE = int(os.environ.get("SRC101_DEPLOY_CACHE_SIZE", str(DEPLOYMENT_CACHE_SIZE)))

# Batch processing configurations
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "3000"))  # Process one full block per batch (~1.5MB raw data)
MAX_BATCH_MEMORY = int(os.environ.get("MAX_BATCH_MEMORY", "250"))  # Conservative memory limit for processing

# Memory thresholds
MEMORY_WARNING_THRESHOLD = float(os.environ.get("MEMORY_WARNING_THRESHOLD", "70.0"))  # Early warning at 70%
MAX_MEMORY_PERCENT = float(os.environ.get("MAX_MEMORY_PERCENT", "80.0"))  # Critical at 80%

# Debug flags
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
DEBUG_SKIP_REBUILD_BALANCES = os.getenv("DEBUG_SKIP_REBUILD_BALANCES", "false").lower() == "true"
DEBUG_PROFILING = os.getenv("DEBUG_PROFILING", "false").lower() == "true"
DISABLE_RUST_PARSER = os.environ.get("DISABLE_RUST_PARSER", "False").lower() == "true"
DEBUG_VALIDATION = os.getenv("DEBUG_VALIDATION", "false").lower() == "true"

STORE_FILES = os.environ.get("STORE_FILES", "true").lower() == "true"

# env vars to be set in docker, or locally if connecting to local nodes
RPC_USER: Optional[str] = os.environ.get("RPC_USER", "rpc")
RPC_PASSWORD: Optional[str] = os.environ.get("RPC_PASSWORD", "rpc")
RPC_IP: Optional[str] = os.environ.get("RPC_IP", "127.0.0.1")
RPC_PORT: Optional[str] = os.environ.get("RPC_PORT", "8332")
RPC_TLS = os.environ.get("RPC_TLS", False)

# ZMQ Configuration
ZMQ_HOST = os.environ.get("ZMQ_HOST", "127.0.0.1")
# Default ZMQ ports for different networks
ZMQ_PORT_MAINNET_TX = 9332
ZMQ_PORT_MAINNET_BLOCK = 9333
ZMQ_PORT_TESTNET_TX = 19332
ZMQ_PORT_TESTNET_BLOCK = 19333
ZMQ_PORT_REGTEST_TX = 29332
ZMQ_PORT_REGTEST_BLOCK = 29333

# These will be set based on network type
ZMQ_TX_PORT: int = ZMQ_PORT_MAINNET_TX
ZMQ_BLOCK_PORT: int = ZMQ_PORT_MAINNET_BLOCK
ZMQ_NOTIFICATION_DELAY = float(os.environ.get("ZMQ_NOTIFICATION_DELAY", "5.0"))  # Delay in seconds after ZMQ notification

# CP RPC Configuration
CP_RPC_URL = os.environ.get("CP_RPC_URL")
if not CP_RPC_URL:
    # Only show warning if not in test mode
    if os.environ.get("TESTING") != "1":
        logger.warning("CP_RPC_URL not set in environment, using default counterparty.io endpoint")
    CP_RPC_URL = "https://api.counterparty.io:4000/"
else:
    logger.info(f"Using configured CP_RPC_URL: {CP_RPC_URL}")

CP_RPC_USER = os.environ.get("CP_RPC_USER", "rpc")
CP_RPC_PASSWORD = os.environ.get("CP_RPC_PASSWORD", "rpc")
CP_AUTH = HTTPBasicAuth(CP_RPC_USER, CP_RPC_PASSWORD)

AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID", None)
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY", None)

try:
    AWS_S3_CLIENT = (
        boto3.client(
            "s3",
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        )
        if boto3
        else None
    )
except Exception:
    AWS_S3_CLIENT = None

AWS_CLOUDFRONT_DISTRIBUTION_ID = os.environ.get("AWS_CLOUDFRONT_DISTRIBUTION_ID", None)
AWS_S3_BUCKETNAME = os.environ.get("AWS_S3_BUCKETNAME", None)
AWS_S3_IMAGE_DIR = os.environ.get("AWS_S3_IMAGE_DIR", None)
S3_OBJECTS: Dict[str, Dict[str, str]] = {}
AWS_INVALIDATE_CACHE: Optional[str] = os.environ.get("AWS_INVALIDATE_CACHE", None)
USE_ASYNC_UPLOADS = os.environ.get("USE_ASYNC_UPLOADS", "1") == "1"

# Define for Quicknode or similar remote nodes which use a token
QUICKNODE_ENDPOINT: Optional[str] = os.environ.get("QUICKNODE_URL", None)  # Fallback to old URL for compatibility
QUICKNODE_API_KEY: Optional[str] = os.environ.get("QUICKNODE_API_KEY", None)  # Used for Bearer token auth

# Strip any surrounding quotes from the URL if present
if QUICKNODE_ENDPOINT:
    QUICKNODE_ENDPOINT = QUICKNODE_ENDPOINT.strip("'\"")


def _has_valid_standard_rpc() -> bool:
    """Check if all standard RPC credentials are properly set."""
    # Just check if all required values are present
    return all(x is not None for x in [RPC_USER, RPC_PASSWORD, RPC_IP, RPC_PORT])


# First check if Quicknode credentials are provided
if QUICKNODE_ENDPOINT or QUICKNODE_API_KEY:
    if not (QUICKNODE_ENDPOINT and QUICKNODE_API_KEY):
        raise ConfigurationError(
            "Both QUICKNODE_ENDPOINT and QUICKNODE_API_KEY must be set to use Quicknode. "
            f"Got QUICKNODE_ENDPOINT={'set' if QUICKNODE_ENDPOINT else 'not set'}, "
            f"QUICKNODE_API_KEY={'set' if QUICKNODE_API_KEY else 'not set'}"
        )
    # Log credential presence without exposing sensitive data
    logger.info("Checking Quicknode credentials:")
    logger.info(f"- QUICKNODE_URL/ENDPOINT present: {'Yes' if QUICKNODE_ENDPOINT else 'No'}")
    logger.info(f"- QUICKNODE_API_KEY present: {'Yes' if QUICKNODE_API_KEY else 'No'}")
    logger.info(f"- QUICKNODE_API_KEY length: {len(QUICKNODE_API_KEY) if QUICKNODE_API_KEY else 0}")

    # Clean and format the URL
    QUICKNODE_ENDPOINT = QUICKNODE_ENDPOINT.strip().rstrip("/")

    # Ensure URL has proper scheme
    if not QUICKNODE_ENDPOINT.startswith(("http://", "https://")):
        QUICKNODE_ENDPOINT = f"https://{QUICKNODE_ENDPOINT}"

    # Add trailing slash for consistent path handling
    QUICKNODE_ENDPOINT = f"{QUICKNODE_ENDPOINT}/"

    logger.info(f"Using formatted Quicknode endpoint: {QUICKNODE_ENDPOINT}")

    # Format: https://sample-endpoint-name.network.quiknode.pro/api-key/
    # Clean API key and include it in URL path for Quicknode
    clean_api_key = QUICKNODE_API_KEY.strip("'\"")  # Remove any quotes
    if not QUICKNODE_ENDPOINT.endswith(clean_api_key):
        RPC_URL = f"{QUICKNODE_ENDPOINT}{clean_api_key}/"
    else:
        RPC_URL = QUICKNODE_ENDPOINT

    # Don't use standard RPC credentials with Quicknode
    RPC_IP = None
    RPC_PORT = None
    RPC_USER = None
    RPC_PASSWORD = None

    logger.debug("Using Quicknode URL format with API key in path")
    logger.debug("Configuration values:")
    logger.debug(f"- RPC_URL: {RPC_URL}")  # No need to mask URL since auth is via Bearer token
    logger.debug(f"- RPC_IP: {RPC_IP}")
    logger.debug(f"- RPC_PORT: {RPC_PORT}")
    logger.debug(f"- RPC_USER: {RPC_USER}")
    logger.debug("Quicknode configuration validated")
else:
    # If not using Quicknode, validate standard RPC credentials
    if not _has_valid_standard_rpc():
        raise ConfigurationError(
            "Must provide either valid Quicknode credentials (QUICKNODE_ENDPOINT and QUICKNODE_API_KEY) "
            "or valid standard RPC credentials (non-default values for RPC_USER, RPC_PASSWORD, "
            "RPC_IP, and RPC_PORT). Using default values is not allowed."
        )

    # Construct RPC URL based on TLS setting
    if RPC_TLS:
        RPC_URL = f"https://{RPC_USER}:{RPC_PASSWORD}@{RPC_IP}:{RPC_PORT}"
        logger.debug(f"Using TLS RPC URL: {RPC_URL.replace(RPC_PASSWORD or '', '****')}")
    else:
        RPC_URL = f"http://{RPC_USER}:{RPC_PASSWORD}@{RPC_IP}:{RPC_PORT}"
        logger.debug(f"Using non-TLS RPC URL: {RPC_URL.replace(RPC_PASSWORD or '', '****')}")
    logger.info("Standard RPC configuration validated")

# Modified URL masking that works for both authentication types
if QUICKNODE_ENDPOINT and QUICKNODE_API_KEY:
    # Mask API key in URL path using regex
    masked_url = re.sub(r"(https?://[^/]+/)([^/]+)(/?)", r"\1****\3", RPC_URL)
else:
    # Standard credential masking
    masked_url = RPC_URL.replace(RPC_PASSWORD or "", "****")

logger.info(f"Final RPC URL format: {masked_url}")

RPC_BATCH_SIZE = 50  # A 1 MB block can hold about 4200 transactions.

# Add new constants for the V2 CP API endpoints
# Configure primary and backup nodes for automatic fallback
primary_url = f"{CP_RPC_URL.rstrip('/').replace('/api/', '/')}/v2"

# Determine backup URL based on primary
if "127.0.0.1" in primary_url or "localhost" in primary_url:
    # If primary is local, use external as backup
    backup_url = "https://api.counterparty.io:4000/v2"
else:
    # If primary is external, use local as backup
    backup_url = "http://127.0.0.1:4000/v2"

XCP_V2_NODES = [
    {
        "name": "counterparty-primary",
        "url": primary_url,
    },
    {
        "name": "counterparty-backup", 
        "url": backup_url,
    },
]  # TODO(reinamora137): check versions of both endpoints, add tracking for validated indexes or reparses on each.

logger.info("XCP V2 Node Configuration:")
for node in XCP_V2_NODES:
    logger.info(f"  - {node['name']}: {node['url']}")

TRANSACTIONS_TABLE = "transactions"
BLOCKS_TABLE = "blocks"
STAMP_TABLE = "StampTableV4"
SRC20_TABLE = "SRC20"
SRC20_VALID_TABLE = "SRC20Valid"
SRC20_BALANCES_TABLE = "balances"
SRC_BACKGROUND_TABLE = "srcbackground"
SRC101_TABLE = "SRC101"
SRC101_VALID_TABLE = "SRC101Valid"
SRC101_PRICE_TABLE = "src101price"
SRC101_OWNERS_TABLE = "owners"
SRC101_RECIPIENTS_TABLE = "recipients"

DOMAINNAME = os.environ.get("DOMAINNAME", "stampchain.io")
SUPPORTED_SUB_PROTOCOLS = ["SRC-721", "SRC-20", "SRC-101"]
INVALID_BTC_STAMP_SUFFIX = ["plain", "octet-stream", "js", "css", "x-empty", "json"]

CP_STAMP_GENESIS_BLOCK: int = 779652  # block height of first valid stamp transaction on counterparty
CP_SRC20_GENESIS_BLOCK: int = 788041  # This initial start of SRC-20 on Counterparty
BTC_SRC20_GENESIS_BLOCK: int = 793068  # block height of first SRC-20 without CP encoding
BTC_SRC20_OLGA_BLOCK: int = 865000  # block height of first SRC-20 with P2WSH OLGA encoding
CP_SRC721_GENESIS_BLOCK: int = 792370  # block height of first SRC-721

BTC_SRC101_GENESIS_BLOCK: int = 870652  # block height of first SRC-101
BTC_SRC101_IMG_OPTIONAL_BLOCK: int = 872200
BTC_SRC101_OLGA_BLOCK: int = 0

CP_SRC20_END_BLOCK: int = 796000  # The last SRC-20 on CP  - IGNORE ALL SRC-20 on CP AFTER THIS BLOCK
CP_BMN_FEAT_BLOCK_START: int = 815130  # BMN audio file support
CP_P2WSH_FEAT_BLOCK_START: int = 833000  # OLGA / P2WSH transactions
CP_SUBASSET_FEAT_BLOCK_START: int = 866000  # Subasset no longer require XCP fees

# Consensus changes
STRIP_WHITESPACE: int = 797200
STOP_BASE64_REPAIR: int = 784550


VERSION_MAJOR: Optional[int]
VERSION_MINOR: Optional[int]
VERSION_REVISION: Optional[int]
VERSION_RELEASE: Optional[str]
VERSION_BUILD: Optional[int]
BACKEND_NAME: str = "bitcoincore"
BACKEND_CONNECT: str = "localhost"
BACKEND_PORT: int = 8332
BACKEND_SSL: bool = True
BACKEND_SSL_NO_VERIFY: bool = False
BACKEND_POLL_INTERVAL: float = 2.0
FORCE: bool = os.environ.get("FORCE", "false").lower() == "true"
PREFIX: bytes = b"stamp:"
CP_PREFIX: bytes = b"CNTRPRTY"
BLOCK_FIRST: int = 0
REQUESTS_TIMEOUT: int = 30
ESTIMATE_FEE_PER_KB: int = 1000
LOG: Optional[str] = None
REGTEST: bool = False
CUSTOMNET: bool = False
CHECKDB: bool = False
TESTNET: Optional[str] = os.environ.get("TESTNET", None)

# Define additional constants used in server.py
DEFAULT_BACKEND_PORT: int = 8332
DEFAULT_BACKEND_PORT_TESTNET: int = 18332
DEFAULT_BACKEND_PORT_REGTEST: int = 18443
DEFAULT_REQUESTS_TIMEOUT: int = 30
DEFAULT_ESTIMATE_FEE_PER_KB: int = 1000
BLOCK_FIRST_MAINNET: int = 0
BLOCK_FIRST_TESTNET: int = 0
BLOCK_FIRST_REGTEST: int = 0
STAMPS_NAME: str = "stamps"
APP_NAME: str = "app"

# Load retry and rate limit settings from environment with validation
CP_RPC_RETRY_COUNT = int(os.environ.get("CP_RPC_RETRY_COUNT", "3"))
CP_RPC_RETRY_DELAY = int(os.environ.get("CP_RPC_RETRY_DELAY", "2"))
CP_RPC_TIMEOUT = int(os.environ.get("CP_RPC_TIMEOUT", "30"))
CP_RATE_LIMIT = int(os.environ.get("CP_RATE_LIMIT", "2"))
CP_MAX_RETRIES = int(os.environ.get("CP_MAX_RETRIES", "5"))
CP_BASE_DELAY = int(os.environ.get("CP_BASE_DELAY", "1"))
CP_BATCH_SIZE = int(os.environ.get("CP_BATCH_SIZE", "50"))


SRC_VALIDATION_API1 = "https://www.okx.com/fullnode/src20/src/rpc/api/v1/reconciliation/balances_hash?block_height="
SRC_VALIDATION_API2 = (
    "https://pkizh327c7.execute-api.us-west-2.amazonaws.com/prod/external/balanceHash?blockIndex={block_index}&secret={secret}"
)
SRC_VALIDATION_SECRET_API2: Optional[str] = os.environ.get("SRC_VALIDATION_SECRET_API2", None)

BURNKEYS = [
    "022222222222222222222222222222222222222222222222222222222222222222",
    "033333333333333333333333333333333333333333333333333333333333333333",
    "020202020202020202020202020202020202020202020202020202020202020202",
    "030303030303030303030303030303030303030303030303030303030303030302",
    "030303030303030303030303030303030303030303030303030303030303030303",
]

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
    "html": "text/html",
    "eps": "image/eps",
    "pdf": "application/pdf",
    "js": "application/javascript",
    "txt": "text/plain",
    "css": "text/css",
    "json": "application/json",
    "xml": "application/xml",
    "zip": "application/zip",
    "rar": "application/x-rar-compressed",
    "7z": "application/x-7z-compressed",
    "gz": "application/x-gzip",
    "bz2": "application/x-bzip2",
    "tar": "application/x-tar",
    "xz": "application/x-xz",
    "bz": "application/x-bzip",
    "lz": "application/x-lzip",
    "lzma": "application/x-lzma",
    "lzo": "application/x-lzop",
    "z": "application/x-compress",
    "Z": "application/x-compress",
    "gz": "application/x-gzip",
    "gzip": "application/gzip",
    "tgz": "application/x-gzip",
    "tar.gz": "application/x-gzip",
    "tgz": "application/x-gzip",
    "tar.gz": "application/x-gzip",
}

BLOCK_FIELDS_POSITION = {
    "block_index": 0,
    "block_hash": 1,
    "block_time": 2,
    "previous_block_hash": 3,
    "difficulty": 4,
    "ledger_hash": 5,
    "txlist_hash": 6,
    "messages_hash": 7,
    "indexed": 8,
}

TXS_FIELDS_POSITION = {
    "tx_index": 0,
    "tx_hash": 1,
    "block_index": 2,
    "block_hash": 3,
    "block_time": 4,
    "source": 5,
    "destination": 6,
    "btc_amount": 7,
    "fee": 8,
    "data": 9,
}

SUPPORTED_CHARS = ".!#$%&()*0123456789<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ^_abcdefghijklmnopqrstuvwxyz~"

SUPPORTED_UNICODE = "\U0001f004\U0001f0cf\U0001f170\U0001f171\U0001f17e\U0001f17f\U0001f18e\U0001f191\U0001f192\U0001f193\U0001f194\U0001f195\U0001f196\U0001f197\U0001f198\U0001f199\U0001f19a\U0001f201\U0001f202\U0001f21a\U0001f22f\U0001f232\U0001f233\U0001f234\U0001f235\U0001f236\U0001f237\U0001f238\U0001f239\U0001f23a\U0001f250\U0001f251\U0001f300\U0001f301\U0001f302\U0001f303\U0001f304\U0001f305\U0001f306\U0001f307\U0001f308\U0001f309\U0001f30a\U0001f30b\U0001f30c\U0001f30d\U0001f30e\U0001f30f\U0001f310\U0001f311\U0001f312\U0001f313\U0001f314\U0001f315\U0001f316\U0001f317\U0001f318\U0001f319\U0001f31a\U0001f31b\U0001f31c\U0001f31d\U0001f31e\U0001f31f\U0001f320\U0001f321\U0001f324\U0001f325\U0001f642\U0001f326\U0001f327\U0001f328\U0001f329\U0001f32a\U0001f32b\U0001f32c\U0001f32d\U0001f32e\U0001f32f\U0001f330\U0001f331\U0001f332\U0001f333\U0001f334\U0001f335\U0001f336\U0001f337\U0001f338\U0001f339\U0001f33a\U0001f33b\U0001f33c\U0001f33d\U0001f33e\U0001f33f\U0001f340\U0001f341\U0001f342\U0001f343\U0001f344\U0001f345\U0001f346\U0001f347\U0001f348\U0001f349\U0001f34a\U0001f34b\U0001f34c\U0001f34d\U0001f34e\U0001f34f\U0001f350\U0001f351\U0001f352\U0001f353\U0001f354\U0001f355\U0001f356\U0001f357\U0001f358\U0001f359\U0001f35a\U0001f35b\U0001f35c\U0001f35d\U0001f35e\U0001f35f\U0001f360\U0001f361\U0001f362\U0001f363\U0001f364\U0001f365\U0001f366\U0001f367\U0001f368\U0001f369\U0001f36a\U0001f36b\U0001f36c\U0001f36d\U0001f36e\U0001f36f\U0001f370\U0001f371\U0001f372\U0001f373\U0001f374\U0001f375\U0001f376\U0001f377\U0001f378\U0001f379\U0001f37a\U0001f37b\U0001f37c\U0001f37d\U0001f37e\U0001f37f\U0001f380\U0001f381\U0001f382\U0001f383\U0001f384\U0001f385\U0001f386\U0001f387\U0001f388\U0001f389\U0001f38a\U0001f38b\U0001f38c\U0001f38d\U0001f38e\U0001f38f\U0001f390\U0001f391\U0001f392\U0001f393\U0001f396\U0001f397\U0001f399\U0001f39a\U0001f39b\U0001f39e\U0001f39f\U0001f3a0\U0001f3a1\U0001f3a2\U0001f3a3\U0001f3a4\U0001f3a5\U0001f3a6\U0001f3a7\U0001f3a8\U0001f3a9\U0001f3aa\U0001f3ab\U0001f3ac\U0001f3ad\U0001f3ae\U0001f3af\U0001f3b0\U0001f3b1\U0001f3b2\U0001f3b3\U0001f3b4\U0001f3b5\U0001f3b6\U0001f3b7\U0001f3b8\U0001f3b9\U0001f3ba\U0001f3bb\U0001f3bc\U0001f3bd\U0001f3be\U0001f3bf\U0001f3c0\U0001f3c1\U0001f3c2\U0001f3c3\U0001f3c4\U0001f3c5\U0001f3c6\U0001f3c7\U0001f3c8\U0001f3c9\U0001f3ca\U0001f3cb\U0001f3cc\U0001f3cd\U0001f3ce\U0001f3cf\U0001f3d0\U0001f3d1\U0001f3d2\U0001f3d3\U0001f3d4\U0001f3d5\U0001f3d6\U0001f3d7\U0001f3d8\U0001f3d9\U0001f3da\U0001f3db\U0001f3dc\U0001f3dd\U0001f3de\U0001f3df\U0001f3e0\U0001f3e1\U0001f3e2\U0001f3e3\U0001f3e4\U0001f3e5\U0001f3e6\U0001f3e7\U0001f3e8\U0001f3e9\U0001f3ea\U0001f3eb\U0001f3ec\U0001f3ed\U0001f3ee\U0001f3ef\U0001f3f0\U0001f3f3\U0001f3f4\U0001f3f5\U0001f3f7\U0001f3f8\U0001f3f9\U0001f3fa\U0001f400\U0001f401\U0001f402\U0001f403\U0001f404\U0001f405\U0001f406\U0001f407\U0001f408\U0001f409\U0001f40a\U0001f40b\U0001f40c\U0001f40d\U0001f40e\U0001f40f\U0001f410\U0001f411\U0001f412\U0001f413\U0001f414\U0001f415\U0001f416\U0001f417\U0001f418\U0001f419\U0001f41a\U0001f41b\U0001f41c\U0001f41d\U0001f41e\U0001f41f\U0001f420\U0001f421\U0001f422\U0001f423\U0001f424\U0001f425\U0001f426\U0001f427\U0001f428\U0001f429\U0001f42a\U0001f42b\U0001f42c\U0001f42d\U0001f42e\U0001f42f\U0001f430\U0001f431\U0001f432\U0001f433\U0001f434\U0001f435\U0001f436\U0001f437\U0001f438\U0001f439\U0001f43a\U0001f43b\U0001f43c\U0001f43d\U0001f43e\U0001f43f\U0001f440\U0001f441\U0001f442\U0001f443\U0001f444\U0001f445\U0001f446\U0001f447\U0001f448\U0001f449\U0001f44a\U0001f44b\U0001f44c\U0001f44d\U0001f44e\U0001f44f\U0001f450\U0001f451\U0001f452\U0001f453\U0001f454\U0001f455\U0001f456\U0001f457\U0001f458\U0001f459\U0001f45a\U0001f45b\U0001f45c\U0001f45d\U0001f45e\U0001f45f\U0001f460\U0001f461\U0001f462\U0001f463\U0001f464\U0001f465\U0001f466\U0001f467\U0001f468\U0001f469\U0001f46a\U0001f46b\U0001f46c\U0001f46d\U0001f46e\U0001f46f\U0001f470\U0001f471\U0001f472\U0001f473\U0001f474\U0001f475\U0001f476\U0001f477\U0001f478\U0001f479\U0001f47a\U0001f47b\U0001f47c\U0001f47d\U0001f47e\U0001f47f\U0001f480\U0001f481\U0001f482\U0001f483\U0001f484\U0001f485\U0001f486\U0001f487\U0001f488\U0001f489\U0001f48a\U0001f48b\U0001f48c\U0001f48d\U0001f48e\U0001f48f\U0001f490\U0001f491\U0001f492\U0001f493\U0001f494\U0001f495\U0001f496\U0001f497\U0001f498\U0001f499\U0001f49a\U0001f49b\U0001f49c\U0001f49d\U0001f49e\U0001f49f\U0001f4a0\U0001f4a1\U0001f4a2\U0001f4a3\U0001f4a4\U0001f4a5\U0001f4a6\U0001f4a7\U0001f4a8\U0001f4a9\U0001f4aa\U0001f4ab\U0001f4ac\U0001f4ad\U0001f4ae\U0001f4af\U0001f4b0\U0001f4b1\U0001f4b2\U0001f4b3\U0001f4b4\U0001f4b5\U0001f4b6\U0001f4b7\U0001f4b8\U0001f4b9\U0001f4ba\U0001f4bb\U0001f4bc\U0001f4bd\U0001f4be\U0001f4bf\U0001f4c0\U0001f4c1\U0001f4c2\U0001f4c3\U0001f4c4\U0001f4c5\U0001f4c6\U0001f4c7\U0001f4c8\U0001f4c9\U0001f4ca\U0001f4cb\U0001f4cc\U0001f4cd\U0001f4ce\U0001f4cf\U0001f4d0\U0001f4d1\U0001f4d2\U0001f4d3\U0001f4d4\U0001f4d5\U0001f4d6\U0001f4d7\U0001f4d8\U0001f4d9\U0001f4da\U0001f4db\U0001f4dc\U0001f4dd\U0001f4de\U0001f4df\U0001f4e0\U0001f4e1\U0001f4e2\U0001f4e3\U0001f4e4\U0001f4e5\U0001f4e6\U0001f4e7\U0001f4e8\U0001f4e9\U0001f4ea\U0001f4eb\U0001f4ec\U0001f4ed\U0001f4ee\U0001f4ef\U0001f4f0\U0001f4f1\U0001f4f2\U0001f4f3\U0001f4f4\U0001f4f5\U0001f4f6\U0001f4f7\U0001f4f8\U0001f4f9\U0001f4fa\U0001f4fb\U0001f4fc\U0001f4fd\U0001f4ff\U0001f500\U0001f501\U0001f502\U0001f503\U0001f504\U0001f505\U0001f506\U0001f507\U0001f508\U0001f509\U0001f50a\U0001f50b\U0001f50c\U0001f50d\U0001f50e\U0001f50f\U0001f510\U0001f511\U0001f512\U0001f513\U0001f514\U0001f515\U0001f516\U0001f517\U0001f518\U0001f519\U0001f51a\U0001f51b\U0001f51c\U0001f51d\U0001f51e\U0001f51f\U0001f520\U0001f521\U0001f522\U0001f523\U0001f524\U0001f525\U0001f526\U0001f527\U0001f528\U0001f529\U0001f52a\U0001f52b\U0001f52c\U0001f52d\U0001f52e\U0001f52f\U0001f530\U0001f531\U0001f532\U0001f533\U0001f534\U0001f535\U0001f536\U0001f537\U0001f538\U0001f539\U0001f53a\U0001f53b\U0001f53c\U0001f53d\U0001f549\U0001f54a\U0001f54b\U0001f54c\U0001f54d\U0001f54e\U0001f550\U0001f551\U0001f552\U0001f553\U0001f554\U0001f555\U0001f556\U0001f557\U0001f558\U0001f559\U0001f55a\U0001f55b\U0001f55c\U0001f55d\U0001f55e\U0001f55f\U0001f560\U0001f561\U0001f562\U0001f563\U0001f564\U0001f565\U0001f566\U0001f567\U0001f56f\U0001f570\U0001f573\U0001f574\U0001f575\U0001f576\U0001f577\U0001f578\U0001f579\U0001f57a\U0001f587\U0001f58a\U0001f58b\U0001f58c\U0001f58d\U0001f590\U0001f595\U0001f596\U0001f5a4\U0001f5a5\U0001f5a8\U0001f5b1\U0001f5b2\U0001f5bc\U0001f5c2\U0001f5c3\U0001f5c4\U0001f5d1\U0001f5d2\U0001f5d3\U0001f5dc\U0001f5dd\U0001f5de\U0001f5e1\U0001f5e3\U0001f5e8\U0001f5ef\U0001f5f3\U0001f5fa\U0001f5fb\U0001f5fc\U0001f5fd\U0001f5fe\U0001f5ff\U0001f600\U0001f601\U0001f602\U0001f603\U0001f604\U0001f605\U0001f606\U0001f607\U0001f608\U0001f609\U0001f60a\U0001f60b\U0001f60c\U0001f60d\U0001f60e\U0001f60f\U0001f610\U0001f611\U0001f612\U0001f613\U0001f614\U0001f615\U0001f616\U0001f617\U0001f618\U0001f619\U0001f61a\U0001f61b\U0001f61c\U0001f61d\U0001f61e\U0001f61f\U0001f620\U0001f621\U0001f622\U0001f623\U0001f624\U0001f625\U0001f626\U0001f627\U0001f628\U0001f629\U0001f62a\U0001f62b\U0001f62c\U0001f62d\U0001f62e\U0001f62f\U0001f630\U0001f631\U0001f632\U0001f633\U0001f634\U0001f635\U0001f636\U0001f637\U0001f638\U0001f639\U0001f63a\U0001f63b\U0001f63c\U0001f63d\U0001f63e\U0001f63f\U0001f640\U0001f641\U0001f642\U0001f643\U0001f644\U0001f645\U0001f646\U0001f647\U0001f648\U0001f649\U0001f64a\U0001f64b\U0001f64c\U0001f64d\U0001f64e\U0001f64f\U0001f680\U0001f681\U0001f682\U0001f683\U0001f684\U0001f685\U0001f686\U0001f687\U0001f688\U0001f689\U0001f68a\U0001f68b\U0001f68c\U0001f68d\U0001f68e\U0001f68f\U0001f690\U0001f691\U0001f692\U0001f693\U0001f694\U0001f695\U0001f696\U0001f697\U0001f698\U0001f699\U0001f69a\U0001f69b\U0001f69c\U0001f69d\U0001f69e\U0001f69f\U0001f6a0\U0001f6a1\U0001f6a2\U0001f6a3\U0001f6a4\U0001f6a5\U0001f6a6\U0001f6a7\U0001f6a8\U0001f6a9\U0001f6aa\U0001f6ab\U0001f6ac\U0001f6ad\U0001f6ae\U0001f6af\U0001f6b0\U0001f6b1\U0001f6b2\U0001f6b3\U0001f6b4\U0001f6b5\U0001f6b6\U0001f6b7\U0001f6b8\U0001f6b9\U0001f6ba\U0001f6bb\U0001f6bc\U0001f6bd\U0001f6be\U0001f6bf\U0001f6c0\U0001f6c1\U0001f6c2\U0001f6c3\U0001f6c4\U0001f6c5\U0001f6cb\U0001f6cc\U0001f6cd\U0001f6ce\U0001f6cf\U0001f6d0\U0001f6d1\U0001f6d2\U0001f6d5\U0001f6d6\U0001f6d7\U0001f6e0\U0001f6e1\U0001f6e2\U0001f6e3\U0001f6e4\U0001f6e5\U0001f6e9\U0001f6eb\U0001f6ec\U0001f6f0\U0001f6f3\U0001f6f4\U0001f6f5\U0001f6f6\U0001f6f7\U0001f6f8\U0001f6f9\U0001f6fa\U0001f6fb\U0001f6fc\U0001f7e0\U0001f7e1\U0001f7e2\U0001f7e3\U0001f7e4\U0001f7e5\U0001f7e6\U0001f7e7\U0001f7e8\U0001f7e9\U0001f7ea\U0001f7eb\U0001f90c\U0001f90d\U0001f90e\U0001f90f\U0001f910\U0001f911\U0001f912\U0001f913\U0001f914\U0001f915\U0001f916\U0001f917\U0001f918\U0001f919\U0001f91a\U0001f91b\U0001f91c\U0001f91d\U0001f91e\U0001f91f\U0001f920\U0001f921\U0001f922\U0001f923\U0001f924\U0001f925\U0001f926\U0001f927\U0001f928\U0001f929\U0001f92a\U0001f92b\U0001f92c\U0001f92d\U0001f92e\U0001f92f\U0001f930\U0001f931\U0001f932\U0001f933\U0001f934\U0001f935\U0001f936\U0001f937\U0001f938\U0001f939\U0001f93a\U0001f93c\U0001f93d\U0001f93e\U0001f93f\U0001f940\U0001f941\U0001f942\U0001f943\U0001f944\U0001f945\U0001f947\U0001f948\U0001f949\U0001f94a\U0001f94b\U0001f94c\U0001f94d\U0001f94e\U0001f94f\U0001f950\U0001f951\U0001f952\U0001f953\U0001f954\U0001f955\U0001f956\U0001f957\U0001f958\U0001f959\U0001f95a\U0001f95b\U0001f95c\U0001f95d\U0001f95e\U0001f95f\U0001f960\U0001f961\U0001f962\U0001f963\U0001f964\U0001f965\U0001f966\U0001f967\U0001f968\U0001f969\U0001f96a\U0001f96b\U0001f96c\U0001f96d\U0001f96e\U0001f96f\U0001f970\U0001f971\U0001f972\U0001f973\U0001f974\U0001f975\U0001f976\U0001f977\U0001f978\U0001f97a\U0001f97b\U0001f97c\U0001f97d\U0001f97e\U0001f97f\U0001f980\U0001f981\U0001f982\U0001f983\U0001f984\U0001f985\U0001f986\U0001f987\U0001f988\U0001f989\U0001f98a\U0001f98b\U0001f98c\U0001f98d\U0001f98e\U0001f98f\U0001f990\U0001f991\U0001f992\U0001f993\U0001f994\U0001f995\U0001f996\U0001f997\U0001f998\U0001f999\U0001f99a\U0001f99b\U0001f99c\U0001f99d\U0001f99e\U0001f99f\U0001f9a0\U0001f9a1\U0001f9a2\U0001f9a3\U0001f9a4\U0001f9a5\U0001f9a6\U0001f9a7\U0001f9a8\U0001f9a9\U0001f9aa\U0001f9ab\U0001f9ac\U0001f9ad\U0001f9ae\U0001f9af\U0001f9b0\U0001f9b1\U0001f9b2\U0001f9b3\U0001f9b4\U0001f9b5\U0001f9b6\U0001f9b7\U0001f9b8\U0001f9b9\U0001f9ba\U0001f9bb\U0001f9bc\U0001f9bd\U0001f9be\U0001f9bf\U0001f9c0\U0001f9c1\U0001f9c2\U0001f9c3\U0001f9c4\U0001f9c5\U0001f9c6\U0001f9c7\U0001f9c8\U0001f9c9\U0001f9ca\U0001f9cb\U0001f9cd\U0001f9ce\U0001f9cf\U0001f9d0\U0001f9d1\U0001f9d2\U0001f9d3\U0001f9d4\U0001f9d5\U0001f9d6\U0001f9d7\U0001f9d8\U0001f9d9\U0001f9da\U0001f9db\U0001f9dc\U0001f9dd\U0001f9de\U0001f9df\U0001f9e0\U0001f9e1\U0001f9e2\U0001f9e3\U0001f9e4\U0001f9e5\U0001f9e6\U0001f9e7\U0001f9e8\U0001f9e9\U0001f9ea\U0001f9eb\U0001f9ec\U0001f9ed\U0001f9ee\U0001f9ef\U0001f9f0\U0001f9f1\U0001f9f2\U0001f9f3\U0001f9f4\U0001f9f5\U0001f9f6\U0001f9f7\U0001f9f8\U0001f9f9\U0001f9fa\U0001f9fb\U0001f9fc\U0001f9fd\U0001f9fe\U0001f9ff\U0001fa70\U0001fa71\U0001fa72\U0001fa73\U0001fa74\U0001fa78\U0001fa79\U0001fa7a\U0001fa80\U0001fa81\U0001fa82\U0001fa83\U0001fa84\U0001fa85\U0001fa86\U0001fa90\U0001fa91\U0001fa92\U0001fa93\U0001fa94\U0001fa95\U0001fa96\U0001fa97\U0001fa98\U0001fa99\U0001fa9a\U0001fa9b\U0001fa9c\U0001fa9d\U0001fa9e\U0001fa9f\U0001faa0\U0001faa1\U0001faa2\U0001faa3\U0001faa4\U0001faa5\U0001faa6\U0001faa7\U0001faa8\U0001fab0\U0001fab1\U0001fab2\U0001fab3\U0001fab4\U0001fab5\U0001fab6\U0001fac0\U0001fac1\U0001fac2\U0001fad0\U0001fad1\U0001fad2\U0001fad3\U0001fad4\U0001fad5\U0001fad6"

UNICODE_SET = set(SUPPORTED_UNICODE)
CHAR_SET = set(SUPPORTED_CHARS)

TICK_PATTERN_SET = UNICODE_SET.union(CHAR_SET)


# Versions
VERSION_STRING = "1.8.26+canary.166"


def update_version_globals(version_string: str):
    global VERSION_MAJOR, VERSION_MINOR, VERSION_REVISION, VERSION_RELEASE, VERSION_BUILD
    match = re.match(r"(\d+)\.(\d+)\.(\d+)(\+([a-z]+)\.(\d+))?", version_string)
    if match:
        (
            major,
            minor,
            revision,
            _,
            release,
            build,
        ) = match.groups()
        VERSION_MAJOR = int(major)
        VERSION_MINOR = int(minor)
        VERSION_REVISION = int(revision)
        VERSION_RELEASE = release or ""
        VERSION_BUILD = int(build) if build and build.isdigit() else 0
    else:
        raise ValueError("Invalid version string")


update_version_globals(VERSION_STRING)


BTC_NAME = "Bitcoin"
STAMPS_NAME = "btc_stamps"
APP_NAME = STAMPS_NAME.lower()


DEFAULT_BACKEND_PORT_REGTEST = 28332
DEFAULT_BACKEND_PORT_TESTNET = 18332
DEFAULT_BACKEND_PORT = 8332

BLOCK_FIRST_TESTNET = int(os.environ.get("BLOCK_FIRST_TESTNET", 2979826))

BLOCK_FIRST_MAINNET = CP_STAMP_GENESIS_BLOCK
BLOCK_FIRST_REGTEST = 0

DEFAULT_REQUESTS_TIMEOUT = 20  # 20 seconds

BACKEND_RPC_BATCH_NUM_WORKERS = 6

LEGACY_COLLECTIONS: List[Dict[str, Union[str, List[str], List[int], Optional[bool]]]] = [
    {
        "name": "POSH",
        "is_posh": True,
    },
    {
        "name": "KEVIN",
        "file_hashes": ["33d7c7c17c36527bd245c59fb37bcea4"],
        "stamps": [
            4258,
            4265,
            4283,
            4303,
            5096,
            5097,
            5104,
            16494,
            16495,
            16496,
            16497,
            16498,
            16499,
            17721,
            17722,
            18315,
            18317,
            18319,
            18321,
            18322,
            18323,
            18324,
            18325,
            18326,
            18327,
            18328,
            18329,
            18330,
            18332,
            18333,
            18335,
            18336,
            18338,
            18339,
            18340,
            18341,
            18342,
            18343,
            18344,
            18345,
            18346,
            18347,
            18348,
            18349,
            18350,
            18351,
            18352,
            18353,
            18354,
            18355,
            18356,
            18357,
            18358,
            18359,
            18360,
            18361,
            18362,
            18363,
            18364,
            18365,
            18366,
            18367,
            18368,
            18369,
            18370,
            18371,
            18373,
            18374,
            18375,
            18376,
            18379,
            18380,
            18381,
            18382,
            18386,
            18387,
            18390,
            18393,
            18394,
            18395,
            18396,
            18398,
            18399,
            18400,
            18401,
            18402,
            18403,
            18405,
            18406,
            18407,
            18408,
            18409,
            18410,
            18412,
            18415,
            18418,
            18419,
            18420,
            18421,
            18422,
            18424,
            18426,
            18428,
            18430,
        ],
    },
    {
        "name": "FLOCKS",
        "stamps": [8, 9, 10, 11, 31, 32, 33, 34, 35, 36, 38, 39, 40, 329, 330, 330, 16690, 16691, 16692],
    },
]

# Bootstrap file GitHub URLs - allows loading bootstrap data directly from GitHub
BOOTSTRAP_GITHUB_BASE_URL = os.environ.get(
    "BOOTSTRAP_GITHUB_BASE_URL", "https://raw.githubusercontent.com/stampchain-io/btc_stamps/dev/indexer/bootstrap"
)
BOOTSTRAP_CREATOR_CSV_URL = os.environ.get("BOOTSTRAP_CREATOR_CSV_URL", f"{BOOTSTRAP_GITHUB_BASE_URL}/creator.csv")
BOOTSTRAP_SRCBACKGROUND_CSV_URL = os.environ.get(
    "BOOTSTRAP_SRCBACKGROUND_CSV_URL", f"{BOOTSTRAP_GITHUB_BASE_URL}/srcbackground.csv"
)
