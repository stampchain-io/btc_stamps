"""
Critical Failure Handler for Bitcoin Stamps Indexer

This module provides a clean shutdown mechanism for critical failures while
maintaining the intended fail-fast behavior. It ensures proper cleanup of
resources, database transactions, and async workers before termination.
"""

import logging
import sys
import threading
import time
from enum import Enum
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)

# Global reference to database connection for emergency rollback
_db_connection = None


class CriticalFailureType(Enum):
    """Types of critical failures that require immediate termination."""

    CONSENSUS_MISMATCH = "consensus_mismatch"
    DATABASE_CORRUPTION = "database_corruption"
    ROLLBACK_LOOP = "rollback_loop"
    BLOCKCHAIN_REORG_FAILURE = "blockchain_reorg_failure"
    INITIALIZATION_FAILURE = "initialization_failure"


class CriticalFailureHandler:
    """
    Handles critical failures with proper cleanup while maintaining fail-fast behavior.

    This handler ensures that when critical failures occur, the system:
    1. Logs detailed failure information
    2. Performs necessary cleanup (database rollback, async worker shutdown)
    3. Terminates the process with appropriate exit code
    """

    def __init__(self):
        self._cleanup_callbacks: List[Callable] = []
        self._shutdown_timeout = 30  # seconds
        self._lock = threading.Lock()

    def register_cleanup_callback(self, callback: Callable) -> None:
        """Register a cleanup function to be called before termination."""
        with self._lock:
            if callback not in self._cleanup_callbacks:
                self._cleanup_callbacks.append(callback)
                logger.debug(f"Registered cleanup callback: {callback.__name__}")

    def unregister_cleanup_callback(self, callback: Callable) -> None:
        """Unregister a cleanup function."""
        with self._lock:
            if callback in self._cleanup_callbacks:
                self._cleanup_callbacks.remove(callback)
                logger.debug(f"Unregistered cleanup callback: {callback.__name__}")

    def handle_critical_failure(
        self,
        failure_type: CriticalFailureType,
        error_message: str,
        exception: Optional[Exception] = None,
        block_index: Optional[int] = None,
        exit_code: int = 1,
    ) -> None:
        """
        Handle a critical failure with proper cleanup and termination.

        Args:
            failure_type: Type of critical failure
            error_message: Human-readable error description
            exception: Original exception that caused the failure
            block_index: Block index where failure occurred (if applicable)
            exit_code: Exit code to use (default: 1)
        """
        logger.critical("=" * 80)
        logger.critical("CRITICAL FAILURE DETECTED - INITIATING CLEAN SHUTDOWN")
        logger.critical("=" * 80)
        logger.critical(f"Failure Type: {failure_type.value}")
        logger.critical(f"Error Message: {error_message}")
        if block_index is not None:
            logger.critical(f"Block Index: {block_index}")
        if exception:
            logger.critical(f"Original Exception: {type(exception).__name__}: {exception}")
            # Log full traceback for debugging
            import traceback

            logger.critical(f"Exception Traceback:\n{traceback.format_exc()}")

        # Perform cleanup with timeout
        self._perform_cleanup()

        # Final log before termination
        logger.critical(f"Clean shutdown completed. Terminating process with exit code {exit_code}")
        logger.critical("=" * 80)

        # Force flush all log handlers
        for handler in logger.handlers:
            try:
                handler.flush()
            except Exception:
                pass

        # Terminate the process
        sys.exit(exit_code)

    def _perform_cleanup(self) -> None:
        """Perform all registered cleanup operations with timeout."""
        logger.info("Starting cleanup procedures...")

        # Set a timeout for cleanup operations
        cleanup_start = time.time()

        with self._lock:
            callbacks_to_execute = self._cleanup_callbacks.copy()

        for callback in callbacks_to_execute:
            try:
                # Check timeout
                if time.time() - cleanup_start > self._shutdown_timeout:
                    logger.warning(f"Cleanup timeout reached ({self._shutdown_timeout}s), skipping remaining callbacks")
                    break

                logger.debug(f"Executing cleanup callback: {callback.__name__}")
                callback()
                logger.debug(f"Completed cleanup callback: {callback.__name__}")
            except Exception as e:
                logger.error(f"Error in cleanup callback {callback.__name__}: {e}")
                # Continue with other cleanup operations

        cleanup_duration = time.time() - cleanup_start
        logger.info(f"Cleanup procedures completed in {cleanup_duration:.2f}s")


# Global instance for use across the application
critical_failure_handler = CriticalFailureHandler()


def handle_critical_failure(
    failure_type: CriticalFailureType,
    error_message: str,
    exception: Optional[Exception] = None,
    block_index: Optional[int] = None,
    exit_code: int = 1,
) -> None:
    """
    Convenience function to handle critical failures.

    This maintains the same interface as sys.exit() calls but provides proper cleanup.
    """
    critical_failure_handler.handle_critical_failure(
        failure_type=failure_type,
        error_message=error_message,
        exception=exception,
        block_index=block_index,
        exit_code=exit_code,
    )


def register_cleanup_callback(callback: Callable) -> None:
    """Register a cleanup callback with the global handler."""
    critical_failure_handler.register_cleanup_callback(callback)


def unregister_cleanup_callback(callback: Callable) -> None:
    """Unregister a cleanup callback from the global handler."""
    critical_failure_handler.unregister_cleanup_callback(callback)


def set_db_connection(db):
    """Set the database connection for emergency rollback during critical failures."""
    global _db_connection
    _db_connection = db
    logger.debug("Database connection registered for critical failure handling")


def emergency_db_rollback():
    """Attempt to rollback any pending database transaction during critical failure."""
    if _db_connection:
        try:
            logger.info("Attempting emergency database rollback...")
            _db_connection.rollback()
            logger.info("Emergency database rollback completed successfully")
        except Exception as e:
            logger.error(f"Emergency database rollback failed: {e}")
    else:
        logger.debug("No database connection available for emergency rollback")


# Specific helper functions for common critical failures
def handle_database_corruption_failure(error_message: str, exception: Exception, block_index: Optional[int] = None) -> None:
    """Handle database corruption failures."""
    handle_critical_failure(
        failure_type=CriticalFailureType.DATABASE_CORRUPTION,
        error_message=error_message,
        exception=exception,
        block_index=block_index,
        exit_code=2,  # Different exit code for database issues
    )


def handle_consensus_mismatch_failure(error_message: str, block_index: int, exception: Optional[Exception] = None) -> None:
    """Handle consensus mismatch failures."""
    handle_critical_failure(
        failure_type=CriticalFailureType.CONSENSUS_MISMATCH,
        error_message=error_message,
        exception=exception,
        block_index=block_index,
        exit_code=3,  # Different exit code for consensus issues
    )


def handle_rollback_loop_failure(error_message: str, block_index: int) -> None:
    """Handle rollback loop detection failures."""
    handle_critical_failure(
        failure_type=CriticalFailureType.ROLLBACK_LOOP,
        error_message=error_message,
        block_index=block_index,
        exit_code=4,  # Different exit code for rollback loops
    )
