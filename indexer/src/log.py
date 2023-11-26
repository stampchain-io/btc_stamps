import logging
logger = logging.getLogger(__name__)
import decimal
D = decimal.Decimal
import binascii
import collections
import json
import time
from datetime import datetime
from dateutil.tz import tzlocal
import os
from colorlog import ColoredFormatter

import config
import src.exceptions as exceptions
import src.util as util
from logging.handlers import RotatingFileHandler

class ModuleLoggingFilter(logging.Filter):
    """
    module level logging filter (NodeJS-style), ie:
        filters="*,-counterpartylib.lib,counterpartylib.lib.api"

        will log:
         - counterpartycli.server
         - counterpartylib.lib.api

        but will not log:
         - counterpartylib.lib
         - counterpartylib.lib.backend.indexd
    """

    def __init__(self, filters):
        self.filters = str(filters).split(",")

        self.catchall = "*" in self.filters
        if self.catchall:
            self.filters.remove("*")

    def filter(self, record):
        """
        Determine if specified record should be logged or not
        """
        result = None

        for filter in self.filters:
            if filter[:1] == "-":
                if result is None and ModuleLoggingFilter.ismatch(record, filter[1:]):
                    result = False
            else:
                if ModuleLoggingFilter.ismatch(record, filter):
                    result = True

        if result is None:
            return self.catchall

        return result

    @classmethod
    def ismatch(cls, record, name):
        """
        Determine if the specified record matches the name, in the same way as original logging.Filter does, ie:
            'counterpartylib.lib' will match 'counterpartylib.lib.check'
        """
        nlen = len(name)
        if nlen == 0:
            return True
        elif name == record.name:
            return True
        elif record.name.find(name, 0, nlen) != 0:
            return False
        return record.name[nlen] == "."


ROOT_LOGGER = None
def set_logger(logger):
    global ROOT_LOGGER
    if ROOT_LOGGER is None:
        ROOT_LOGGER = logger


LOGGING_SETUP = False
LOGGING_TOFILE_SETUP = False
def set_up(logger, verbose=False, logfile=None, console_logfilter=None):
    global LOGGING_SETUP
    global LOGGING_TOFILE_SETUP



    def set_up_file_logging():
        assert logfile
        max_log_size = 20 * 1024 * 1024 # 20 MB
        fileh = RotatingFileHandler(logfile, maxBytes=max_log_size, backupCount=5)
        fileh.setLevel(logging.DEBUG)
        LOGFORMAT = '%(asctime)s [%(levelname)s] %(message)s'
        formatter = logging.Formatter(LOGFORMAT, '%Y-%m-%d-T%H:%M:%S%z')
        fileh.setFormatter(formatter)
        logger.addHandler(fileh)

    if LOGGING_SETUP:
        if logfile and not LOGGING_TOFILE_SETUP:
             set_up_file_logging()
             LOGGING_TOFILE_SETUP = True
        logger.getChild('log.set_up').debug('logging already setup')
        return
    LOGGING_SETUP = True

    log_level = logging.DEBUG if verbose else logging.INFO
    logger.setLevel(log_level)

    # Console Logging
    console = logging.StreamHandler()
    console.setLevel(log_level)

    # only add [%(name)s] to LOGFORMAT if we're using console_logfilter
    LOGFORMAT = '%(log_color)s[%(asctime)s][%(levelname)s]' + ('' if console_logfilter is None else '[%(name)s]') + ' %(message)s%(reset)s'
    LOGCOLORS = {'WARNING': 'yellow', 'ERROR': 'red', 'CRITICAL': 'red'}
    formatter = ColoredFormatter(LOGFORMAT, "%Y-%m-%d %H:%M:%S", log_colors=LOGCOLORS)
    console.setFormatter(formatter)
    logger.addHandler(console)

    if console_logfilter:
        console.addFilter(ModuleLoggingFilter(console_logfilter))

    # File Logging
    if logfile:
        set_up_file_logging()
        LOGGING_TOFILE_SETUP = True

    # Quieten noisy libraries.
    requests_log = logging.getLogger("requests")
    requests_log.setLevel(log_level)
    requests_log.propagate = False
    urllib3_log = logging.getLogger('urllib3')
    urllib3_log.setLevel(log_level)
    urllib3_log.propagate = False

    # Disable InsecureRequestWarning
    import requests
    requests.packages.urllib3.disable_warnings()

def curr_time():
    return int(time.time())

def isodt (epoch_time):
    try:
        return datetime.fromtimestamp(epoch_time, tzlocal()).isoformat()
    except OSError:
        return '<datetime>'


def log (db, command, category, bindings):

    cursor = db.cursor()

    for element in bindings.keys():
        try:
            str(bindings[element])
        except KeyError:
            bindings[element] = '<Error>'

    cursor.close()


def get_tx_info(cursor, tx_hash):
    cursor.execute('SELECT * FROM transactions WHERE tx_hash=:tx_hash', {
        'tx_hash': tx_hash
    })
    transactions = cursor.fetchall()
    transaction = transactions[0]
    
    return transaction["btc_amount"]

# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
