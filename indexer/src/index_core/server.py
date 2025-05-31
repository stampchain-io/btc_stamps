"""Server initialization and configuration."""

import concurrent.futures
import csv
import decimal
import hashlib
import logging
import os
import signal
import sys
import threading
import time
from pathlib import Path

import appdirs
import requests
from bitcoin import SelectParams
from pymysql.connections import Connection

import config
import index_core.blocks as blocks
import index_core.log as log
import index_core.util as util
from exceptions import ConfigurationError
from index_core.async_upload import start_upload_worker, stop_upload_worker, wait_for_uploads
from index_core.aws import get_s3_objects
from index_core.backend import Backend
from index_core.check import cp_version, software_version
from index_core.database import last_db_index
from index_core.database_manager import db_manager

logger = logging.getLogger(__name__)

D = decimal.Decimal

# Global flag for graceful shutdown
shutdown_flag = threading.Event()

# Global backend instance - use the singleton
backend_instance = Backend()

CACHE_DIR = Path(appdirs.user_cache_dir(appauthor=config.STAMPS_NAME, appname=config.APP_NAME)) / ".indexer_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


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


def initialize_tables(db):
    try:
        logger.info("initializing tables...")
        cursor = db.cursor()
        
        # Check if tables already exist to avoid unnecessary schema execution
        required_tables = [
            'blocks', 'transactions', 'StampTableV4', 'srcbackground', 'creator',
            'SRC20', 'SRC20Valid', 'balances', 's3objects', 'collections',
            'collection_creators', 'collection_stamps', 'src20_metadata',
            'SRC101', 'SRC101Valid', 'owners', 'recipients', 'src101price', 'src20_token_stats'
        ]
        
        # Quick check if all tables exist
        cursor.execute("""
            SELECT COUNT(*) as table_count 
            FROM information_schema.tables 
            WHERE table_schema = DATABASE() 
            AND table_name IN ({})
        """.format(','.join(['%s'] * len(required_tables))), required_tables)
        
        existing_count = cursor.fetchone()[0]
        
        if existing_count == len(required_tables):
            logger.info(f"All {len(required_tables)} required tables already exist, skipping schema execution")
        else:
            logger.info(f"Found {existing_count}/{len(required_tables)} tables, executing schema...")
            # Get the path to table_schema.sql relative to this file
            schema_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "table_schema.sql")
            with open(schema_path, "r") as file:
                sql_script = file.read()
            sql_commands = [cmd.strip() for cmd in sql_script.split(";") if cmd.strip()]
            for command in sql_commands:
                try:
                    db_manager.execute_with_retry(cursor, command)
                except Exception as e:
                    logger.error(f"Error executing command:{command};\nerror:{e}")
                    raise e

        import_csv_data(
            cursor,
            config.BOOTSTRAP_CREATOR_CSV_URL,
            """
            INSERT INTO creator (address, creator)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE creator = VALUES(creator)
            """,
            is_url=True,
        )
        import_csv_data(
            cursor,
            config.BOOTSTRAP_SRCBACKGROUND_CSV_URL,
            """INSERT INTO srcbackground
            (tick, tick_hash, base64, font_size, text_color, unicode, p)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
            base64 = VALUES(base64),
            font_size = VALUES(font_size),
            text_color = VALUES(text_color),
            unicode = VALUES(unicode),
            p = VALUES(p)""",
            is_url=True,
        )
        db.commit()
        cursor.close()
    except Exception as e:
        logger.error("Error initializing tables: {}".format(e))
        raise e


def import_csv_data(cursor, csv_url, insert_query, is_url=False):
    max_int = sys.maxsize
    while True:
        try:
            csv.field_size_limit(max_int)
            break
        except OverflowError:
            max_int = int(max_int / 10)

    if not is_url:
        # Handle local file case (unchanged)
        with open(csv_url, "r") as file:
            csv_reader = csv.reader(file)
            for row in csv_reader:
                cursor.execute(insert_query, tuple(row))
        return

    # Handle URL case with ETag checking
    try:
        filename = Path(csv_url).name
        etag_file = CACHE_DIR / f".{filename}.etag"
        headers = {}
        current_etag = None

        if etag_file.exists():
            try:
                current_etag = etag_file.read_text().strip()
                if current_etag:
                    headers["If-None-Match"] = current_etag
                    logger.debug(f"Found local ETag for {filename}: '{current_etag}'")
                else:
                    logger.debug(f"ETag file {etag_file} was empty.")
            except Exception as e:
                logger.warning(f"Could not read ETag file {etag_file}: {e}")
        else:
            logger.debug(f"ETag file {etag_file} not found.")

        logger.info(f"Checking bootstrap data from {csv_url}")
        logger.debug(f"Sending request headers: {headers}")
        response = requests.get(csv_url, headers=headers, timeout=config.REQUESTS_TIMEOUT)
        logger.debug(f"Received response status: {response.status_code}")
        logger.debug(f"Received response headers: {response.headers}")

        if response.status_code == 304:
            logger.info(f"Bootstrap data for {filename} is unchanged (ETag: {current_etag}). Skipping download/processing.")
            return  # File hasn't changed, nothing more to do

        response.raise_for_status()  # Raise an exception for other HTTP errors (4xx, 5xx)

        # Process the CSV data if status code was 200 OK
        logger.info(f"Processing bootstrap data from {csv_url} (ETag: {response.headers.get('ETag') or 'None'})")
        new_etag = response.headers.get("ETag")
        logger.debug(f"Received new ETag from server: '{new_etag}'")
        csv_reader = csv.reader(response.text.splitlines())

        # Execute the insert_query for each row.
        # The query itself (passed as argument) handles INSERT or UPDATE logic.
        rows_processed = 0
        for row in csv_reader:
            # Skip empty rows if any
            if not any(field.strip() for field in row):
                continue
            try:
                cursor.execute(insert_query, tuple(row))
                rows_processed += 1
            except Exception as e:
                logger.error(f"Error processing row {row} from {filename}: {e}")
                # Decide if you want to continue or raise the exception
                # raise # Uncomment to stop processing on the first error
                continue  # Comment out to stop processing on the first error

        logger.info(f"Finished processing {rows_processed} rows from {filename}")

        # Save the new ETag
        if new_etag:
            try:
                etag_file.write_text(new_etag)
                logger.debug(f"Saved new ETag '{new_etag}' to {etag_file}")
            except Exception as e:
                logger.warning(f"Could not write ETag file {etag_file}: {e}")
        elif current_etag:  # If server didn't send ETag, remove old one
            logger.debug(f"Server did not send ETag for {filename}. Removing local ETag file {etag_file}.")
            try:
                etag_file.unlink()
            except OSError as e:
                logger.warning(f"Could not remove ETag file {etag_file}: {e}")

    except requests.RequestException as e:
        logger.error(f"Error checking/downloading bootstrap data from {csv_url}: {e}")
        # Optionally: Add logic here to use a cached local version if download fails
        raise


def initialize_db():
    """Initialize database connection and tables."""
    logger.info("Initializing database...")
    if config.FORCE:
        logger.warning("THE OPTION `--force` IS NOT FOR USE ON PRODUCTION SYSTEMS.")

    max_retries = 5
    retry_delay = 5
    attempt = 0

    while attempt < max_retries:
        try:
            # Get connection from database manager
            db = db_manager.connect()

            # Test connection first
            with db.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
                logger.info("Successfully connected to database server")

            # Now try to create and use the database
            with db.cursor() as cursor:
                database_name = os.environ.get("RDS_DATABASE", "btc_stamps")
                cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{database_name}`")
                cursor.execute(f"USE `{database_name}`")
                db.commit()
                logger.info(f"Successfully initialized database: {database_name}")

            util.CURRENT_BLOCK_INDEX = last_db_index(db)

            # Initialize tables from schema
            initialize_tables(db)

            return db

        except Exception as e:
            attempt += 1
            if attempt >= max_retries:
                logger.error(f"Failed to initialize database after {max_retries} attempts: {e}")
                raise
            else:
                logger.warning(f"Database initialization attempt {attempt} failed: {e}. Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff


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
