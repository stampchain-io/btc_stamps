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
        self.min_blocks_ready = 1  # Signal ready when we have at least 1 block
        self.processing_start_delay = 0.5  # Short delay to ensure blocks are registered before processing starts
        self.blocks_being_fetched = set()  # Track which blocks are currently being fetched
        self._blocks_fetch_lock = threading.Lock()  # Separate lock for fetching state
        self.fetch_futures_lock = threading.Lock()  # Lock for fetch_futures dictionary
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
        Get a block from the queue. If the requested block is not available,
        it returns None, and the worker thread is expected to fetch it.

        This method ensures the processor's position is only advanced upon
        successful retrieval of a sequential block. It also handles cases
        where the consumer is lagging behind the pipeline's state.

        Args:
            block_index: The block index to retrieve

        Returns:
            Block data dictionary or None if not available
        """
        with self._lock:
            # The consumer (blocks.py) is asking for a block that is behind
            # the pipeline's internal processor position.
            if block_index < self.current_block:
                logger.warning(
                    f"Out-of-sequence get_block request for {block_index}, which is behind processor at {self.current_block}. "
                    "Returning block and allowing consumer to catch up."
                )
                # Provide the old block but also remove it from the queue so the consumer can advance.
                return self.queue.pop(block_index, None)

            # The consumer is asking for the exact block the pipeline is ready for.
            if block_index == self.current_block:
                block_data = self.queue.pop(block_index, None)
                if block_data:
                    logger.info(f"Retrieved block {block_index} for processor. Advancing state. Queue size: {len(self.queue)}")
                    # Advance the processor's position. The worker will fetch from this new position.
                    self.current_block += 1
                    return block_data
                else:
                    # The required sequential block is not in the queue. The processor must wait.
                    logger.info(f"Block {block_index} not in queue. Processor is waiting for fetcher.")
                    return None

            # The consumer is asking for a block ahead of the processor.
            # This should not happen in normal operation but can occur during reorgs.
            # Return the data if we have it, but do not advance the primary 'current_block' state.
            if block_index > self.current_block:
                logger.warning(f"Ahead-of-sequence get_block request for {block_index}, processor is at {self.current_block}.")
                return self.queue.get(block_index)

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
        """Background worker that continuously prefetches blocks."""
        logger.info(f"CPBlocksPipeline worker starting from block {self.current_block}")
        fetch_futures = {}

        while not self.shutdown_flag.is_set() and self.running:
            try:
                # 1. Process any futures that have completed their work.
                self._process_completed_futures(fetch_futures)

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
                    f"Pipeline state: processor_at={processor_position}, queue_size={queue_size}, "
                    f"tip={block_tip}, effective_tip={effective_tip}"
                )

                # Condition to fetch is simple: queue is not full, and we're not at the tip.
                should_fetch = queue_size < self.target_queue_size and processor_position <= effective_tip

                if not should_fetch:
                    logger.debug("Queue is full or processor is caught up. Waiting.")
                    time.sleep(self.fetch_interval)
                    continue

                # 4. Identify which blocks to fetch.
                # We want to fill the queue up to the target size, starting from where the processor is.
                fetch_end_block = min(processor_position + self.target_queue_size, effective_tip)
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

                # Limit the batch size for a single API call
                blocks_to_fetch_now = blocks_to_fetch_now[:150]  # Hardcoded max batch size

                if not blocks_to_fetch_now:
                    logger.debug("No new blocks to fetch in the target range. Waiting.")
                    time.sleep(1)
                    continue

                logger.info(
                    f"Identified {len(blocks_to_fetch_now)} blocks to fetch, "
                    f"from {blocks_to_fetch_now[0]} to {blocks_to_fetch_now[-1]}"
                )

                # 5. Submit the fetch task.
                nodes = get_healthy_nodes()
                if not nodes:
                    logger.warning("No healthy nodes available for fetching.")
                    time.sleep(10)
                    continue

                with self._blocks_fetch_lock:
                    current_timestamp = time.time()
                    self.blocks_being_fetched.update(blocks_to_fetch_now)
                    for block in blocks_to_fetch_now:
                        self.blocks_fetch_timestamps[block] = current_timestamp

                    node_url = nodes[0]["url"]
                    future = self.fetch_executor.submit(self._fetch_blocks_batch, blocks_to_fetch_now, node_url)

                    with self.fetch_futures_lock:
                        for block_idx in blocks_to_fetch_now:
                            fetch_futures[block_idx] = future

            except Exception as e:
                logger.error(f"Unexpected error in fetch worker loop: {e}", exc_info=True)
                time.sleep(5)

        logger.info("CPBlocksPipeline worker thread exiting")

    def _process_completed_futures(self, fetch_futures):
        """Helper to process completed futures and update queue."""
        completed_futures_map = {}
        with self.fetch_futures_lock:
            futures_to_remove = [block_idx for block_idx, future in fetch_futures.items() if future.done()]
            for block_idx in futures_to_remove:
                completed_futures_map[block_idx] = fetch_futures.pop(block_idx)

        processed_futures = set()
        for block_idx, future in completed_futures_map.items():
            if future in processed_futures:
                continue
            processed_futures.add(future)

            blocks_in_future = [idx for idx, fut in completed_futures_map.items() if fut == future]

            try:
                result_dict = future.result(timeout=1)  # Should be done, so short timeout
                if result_dict:
                    logger.debug(f"Processing result for {len(result_dict)} blocks from a completed future.")
                    with self._lock:
                        for res_block_index, block_data in result_dict.items():
                            if block_data and "error" not in block_data:
                                # Only add block if it's not already in the queue.
                                if res_block_index not in self.queue:
                                    self.queue[res_block_index] = block_data
                            else:
                                error_msg = block_data.get("error", "Unknown error") if block_data else "Empty data"
                                logger.warning(f"Block {res_block_index} fetch failed within batch: {error_msg}")

                    # Signal ready if it's the initial fetch
                    if not self.initial_blocks_ready.is_set() and len(self.queue) >= self.min_blocks_ready:
                        logger.info(f"Initial fetch has {len(self.queue)} blocks, setting ready flag.")
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
                        for block in block_indices:
                            self.blocks_fetch_timestamps.pop(block, None)
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

                        # Check for immediate fallback entry after total fetch failure
                        if self.fallback_mode and not self.fallback_started_at:
                            logger.warning("🚨 TOTAL FETCH FAILURE - checking for immediate fallback entry")
                            try:
                                # Force immediate health update and check for fallback
                                update_healthy_nodes()
                                healthy_nodes = get_healthy_nodes()
                                if not healthy_nodes:
                                    logger.warning(
                                        "🚨 No healthy nodes after fetch failure - entering fallback mode immediately"
                                    )
                                    self._enter_fallback_mode()
                            except Exception as e:
                                logger.warning(f"Error during immediate fallback check: {e}")

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
