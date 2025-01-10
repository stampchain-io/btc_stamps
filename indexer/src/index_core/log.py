import decimal
import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Any

from colorlog import ColoredFormatter

logger = logging.getLogger(__name__)
D = decimal.Decimal

# Create custom log level
BLOCK_STATUS = 25  # Between INFO (20) and WARNING (30)
logging.addLevelName(BLOCK_STATUS, "BLOCK")


# Add method to logger
def block_status(self: logging.Logger, message: Any, *args: Any, **kwargs: Any) -> None:
    if self.isEnabledFor(BLOCK_STATUS):
        self._log(BLOCK_STATUS, message, args, **kwargs)


if not hasattr(logging.Logger, "block_status"):
    setattr(logging.Logger, "block_status", block_status)
    logging.Logger.block_status = block_status  # type: ignore[attr-defined]


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

    # Set up file logging if needed
    def set_up_file_logging():
        if not logfile:
            raise ValueError("logfile must be defined")
        max_log_size = 20 * 1024 * 1024  # 20 MB
        file_handler = RotatingFileHandler(logfile, maxBytes=max_log_size, backupCount=5)
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", "%Y-%m-%d-T%H:%M:%S%z")
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    # Check if logging is already set up
    if LOGGING_SETUP:
        if logfile and not LOGGING_TOFILE_SETUP:
            set_up_file_logging()
            LOGGING_TOFILE_SETUP = True
        logger.getChild("log.set_up").debug("logging already setup")
        return
    LOGGING_SETUP = True

    # Set base logging level
    logger.setLevel(logging.DEBUG if verbose or os.environ.get("DEBUG", "").lower() == "true" else logging.INFO)

    # Remove any existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Console logging with colors
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG if verbose or os.environ.get("DEBUG") == "True" else logging.INFO)

    # Detailed color formatter
    console_formatter = ColoredFormatter(
        "%(log_color)s%(asctime)s [%(levelname)s] %(name)s: %(message)s%(reset)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        reset=True,
        log_colors={
            "DEBUG": "cyan",
            "INFO": "green",
            "BLOCK": "light_blue",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "red,bg_white",
        },
    )

    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # Apply console log filter if specified
    if console_logfilter:
        console_handler.addFilter(ModuleLoggingFilter(console_logfilter))

    # Set up file logging
    if logfile:
        set_up_file_logging()
        LOGGING_TOFILE_SETUP = True

    # Quieten noisy libraries
    requests_log = logging.getLogger("requests")
    requests_log.setLevel(logging.WARNING)
    requests_log.propagate = False
    urllib3_log = logging.getLogger("urllib3")
    urllib3_log.setLevel(logging.WARNING)
    urllib3_log.propagate = False

    # Disable InsecureRequestWarning
    import requests

    requests.packages.urllib3.disable_warnings()

    return logger
