import csv
import decimal
import hashlib
import logging
import os
import signal
import sys

import appdirs
import bitcoin as bitcoinlib
import pymysql as mysql
from pymysql.connections import Connection

import config
import index_core.backend as backend
import index_core.blocks as blocks
import index_core.log as log
import index_core.util as util
from index_core.aws import get_s3_objects
from index_core.check import software_version
from index_core.database import last_db_index

logger = logging.getLogger(__name__)
log.set_logger(logger)  # set root logger

D = decimal.Decimal


class ConfigurationError(Exception):
    pass


def sigterm_handler(_signo, _stack_frame):
    if _signo == 15:
        signal_name = "SIGTERM"
    elif _signo == 2:
        signal_name = "SIGINT"
    else:
        raise ValueError("Unexpected signal number received")
    logger.info("Received {}.".format(signal_name))
    logger.info("Stopping backend.")
    # backend.stop() this would typically stop addrindexrs
    logger.info("Shutting down.")
    logging.shutdown()
    sys.exit(0)


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

    if config.TESTNET or testnet:
        config.TESTNET = True
        config.BLOCK_FIRST = config.BLOCK_FIRST_TESTNET
    elif regtest:
        config.BLOCK_FIRST = config.BLOCK_FIRST_REGTEST
    else:
        config.BLOCK_FIRST = config.BLOCK_FIRST_MAINNET

    # Set other config attributes based on parameters
    config.BACKEND_NAME = "bitcoincore"
    config.BACKEND_CONNECT = backend_connect or "localhost"
    config.BACKEND_PORT = int(
        backend_port or (config.DEFAULT_BACKEND_PORT_TESTNET if testnet else config.DEFAULT_BACKEND_PORT)
    )
    config.BACKEND_SSL = backend_ssl
    config.BACKEND_SSL_NO_VERIFY = backend_ssl_no_verify
    config.BACKEND_POLL_INTERVAL = float(backend_poll_interval or 0.5)
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
    software_version()

    # regtest
    config.REGTEST = regtest
    # ignore-scan
    if customnet is not None and len(customnet) > 0:
        config.CUSTOMNET = True
        config.REGTEST = True  # Custom nets are regtests with different parameters
    else:
        config.CUSTOMNET = False

    if config.TESTNET:
        bitcoinlib.SelectParams("testnet")
    elif config.REGTEST:
        bitcoinlib.SelectParams("regtest")
    else:
        bitcoinlib.SelectParams("mainnet")

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

    # Log unhandled errors.
    def handle_exception(exc_type, exc_value, exc_traceback):
        logger.error("Unhandled Exception", exc_info=(exc_type, exc_value, exc_traceback))

    sys.excepthook = handle_exception

    ##############
    # THINGS WE CONNECT TO

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


def initialize_tables(db):
    try:
        logger.warning("initializing tables...")
        cursor = db.cursor()
        with open("table_schema.sql", "r") as file:
            sql_script = file.read()
        sql_commands = [cmd.strip() for cmd in sql_script.split(";") if cmd.strip()]
        for command in sql_commands:
            try:
                cursor.execute(command)
            except Exception as e:
                logger.error(f"Error executing command:{command};\nerror:{e}")
                raise e
        import_csv_data(
            cursor,
            "bootstrap/creator.csv",
            """
            INSERT INTO creator (address, creator)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE creator = VALUES(creator)
            """,
        )
        import_csv_data(
            cursor,
            "bootstrap/srcbackground.csv",
            """INSERT INTO srcbackground
            (tick, tick_hash, base64, font_size, text_color, unicode, p)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
            base64 = VALUES(base64),
            font_size = VALUES(font_size),
            text_color = VALUES(text_color),
            unicode = VALUES(unicode),
            p = VALUES(p)""",
        )
        import_csv_data(
            cursor,
            "bootstrap/src101price.csv",
            """
            INSERT INTO src101price (len, price)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE len = VALUES(len)
            """,
        )
        db.commit()
        cursor.close()
    except Exception as e:
        logger.error("Error initializing tables: {}".format(e))
        raise e


def import_csv_data(cursor, csv_file, insert_query):
    max_int = sys.maxsize
    while True:
        try:
            csv.field_size_limit(max_int)
            break
        except OverflowError:
            max_int = int(max_int / 10)
    with open(csv_file, "r") as file:
        csv_reader = csv.reader(file)
        for row in csv_reader:
            cursor.execute(insert_query, tuple(row))


def initialize_db() -> Connection:
    logger.warning("Initializing database...")
    if config.FORCE:
        logger.warning("THE OPTION `--force` IS NOT FOR USE ON PRODUCTION SYSTEMS.")

    rds_host = os.environ.get("RDS_HOSTNAME")
    rds_user = os.environ.get("RDS_USER")
    rds_password = os.environ.get("RDS_PASSWORD")
    rds_database = os.environ.get("RDS_DATABASE")
    rds_port = int(os.environ.get("RDS_PORT", 3306))

    if rds_password is None:
        logger.error("Database password is not set.")
        raise ValueError("Database password is not set.")

    logger.info("Connecting to database (MySQL).")
    db: Connection = mysql.connect(
        host=rds_host,
        user=rds_user,
        password=rds_password,
        port=rds_port,
        database=rds_database,
    )
    util.CURRENT_BLOCK_INDEX = last_db_index(db)

    initialize_tables(db)

    return db


def connect_to_backend():
    if not config.FORCE:
        logger.info("Connecting to Bitcoin Node")
        backend.getblockcount()


def start_all(db: Connection) -> None:

    # Backend.
    connect_to_backend()

    if config.AWS_SECRET_ACCESS_KEY and config.AWS_ACCESS_KEY_ID and config.AWS_S3_BUCKETNAME:
        config.S3_OBJECTS = get_s3_objects(db, config.AWS_S3_BUCKETNAME, config.AWS_S3_CLIENT)

    # Server.
    blocks.follow(db)


# TODO
def reparse(db, block_index=None, quiet=True):
    connect_to_backend()
    blocks.reparse(db, block_index=block_index, quiet=quiet)
