import os
import decimal
import sys
import pymysql as mysql
import signal
import appdirs
import bitcoin as bitcoinlib
import logging
import csv
import hashlib

import src.log as log
import config
import src.util as util
import blocks
import src.backend as backend
from src.aws import get_s3_objects

logger = logging.getLogger(__name__)
log.set_logger(logger)  # set root logger

D = decimal.Decimal


class ConfigurationError(Exception):
    pass


def sigterm_handler(_signo, _stack_frame):
    if _signo == 15:
        signal_name = 'SIGTERM'
    elif _signo == 2:
        signal_name = 'SIGINT'
    else:
        assert False
    logger.info('Received {}.'.format(signal_name))
    logger.info('Stopping backend.')
    # backend.stop() this would typically stop addrindexrs
    logger.info('Shutting down.')
    logging.shutdown()
    sys.exit(0)
signal.signal(signal.SIGTERM, sigterm_handler)
signal.signal(signal.SIGINT, sigterm_handler)


# TODO: MySQL Locking Function - perhaps we want this :)
# This code creates a table called server_lock in the MySQL database and inserts a single row into the table.
# If another instance of the server tries to insert a row into the table, it will fail with an IntegrityError, 
# indicating that another copy of the server is already running.

# class LockingError(Exception):
#     pass

# def get_lock():
#     logger.info('Acquiring lock.')

#     db = mysql.connector.connect(
#         host='your-mysql-hostname',
#         user='your-username',
#         password='your-password',
#         database='your-database-name'
#     )
#     cursor = db.cursor()

#     try:
#         cursor.execute('CREATE TABLE server_lock (id INT PRIMARY KEY)')
#     except mysql.connector.errors.ProgrammingError:
#         pass

#     try:
#         cursor.execute('INSERT INTO server_lock (id) VALUES (1)')
#         db.commit()
#     except mysql.connector.errors.IntegrityError:
#         raise LockingError('Another copy of server is currently running.')

#     logger.debug('Lock acquired.')

# Lock database access by opening a socket.


def initialize(*args, **kwargs):
    initialize_config(*args, **kwargs)
    return initialize_db()


def initialize_config(
    log_file=None,
    testnet=False, regtest=False,
    api_limit_rows=1000,
    backend_connect=None, backend_port=None,
    backend_user=None, backend_password=None,
    backend_ssl=False, backend_ssl_no_verify=False,
    backend_poll_interval=None,
    force=False, verbose=False, console_logfilter=None,
    requests_timeout=config.DEFAULT_REQUESTS_TIMEOUT,
    estimate_fee_per_kb=None,
    backend_ssl_verify=None,
    customnet=None, checkdb=False
):

    try:
        assert hashlib.sha3_256(''.encode('utf-8')).hexdigest() == 'a7ffc6f8bf1ed76651c14756a061d662f580ff4de43b49fa82d80a4b80f8434a'
        assert hashlib.sha256(''.encode('utf-8')).hexdigest() == 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
    except AssertionError as e:
        logger.error(f'SHA Hash Inconsistencies: {e}')
        raise e
    
    # Data directory
    data_dir = appdirs.user_data_dir(appauthor=config.STAMPS_NAME, appname=config.APP_NAME, roaming=True)
    if not os.path.isdir(data_dir):
        os.makedirs(data_dir, mode=0o755)

    print("data_dir: {}".format(data_dir))
    print("log_file: {}".format(log_file))

    # testnet
    if testnet:
        config.TESTNET = testnet
    else:
        config.TESTNET = False

    # regtest
    if regtest:
        config.REGTEST = regtest
    else:
        config.REGTEST = False

    if customnet is not None and len(customnet) > 0:
        config.CUSTOMNET = True
        config.REGTEST = True # Custom nets are regtests with different parameters
    else:
        config.CUSTOMNET = False

    if config.TESTNET:
        bitcoinlib.SelectParams('testnet')
    elif config.REGTEST:
        bitcoinlib.SelectParams('regtest')
    else:
        bitcoinlib.SelectParams('mainnet')

    network = ''
    if config.TESTNET:
        network += '.testnet'
    if config.REGTEST:
        network += '.regtest'

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
        filename = 'server{}.log'.format(network)
        config.LOG = os.path.join(log_dir, filename)
    else:  # user-specified location
        config.LOG = log_file

    # Set up logging.
    log.set_up(log.ROOT_LOGGER, verbose=verbose, logfile=config.LOG, console_logfilter=console_logfilter)
    if config.LOG:
        logger.debug('Writing server log to file: `{}`'.format(config.LOG))

    # Log unhandled errors.
    def handle_exception(exc_type, exc_value, exc_traceback):
        logger.error("Unhandled Exception", exc_info=(exc_type, exc_value, exc_traceback))
    sys.excepthook = handle_exception

    config.API_LIMIT_ROWS = api_limit_rows

    ##############
    # THINGS WE CONNECT TO

    # Backend name
    config.BACKEND_NAME = 'bitcoincore'

    # Backend RPC host (Bitcoin Core)
    if backend_connect:
        config.BACKEND_CONNECT = backend_connect
    else:
        config.BACKEND_CONNECT = 'localhost'

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
            raise ConfigurationError('invalid backend API port number')
    except:
        raise ConfigurationError("Please specific a valid port number backend-port configuration parameter")

    # Backend Core RPC user (Bitcoin Core)
    if backend_user:
        config.BACKEND_USER = backend_user
    else:
        config.BACKEND_USER = 'bitcoinrpc'

    # Backend Core RPC password (Bitcoin Core)
    if backend_password:
        config.BACKEND_PASSWORD = backend_password
    else:
        raise ConfigurationError('backend RPC password not set. (Use configuration file or --backend-password=PASSWORD)')

    # Backend Core RPC SSL
    if backend_ssl:
        config.BACKEND_SSL = backend_ssl
    else:
        config.BACKEND_SSL = False  # Default to off.

    # Backend Core RPC SSL Verify
    if backend_ssl_verify is not None:
        logger.warning('The server parameter `backend_ssl_verify` is deprecated. Use `backend_ssl_no_verify` instead.')
        config.BACKEND_SSL_NO_VERIFY = not backend_ssl_verify
    else:
        if backend_ssl_no_verify:
            config.BACKEND_SSL_NO_VERIFY = backend_ssl_no_verify
        else:
            config.BACKEND_SSL_NO_VERIFY = False # Default to on (don't support self‐signed certificates)

    # Backend Poll Interval
    if backend_poll_interval:
        config.BACKEND_POLL_INTERVAL = backend_poll_interval
    else:
        config.BACKEND_POLL_INTERVAL = float(
            os.environ.get('BACKEND_POLL_INTERVAL', "0.5")
        )

    # Construct backend URL.
    config.BACKEND_URL = config.BACKEND_USER + ':' + config.BACKEND_PASSWORD + '@' + config.BACKEND_CONNECT + ':' + str(config.BACKEND_PORT)
    if config.BACKEND_SSL:
        config.BACKEND_URL = 'https://' + config.BACKEND_URL
    else:
        config.BACKEND_URL = 'http://' + config.BACKEND_URL


    ##############
    # OTHER SETTINGS

    # skip checks
    if force:
        config.FORCE = force
    else:
        config.FORCE = False

    # Encoding
    config.PREFIX = b'stamp:' 
    config.CP_PREFIX = b'CNTRPRTY'

    config.BLOCK_FIRST = config.BLOCK_FIRST_MAINNET
    # Misc
    config.REQUESTS_TIMEOUT = requests_timeout

    if estimate_fee_per_kb is not None:
        config.ESTIMATE_FEE_PER_KB = estimate_fee_per_kb


def initialize_tables(db):
    try:
        logger.warning("initializing tables...")
        cursor = db.cursor()
        with open('table_schema.sql', 'r') as file:
            sql_script = file.read()
        sql_commands = [
            cmd.strip() for cmd in sql_script.split(';') if cmd.strip()
        ]
        for command in sql_commands:
            try:
                cursor.execute(command)
            except Exception as e:
                logger.error(
                    f"Error executing command:{command};\nerror:{e}"
                )
                raise e
        import_csv_data(
            cursor,
            'bootstrap/creator.csv',
            '''
            INSERT INTO creator (address, creator)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE creator = VALUES(creator)
            '''
        )
        import_csv_data(
            cursor,
            'bootstrap/srcbackground.csv',
            '''INSERT INTO srcbackground
            (tick, base64, font_size, text_color, unicode, p)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
            base64 = VALUES(base64),
            font_size = VALUES(font_size),
            text_color = VALUES(text_color),
            unicode = VALUES(unicode),
            p = VALUES(p)'''
        )
        db.commit()
        cursor.close()
    except Exception as e:
        logger.error(
            "Error initializing tables: {}".format(e)
        )
        raise e


def import_csv_data(cursor, csv_file, insert_query):
    max_int = sys.maxsize
    while True:
        try:
            csv.field_size_limit(max_int)
            break
        except OverflowError:
            max_int = int(max_int/10)
    with open(csv_file, 'r') as file:
        csv_reader = csv.reader(file)
        for row in csv_reader:
            cursor.execute(insert_query, tuple(row))


def initialize_db():
    logger.warning("Initializing database...")
    if config.FORCE:
        logger.warning('THE OPTION `--force` IS NOT FOR USE ON PRODUCTION SYSTEMS.')

    rds_host = os.environ.get('RDS_HOSTNAME')
    rds_user = os.environ.get('RDS_USER')
    rds_password = os.environ.get('RDS_PASSWORD')
    rds_database = os.environ.get('RDS_DATABASE')
    rds_port = int(os.environ.get("RDS_PORT", 3306))
    # Database
    logger.info('Connecting to database (MySQL).')
    db = mysql.connect(
        host=rds_host,
        user=rds_user,
        password=rds_password,
        port=rds_port,
        database=rds_database
    )
    util.CURRENT_BLOCK_INDEX = blocks.last_db_index(db)

    initialize_tables(db)

    return db


def connect_to_backend():
    if not config.FORCE:
        logger.info('Connecting to Bitcoin Node')
        backend.getblockcount()


def start_all(db):

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
