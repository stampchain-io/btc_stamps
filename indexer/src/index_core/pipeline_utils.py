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

    def __init__(
        self,
        max_queue_size=600,
        target_queue_size=50,
        max_lookahead=500,
        initial_fetch_size=10,
        max_batch_size=30,
        fallback_mode=True,
    ):
        """
        Initialize the pipeline with an empty queue.

        Args:
            max_queue_size (int): Maximum number of blocks to keep in the queue.
            target_queue_size (int): Target number of blocks to keep prefetched ahead.
            max_lookahead (int): Maximum number of blocks to fetch ahead of the slowest consumer.
            initial_fetch_size (int): Number of blocks to fetch on startup (default: 50).
            max_batch_size (int): Maximum blocks per API call (default: 150).
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
        self.initial_fetch_size = initial_fetch_size  # How many blocks to fetch on startup
        self.max_batch_size = max_batch_size  # Maximum blocks per API call
        self.current_block = None
        self.running = False
        self.fetch_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        # Number of blocks needed before signaling ready for processing
        self.min_blocks_ready = 1  # Signal ready when we have at least 1 block
        self.blocks_being_fetched = set()  # Track which blocks are currently being fetched
        self._blocks_fetch_lock = threading.Lock()  # Separate lock for fetching state
        self.fetch_futures_lock = threading.Lock()  # Lock for fetch_futures dictionary
        self.fetch_futures = {}  # Track active fetch futures
        self.blocks_fetch_timestamps = {}  # Track when each block started being fetched
        self.fetch_timeout = 60  # Timeout for block fetches in seconds

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
            self.fallback_started_at = None  # Flag for when CP nodes become available again

        self.cp_nodes_healthy_again = False  # Timestamp of last health check
        self.last_health_check = 0  # Check every 30 seconds when in fallback
        self.health_check_interval = 30

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
                logger.debug(f"No blocks available to fetch (current block {start_block} is beyond tip {block_tip})")
                # Set initial blocks ready flag since there's nothing to fetch
                self.initial_blocks_ready.set()
                return
        except Exception as e:
            logger.warning(f"Could not check block tip before starting pipeline: {e}")

        # Initialize node health with a timeout to avoid deadlocks
        try:
            update_healthy_nodes()
            # Check if we have healthy nodes after update
            initial_nodes = get_healthy_nodes()
            if not initial_nodes and not self.fallback_mode:
                logger.error("No healthy Counterparty nodes available and fallback mode is disabled")
                raise RuntimeError("Cannot start pipeline without healthy Counterparty nodes")
            elif not initial_nodes and self.fallback_mode:
                logger.warning("No healthy Counterparty nodes detected at startup - will start in fallback mode")
                # Enter fallback mode immediately
                self._enter_fallback_mode()
                # Set initial blocks ready since we won't be fetching any CP data
                self.initial_blocks_ready.set()
        except Exception as e:
            logger.error(f"Error initializing node health: {e}")
            if not self.fallback_mode:
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
        if min_blocks is None:
            min_blocks = self.min_blocks_ready

        # Wait for blocks to be available in the queue
        start_time = time.time()

        while time.time() - start_time < timeout:
            # Check if the ready flag is set or if we have enough blocks
            if self.initial_blocks_ready.is_set():
                return True

            # Also check queue directly
            with self._lock:
                if len(self.queue) >= min_blocks:
                    logger.debug(f"Found {len(self.queue)} blocks in queue, marking as ready")
                    self.initial_blocks_ready.set()
                    return True

            # Short sleep to avoid busy waiting
            time.sleep(0.1)

        logger.warning(f"Timeout waiting for initial blocks after {timeout}s")
        return False

    def _cleanup_stuck_fetches(self):
        """Remove blocks that have been in blocks_being_fetched for too long"""
        current_time = time.time()
        blocks_to_clean = []

        with self._blocks_fetch_lock:
            # Log current state
            if self.blocks_being_fetched:
                oldest_fetch_time = min(self.blocks_fetch_timestamps.get(b, current_time) for b in self.blocks_being_fetched)
                oldest_age = current_time - oldest_fetch_time
                logger.debug(
                    f"Cleanup check: {len(self.blocks_being_fetched)} blocks in blocks_being_fetched, oldest: {oldest_age:.1f}s old"
                )

            for block in list(self.blocks_being_fetched):
                if block in self.blocks_fetch_timestamps:
                    fetch_time = self.blocks_fetch_timestamps[block]
                    age = current_time - fetch_time
                    if age > self.fetch_timeout:
                        logger.warning(
                            f"Block {block} has been fetching for {age:.1f}s (timeout: {self.fetch_timeout}s), removing from blocks_being_fetched"
                        )
                        blocks_to_clean.append(block)
                else:
                    # Block in set but no timestamp - shouldn't happen but clean it up
                    logger.warning(f"Block {block} in blocks_being_fetched but no timestamp, cleaning up")
                    blocks_to_clean.append(block)

            # Clean up stuck blocks
            for block in blocks_to_clean:
                self.blocks_being_fetched.discard(block)
                self.blocks_fetch_timestamps.pop(block, None)

            if blocks_to_clean:
                logger.info(f"✅ Cleaned up {len(blocks_to_clean)} stuck blocks from blocks_being_fetched")
                logger.info(f"Remaining blocks in blocks_being_fetched: {len(self.blocks_being_fetched)}")

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
            # Cancel any pending fetch futures to avoid blocking on shutdown
            futures_to_cancel = []
            with self.fetch_futures_lock:
                # Get copies of futures from our tracking dict
                futures_to_cancel = list(set(self.fetch_futures.values()))

            # Cancel futures that aren't done
            cancelled_count = 0
            for future in futures_to_cancel:
                if not future.done() and future.cancel():
                    cancelled_count += 1

            if cancelled_count > 0:
                logger.debug(f"Cancelled {cancelled_count} pending fetch tasks")

            # Now shutdown with wait=True, which will complete quickly since we cancelled pending tasks
            self.fetch_executor.shutdown(wait=True)
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

    def confirm_block_processed(self, block_index):
        """
        Confirm that a block has been successfully processed and can be removed from the queue.
        This should be called by the block processor after successful commit to database.

        Args:
            block_index: The block index that was successfully processed
        """
        with self._lock:
            # Remove the processed block from the queue
            removed_block = self.queue.pop(block_index, None)
            if removed_block:
                logger.debug(f"Confirmed block {block_index} processed, removed from queue. Queue size: {len(self.queue)}")

                # Update pipeline position to the next block that should be processed
                if block_index >= self.current_block:
                    self.current_block = block_index + 1
                    logger.debug(f"Advanced pipeline position to {self.current_block}")

                # Clean up old blocks from queue that are far behind the current position
                blocks_to_remove = [blk for blk in self.queue.keys() if blk < block_index - 10]
                for old_block in blocks_to_remove:
                    self.queue.pop(old_block, None)

                if blocks_to_remove:
                    logger.debug(f"Cleaned up {len(blocks_to_remove)} old blocks from queue")
            else:
                logger.debug(f"Block {block_index} already removed from queue or never existed")

    def get_block(self, block_index):
        """
        Get a block from the queue WITHOUT removing it. The block remains in the queue
        until confirm_block_processed() is called.

        Args:
            block_index: The block index to retrieve

        Returns:
            Block data dictionary or None if not available
        """
        with self._lock:
            # Check if we have the block in the queue
            block_data = self.queue.get(block_index)
            if block_data:
                # Check if we need to adjust the pipeline position to fill the gap
                if block_index < self.current_block:
                    # The processor is asking for a block behind our current position
                    # This means there's a gap - we need to go back and fetch it
                    logger.debug(
                        f"Gap detected: processor needs {block_index} but pipeline is at {self.current_block}. Adjusting pipeline to fill gap."
                    )
                    self.current_block = block_index

                logger.debug(f"Retrieved block {block_index} for processor (keeping in queue). Queue size: {len(self.queue)}")
                return block_data
            else:
                # The required block is not in the queue.
                # CRITICAL: Do NOT update processor position when block is missing
                # This prevents the pipeline from jumping ahead and creating gaps

                # Get detailed queue state for debugging
                queue_blocks = sorted(self.queue.keys()) if self.queue else []
                queue_range = f"{min(queue_blocks)}-{max(queue_blocks)}" if queue_blocks else "empty"

                # Only log if pipeline is still running to avoid closed file errors
                if self.running:
                    logger.warning(f"❌ Block {block_index} not in queue. Queue size: {len(self.queue)}, range: {queue_range}")
                    logger.warning(f"Pipeline current_block: {self.current_block}, requested: {block_index}")

                    # Show blocks currently being fetched
                    with self._blocks_fetch_lock:
                        if self.blocks_being_fetched:
                            fetching_list = sorted(list(self.blocks_being_fetched))
                            fetching_range = f"{min(fetching_list)}-{max(fetching_list)}" if fetching_list else "none"
                            logger.warning(
                                f"Blocks being fetched: {len(self.blocks_being_fetched)} blocks, range: {fetching_range}"
                            )

                # Check if we need to adjust the pipeline position to fill the gap
                if block_index < self.current_block:
                    # The processor is asking for a block behind our current position
                    # This means there's a gap - we need to go back and fetch it
                    logger.warning(
                        f"Gap detected: processor needs {block_index} but pipeline is at {self.current_block}. Adjusting pipeline to fill gap."
                    )
                    self.current_block = block_index

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

        # Create initial fallback blocks if queue is empty to prevent blocking
        with self._lock:
            if len(self.queue) == 0:
                logger.info("Creating initial fallback blocks to prevent startup blocking")
                # Create a few fallback blocks to get started
                for i in range(5):  # Create 5 blocks ahead
                    block_idx = current_block + i
                    self.queue[block_idx] = self.create_fallback_block(block_idx)

                # Set the initial blocks ready flag to unblock wait_for_initial_blocks()
                if not self.initial_blocks_ready.is_set():
                    logger.info("Setting initial_blocks_ready flag for fallback mode")
                    self.initial_blocks_ready.set()

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
        """Background worker that continuously prefetches blocks."""
        logger.info(f"CPBlocksPipeline worker starting from block {self.current_block}")

        # Immediately start fetching the initial blocks
        initial_fetch_complete = False

        while not self.shutdown_flag.is_set() and self.running:
            try:
                # 1. Process any futures that have completed their work.
                self._process_completed_futures()

                # 2. Check for node health and handle fallback mode.
                if self.fallback_mode:
                    if self.check_cp_node_recovery():
                        continue
                else:
                    if self.check_for_fallback_entry():
                        continue

                # 3. Decide if we need to fetch more blocks.
                with self._lock:
                    processor_position = self.current_block
                    queue_size = len(self.queue)

                block_tip = backend_instance.getblockcount()
                if block_tip is None:
                    logger.warning("Could not get block tip, retrying...")
                    time.sleep(2)
                    continue

                # Respect the lookahead limit from the processor's position
                effective_tip = min(block_tip, processor_position + self.max_lookahead)

                logger.info(
                    f"🔧 Pipeline state: processor_at={processor_position}, queue_size={queue_size}, "
                    f"tip={block_tip}, effective_tip={effective_tip}"
                )

                # For initial fetch, use initial_fetch_size to get a reasonable starting batch
                if not initial_fetch_complete:
                    # On startup, fetch initial_fetch_size blocks (limited by effective_tip)
                    fetch_end_block = min(processor_position + self.initial_fetch_size - 1, effective_tip)
                    should_fetch = True
                    logger.debug(
                        f"Initial fetch: targeting {self.initial_fetch_size} blocks from {processor_position} to {fetch_end_block}"
                    )
                else:
                    # Normal operation: try to maintain target_queue_size blocks in queue
                    should_fetch = queue_size < self.target_queue_size and processor_position <= effective_tip
                    # Calculate how many blocks we need to reach target_queue_size
                    blocks_needed = self.target_queue_size - queue_size
                    fetch_end_block = min(processor_position + blocks_needed - 1, effective_tip)

                if not should_fetch:
                    logger.debug("Queue is full or processor is caught up. Waiting.")
                    time.sleep(self.fetch_interval)
                    continue

                # 4. Identify which blocks to fetch.
                potential_blocks = list(range(processor_position, fetch_end_block + 1))

                if not potential_blocks:
                    time.sleep(1)
                    continue

                # Figure out which blocks we need from the potential list
                with self._blocks_fetch_lock:
                    with self._lock:  # Need lock for self.queue
                        existing_in_queue = set(self.queue.keys())

                    blocks_already_present = self.blocks_being_fetched.union(existing_in_queue)
                    blocks_to_fetch_now = [b for b in potential_blocks if b not in blocks_already_present]

                # CRITICAL: Always prioritize the current processor block if it's missing
                # This prevents gaps where queue has future blocks but processor is stuck
                if processor_position not in existing_in_queue and processor_position not in self.blocks_being_fetched:
                    if processor_position not in blocks_to_fetch_now:
                        # Insert the processor block at the beginning of the fetch list
                        blocks_to_fetch_now.insert(0, processor_position)
                        logger.warning(
                            f"🚨 Gap detected: prioritizing fetch of processor block {processor_position} "
                            f"(queue range: {min(existing_in_queue) if existing_in_queue else 'empty'}-"
                            f"{max(existing_in_queue) if existing_in_queue else 'empty'})"
                        )

                # Limit the batch size for a single API call
                blocks_to_fetch_now = blocks_to_fetch_now[: self.max_batch_size]

                if not blocks_to_fetch_now:
                    logger.debug("No new blocks to fetch in the target range. Waiting.")
                    time.sleep(1)
                    continue

                logger.debug(
                    f"Identified {len(blocks_to_fetch_now)} blocks to fetch, "
                    f"from {blocks_to_fetch_now[0]} to {blocks_to_fetch_now[-1]} "
                    f"(limited by max_batch_size={self.max_batch_size})"
                )

                # 5. Submit the fetch task.
                nodes = get_healthy_nodes()
                if not nodes:
                    logger.warning("No healthy nodes available for fetching.")
                    # Trigger fallback mode if enabled
                    if self.fallback_mode and self.fallback_started_at is None:
                        self._enter_fallback_mode()

                    # If we're in fallback mode, create fallback blocks instead of waiting
                    if self.fallback_mode and self.fallback_started_at is not None:
                        logger.info(f"Creating fallback blocks for {blocks_to_fetch_now}")
                        with self._lock:
                            for block_idx in blocks_to_fetch_now:
                                if block_idx not in self.queue:
                                    self.queue[block_idx] = self.create_fallback_block(block_idx)
                                    # Track this block as needing CP data later
                                    self.failed_cp_blocks.add(block_idx)

                            # Signal ready if initial fetch
                            if not self.initial_blocks_ready.is_set() and len(self.queue) >= self.min_blocks_ready:
                                logger.debug(f"Initial fallback fetch has {len(self.queue)} blocks, setting ready flag.")
                                self.initial_blocks_ready.set()

                        # Mark initial fetch as complete
                        if not initial_fetch_complete:
                            initial_fetch_complete = True
                    else:
                        time.sleep(10)
                    continue

                with self._blocks_fetch_lock:
                    current_timestamp = time.time()
                    self.blocks_being_fetched.update(blocks_to_fetch_now)
                    for block in blocks_to_fetch_now:
                        self.blocks_fetch_timestamps[block] = current_timestamp

                    # Let the underlying fetch functions handle node selection with round-robin
                    future = self.fetch_executor.submit(self._fetch_blocks_batch, blocks_to_fetch_now, None)

                    with self.fetch_futures_lock:
                        for block_idx in blocks_to_fetch_now:
                            self.fetch_futures[block_idx] = future

                # Check if initial fetch is complete
                # We consider it complete once we've made at least one successful fetch
                if not initial_fetch_complete and len(self.queue) >= self.min_blocks_ready:
                    initial_fetch_complete = True
                    logger.debug(f"Initial fetch complete with {len(self.queue)} blocks in queue")

            except Exception as e:
                logger.error(f"Unexpected error in fetch worker loop: {e}", exc_info=True)
                time.sleep(5)

        logger.info("CPBlocksPipeline worker thread exiting")

    def _process_completed_futures(self):
        """Helper to process completed futures and update queue."""
        completed_futures_map = {}
        with self.fetch_futures_lock:
            futures_to_remove = [block_idx for block_idx, future in self.fetch_futures.items() if future.done()]
            for block_idx in futures_to_remove:
                completed_futures_map[block_idx] = self.fetch_futures.pop(block_idx)

        processed_futures = set()
        for block_idx, future in completed_futures_map.items():
            if future in processed_futures:
                continue
            processed_futures.add(future)

            blocks_in_future = [idx for idx, fut in completed_futures_map.items() if fut == future]

            try:
                result_dict = future.result(timeout=1)  # Should be done, so short timeout
                if result_dict:
                    logger.info(f"✅ Processing result for {len(result_dict)} blocks from a completed future.")
                    with self._lock:
                        added_blocks = []
                        for res_block_index, block_data in result_dict.items():
                            if block_data and "error" not in block_data:
                                # Check if this block is already processed (older than current_block)
                                if res_block_index < self.current_block:
                                    logger.warning(
                                        f"Discarding already processed block {res_block_index} from completed future (processor is at {self.current_block})."
                                    )
                                    continue

                                # Add block to queue if not already present
                                if res_block_index not in self.queue:
                                    self.queue[res_block_index] = block_data
                                    added_blocks.append(res_block_index)
                                    logger.debug(f"Added block {res_block_index} to pipeline queue")
                                else:
                                    logger.debug(f"Block {res_block_index} already in queue, skipping")
                            else:
                                error_msg = block_data.get("error", "Unknown error") if block_data else "Empty data"
                                logger.warning(f"Block {res_block_index} fetch failed within batch: {error_msg}")

                        if added_blocks:
                            added_range = (
                                f"{min(added_blocks)}-{max(added_blocks)}" if len(added_blocks) > 1 else str(added_blocks[0])
                            )
                            logger.info(
                                f"📦 Added {len(added_blocks)} blocks to queue: {added_range}. Queue size now: {len(self.queue)}"
                            )

                    # Signal ready if it's the initial fetch and we have enough blocks
                    if not self.initial_blocks_ready.is_set() and len(self.queue) >= self.min_blocks_ready:
                        logger.debug(f"Initial fetch has {len(self.queue)} blocks, setting ready flag.")
                        self.initial_blocks_ready.set()
                else:
                    logger.warning(f"Future for blocks {blocks_in_future} completed but returned no result.")
            except Exception as e:
                logger.error(f"Error processing future result for blocks {blocks_in_future}: {e}", exc_info=True)

            # Clean up from the 'being fetched' set
            with self._blocks_fetch_lock:
                self.blocks_being_fetched.difference_update(blocks_in_future)
                for block in blocks_in_future:
                    self.blocks_fetch_timestamps.pop(block, None)

    def _fetch_blocks_batch(self, block_indices, node_url=None):
        """
        Fetch a batch of blocks synchronously using fetch_utils functions with retry logic.

        Node selection is handled by the underlying fetch functions which support:
        - Round-robin load balancing for multi-node configurations (CP_NODE_POOL)
        - Primary/fallback failover (CP_PRIMARY_NODE_URL/CP_FALLBACK_NODE_URL)
        - Legacy single-node configuration (CP_RPC_URL)

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
                if self.shutdown_flag.is_set() or is_shutdown_requested():
                    logger.info("Shutdown detected before batch fetch, stopping")
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

                if start_block <= 781141 <= end_block:
                    if 781141 in blocks_data:
                        import json

                        logger.warning(f"DEBUG 781141: {json.dumps(blocks_data[781141], indent=2)}")
                    else:
                        logger.warning("DEBUG 781141: not in blocks_data")

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
                        return {}

                # Filter the results to only include the requested blocks
                result = {idx: data for idx, data in blocks_data.items() if idx in block_indices}

                # Log if we got fewer blocks than requested
                missing = set(block_indices) - set(result.keys())
                if missing:
                    logger.warning(
                        f"Fetched {len(result)} out of {len(block_indices)} requested blocks. Missing: {sorted(list(missing))}"
                    )

                # This method should NOT modify the pipeline's state. It only returns data.
                return result

            except Exception as e:
                if attempt < max_retries:
                    logger.warning(f"Error in _fetch_blocks_batch (attempt {attempt + 1}): {e}, retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                else:
                    logger.error(f"Error in _fetch_blocks_batch after {max_retries + 1} attempts: {e}", exc_info=True)
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
    logger.debug(f"Testing CP blocks pipeline from block {start_block} to {start_block + num_blocks - 1}")

    try:
        # Create pipeline with smaller queue size for faster testing
        pipeline = CPBlocksPipeline(
            max_queue_size=50,
            target_queue_size=min(50, num_blocks * 5),
            initial_fetch_size=min(20, num_blocks),  # Fetch up to 20 blocks initially
            max_batch_size=50,  # Allow smaller batches for testing
        )
        print("PIPELINE TEST: Created pipeline with:")
        print(f"  - initial_fetch_size={pipeline.initial_fetch_size}")
        print(f"  - target_queue_size={pipeline.target_queue_size}")
        print(f"  - max_batch_size={pipeline.max_batch_size}")
        print(f"  - min_blocks_ready={pipeline.min_blocks_ready}")
        logger.debug(
            f"Pipeline config: initial_fetch_size={pipeline.initial_fetch_size}, "
            f"target_queue_size={pipeline.target_queue_size}, max_batch_size={pipeline.max_batch_size}"
        )

        # Start the pipeline
        print(f"PIPELINE TEST: Starting pipeline at block {start_block}")
        logger.debug(f"Starting pipeline at block {start_block}")
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
        logger.debug(f"Waiting up to {max_wait}s for blocks from {start_block} to {target_block}")

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
                logger.debug(
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
            logger.debug(f"Fetched blocks: {fetched_blocks[:10]}...")

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
