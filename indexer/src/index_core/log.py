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


def set_up(logger, verbose=False, logfile=None, console_logfilter=None, clear_logfile=True):
    global LOGGING_SETUP
    global LOGGING_TOFILE_SETUP

    # Set up file logging if needed
    def set_up_file_logging():
        if not logfile:
            raise ValueError("logfile must be defined")

        # Clear log file if requested (useful for debugging)
        if clear_logfile and os.path.exists(logfile):
            try:
                open(logfile, "w").close()  # Truncate the file
                print(f"Cleared existing log file: {logfile}")
            except Exception as e:
                print(f"Warning: Could not clear log file {logfile}: {e}")

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


# Enhanced Block Status Logging Functions
def create_progress_bar(progress: float, width: int = 20) -> str:
    """Create a visual progress bar."""
    filled = int(progress * width)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}]"


def get_speed_indicator(processing_time: float) -> str:
    """Get speed indicator emoji based on processing time."""
    if processing_time < 0.1:
        return "🚀"  # Very fast
    elif processing_time < 0.5:
        return "⚡"  # Fast
    elif processing_time < 2.0:
        return "🏃"  # Normal
    elif processing_time < 5.0:
        return "🚶"  # Slow
    else:
        return "🐌"  # Very slow


def get_activity_indicator(stamps: int, src20: int, src101: int) -> str:
    """Get activity indicator based on transaction counts."""
    total = stamps + src20 + src101
    if total == 0:
        return "💤"  # No activity
    elif total <= 2:
        return "📝"  # Light activity
    elif total <= 10:
        return "📊"  # Moderate activity
    elif total <= 50:
        return "🔥"  # High activity
    else:
        return "💥"  # Very high activity


def format_eta(seconds: float) -> str:
    """Format ETA in human-readable format."""
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f"{minutes}m"
    else:
        hours = int(seconds / 3600)
        minutes = int((seconds % 3600) / 60)
        return f"{hours}h {minutes:02d}m"


def log_enhanced_block_status(
    block_index: int,
    block_tip: int,
    processing_time: float,
    avg_time: str,
    stamps_in_block: int,
    src20_in_block: int,
    src101_in_block: int = 0,
    eta_seconds: float = 0,
    is_zmq: bool = False,
    display_mode: str = "enhanced",
    start_block: int = 0,
) -> None:
    """
    Log block status with enhanced formatting.

    Args:
        block_index: Current block being processed
        block_tip: Latest block height
        processing_time: Time taken to process this block
        avg_time: Average processing time (formatted string)
        stamps_in_block: Number of stamps found
        src20_in_block: Number of SRC-20 transactions
        src101_in_block: Number of SRC-101 transactions
        eta_seconds: Estimated time to completion
        is_zmq: Whether this is from ZMQ feed
        display_mode: Display mode (compact, enhanced, detailed)
        start_block: Starting block for progress calculation (defaults to 0)
    """
    # Calculate progress
    if block_tip > start_block and block_index >= start_block:
        total_blocks = block_tip - start_block
        processed_blocks = block_index - start_block
        current_progress = processed_blocks / total_blocks
    elif block_index < start_block:
        # If we're before the start block, progress is 0
        current_progress = 0.0
    else:
        current_progress = 0.0
    current_progress = min(1.0, max(0.0, current_progress))

    # Determine if we're at the tip (within 5 blocks)
    at_tip = (block_tip - block_index) <= 5

    # Get display components
    progress_bar = create_progress_bar(current_progress, 20)
    speed_indicator = get_speed_indicator(processing_time)
    activity_indicator = get_activity_indicator(stamps_in_block, src20_in_block, src101_in_block)

    # Format progress with appropriate precision
    blocks_remaining = block_tip - block_index
    if blocks_remaining <= 20 and blocks_remaining > 0:
        progress_format = "%.3f%%"
    elif blocks_remaining <= 100 and blocks_remaining > 0:
        progress_format = "%.2f%%"
    else:
        progress_format = "%.1f%%"

    progress_str = progress_format % (current_progress * 100)

    # Get logger
    block_logger = logging.getLogger("index_core.blocks")

    if display_mode == "compact":
        if at_tip:
            log_format = "%s/%s │ %ss │ Avg: %s │ %s │ [S:%s|20:%s|101:%s]%s"
            block_logger.block_status(  # type: ignore[attr-defined]
                log_format,
                str(block_index),
                str(block_tip),
                "{:.2f}".format(processing_time),
                avg_time,
                progress_str,
                stamps_in_block,
                src20_in_block,
                src101_in_block,
                " (ZMQ)" if is_zmq else "",
            )
        else:
            eta_str = format_eta(eta_seconds)
            log_format = "%s/%s │ %ss │ Avg: %s │ ETA: %s │ %s │ [S:%s|20:%s|101:%s]%s"
            block_logger.block_status(  # type: ignore[attr-defined]
                log_format,
                str(block_index),
                str(block_tip),
                "{:.2f}".format(processing_time),
                avg_time,
                eta_str,
                progress_str,
                stamps_in_block,
                src20_in_block,
                src101_in_block,
                " (ZMQ)" if is_zmq else "",
            )

    elif display_mode == "enhanced":
        if at_tip:
            log_format = f"🔗 Block %s/%s %s %s {speed_indicator} %ss (avg: %s) {activity_indicator} S:%s SRC20:%s SRC101:%s%s"
            block_logger.block_status(  # type: ignore[attr-defined]
                log_format,
                str(block_index),
                str(block_tip),
                progress_bar,
                progress_str,
                "{:.2f}".format(processing_time),
                avg_time,
                stamps_in_block,
                src20_in_block,
                src101_in_block,
                " 📡" if is_zmq else "",
            )
        else:
            eta_str = format_eta(eta_seconds)
            log_format = (
                f"🔗 Block %s/%s %s %s {speed_indicator} %ss (avg: %s) ⏱️ %s {activity_indicator} S:%s SRC20:%s SRC101:%s%s"
            )
            block_logger.block_status(  # type: ignore[attr-defined]
                log_format,
                str(block_index),
                str(block_tip),
                progress_bar,
                progress_str,
                "{:.2f}".format(processing_time),
                avg_time,
                eta_str,
                stamps_in_block,
                src20_in_block,
                src101_in_block,
                " 📡" if is_zmq else "",
            )

    elif display_mode == "detailed":
        if at_tip:
            block_logger.block_status(  # type: ignore[attr-defined]
                "┌─ BLOCK %s/%s (%s) ─ AT TIP%s", str(block_index), str(block_tip), progress_str, " [ZMQ]" if is_zmq else ""
            )
        else:
            eta_str = format_eta(eta_seconds)
            block_logger.block_status(  # type: ignore[attr-defined]
                "┌─ BLOCK %s/%s (%s) ─ ⏱️ %s%s",
                str(block_index),
                str(block_tip),
                progress_str,
                eta_str,
                " [ZMQ]" if is_zmq else "",
            )

        block_logger.block_status(  # type: ignore[attr-defined]
            "├─ ⚡ Processing: %ss (avg: %s) %s", "{:.2f}".format(processing_time), avg_time, speed_indicator
        )

        block_logger.block_status("├─ %s %s", progress_bar, activity_indicator)  # type: ignore[attr-defined]

        block_logger.block_status(  # type: ignore[attr-defined]
            "└─ 📊 Found: %s stamps, %s SRC-20, %s SRC-101", stamps_in_block, src20_in_block, src101_in_block
        )
