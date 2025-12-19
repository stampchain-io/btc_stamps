"""
Asynchronous SRC-20 holder count updater for Bitcoin Stamps Indexer.

This module provides asynchronous holder count and progress percentage updates,
allowing the main indexer process to continue while market data is updated
in the background.
"""

import logging
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Set

from index_core.src20_holder_updater import SRC20HolderCountUpdater

logger = logging.getLogger(__name__)

# Maximum number of concurrent update operations
MAX_CONCURRENT_UPDATES = 1  # Single threaded to avoid lock contention

# Thread pool for handling updates
update_executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_UPDATES)

# Flag to control the update worker thread
_update_worker_running = False
_update_worker_thread = None


class HolderUpdateTask:
    """Represents a holder count update task."""

    def __init__(self, block_index: int, affected_tokens: Set[str], force: bool = False):
        """
        Initialize a holder update task.

        Args:
            block_index: The block index where updates are needed
            affected_tokens: Set of token tickers affected in this block
            force: Whether to force update all tokens
        """
        self.block_index = block_index
        self.affected_tokens = affected_tokens.copy()  # Make a copy to avoid mutations
        self.force = force


# Queue for pending updates
update_queue: queue.Queue = queue.Queue()


def _process_update_task(task: HolderUpdateTask) -> None:
    """
    Process a single holder update task.

    This function handles the actual database updates for holder counts
    and progress percentages.

    Args:
        task: The update task to process
    """
    from index_core.background_coordinator import BackgroundCoordinator

    coordinator = BackgroundCoordinator.get_instance()

    # Try to acquire coordination lock
    if not coordinator.start_task("holder_update", is_heavy=True):
        logger.debug("Holder update skipped - another heavy operation is running")
        return

    try:
        # Create a dedicated holder updater with its own DB connection
        holder_updater = SRC20HolderCountUpdater()

        # Restore the tracked tokens
        for token in task.affected_tokens:
            holder_updater.track_affected_token(token)

        # Perform the update with a fresh connection
        updated_count = holder_updater.update_holder_counts(task.block_index, force=task.force)

        if updated_count > 0:
            logger.debug(f"Async update completed: {updated_count} tokens updated at block {task.block_index}")

    except Exception as e:
        import traceback

        logger.error(f"Error in async holder update for block {task.block_index}: {e}")
        logger.error(f"Exception type: {type(e).__name__}")
        logger.error(f"Exception details: {repr(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        # Re-raise so the outer exception handler can also catch it
        raise
    finally:
        # Always release the coordinator lock
        coordinator.end_task("holder_update", is_heavy=True)


def _upload_worker():
    """
    Worker thread that processes the update queue.

    This function runs in a separate thread and continuously processes
    holder update tasks from the queue.
    """
    logger.debug("Async holder update worker thread started")

    while _update_worker_running:
        try:
            # Get a task from the queue with timeout
            try:
                task = update_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            # Submit the task to the executor
            future = update_executor.submit(_process_update_task, task)

            # Wait for completion with timeout
            try:
                future.result(timeout=300.0)  # 5 minutes timeout for complex holder queries
            except Exception as e:
                import traceback

                logger.error(f"Failed to process holder update task: {e}")
                logger.error(f"Exception type: {type(e).__name__}")
                logger.error(f"Exception details: {repr(e)}")
                logger.error(f"Traceback: {traceback.format_exc()}")

            update_queue.task_done()

        except Exception as e:
            logger.error(f"Error in holder update worker thread: {e}")
            time.sleep(5)  # Longer pause on error to reduce contention

    logger.debug("Async holder update worker thread stopped")


def schedule_holder_update(block_index: int, affected_tokens: Set[str], force: bool = False) -> bool:
    """
    Schedule a holder count update for asynchronous processing.

    Args:
        block_index: The block index where updates are needed
        affected_tokens: Set of token tickers affected in this block
        force: Whether to force update all tokens

    Returns:
        True if the task was successfully queued, False otherwise
    """
    if not _update_worker_running:
        logger.warning("Holder update worker is not running, cannot schedule update")
        return False

    if not affected_tokens and not force:
        return True  # Nothing to update

    try:
        task = HolderUpdateTask(block_index, affected_tokens, force)
        update_queue.put_nowait(task)

        queue_size = update_queue.qsize()
        if queue_size > 10:
            logger.warning(f"Holder update queue size is {queue_size}, consider monitoring for delays")

        return True

    except queue.Full:
        logger.error("Holder update queue is full, dropping update task")
        return False
    except Exception as e:
        logger.error(f"Failed to schedule holder update: {e}")
        return False


def start_worker():
    """Start the async holder update worker thread."""
    global _update_worker_running, _update_worker_thread

    if _update_worker_running:
        logger.warning("Holder update worker is already running")
        return

    _update_worker_running = True
    _update_worker_thread = threading.Thread(target=_upload_worker, name="HolderUpdateWorker", daemon=True)
    _update_worker_thread.start()
    logger.debug("Started async holder update worker")


def stop_worker(timeout: float = 5.0):
    """
    Stop the async holder update worker thread.

    Args:
        timeout: Maximum time to wait for the worker to stop
    """
    global _update_worker_running, _update_worker_thread  # noqa: F824

    if not _update_worker_running:
        return

    logger.debug("Stopping async holder update worker thread...")
    _update_worker_running = False

    # Wait for pending tasks to complete
    if not update_queue.empty():
        logger.debug(f"Waiting for {update_queue.qsize()} pending holder updates to complete...")
        try:
            update_queue.join()
        except Exception as e:
            logger.warning(f"Error waiting for queue to empty: {e}")

    # Wait for the worker thread to stop
    if _update_worker_thread and _update_worker_thread.is_alive():
        _update_worker_thread.join(timeout=timeout)
        if _update_worker_thread.is_alive():
            logger.warning("Holder update worker thread did not stop gracefully")

    # Shutdown the executor
    update_executor.shutdown(wait=True, cancel_futures=True)
    logger.debug("Async holder update worker stopped")


def get_queue_size() -> int:
    """Get the current size of the update queue."""
    return update_queue.qsize()


def is_worker_running() -> bool:
    """Check if the update worker is running."""
    return _update_worker_running
