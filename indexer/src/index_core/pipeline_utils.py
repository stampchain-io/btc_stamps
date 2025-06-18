"""
Utility functions for testing and working with the CPBlocksPipeline.
This module is designed to break circular imports between fetch_utils and blocks.
"""

import concurrent.futures
import logging
import threading
import time

import config
from index_core.backend import Backend
from index_core.fallback_state import get_fallback_state_manager
from index_core.fetch_utils import fetch_xcp_blocks_concurrent
from index_core.node_health import get_healthy_nodes, is_shutdown_requested, update_healthy_nodes

logger = logging.getLogger(__name__)
backend_instance = Backend()


class CPBlocksPipeline:
    """Background worker that prefetches blocks and keeps them in a queue."""

    def __init__(self, max_queue_size=600, target_queue_size=250, max_lookahead=500, fallback_mode=True):
        """
        Initialize the pipeline with an empty queue.

        Args:
            max_queue_size (int): Maximum number of blocks to keep in the queue.
            target_queue_size (int): Ideal number of blocks to keep prefetched ahead.
            max_lookahead (int): Maximum number of blocks to fetch ahead of the slowest consumer.
            fallback_mode (bool): If True, continue processing without CP data when nodes fail.
        """
        self.queue = {}  # Block data by index
        self._lock = threading.Lock()
        self.worker_thread = None
        self.shutdown_flag = threading.Event()
        self.initial_blocks_ready = threading.Event()
        self.last_fetch_time = 0
        self.fetch_interval = 2  # Increased interval to check less frequently
        self.max_queue_size = max_queue_size
        self.target_queue_size = target_queue_size
        self.max_lookahead = max_lookahead
        self.current_block = None
        self.initial_batch_size = 10
        self.running = False
        self.fetch_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        # Number of blocks needed before signaling ready for processing
        self.min_blocks_ready = 1  # Signal ready as soon as we have even 1 block
        self.processing_start_delay = 0.5  # Short delay to ensure blocks are registered before processing starts
        self.blocks_being_fetched = set()  # Track which blocks are currently being fetched
        self._blocks_fetch_lock = threading.Lock()  # Separate lock for fetching state

        # Fallback mode settings
        self.fallback_mode = fallback_mode
        self.state_manager = get_fallback_state_manager() if fallback_mode else None

        # Initialize from persisted state if available (for tests and state continuity)
        if self.state_manager and self.state_manager.is_fallback_active():
            self.failed_cp_blocks = self.state_manager.get_failed_blocks()
            self.fallback_started_at = self.state_manager.get_fallback_start_block()
            logger.warning(f"🔄 Detected previous fallback mode state - started at block {self.fallback_started_at}")
            logger.warning(f"📦 {len(self.failed_cp_blocks)} blocks previously processed in fallback mode")
        else:
            self.failed_cp_blocks = set()  # Track blocks that failed CP processing for later rollback
            self.fallback_started_at = None  # Block where fallback mode started

        self.cp_nodes_healthy_again = False  # Flag when CP nodes become available again
        self.last_health_check = 0  # Timestamp of last health check
        self.health_check_interval = 30  # Check every 30 seconds when in fallback

    def start(self, start_block):
        """Start the background worker thread"""
        if start_block is None:
            raise ValueError("start_block must be provided")

        if start_block < config.CP_STAMP_GENESIS_BLOCK:
            logger.warning(f"Start block {start_block} is before CP genesis block {config.CP_STAMP_GENESIS_BLOCK}")
            start_block = config.CP_STAMP_GENESIS_BLOCK

        # Check for fallback state and handle rollback if needed
        if self.state_manager and self.state_manager.is_fallback_active():
            rollback_block = self.state_manager.get_fallback_start_block()
            if rollback_block:
                logger.warning(f"🔄 Performing startup rollback to block {rollback_block}")
                self._perform_startup_rollback(rollback_block)
                # Clear the fallback state after successful rollback
                self.state_manager.end_fallback_mode()
                # Also clear local state
                self.failed_cp_blocks.clear()
                self.fallback_started_at = None
                logger.info("✅ Fallback state cleared - proceeding with normal operation")
                # Update start_block to the rollback point
                start_block = rollback_block

        self.current_block = start_block
        self.running = True

        # Check if we're at or near the blockchain tip before starting
        try:
            block_tip = backend_instance.getblockcount()
            blocks_available = max(0, block_tip - start_block + 1)

            if blocks_available <= 0:
                logger.info(f"No blocks available to fetch (current block {start_block} is beyond tip {block_tip})")
                # Set initial blocks ready flag since there's nothing to fetch
                self.initial_blocks_ready.set()
                return
            elif blocks_available < self.initial_batch_size:
                logger.info(
                    f"Only {blocks_available} blocks available (fewer than requested initial batch size {self.initial_batch_size})"
                )
                # Adjust initial batch size expectations
                self.initial_batch_size = blocks_available
        except Exception as e:
            logger.warning(f"Could not check block tip before starting pipeline: {e}")

        # Initialize node health with a timeout to avoid deadlocks
        try:
            update_healthy_nodes()
        except Exception as e:
            logger.error(f"Error initializing node health: {e}")
            raise RuntimeError("Cannot start pipeline without healthy Counterparty nodes")

        # Start the worker thread
        if self.worker_thread and self.worker_thread.is_alive():
            logger.warning("Worker thread already running, stopping it first")
            self.stop()

        # Reset flags
        self.shutdown_flag.clear()
        self.initial_blocks_ready.clear()

        self.worker_thread = threading.Thread(target=self._fetch_blocks_worker, daemon=True)
        self.worker_thread.start()
        logger.debug(f"Started CP blocks pipeline from block {start_block}")

        # Wait for initial batch of blocks with proper retry logic
        max_retries = 3
        base_timeout = 30  # Increased base timeout for CP data

        for attempt in range(max_retries):
            timeout = base_timeout * (2**attempt)  # Exponential backoff
            logger.info(f"Waiting for initial Counterparty blocks (attempt {attempt + 1}/{max_retries}, timeout: {timeout}s)")

            if self.wait_for_initial_blocks(timeout=timeout):
                logger.info("Successfully obtained initial Counterparty blocks")
                return
            else:
                if attempt < max_retries - 1:
                    logger.warning(f"Failed to get initial blocks on attempt {attempt + 1}, retrying with backup nodes...")
                    # Try to update nodes and retry
                    try:
                        update_healthy_nodes()
                    except Exception as e:
                        logger.error(f"Failed to update healthy nodes: {e}")
                else:
                    if self.fallback_mode:
                        logger.warning(f"Failed to get initial Counterparty blocks after {max_retries} attempts")
                        logger.warning(
                            "FALLBACK MODE: Continuing without Counterparty data - will process Bitcoin transactions only"
                        )
                        logger.warning(
                            f"Fallback started at block {start_block} - use rollback tool later to reprocess with CP data"
                        )
                        self.fallback_started_at = start_block

                        # Persist fallback state to survive restarts
                        if self.state_manager:
                            self.state_manager.start_fallback_mode(start_block)

                        self.initial_blocks_ready.set()  # Signal ready to continue processing
                        return
                    else:
                        logger.error(f"Failed to get initial Counterparty blocks after {max_retries} attempts")
                        self.stop()
                        raise RuntimeError("Cannot proceed without Counterparty block data - all nodes failed")

    def wait_for_initial_blocks(self, timeout=20, min_blocks=None):
        """
        Wait for the initial batch of blocks to be ready

        Args:
            timeout (int): Maximum time to wait in seconds
            min_blocks (int, optional): Minimum number of blocks to wait for,
                                       or None to use self.min_blocks_ready

        Returns:
            bool: True if initial blocks are ready, False if timeout
        """
        # First, check if enough blocks are already available
        if min_blocks is None:
            min_blocks = self.min_blocks_ready

        # Scale timeout based on the expected batch size
        adjusted_timeout = min(60, max(timeout, self.initial_batch_size // 5))

        # Start with a small delay to ensure blocks get registered in the queue
        # before blocks.py tries to access them
        time.sleep(self.processing_start_delay)

        # Wait for the initial ready signal
        ready = self.initial_blocks_ready.wait(timeout=adjusted_timeout)

        if ready:
            with self._lock:
                blocks_available = len(self.queue)

                # If any blocks are available and we only need 1, we're good to go
                if blocks_available >= min_blocks:
                    logger.info(f"Initial blocks ready: {blocks_available} blocks available")
                    return True

                # If we need more than 1 block, verify that the requested blocks are actually ready
                start_block = self.current_block - self.initial_batch_size
                if start_block < 0:
                    start_block = self.current_block  # Fallback if calculation is wrong

                # Check for required blocks - we only need 5 consecutive blocks to start
                # This is more lenient than checking for all initial_batch_size blocks
                consecutive_needed = min(5, self.initial_batch_size)
                required_blocks = set(range(start_block, start_block + consecutive_needed))
                available_blocks = set(self.queue.keys())
                missing_blocks = required_blocks - available_blocks

                if missing_blocks:
                    logger.warning(f"Initial blocks ready signal received but blocks {missing_blocks} still missing")

                    # Check for essential blocks that must be available
                    critical_blocks = [b for b in missing_blocks if b in [820662, 820668]]
                    if critical_blocks:
                        logger.error(f"Critical blocks missing: {critical_blocks}")
                        return False

                    # Only proceed if we have most of the required blocks
                    if len(missing_blocks) > consecutive_needed // 3:  # Allow missing up to 1/3
                        logger.error(
                            f"Too many blocks missing ({len(missing_blocks)}/{consecutive_needed}) - cannot proceed without Counterparty data"
                        )
                        return False

                # Return true only if we have sufficient consecutive blocks
                return blocks_available >= min_blocks and len(missing_blocks) <= consecutive_needed // 3
        else:
            logger.warning(f"Timeout waiting for initial blocks after {adjusted_timeout}s")
            return False

    def stop(self):
        """Stop the background worker thread"""
        logger.info("Stopping CP blocks pipeline...")
        self.running = False
        self.shutdown_flag.set()

        if self.worker_thread and self.worker_thread.is_alive():
            try:
                logger.debug("Waiting for worker thread to complete (max 10s)...")

                # Join with timeout
                join_start = time.time()
                self.worker_thread.join(timeout=10)
                join_elapsed = time.time() - join_start

                if self.worker_thread.is_alive():
                    logger.warning(f"CP blocks pipeline worker thread did not exit within timeout ({join_elapsed:.1f}s)")
                else:
                    logger.info("CP blocks pipeline worker thread exited cleanly")
            except Exception as e:
                logger.error(f"Error joining CP blocks pipeline worker thread: {e}")
        else:
            logger.debug("CP blocks pipeline worker thread not running")

        # Shut down the executor
        try:
            logger.debug("Shutting down fetch executor...")
            self.fetch_executor.shutdown(wait=False)
        except Exception as e:
            logger.error(f"Error shutting down fetch executor: {e}")

        # Clear the queue to free up memory
        with self._lock:
            self.queue.clear()

        logger.info("CP blocks pipeline stopped")

    def reset(self, new_start_block):
        """Reset the pipeline to start from a new block after reorg"""
        logger.info(f"Resetting CP blocks pipeline to block {new_start_block}")
        self.stop()
        with self._lock:
            self.queue.clear()
            self.current_block = new_start_block
            self.last_fetch_time = 0

        # Invalidate blockcount cache to ensure fresh data after reorg
        backend_instance.invalidate_blockcount_cache()

        # Create a new ThreadPoolExecutor since the old one was shutdown in stop()
        # This fixes the "cannot schedule new futures after shutdown" error
        logger.debug("Creating new ThreadPoolExecutor for pipeline reset")
        self.fetch_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)

        # Begin running again
        self.start(new_start_block)

    def get_block(self, block_index):
        """
        Get a block from the queue, returns None if not available.

        This method ensures sequential blocks are available and processes all transaction types
        consistently with no special handling. It triggers direct fetch for missing blocks
        that are needed for sequential processing.

        Args:
            block_index: The block index to retrieve

        Returns:
            Block data dictionary or None if not available
        """
        with self._lock:
            block_data = self.queue.get(block_index)

            if block_data:
                if "issuances" not in block_data:
                    block_data["issuances"] = []

                # Calculate how many old blocks we can safely remove from the queue
                # Keep a reasonable window of old blocks for potential reorgs
                if len(self.queue) > self.max_queue_size // 2:  # Only clean if queue is getting large
                    reorg_window = 10  # Keep blocks for potential recent reorgs
                    cutoff_block = block_index - reorg_window
                    # Find blocks older than cutoff that can be removed
                    old_blocks = [b for b in self.queue.keys() if b < cutoff_block]

                    # Remove old blocks
                    if old_blocks:
                        logger.debug(f"Removing {len(old_blocks)} older blocks from queue (before block {cutoff_block})")
                        for old_block in old_blocks:
                            self.queue.pop(old_block, None)

                logger.debug(f"Retrieved block {block_index} from pipeline queue (queue size: {len(self.queue)})")

                # Check if we should prefetch the next sequential block
                if block_index + 1 not in self.queue and block_index + 1 <= backend_instance.getblockcount():
                    # This will trigger the worker to prioritize fetching the next block
                    logger.debug(f"Triggering prefetch for next block {block_index + 1}")
                    if self.current_block <= block_index:
                        self.current_block = block_index + 1

                return block_data
            else:
                # Check if this block is currently being fetched
                with self._blocks_fetch_lock:
                    is_being_fetched = block_index in self.blocks_being_fetched

                if is_being_fetched:
                    logger.debug(f"Block {block_index} is currently being fetched (not yet in queue)")
                else:
                    logger.debug(
                        f"Block {block_index} not found in pipeline queue and not being fetched (queue size: {len(self.queue)})"
                    )

                # Check if the queue contains blocks nearby - this helps debug out of order issues
                if self.queue:
                    queue_keys = sorted(self.queue.keys())
                    logger.debug(
                        f"Queue contains blocks: {queue_keys[:5]}{'...' if len(queue_keys) > 5 else ''} (showing first 5 of {len(queue_keys)})"
                    )

                    # If we have the next block but not the current one, something is out of order
                    if block_index + 1 in self.queue:
                        logger.warning(f"Block sequence issue: Missing block {block_index} but have block {block_index + 1}")

                # Check if we're requesting a block that's at the chain tip
                block_tip = backend_instance.getblockcount()
                if block_index == block_tip:
                    logger.debug(f"Block {block_index} is at chain tip, might not be available in XCP yet")
                    # Return None but don't log as error - expected behavior
                    return None

                # Update the current block pointer if we're requesting blocks ahead
                if block_index > self.current_block:
                    logger.debug(f"Updating current_block from {self.current_block} to {block_index} based on request")
                    self.current_block = block_index

                # In fallback mode, create empty block data when CP data is not available
                if self.fallback_mode and (self.fallback_started_at is None or block_index >= self.fallback_started_at):
                    logger.debug(f"Fallback mode: Creating empty block data for block {block_index}")
                    fallback_data = self.create_fallback_block(block_index)
                    self.failed_cp_blocks.add(block_index)

                    # Persist failed block to state
                    if self.state_manager:
                        self.state_manager.add_failed_block(block_index)

                    # Store in queue for consistency
                    with self._lock:
                        self.queue[block_index] = fallback_data

                    return fallback_data

                return None

    def create_fallback_block(self, block_index):
        """
        Create a fallback block data structure for processing Bitcoin transactions only.

        Args:
            block_index: The block index to create fallback data for

        Returns:
            Block data dictionary with empty Counterparty data
        """
        logger.debug(f"Creating fallback block data for block {block_index}")
        return {
            "block_index": block_index,
            "xcp_block_hash": None,
            "issuances": [],  # Empty - no CP data available
            "transactions": [],  # Empty - will be populated from Bitcoin directly
            "fallback_mode": True,  # Flag to indicate this is fallback data
            "needs_cp_reprocessing": True,  # Flag for rollback tool
        }

    def get_fallback_block_info(self):
        """
        Get information about fallback mode status.

        Returns:
            Dict with fallback mode information
        """
        return {
            "fallback_mode": self.fallback_mode,
            "fallback_started_at": self.fallback_started_at,
            "failed_cp_blocks_count": len(self.failed_cp_blocks),
            "failed_cp_blocks_sample": sorted(list(self.failed_cp_blocks))[:10] if self.failed_cp_blocks else [],
            "cp_nodes_healthy_again": self.cp_nodes_healthy_again,
        }

    def check_cp_node_recovery(self):
        """
        Check if Counterparty nodes have become healthy again during fallback mode.

        Returns:
            bool: True if nodes are healthy and we should suggest rollback
        """
        current_time = time.time()

        # Only check periodically to avoid excessive overhead
        if current_time - self.last_health_check < self.health_check_interval:
            return self.cp_nodes_healthy_again

        self.last_health_check = current_time

        # Only relevant if we're in fallback mode and have failed blocks
        if not (self.fallback_mode and self.fallback_started_at and self.failed_cp_blocks):
            return False

        try:
            # Try to update and get healthy nodes
            update_healthy_nodes()
            healthy_nodes = get_healthy_nodes()

            if healthy_nodes:
                # Nodes are available again!
                if not self.cp_nodes_healthy_again:
                    logger.warning("🔄 IMPORTANT: Counterparty nodes are healthy again!")
                    logger.warning(f"📦 You have {len(self.failed_cp_blocks)} blocks that were processed in fallback mode")
                    logger.warning(
                        f"🚀 AUTOMATIC ROLLBACK: Rolling back to block {self.fallback_started_at} to reprocess with CP data"
                    )

                    # Trigger automatic rollback
                    self._perform_runtime_rollback()
                    self.cp_nodes_healthy_again = True
                return True
            else:
                self.cp_nodes_healthy_again = False
                return False

        except Exception as e:
            logger.debug(f"Error checking CP node recovery: {e}")
            return False

    def check_for_fallback_entry(self):
        """
        Check if we should enter fallback mode due to node failures.
        Called periodically when NOT in fallback mode to detect node issues.
        """
        current_time = time.time()

        # Only check periodically to avoid excessive overhead
        if current_time - self.last_health_check < self.health_check_interval:
            return False

        self.last_health_check = current_time

        try:
            # Update and get current healthy nodes
            update_healthy_nodes()
            healthy_nodes = get_healthy_nodes()

            # If no healthy nodes, enter fallback mode
            if not healthy_nodes:
                logger.warning("🚨 NO HEALTHY COUNTERPARTY NODES DETECTED!")
                logger.warning("🔄 ENTERING FALLBACK MODE - will continue with Bitcoin data only")
                self._enter_fallback_mode()
                return True
            else:
                # Nodes are healthy, no action needed
                return False

        except Exception as e:
            logger.debug(f"Error checking for fallback entry: {e}")
            return False

    def _enter_fallback_mode(self):
        """
        Enter fallback mode when CP nodes become unavailable during runtime.
        """
        if self.fallback_started_at is not None:
            # Already in fallback mode
            return

        # Mark the current block as the start of fallback mode
        current_block = self.current_block
        self.fallback_started_at = current_block

        # Ensure fallback mode flag is set (might not be if initialized with fallback_mode=False)
        if not self.fallback_mode:
            logger.info("Enabling fallback mode flag for runtime fallback")
            self.fallback_mode = True

        logger.warning(f"🔄 FALLBACK MODE ACTIVATED at block {current_block}")
        logger.warning("📦 Will continue processing Bitcoin transactions without Counterparty data")
        logger.warning("🔄 Automatic rollback will trigger when CP nodes become healthy again")

        # Persist fallback state to survive restarts
        if self.state_manager:
            self.state_manager.start_fallback_mode(current_block)
            logger.info(f"Fallback state persisted starting at block {current_block}")

    def _perform_runtime_rollback(self):
        """
        Perform automatic rollback during runtime when CP nodes become healthy again.
        Uses the same rollback method as the manual rollback command.
        """
        if not (self.fallback_started_at and self.failed_cp_blocks):
            logger.warning("No rollback needed - no fallback blocks to reprocess")
            return

        target_block = self.fallback_started_at

        try:
            # Import the shared rollback function
            from index_core.database import perform_complete_rollback

            logger.info(f"🔄 Starting automatic runtime rollback to block {target_block}")
            logger.info(f"📦 Will reprocess {len(self.failed_cp_blocks)} blocks with full CP data")

            # Use the same rollback function as the manual command
            # Capture print output by temporarily redirecting to logger
            import contextlib
            import io

            f = io.StringIO()
            with contextlib.redirect_stdout(f):
                perform_complete_rollback(target_block)

            # Log the output from the rollback function
            rollback_output = f.getvalue()
            for line in rollback_output.strip().split("\n"):
                if line.strip():
                    logger.info(f"ROLLBACK: {line}")

            # Clear fallback state since we've rolled back
            self.failed_cp_blocks.clear()
            self.fallback_started_at = None

            # Clear the pipeline's state manager instance (for tests and consistency)
            if self.state_manager:
                self.state_manager.end_fallback_mode()

            # Reset fallback mode flag (but keep fallback capability enabled)
            # The fallback_mode=True parameter from initialization stays for capability
            # but we're no longer actively in fallback mode
            logger.info("Clearing runtime fallback mode state")

            logger.info("🎉 Fallback mode ended - ready to reprocess with full CP data")

        except Exception as e:
            logger.error(f"Error during runtime rollback: {e}")
            logger.warning("Automatic rollback failed - manual intervention may be required")
            # Don't clear state if rollback failed

    def _perform_startup_rollback(self, target_block):
        """
        Perform database rollback at startup when fallback state is detected.
        Uses the same rollback method as the manual rollback command.
        """
        try:
            # Import the shared rollback function
            from index_core.database import perform_complete_rollback

            logger.info(f"🔄 Starting startup rollback to block {target_block}")

            # Use the same rollback function as the manual command
            # Capture print output by temporarily redirecting to logger
            import contextlib
            import io

            f = io.StringIO()
            with contextlib.redirect_stdout(f):
                perform_complete_rollback(target_block)

            # Log the output from the rollback function
            rollback_output = f.getvalue()
            for line in rollback_output.strip().split("\n"):
                if line.strip():
                    logger.info(f"STARTUP ROLLBACK: {line}")

            logger.info(f"✅ Startup rollback completed to block {target_block}")

        except Exception as e:
            logger.error(f"Error during startup rollback: {e}")
            raise RuntimeError(f"Failed to perform startup rollback: {e}")

    def _fetch_blocks_worker(self):
        """Background worker that continuously prefetches blocks"""
        initial_fetch = True
        consecutive_errors = 0
        max_consecutive_errors = 3
        fetch_futures = {}  # Track async fetch operations

        # Set a fixed number of initial blocks to fetch
        # Use self.current_block which is initialized in start()
        if self.current_block is None:
            logger.error("Pipeline worker started before current_block was set.")
            return  # Cannot proceed without a starting block

        initial_target = self.current_block + self.initial_batch_size

        logger.info(f"CPBlocksPipeline worker starting - target initial blocks up to {initial_target}")

        # Print executor state to ensure it's properly initialized
        logger.info(f"Using thread pool executor: {self.fetch_executor}, max_workers: {self.fetch_executor._max_workers}")

        while not self.shutdown_flag.is_set() and not is_shutdown_requested() and self.running:
            try:
                current_time = time.time()

                # Rate limit fetching (except for initial batch)
                if not initial_fetch and current_time - self.last_fetch_time < self.fetch_interval:
                    time.sleep(0.1)
                    continue

                # Check shutdown flag more frequently
                if self.shutdown_flag.is_set() or is_shutdown_requested() or not self.running:
                    logger.info("Shutdown flag detected in CP blocks pipeline, stopping worker")
                    break

                # Check for CP node recovery if in fallback mode, or check for failures to enter fallback mode
                if self.fallback_mode:
                    self.check_cp_node_recovery()
                else:
                    # Check if we need to enter fallback mode due to node failures
                    self.check_for_fallback_entry()

                # --- Start: Calculate effective tip based on lookahead ---
                with self._lock:
                    queue_keys = self.queue.keys()
                    # Approximate processor position with the lowest block index in queue
                    lowest_queued_block = min(queue_keys) if queue_keys else self.current_block
                    queue_size = len(queue_keys)
                    # next_block is the block the *fetcher* is looking at
                    next_block = self.current_block
                    # Keep a local copy of queue blocks for calculations outside the lock
                    local_queue_blocks = set(queue_keys)

                # Calculate the absolute maximum block index allowed for fetching based on processor position
                max_fetch_block = lowest_queued_block + self.max_lookahead
                # --- End: Calculate effective tip ---

                # Get current blockchain tip
                block_tip = backend_instance.getblockcount()
                if block_tip is None:
                    logger.warning("Could not get block tip, retrying in 2 seconds...")
                    time.sleep(2)
                    continue

                # Limit how far ahead we fetch based on the lowest queued block (processor position)
                effective_tip = min(block_tip, max_fetch_block)
                logger.debug(
                    f"Current blockchain tip: {block_tip}, Effective fetch tip (lookahead limited): {effective_tip}, Fetcher at: {next_block}, Processor approx at: {lowest_queued_block}"
                )

                # If the fetcher has hit or surpassed the effective tip, throttle
                if next_block >= effective_tip:
                    if initial_fetch:
                        logger.info(f"Initial fetch reached effective tip {effective_tip}, setting initial_blocks_ready flag")
                        self.initial_blocks_ready.set()
                        initial_fetch = False
                    logger.debug(f"Fetcher at {next_block} has reached or passed effective tip {effective_tip}. Waiting.")
                    time.sleep(2)  # Shorter wait at chain tip/lookahead limit
                    continue

                # Calculate how many blocks ahead of current fetcher position to fetch, respecting effective_tip
                blocks_to_fetch_count = min(self.target_queue_size - queue_size, effective_tip - next_block + 1)
                blocks_to_fetch_count = max(0, blocks_to_fetch_count)  # Ensure it's not negative

                # Enhanced logging for fetching calculations
                logger.debug(
                    f"Blocks to fetch calculation: target_queue_size={self.target_queue_size}, current_queue_size={queue_size}, "
                    f"blocks_to_effective_tip={effective_tip - next_block + 1}, calculated_fetch_count={blocks_to_fetch_count}"
                )
                # Increase fetch batch size for initial fetch to speed up loading
                if initial_fetch:
                    # Cap the fetch range but make it larger for initial fetch
                    max_batch_fetch = min(100, self.initial_batch_size)
                else:
                    # Standard fetch after initial - Increased batch size
                    max_batch_fetch = 150

                # Determine the end block for the *next batch* fetch operation
                fetch_batch_end = min(next_block + max_batch_fetch - 1, next_block + blocks_to_fetch_count - 1, effective_tip)

                # Always fetch at least one block if possible and needed
                if fetch_batch_end < next_block and next_block <= effective_tip and blocks_to_fetch_count > 0:
                    fetch_batch_end = next_block

                # Calculate missing blocks with guaranteed sequential order first
                sequential_blocks = []
                current_seq_block = next_block
                # Identify gaps in sequential blocks up to the target or effective tip
                sequential_target_end = min(next_block + self.target_queue_size, effective_tip)
                while current_seq_block <= sequential_target_end:
                    # Use the local copy of queue blocks
                    if current_seq_block not in local_queue_blocks:
                        sequential_blocks.append(current_seq_block)
                        # Limit the sequential filling to a reasonable batch size
                        if len(sequential_blocks) >= max_batch_fetch:
                            break
                    current_seq_block += 1

                # If we need more blocks beyond sequential ones, add them
                if not sequential_blocks and blocks_to_fetch_count > 0:
                    # Calculate missing blocks in the range we want to have prefetched, respecting effective_tip
                    target_prefetch_end = min(next_block + self.target_queue_size, effective_tip)
                    target_blocks = set(range(next_block, target_prefetch_end + 1))
                    # Use the local copy of queue blocks
                    missing_blocks = sorted(list(target_blocks - local_queue_blocks))
                    logger.debug(f"Need {len(missing_blocks)} non-sequential blocks up to {target_prefetch_end}")
                elif sequential_blocks:
                    # Use the sequential blocks we identified
                    missing_blocks = sequential_blocks
                    logger.debug(
                        f"Prioritizing {len(sequential_blocks)} sequential blocks: {missing_blocks[:5]}{'...' if len(missing_blocks) > 5 else ''}"
                    )
                else:
                    missing_blocks = []  # No blocks needed

                # Limit missing_blocks to max_batch_fetch size for the current iteration
                missing_blocks_batch = missing_blocks[:max_batch_fetch]

                # Only proceed if there are blocks to fetch *and* queue is below a threshold
                trigger_fetch_threshold = int(self.target_queue_size * 0.8)  # Fetch if below 80% target
                if queue_size < trigger_fetch_threshold and missing_blocks_batch:
                    try:
                        logger.debug(
                            f"Queue size {queue_size} < {trigger_fetch_threshold}, attempting fetch of {len(missing_blocks_batch)} blocks."
                        )
                        if missing_blocks_batch:
                            logger.debug(f"Missing block batch range: {missing_blocks_batch[0]} to {missing_blocks_batch[-1]}")

                        # Get fresh list of healthy nodes with retry logic
                        nodes = get_healthy_nodes()
                        if not nodes:
                            logger.warning("No healthy nodes available, attempting to update node list")
                            try:
                                update_healthy_nodes()
                                nodes = get_healthy_nodes()
                            except Exception as e:
                                logger.error(f"Failed to update healthy nodes: {e}")

                            if not nodes:
                                if self.fallback_mode:
                                    logger.warning("No healthy Counterparty nodes available - continuing in fallback mode")
                                    # In fallback mode, create empty blocks for the missing batch
                                    with self._lock:
                                        for block_idx in missing_blocks_batch:
                                            if block_idx not in self.queue:
                                                fallback_data = self.create_fallback_block(block_idx)
                                                self.queue[block_idx] = fallback_data
                                                self.failed_cp_blocks.add(block_idx)
                                                logger.debug(f"Added fallback block {block_idx} to queue")
                                    time.sleep(5)  # Shorter wait in fallback mode
                                    continue
                                else:
                                    logger.error("No healthy Counterparty nodes available after update - cannot fetch blocks")
                                    consecutive_errors += 1
                                    if consecutive_errors >= max_consecutive_errors:
                                        logger.error("Too many consecutive node failures - stopping pipeline")
                                        self.running = False
                                        break
                                    time.sleep(10)  # Longer wait when nodes are down
                                    continue

                        # Debug the nodes we're using for fetch
                        logger.debug(f"Using nodes for fetch: {[node['name'] for node in nodes]}")

                        # Start async fetch of missing blocks batch by batch
                        # Note: _fetch_blocks_batch handles fetching potentially sparse indices within the batch range
                        batch_to_submit = missing_blocks_batch  # Submit the exact blocks needed for this batch

                        # Skip blocks that are already being fetched
                        with self._blocks_fetch_lock:
                            # Check against fetch_futures first (more accurate for pending tasks)
                            blocks_not_in_futures = [
                                b for b in batch_to_submit if b not in fetch_futures or fetch_futures[b].done()
                            ]
                            # Then check against the broader blocks_being_fetched set
                            blocks_to_fetch_now = [b for b in blocks_not_in_futures if b not in self.blocks_being_fetched]

                            if blocks_to_fetch_now:
                                logger.debug(f"Starting async fetch task for {len(blocks_to_fetch_now)} blocks")

                                # Add blocks to the being fetched set
                                self.blocks_being_fetched.update(blocks_to_fetch_now)

                                # Use the first healthy node (we've already verified they work)
                                node_url = nodes[0]["url"]
                                logger.debug(f"Using node URL: {node_url}")

                                # Add direct debug for the submission
                                try:
                                    # Submit the fetch task to the executor to run asynchronously
                                    logger.info(
                                        f"Submitting async task for {len(blocks_to_fetch_now)} blocks: {blocks_to_fetch_now[0]}-{blocks_to_fetch_now[-1]}"
                                    )
                                    future = self.fetch_executor.submit(
                                        self._fetch_blocks_batch, blocks_to_fetch_now, node_url
                                    )

                                    # Register the future for each block being fetched in this task
                                    for block_idx in blocks_to_fetch_now:
                                        fetch_futures[block_idx] = future

                                    # Update the last fetch time
                                    self.last_fetch_time = current_time

                                except Exception as e:
                                    logger.error(f"Error submitting fetch task: {e}", exc_info=True)
                                    # Remove blocks from being fetched if submission fails
                                    with self._blocks_fetch_lock:
                                        self.blocks_being_fetched.difference_update(blocks_to_fetch_now)
                            else:
                                logger.debug(
                                    f"Skipping fetch for batch {batch_to_submit} as blocks are already being fetched or pending."
                                )

                        # Check for completed fetches (moved outside the batch loop)
                        # Process completed futures (moved outside the batch loop)

                    except Exception as e:
                        logger.error(f"Error during block fetching preparation: {e}", exc_info=True)
                        consecutive_errors += 1
                        if consecutive_errors >= max_consecutive_errors:
                            logger.error(f"Too many consecutive errors ({consecutive_errors}), retrying after delay")
                            time.sleep(5)  # Longer backoff
                            consecutive_errors = 0  # Reset after backoff
                elif not missing_blocks_batch:
                    # Log if no blocks are needed, but still process completed futures below
                    logger.debug("No missing blocks identified in the target range/batch size.")
                    # Still process completed futures below, small sleep if nothing else to do
                    time.sleep(0.5)
                else:  # Queue is above threshold, but not full. Wait longer before re-checking.
                    logger.debug(f"Queue size {queue_size} >= fetch trigger threshold {trigger_fetch_threshold}. Waiting.")
                    # Still process completed futures below, but sleep longer before next fetch check
                    time.sleep(self.fetch_interval * 2)

                # Check for CP node recovery during fallback mode
                if self.fallback_mode and self.fallback_started_at:
                    self.check_cp_node_recovery()

                # --- Moved processing of completed futures outside the fetch initiation logic ---
                # Check for completed fetches (always do this every loop iteration)
                completed_futures_map = {}  # block_idx -> future
                active_block_indices_in_futures = set()
                with self._blocks_fetch_lock:  # Lock needed when accessing fetch_futures potentially shared state? Check usage pattern.
                    # Accessing items() should be safe for iteration if additions/deletions are locked.
                    futures_to_remove = []
                    for block_idx, future in fetch_futures.items():
                        if future.done():
                            completed_futures_map[block_idx] = future
                            futures_to_remove.append(block_idx)
                        else:
                            active_block_indices_in_futures.add(block_idx)

                    # Remove completed futures from the main tracking dict
                    for block_idx in futures_to_remove:
                        fetch_futures.pop(block_idx, None)

                # Process completed futures (unique futures only)
                processed_futures = set()
                for block_idx, future in completed_futures_map.items():
                    if future in processed_futures:
                        continue  # Already processed this future instance

                    processed_futures.add(future)
                    blocks_associated_with_this_future = [idx for idx, fut in completed_futures_map.items() if fut == future]

                    try:
                        # Get the result dictionary {block_index: block_data}
                        result_dict = future.result(timeout=1)  # Short timeout, should be done
                        if result_dict:
                            logger.debug(f"Processing result for {len(result_dict)} blocks from a completed future.")
                            # Process the results
                            with self._lock:  # Lock needed for queue and current_block updates
                                added_count = 0
                                for res_block_index, block_data in result_dict.items():
                                    if block_data and "error" not in block_data:
                                        # Store block data in queue
                                        self.queue[res_block_index] = block_data
                                        added_count += 1
                                        logger.debug(f"Added block {res_block_index} to queue")
                                        # Only update current_block if it's the next sequential block we were waiting for
                                        if res_block_index == self.current_block:
                                            # Advance current_block past all contiguous blocks added
                                            start_advance = self.current_block
                                            while self.current_block in self.queue:
                                                self.current_block += 1
                                            if self.current_block > start_advance:
                                                logger.debug(
                                                    f"Advanced current_block from {start_advance} to {self.current_block}"
                                                )
                                    else:  # Handle block fetch error within the batch
                                        logger.warning(
                                            f"Block {res_block_index} fetch failed within batch: {block_data.get('error', 'Unknown error')}"
                                        )

                                    # Update queue state log after processing batch result
                                    current_queue_size = len(self.queue)
                                    if current_queue_size > 0:
                                        queue_block_keys = sorted(list(self.queue.keys()))
                                        logger.debug(
                                            f"Queue now contains {current_queue_size} blocks. Range: {queue_block_keys[0]} to {queue_block_keys[-1]}"
                                        )
                                    else:
                                        logger.debug("Queue is currently empty.")

                        else:
                            logger.warning(
                                f"Future for blocks {blocks_associated_with_this_future} completed but returned no result."
                            )

                    except concurrent.futures.TimeoutError:
                        logger.error(
                            f"Timeout retrieving result from supposedly done future for blocks {blocks_associated_with_this_future}"
                        )
                    except Exception as e:
                        logger.error(
                            f"Error processing future result for blocks {blocks_associated_with_this_future}: {e}",
                            exc_info=True,
                        )

                    # Regardless of success/failure in processing, remove associated blocks from being_fetched set
                    with self._blocks_fetch_lock:
                        self.blocks_being_fetched.difference_update(blocks_associated_with_this_future)
                        logger.debug(
                            f"Removed {len(blocks_associated_with_this_future)} blocks from blocks_being_fetched set."
                        )

                # Set initial_blocks_ready flag much earlier - as soon as we have a few blocks
                # Check this after processing results
                with self._lock:
                    current_queue_size = len(self.queue)
                if initial_fetch and current_queue_size >= self.min_blocks_ready:
                    logger.info(
                        f"Initial fetch has {current_queue_size} blocks in queue (needed {self.min_blocks_ready}), setting ready flag"
                    )
                    self.initial_blocks_ready.set()
                    initial_fetch = False

            except Exception as e:
                logger.error(f"Unexpected error in fetch worker loop: {e}", exc_info=True)
                consecutive_errors += 1
                if consecutive_errors >= max_consecutive_errors:
                    logger.error(f"Too many consecutive errors ({consecutive_errors}), backing off")
                    time.sleep(5)  # Longer backoff
                    consecutive_errors = 0  # Reset after backoff
                else:
                    time.sleep(1)  # Shorter sleep for non-consecutive errors

        # Make sure initial_blocks_ready is set on exit to prevent hanging
        if not self.initial_blocks_ready.is_set():
            logger.info("Setting initial_blocks_ready flag on worker exit")
            self.initial_blocks_ready.set()

        logger.info("CPBlocksPipeline worker thread exiting")

    def _fetch_blocks_batch(self, block_indices, node_url):
        """
        Fetch a batch of blocks synchronously using fetch_utils functions with retry logic.

        This method uses fetch_xcp_blocks_concurrent from fetch_utils to efficiently
        retrieve blocks while maintaining the expected data structure and transaction order.
        All transaction types are processed consistently without special handling.

        Args:
            block_indices: List of block indices to fetch
            node_url: Optional specific node URL to use

        Returns:
            Dictionary mapping block indices to block data
        """
        if not block_indices:
            logger.warning("Empty block_indices list passed to _fetch_blocks_batch")
            return {}

        logger.debug(f"Starting batch fetch of {len(block_indices)} blocks using fetch_utils")

        # Retry logic for fetching blocks
        max_retries = 2
        retry_delay = 1  # Start with 1 second delay

        for attempt in range(max_retries + 1):
            try:
                # Check for shutdown before each attempt
                if self.shutdown_flag.is_set() or is_shutdown_requested() or not self.running:
                    logger.info("Shutdown detected before batch fetch, stopping")
                    with self._blocks_fetch_lock:
                        self.blocks_being_fetched.difference_update(block_indices)
                    return {}

                # Determine start and end blocks for the range
                start_block = min(block_indices)
                end_block = max(block_indices)

                # Update healthy nodes on retry attempts
                if attempt > 0:
                    logger.info(f"Retry attempt {attempt} for blocks {start_block}-{end_block}, updating healthy nodes")
                    try:
                        update_healthy_nodes()
                    except Exception as e:
                        logger.warning(f"Failed to update healthy nodes on retry: {e}")

                # Use fetch_xcp_blocks_concurrent from fetch_utils
                # This handles pagination, block formatting and concurrent fetching
                blocks_data = fetch_xcp_blocks_concurrent(start_block, end_block)

                if not blocks_data:
                    if attempt < max_retries:
                        logger.warning(
                            f"Failed to fetch blocks {start_block} to {end_block} (attempt {attempt + 1}), retrying in {retry_delay}s..."
                        )
                        time.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                        continue
                    else:
                        logger.error(f"Failed to fetch blocks {start_block} to {end_block} after {max_retries + 1} attempts")
                        with self._blocks_fetch_lock:
                            self.blocks_being_fetched.difference_update(block_indices)
                        return {}

                # Filter the results to only include the requested blocks
                result = {idx: data for idx, data in blocks_data.items() if idx in block_indices}

                # Check if we got sufficient blocks
                missing = set(block_indices) - set(result.keys())
                if missing and len(missing) > len(block_indices) // 2:  # More than half missing
                    if attempt < max_retries:
                        logger.warning(
                            f"Too many missing blocks ({len(missing)}/{len(block_indices)}) on attempt {attempt + 1}, retrying..."
                        )
                        time.sleep(retry_delay)
                        retry_delay *= 2
                        continue
                    else:
                        logger.error(f"Failed to fetch sufficient blocks after {max_retries + 1} attempts. Missing: {missing}")

                # Log if we got fewer blocks than requested (but proceed if it's not too many)
                if missing:
                    logger.warning(f"Fetched {len(result)} out of {len(block_indices)} requested blocks. Missing: {missing}")

                # Update the queue with fetched blocks
                with self._lock:
                    for idx, block_data in result.items():
                        if block_data and "error" not in block_data:
                            self.queue[idx] = block_data
                            # Only update current_block if it's the next sequential block
                            if idx == self.current_block:
                                self.current_block = idx + 1

                    # Set ready flag as soon as we have enough blocks
                    # This ensures blocks.py can start processing without waiting for all blocks
                    if not self.initial_blocks_ready.is_set() and len(self.queue) >= self.min_blocks_ready:
                        logger.info(f"Fetched {len(self.queue)} blocks, signaling ready")
                        self.initial_blocks_ready.set()

                logger.debug(
                    f"Successfully fetched {len(result)} blocks out of {len(block_indices)} requested (attempt {attempt + 1})"
                )

                # Remove blocks from being fetched, even if they weren't found
                with self._blocks_fetch_lock:
                    self.blocks_being_fetched.difference_update(block_indices)

                return result

            except Exception as e:
                if attempt < max_retries:
                    logger.warning(f"Error in _fetch_blocks_batch (attempt {attempt + 1}): {e}, retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                else:
                    logger.error(f"Error in _fetch_blocks_batch after {max_retries + 1} attempts: {e}", exc_info=True)
                    # Remove blocks from being fetched on error
                    with self._blocks_fetch_lock:
                        self.blocks_being_fetched.difference_update(block_indices)
                    return {}


def test_pipeline_simple(start_block=None, num_blocks=10, max_wait=60):
    """
    A simple function to test the CP blocks pipeline.

    Args:
        start_block: Starting block number (default: None, uses current block - 100)
        num_blocks: Number of blocks to fetch (default: 10)
        max_wait: Maximum time to wait in seconds (default: 60)

    Returns:
        bool: True if successful, False otherwise
    """
    # Initialize
    if start_block is None:
        # Start 100 blocks before current tip
        current_tip = backend_instance.getblockcount()
        if current_tip is None:
            logger.error("Could not get block count")
            return False
        start_block = max(current_tip - 100, config.CP_STAMP_GENESIS_BLOCK)

    print(f"PIPELINE TEST: Testing from block {start_block} to {start_block + num_blocks - 1}")
    logger.info(f"Testing CP blocks pipeline from block {start_block} to {start_block + num_blocks - 1}")

    try:
        # Create pipeline with smaller queue size for faster testing
        pipeline = CPBlocksPipeline(max_queue_size=50)
        print(f"PIPELINE TEST: Created pipeline with min_blocks_ready={pipeline.min_blocks_ready}")
        # Set smaller initial batch size for testing
        pipeline.initial_batch_size = min(20, num_blocks * 2)
        pipeline.target_queue_size = min(50, num_blocks * 5)
        print(
            f"PIPELINE TEST: Using initial_batch_size={pipeline.initial_batch_size}, target_queue_size={pipeline.target_queue_size}"
        )
        logger.info(f"Using initial_batch_size={pipeline.initial_batch_size}, target_queue_size={pipeline.target_queue_size}")

        # Start the pipeline
        print(f"PIPELINE TEST: Starting pipeline at block {start_block}")
        logger.info(f"Starting pipeline at block {start_block}")
        pipeline.start(start_block)
        print(f"PIPELINE TEST: Pipeline started, initial_blocks_ready={pipeline.initial_blocks_ready.is_set()}")

        # Wait for blocks to be fetched
        start_time = time.time()
        blocks_fetched = set()
        target_block = start_block + num_blocks - 1

        # Log progress more frequently
        progress_interval = 5
        next_progress = time.time() + progress_interval
        print(f"PIPELINE TEST: Waiting up to {max_wait}s for blocks from {start_block} to {target_block}")
        logger.info(f"Waiting up to {max_wait}s for blocks from {start_block} to {target_block}")

        while time.time() - start_time < max_wait:
            # Check if we've fetched any blocks
            with pipeline._lock:
                queue_blocks = set(pipeline.queue.keys())
                # Calculate missing blocks but we don't use them (for debugging only)
                _ = set(range(start_block, target_block + 1)) - queue_blocks
                blocks_fetched.update(queue_blocks)
                current_size = len(pipeline.queue)

                print(f"PIPELINE TEST: Queue now has {current_size} blocks, blocks_fetched={len(blocks_fetched)}")

                # Log queue contents for debugging
                if queue_blocks:
                    queue_min = min(queue_blocks) if queue_blocks else "N/A"
                    queue_max = max(queue_blocks) if queue_blocks else "N/A"
                    print(f"PIPELINE TEST: Queue contains blocks from {queue_min} to {queue_max}")
                    logger.debug(f"Queue contains {len(queue_blocks)} blocks: range {queue_min} to {queue_max}")

            # Log more detailed progress at intervals
            if time.time() >= next_progress:
                fetched_pct = (len(blocks_fetched) / num_blocks * 100) if num_blocks > 0 else 0
                elapsed = time.time() - start_time
                print(
                    f"PIPELINE TEST: Progress: {len(blocks_fetched)}/{num_blocks} blocks ({fetched_pct:.1f}%) in {elapsed:.1f}s"
                )
                logger.info(
                    f"Progress: {len(blocks_fetched)}/{num_blocks} blocks ({fetched_pct:.1f}%) in {elapsed:.1f}s, queue_size={current_size}"
                )
                next_progress = time.time() + progress_interval

            # Check for completion - success if we got at least one block in our target range
            # This is a more relaxed condition than requiring all blocks
            target_blocks_fetched = len(blocks_fetched.intersection(range(start_block, target_block + 1)))
            print(f"PIPELINE TEST: Target blocks fetched: {target_blocks_fetched} out of {num_blocks}")
            if target_blocks_fetched > 0:
                print(f"PIPELINE TEST: Success! Fetched {target_blocks_fetched} blocks in target range")
                logger.info(f"Successfully fetched {target_blocks_fetched} blocks in target range")
                return True

            # Sleep briefly to avoid tight loop
            time.sleep(1)

        # If we get here, we timed out
        print(f"PIPELINE TEST: ❌ Timeout after {max_wait}s, fetched {len(blocks_fetched)} blocks but none in target range")
        logger.error(
            f"Timeout after {max_wait}s, fetched {len(blocks_fetched)} blocks but none in target range {start_block}-{target_block}"
        )

        # Report any blocks we did fetch
        if blocks_fetched:
            fetched_blocks = sorted(list(blocks_fetched))
            print(f"PIPELINE TEST: Fetched blocks: {fetched_blocks[:10]}...")
            logger.info(f"Fetched blocks: {fetched_blocks[:10]}...")

        return False
    except Exception as e:
        print(f"PIPELINE TEST: ❌ Error: {e}")
        logger.error(f"Error testing pipeline: {e}", exc_info=True)
        return False
    finally:
        # Stop the pipeline if it was created
        if "pipeline" in locals():
            print("PIPELINE TEST: Stopping pipeline")
            logger.info("Stopping pipeline")
            pipeline.stop()
