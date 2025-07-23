"""
Safety module for reprocessing queue to prevent catastrophic rollbacks.

This module implements multiple safety checks to ensure that:
1. No test data can persist in production
2. Rollback blocks are within valid ranges
3. Fallback states are properly validated
"""

import logging
import os

logger = logging.getLogger(__name__)

# Safety constants
MIN_VALID_BLOCK = 779652  # CP_STAMP_GENESIS_BLOCK - First valid stamp
MAX_ROLLBACK_BLOCKS = 1000  # Maximum blocks allowed to rollback - reduced for safety
TEST_BLOCK_RANGES = [
    (0, 1000),  # Common test block range
    (10000, 20000),  # Another common test range
    (12345, 12345),  # Specific test block that caused the issue
]


class ReprocessSafetyError(Exception):
    """Raised when a safety check fails."""

    pass


def validate_block_number(block: int, context: str = "block") -> None:
    """
    Validate that a block number is safe for production use.

    Args:
        block: Block number to validate
        context: Context for error messages (e.g., "rollback target", "start block")

    Raises:
        ReprocessSafetyError: If block number is invalid
    """
    # Skip validation in test mode
    if not is_production_environment():
        return

    # Check if block is in test ranges
    for start, end in TEST_BLOCK_RANGES:
        if start <= block <= end:
            raise ReprocessSafetyError(
                f"SAFETY VIOLATION: {context} {block} is in test block range [{start}, {end}]. "
                "This appears to be test data and must not be used in production!"
            )

    # Check if block is too old
    if block < MIN_VALID_BLOCK:
        raise ReprocessSafetyError(
            f"SAFETY VIOLATION: {context} {block} is before the first valid stamp block {MIN_VALID_BLOCK}. "
            "This is either test data or an invalid rollback target."
        )

    # Additional check for suspiciously round numbers that might be test data
    if block > 0 and block < MIN_VALID_BLOCK and block % 1000 == 0:
        logger.warning(
            f"WARNING: {context} {block} is a suspiciously round number before genesis. " "This might be test data."
        )


def validate_rollback_distance(current_block: int, target_block: int) -> None:
    """
    Validate that a rollback isn't too extreme.

    Args:
        current_block: Current block height
        target_block: Target rollback block

    Raises:
        ReprocessSafetyError: If rollback distance is too large
    """
    # Skip validation in test mode
    if not is_production_environment():
        return

    if current_block <= target_block:
        raise ReprocessSafetyError(
            f"SAFETY VIOLATION: Cannot rollback from {current_block} to {target_block}. "
            "Target must be less than current block."
        )

    distance = current_block - target_block
    if distance > MAX_ROLLBACK_BLOCKS:
        raise ReprocessSafetyError(
            f"SAFETY VIOLATION: Rollback distance {distance} blocks exceeds maximum allowed {MAX_ROLLBACK_BLOCKS}. "
            f"(Current: {current_block}, Target: {target_block}). "
            "This might indicate corrupted state or test data."
        )


def validate_fallback_state(start_block: int, failed_blocks: dict) -> None:
    """
    Validate a fallback state before using it.

    Args:
        start_block: Start block of the fallback session
        failed_blocks: Dictionary of failed blocks

    Raises:
        ReprocessSafetyError: If fallback state is invalid
    """
    # Validate start block
    validate_block_number(start_block, "fallback start block")

    # Validate all failed blocks
    for block_index in failed_blocks.keys():
        if isinstance(block_index, str):
            block_index = int(block_index)
        validate_block_number(block_index, "failed block")

        # Ensure failed blocks are after start block
        if block_index < start_block:
            raise ReprocessSafetyError(
                f"SAFETY VIOLATION: Failed block {block_index} is before fallback start {start_block}. "
                "This indicates corrupted fallback state."
            )


def is_production_environment() -> bool:
    """Check if we're running in production environment."""
    # First check if we're explicitly in test mode
    if os.environ.get("TESTING") == "1":
        return False
    if os.environ.get("USE_TEST_DB") == "1":
        return False

    # Check various indicators
    env = os.environ.get("ENVIRONMENT", "").lower()
    hostname = os.environ.get("RDS_HOSTNAME", "")

    # Production indicators
    if env in ["production", "prod"]:
        return True
    if "prod" in hostname or "production" in hostname:
        return True
    if os.path.exists("/home/ubuntu/btc_stamps/indexer"):  # Production path
        return True

    return False


def get_safe_reprocess_db_path() -> str:
    """
    Get a safe path for the reprocess queue database.

    In production, ensures the database is in a proper location.
    In development/test, uses a separate path.
    """
    if is_production_environment():
        # Production path - in data directory
        if data_dir := os.environ.get("DATA_DIR"):
            # Use explicitly configured DATA_DIR
            pass
        else:
            # Use platform-appropriate default via appdirs
            import appdirs

            data_dir = appdirs.user_data_dir(appauthor="btc_stamps", appname="btc_stamps", roaming=True)

        db_path = os.path.join(data_dir, "reprocess_queue.db")
        logger.info(f"Using production reprocess DB path: {db_path}")
    else:
        # Development/test path
        db_path = os.environ.get("REPROCESS_DB_PATH", "test_reprocess_queue.db")
        logger.info(f"Using development reprocess DB path: {db_path}")

    return db_path


def log_safety_check(message: str) -> None:
    """Log a safety check with appropriate severity."""
    if is_production_environment():
        logger.warning(f"🛡️ PRODUCTION SAFETY CHECK: {message}")
    else:
        logger.debug(f"Safety check: {message}")
