"""Server initialization and configuration."""

import concurrent.futures
import decimal
import hashlib
import logging
import os
import signal
import sys
import threading

import appdirs
from bitcoin import SelectParams
from pymysql.connections import Connection

import config
import index_core.blocks as blocks
import index_core.log as log
from exceptions import ConfigurationError
from index_core.async_upload import start_upload_worker, stop_upload_worker, wait_for_uploads
from index_core.aws import get_s3_objects
from index_core.backend import Backend
from index_core.check import cp_version, software_version
from index_core.database import initialize_db

logger = logging.getLogger(__name__)

D = decimal.Decimal

# Global flag for graceful shutdown
shutdown_flag = threading.Event()

# Global backend instance - use the singleton
backend_instance = Backend()


def sigterm_handler(_signo, _stack_frame):
    """Handle shutdown signals gracefully."""
    if _signo == signal.SIGINT:
        signal_name = "SIGINT"
        exit_code = 130
    elif _signo == signal.SIGTERM:
        signal_name = "SIGTERM"
        exit_code = 143
    else:
        exit_code = 1
        signal_name = f"SIGNAL_{_signo}"

    logger.info(f"Received {signal_name}, shutting down...")

    # Set the shutdown flag to stop the main loop
    shutdown_flag.set()

    # Wait for pending uploads to complete with a timeout
    if config.USE_ASYNC_UPLOADS and config.STORE_FILES:
        logger.info("Waiting for pending uploads to complete...")
        if wait_for_uploads(timeout=10.0):
            logger.info("All pending uploads completed successfully.")
        else:
            logger.warning("Timed out waiting for uploads to complete. Some uploads may be lost.")

        # Stop the async upload worker
        logger.info("Stopping async upload worker...")
        stop_upload_worker()

    # Exit with the appropriate code
    sys.exit(exit_code)


signal.signal(signal.SIGTERM, sigterm_handler)
signal.signal(signal.SIGINT, sigterm_handler)


def initialize(*args, **kwargs):
    initialize_config(*args, **kwargs)
    return initialize_db()


def initialize_config(
    log_file=None,
    testnet=False,
    regtest=False,
    backend_connect=None,
    backend_port=None,
    backend_ssl=False,
    backend_ssl_no_verify=False,
    backend_poll_interval=None,
    force=False,
    verbose=False,
    console_logfilter=None,
    requests_timeout=config.DEFAULT_REQUESTS_TIMEOUT,
    estimate_fee_per_kb=None,
    backend_ssl_verify=None,
    customnet=None,
    checkdb=False,
):
    """Initialize configuration with proper network selection."""
    # Set network based on config
    if config.TESTNET or testnet:
        config.BLOCK_FIRST = config.BLOCK_FIRST_TESTNET
        SelectParams("testnet")
    elif regtest:
        config.BLOCK_FIRST = config.BLOCK_FIRST_REGTEST
        SelectParams("regtest")
    else:
        config.BLOCK_FIRST = config.BLOCK_FIRST_MAINNET
        SelectParams("mainnet")

    # Set other config attributes based on parameters
    config.BACKEND_NAME = "bitcoincore"
    config.BACKEND_CONNECT = backend_connect or "localhost"
    config.BACKEND_PORT = int(
        backend_port or (config.DEFAULT_BACKEND_PORT_TESTNET if testnet else config.DEFAULT_BACKEND_PORT)
    )
    config.BACKEND_SSL = backend_ssl
    config.BACKEND_SSL_NO_VERIFY = backend_ssl_no_verify
    config.BACKEND_POLL_INTERVAL = float(backend_poll_interval or 1)
    config.FORCE = force
    config.PREFIX = b"stamp:"
    config.CP_PREFIX = b"CNTRPRTY"
    config.REQUESTS_TIMEOUT = requests_timeout
    config.ESTIMATE_FEE_PER_KB = estimate_fee_per_kb or config.DEFAULT_ESTIMATE_FEE_PER_KB

    try:
        sha3_256_hash = hashlib.sha3_256("".encode("utf-8")).hexdigest()
        if sha3_256_hash != "a7ffc6f8bf1ed76651c14756a061d662f580ff4de43b49fa82d80a4b80f8434a":
            raise ValueError(f"SHA3-256 hash mismatch: {sha3_256_hash}")

        sha256_hash = hashlib.sha256("".encode("utf-8")).hexdigest()
        if sha256_hash != "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855":
            raise ValueError(f"SHA-256 hash mismatch: {sha256_hash}")

    except ValueError as e:
        logger.error(f"SHA Hash Inconsistencies: {e}")
        raise e

    # Data directory
    data_dir = appdirs.user_data_dir(appauthor=config.STAMPS_NAME, appname=config.APP_NAME, roaming=True)
    if not os.path.isdir(data_dir):
        os.makedirs(data_dir, mode=0o755)

    logger.info("data_dir: {}".format(data_dir))
    logger.info("log_file: {}".format(log_file))

    # regtest
    config.REGTEST = regtest
    # ignore-scan
    if customnet is not None and len(customnet) > 0:
        config.CUSTOMNET = True
        config.REGTEST = True  # Custom nets are regtests with different parameters
    else:
        config.CUSTOMNET = False

    network = ""
    if config.TESTNET:
        network += ".testnet"
    if config.REGTEST:
        network += ".regtest"

    if checkdb:
        config.CHECKDB = True
    else:
        config.CHECKDB = False

    # Log directory
    log_dir = appdirs.user_log_dir(appauthor=config.STAMPS_NAME, appname=config.APP_NAME)
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir, mode=0o755)

    # Log
    if log_file is False:  # no file logging
        config.LOG = None
    elif not log_file:  # default location
        filename = "server{}.log".format(network)
        config.LOG = os.path.join(log_dir, filename)
    else:  # user-specified location
        config.LOG = log_file

    # Set up logging.
    log.set_up(
        log.ROOT_LOGGER,
        verbose=verbose,
        logfile=config.LOG,
        console_logfilter=console_logfilter,
    )
    if config.LOG:
        logger.debug("Writing server log to file: `{}`".format(config.LOG))

    # Log software version and CP version only once during initialization
    software_version()
    cp_version(log_connection=True)

    # Log unhandled errors.
    def handle_exception(exc_type, exc_value, exc_traceback):
        logger.error("Unhandled Exception", exc_info=(exc_type, exc_value, exc_traceback))

    sys.excepthook = handle_exception

    ##############
    # Backend Connection Configuration
    # Handles setup of Bitcoin Core RPC connection parameters

    # Backend name
    config.BACKEND_NAME = "bitcoincore"

    # Backend RPC host (Bitcoin Core)
    if backend_connect:
        config.BACKEND_CONNECT = backend_connect
    else:
        config.BACKEND_CONNECT = "localhost"

    # Backend Core RPC port (Bitcoin Core)
    if backend_port:
        config.BACKEND_PORT = backend_port
    else:
        if config.TESTNET:
            config.BACKEND_PORT = config.DEFAULT_BACKEND_PORT_TESTNET
        elif config.REGTEST:
            config.BACKEND_PORT = config.DEFAULT_BACKEND_PORT_REGTEST
        else:
            config.BACKEND_PORT = config.DEFAULT_BACKEND_PORT

    try:
        config.BACKEND_PORT = int(config.BACKEND_PORT)
        if not (int(config.BACKEND_PORT) > 1 and int(config.BACKEND_PORT) < 65535):
            raise ConfigurationError("invalid backend API port number")
    except Exception as e:
        raise ConfigurationError(f"Please specify a valid port number backend-port configuration parameter {e}")

    # Backend Core RPC SSL
    if backend_ssl:
        config.BACKEND_SSL = backend_ssl
    else:
        config.BACKEND_SSL = False  # Default to off.

    # Backend Core RPC SSL Verify
    if backend_ssl_verify is not None:
        logger.warning("The server parameter `backend_ssl_verify` is deprecated. Use `backend_ssl_no_verify` instead.")
        config.BACKEND_SSL_NO_VERIFY = not backend_ssl_verify
    else:
        if backend_ssl_no_verify:
            config.BACKEND_SSL_NO_VERIFY = backend_ssl_no_verify
        else:
            config.BACKEND_SSL_NO_VERIFY = False  # Default to on (don't support self‐signed certificates)

    # Backend Poll Interval
    if backend_poll_interval:
        config.BACKEND_POLL_INTERVAL = backend_poll_interval
    else:
        config.BACKEND_POLL_INTERVAL = float(os.environ.get("BACKEND_POLL_INTERVAL", "0.5"))

    ##############
    # OTHER SETTINGS

    # skip checks
    if force:
        config.FORCE = force
    else:
        config.FORCE = False

    # Encoding
    config.PREFIX = b"stamp:"
    config.CP_PREFIX = b"CNTRPRTY"

    # Misc
    config.REQUESTS_TIMEOUT = requests_timeout

    if estimate_fee_per_kb is not None:
        config.ESTIMATE_FEE_PER_KB = estimate_fee_per_kb

    # Set ZMQ ports based on network type
    if config.TESTNET:
        config.ZMQ_TX_PORT = config.ZMQ_PORT_TESTNET_TX
        config.ZMQ_BLOCK_PORT = config.ZMQ_PORT_TESTNET_BLOCK
    elif config.REGTEST:
        config.ZMQ_TX_PORT = config.ZMQ_PORT_REGTEST_TX
        config.ZMQ_BLOCK_PORT = config.ZMQ_PORT_REGTEST_BLOCK
    else:
        config.ZMQ_TX_PORT = config.ZMQ_PORT_MAINNET_TX
        config.ZMQ_BLOCK_PORT = config.ZMQ_PORT_MAINNET_BLOCK

    logger.info(f"ZMQ configured for {config.ZMQ_HOST}:{config.ZMQ_TX_PORT} (tx) and {config.ZMQ_BLOCK_PORT} (blocks)")


# Database initialization functions moved to database.py to break circular import


def connect_to_backend():
    """Connect to the backend."""
    # Use the singleton instance
    return Backend()


def start_all(db: Connection) -> None:
    """Start the server with proper initialization and shutdown handling."""
    executor = None  # Initialize executor to None
    try:
        # Initialize the executor
        executor = concurrent.futures.ThreadPoolExecutor()

        # Backend
        connect_to_backend()  # This sets the global backend_instance
        if config.STORE_FILES:
            if config.AWS_SECRET_ACCESS_KEY and config.AWS_ACCESS_KEY_ID and config.AWS_S3_BUCKETNAME:
                config.S3_OBJECTS = get_s3_objects(db, config.AWS_S3_BUCKETNAME, config.AWS_S3_CLIENT)

                # Start the async upload worker if async uploads are enabled
                if config.USE_ASYNC_UPLOADS:
                    logger.info("Starting async upload worker...")
                    start_upload_worker()

        # Start the main indexing process
        blocks.follow(db)
    except Exception as e:
        logger.error(f"Error in main server loop: {e}")
    finally:
        if not shutdown_flag.is_set():
            shutdown_flag.set()
        logger.info("Server shutdown initiated.")

        # Wait for pending uploads to complete with a timeout
        if config.USE_ASYNC_UPLOADS and config.STORE_FILES:
            logger.info("Waiting for pending uploads to complete...")
            if wait_for_uploads(timeout=30.0):
                logger.info("All pending uploads completed successfully.")
            else:
                logger.warning("Timed out waiting for uploads to complete. Some uploads may be lost.")

            # Stop the async upload worker
            logger.info("Stopping async upload worker...")
            stop_upload_worker()

        # Ensure proper cleanup
        if executor:
            executor.shutdown(wait=True)


def reparse(db, block_index=None, quiet=True):
    """Reparse from a specific block index."""
    connect_to_backend()  # This sets the global backend_instance
    blocks.reparse(db, block_index=block_index, quiet=quiet)
