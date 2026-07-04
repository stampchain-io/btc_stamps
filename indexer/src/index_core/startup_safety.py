"""
Startup safety checks for the indexer.

This module performs critical safety checks before the indexer starts
to prevent catastrophic issues like the test data rollback incident.
"""

import logging
import os
import sqlite3
from typing import Tuple

from index_core.reprocess_safety import (
    ReprocessSafetyError,
    get_safe_reprocess_db_path,
    is_production_environment,
    validate_block_number,
)

logger = logging.getLogger(__name__)


def check_reprocess_queue_safety() -> Tuple[bool, str]:
    """
    Check the reprocess queue for safety issues before startup.

    Returns:
        Tuple of (is_safe, message)
    """
    db_path = get_safe_reprocess_db_path()

    # If database doesn't exist, it's safe
    if not os.path.exists(db_path):
        return True, "Reprocess queue database not found (safe to proceed)"

    try:
        conn = sqlite3.connect(db_path, timeout=5.0)
        cursor = conn.cursor()

        # Check for any sessions with test block numbers
        cursor.execute("""
            SELECT start_block_index FROM fallback_sessions
            ORDER BY start_block_index LIMIT 10
        """)

        sessions = cursor.fetchall()
        for (start_block,) in sessions:
            try:
                validate_block_number(start_block, "startup check")
            except ReprocessSafetyError as e:
                conn.close()
                return False, f"Found invalid fallback session at block {start_block}: {e}"

        conn.close()
        return True, f"Reprocess queue validated ({len(sessions)} sessions checked)"

    except Exception as e:
        logger.error(f"Error checking reprocess queue: {e}")
        # In case of error, be conservative and fail the check
        return False, f"Failed to validate reprocess queue: {e}"


def perform_startup_safety_checks() -> None:
    """
    Perform all startup safety checks.

    Raises:
        RuntimeError: If any safety check fails
    """
    logger.info("🛡️ Performing startup safety checks...")

    # Check 1: Reprocess queue safety
    is_safe, message = check_reprocess_queue_safety()
    logger.info(f"  Reprocess queue: {message}")

    if not is_safe:
        if is_production_environment():
            # In production, this is a critical error
            raise RuntimeError(
                f"CRITICAL SAFETY VIOLATION: {message}\n"
                "The indexer cannot start due to potentially dangerous state.\n"
                "Please run: poetry run python tools/validate_reprocess_state.py --clean"
            )
        else:
            # In development, just warn
            logger.warning(f"Safety check failed in development: {message}")

    # Add more safety checks here as needed

    logger.info("✅ All startup safety checks passed")
