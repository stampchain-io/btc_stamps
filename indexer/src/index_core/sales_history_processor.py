"""
Sales History Processor for Bitcoin Stamps

This module handles fetching and processing all types of stamp sales data:
- Dispenser sales (from Counterparty)
- Atomic swaps (future)
- OTC/Private sales (future)

Provides two modes:
1. Full Catchup Mode: Fetches ALL dispenses once via paginated /dispenses endpoint
   - Used when >50 blocks behind tip
   - Filters locally for stamp CPIDs
   - Checks for new CPIDs every 100 blocks
2. Real-time Mode: Fetches sales by block (for new blocks at tip)
   - Used when ≤50 blocks from tip
   - One API call per block

Stores all sales in stamp_sales_history table for charting, recent sales, and analytics.
"""

import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from index_core.database_manager import DatabaseManager
from index_core.fetch_utils import RateLimiter, fetch_xcp, is_valid_counterparty_asset

logger = logging.getLogger(__name__)

# Constants
STAMPS_GENESIS_BLOCK = 779652
MAX_WORKERS = 3  # Concurrent workers for catchup mode (reduced to minimize contention)
RATE_LIMIT = 1.0  # Requests per second to Counterparty API (reduced to be gentler)
INSERT_BATCH_SIZE = 100  # Max records per insert to avoid long-running transactions

# Rate limiter for API calls
rate_limiter = RateLimiter(calls_per_second=RATE_LIMIT)


class SalesHistoryProcessor:
    """Unified processor for all stamp sales types."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db_manager = db_manager or DatabaseManager()
        self.cpid_cache: Set[str] = set()
        self.last_cache_update = 0
        self.cache_update_interval = 300  # 5 minutes
        self._lock = threading.Lock()
        self.catchup_running = False
        self.catchup_executor: Optional[ThreadPoolExecutor] = None
        self.progress: Dict[str, int] = {
            "total_blocks": 0,
            "total_cpids": 0,  # For CPID mode
            "processed_cpids": 0,  # For CPID mode
            "total_sales": 0,
            "last_block_processed": 0,
            "catchup_start_time": 0,
            "errors": 0,
        }
        # Buffer for batched writes during catchup
        self.catchup_buffer: List[tuple] = []
        self.catchup_buffer_lock = threading.Lock()
        self.buffer_flush_interval = 100  # Flush every 100 blocks
        self.last_buffer_flush_block = 0

        # New: Dispense cache for Full Catchup Mode
        self.dispense_cache: Dict[str, Any] = {
            "data": [],
            "highest_block": 0,
            "fetched_at_tip": 0,
            "last_cpid_check_block": 0,
        }
        self.mode = "REALTIME"  # Current processing mode
        self.mode_threshold = 200  # Blocks behind threshold for mode switching

    def determine_processing_mode(self, db=None) -> str:
        """
        Determine which processing mode to use based on current state.

        Returns:
            "FULL_CATCHUP" if >50 blocks behind
            "REALTIME" if <=50 blocks from tip
        """
        if db is None:
            db = self.db_manager.connect()
            close_db = True
        else:
            close_db = False

        try:
            # Get highest block in sales history
            with db.cursor() as cursor:
                cursor.execute("SELECT MAX(block_index) FROM stamp_sales_history")
                result = cursor.fetchone()
                highest_sales_block = result[0] if result and result[0] else 0

            # Get current Bitcoin tip
            with db.cursor() as cursor:
                cursor.execute("SELECT MAX(block_index) FROM blocks")
                result = cursor.fetchone()
                current_tip = result[0] if result and result[0] else 0

            blocks_behind = current_tip - highest_sales_block

            logger.info(
                f"Mode determination: sales at block {highest_sales_block}, "
                f"tip at {current_tip}, {blocks_behind} blocks behind"
            )

            if blocks_behind > self.mode_threshold:
                logger.debug(
                    f"Determined mode: FULL_CATCHUP (blocks behind: {blocks_behind} > threshold: {self.mode_threshold})"
                )
                return "FULL_CATCHUP"
            else:
                logger.debug(f"Determined mode: REALTIME (blocks behind: {blocks_behind} <= threshold: {self.mode_threshold})")
                return "REALTIME"

        finally:
            if close_db:
                db.close()

    def update_cpid_cache(self, db=None):
        """Update the in-memory CPID cache from database."""
        current_time = time.time()
        if current_time - self.last_cache_update < self.cache_update_interval:
            return  # Cache still fresh

        if db is None:
            db = self.db_manager.connect()
            close_db = True
        else:
            close_db = False

        try:
            with db.cursor() as cursor:
                # Get all stamp CPIDs
                cursor.execute(
                    """
                    SELECT DISTINCT cpid
                    FROM StampTableV4
                    WHERE ident IN ('STAMP', 'SRC-721')
                    AND cpid IS NOT NULL
                """
                )

                raw_cpids = {row[0] for row in cursor.fetchall() if row[0]}

                # Filter out invalid CPIDs (e.g., SRC-20 hash tokens)
                valid_cpids = {cpid for cpid in raw_cpids if is_valid_counterparty_asset(cpid)}
                invalid_count = len(raw_cpids) - len(valid_cpids)

                with self._lock:
                    self.cpid_cache = valid_cpids
                    self.last_cache_update = current_time

                logger.info(
                    f"Updated CPID cache with {len(valid_cpids)} valid stamps (filtered out {invalid_count} invalid CPIDs)"
                )
                logger.debug(f"CPID cache update took {time.time() - current_time:.2f} seconds")

        finally:
            if close_db:
                db.close()

    def process_block_dispenses(self, block_index: int, db=None) -> int:
        """
        Process all dispenses in a specific block (real-time mode).

        Args:
            block_index: The block to process
            db: Optional database connection

        Returns:
            Number of stamp dispenses processed
        """
        if block_index < STAMPS_GENESIS_BLOCK:
            return 0

        # In Full Catchup Mode, we should skip individual block processing entirely
        # The background thread is handling all dispenses in bulk
        if self.mode == "FULL_CATCHUP" and self.catchup_running:
            # Check for new CPIDs periodically (this doesn't make API calls)
            self.check_and_process_new_cpids(block_index)

            # Skip individual block processing completely during Full Catchup
            # Don't even log "Processing block X" to avoid confusion
            cached_highest = self.dispense_cache.get("highest_block", 0)
            if cached_highest > 0:  # We have cached data
                logger.debug(
                    f"Skipping block {block_index} in FULL_CATCHUP mode "
                    f"(background thread is processing bulk data up to block {cached_highest})"
                )
            return 0

        # Only log this in REALTIME mode
        logger.info(f"Processing block {block_index} for stamp dispenses")

        # Ensure cache is updated
        self.update_cpid_cache(db)

        # Rate limiting
        rate_limiter.acquire()

        try:
            # Fetch all dispenses in the block with verbose data
            response = fetch_xcp(f"/blocks/{block_index}/dispenses", {"verbose": "true", "show_unconfirmed": "false"})

            if not response or "result" not in response:
                logger.info(f"No dispenses found in block {block_index}")
                return 0

            dispenses = response["result"]
            logger.info(f"Found {len(dispenses)} total dispenses in block {block_index}")

            # Filter for stamp CPIDs
            stamp_dispenses = []
            invalid_assets = set()
            with self._lock:
                for dispense in dispenses:
                    asset = dispense.get("asset")
                    if asset in self.cpid_cache:
                        stamp_dispenses.append(dispense)
                    elif asset and not is_valid_counterparty_asset(asset):
                        invalid_assets.add(asset)

            if invalid_assets:
                logger.debug(
                    f"Filtered out {len(invalid_assets)} invalid assets (likely SRC-20): {list(invalid_assets)[:5]}..."
                )

            if stamp_dispenses:
                logger.info(f"Found {len(stamp_dispenses)} stamp dispenses in block {block_index}")
                # Use buffering if we're in catchup mode
                self._store_dispenser_sales(stamp_dispenses, db, use_buffer=self.catchup_running)
                logger.info(
                    f"Successfully processed and stored {len(stamp_dispenses)} stamp dispenses from block {block_index}"
                )
            else:
                logger.info(f"No stamp dispenses found in block {block_index}")

            return len(stamp_dispenses)

        except Exception as e:
            logger.error(f"Error processing block {block_index} dispenses: {e}")
            self.progress["errors"] = self.progress["errors"] + 1
            return 0

    def start_catchup_mode(self):
        """
        Start catchup mode to backfill historical sales.
        Mode is automatically determined based on how far behind we are.
        """
        if self.catchup_running:
            logger.warning("Catchup mode already running")
            return

        self.catchup_running = True
        self.catchup_executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
        self.progress["catchup_start_time"] = int(datetime.now().timestamp())

        # Determine mode
        previous_mode = self.mode
        self.mode = self.determine_processing_mode()

        if previous_mode != self.mode:
            logger.info(f"Mode switch: {previous_mode} -> {self.mode}")

        logger.info(f"Starting sales history catchup in {self.mode} mode")

        # Start the catchup in a background thread
        threading.Thread(target=self._run_catchup, daemon=True).start()

        logger.info("Started sales history catchup mode in background")

    def stop_catchup_mode(self):
        """Stop the catchup mode if running."""
        if not self.catchup_running:
            return

        logger.info("Stopping sales history catchup mode...")
        self.catchup_running = False

        if self.catchup_executor:
            self.catchup_executor.shutdown(wait=True)
            self.catchup_executor = None

        logger.info("Sales history catchup mode stopped")

    def get_progress(self) -> Dict:
        """Get current catchup progress."""
        with self._lock:
            return self.progress.copy()

    def _get_cpids_needing_catchup(self, db, start_block: Optional[int], end_block: Optional[int]) -> List[str]:
        """Get list of CPIDs that need sales history catchup."""
        with db.cursor() as cursor:
            # Get all stamp CPIDs with their earliest block (to maintain some ordering)
            query = """
                SELECT cpid, MIN(block_index) as first_block
                FROM StampTableV4
                WHERE ident IN ('STAMP', 'SRC-721')
                AND cpid IS NOT NULL
                AND block_index >= %s
                GROUP BY cpid
                ORDER BY first_block
            """
            cursor.execute(query, (start_block or STAMPS_GENESIS_BLOCK,))
            all_cpids = [row[0] for row in cursor.fetchall() if row[0]]

            # Filter out invalid CPIDs
            valid_cpids = [cpid for cpid in all_cpids if is_valid_counterparty_asset(cpid)]
            invalid_count = len(all_cpids) - len(valid_cpids)

            if invalid_count > 0:
                logger.info(f"Filtered out {invalid_count} invalid CPIDs from catchup list")

            return valid_cpids

    def _fetch_all_dispenses(self) -> bool:
        """
        Fetch ALL dispenses from Counterparty API using paginated requests.
        This is the core of Full Catchup Mode - one bulk fetch instead of per-CPID.

        Returns:
            True if successful, False otherwise
        """
        logger.info("Starting Full Catchup Mode - fetching all dispenses from Counterparty API")

        all_dispenses = []
        cursor = None
        highest_block = 0
        page = 0

        try:
            while True:
                # Rate limiting
                rate_limiter.acquire()

                # Build params
                params = {"verbose": "true", "limit": 1000}
                if cursor:
                    params["cursor"] = cursor

                logger.info(f"Fetching dispenses page {page + 1} (cursor: {cursor})")

                # Fetch page
                response = fetch_xcp("/dispenses", params)

                if not response or "result" not in response:
                    logger.error("Failed to fetch dispenses")
                    return False

                page_dispenses = response["result"]
                all_dispenses.extend(page_dispenses)

                # Track highest block
                for dispense in page_dispenses:
                    block_index = dispense.get("block_index", 0)
                    if block_index > highest_block:
                        highest_block = block_index

                logger.info(f"Fetched page {page + 1}: {len(page_dispenses)} dispenses, total so far: {len(all_dispenses)}")

                # Check for next page
                cursor = response.get("next_cursor")
                if not cursor:
                    break

                page += 1

                # Small delay between pages to be nice to the API
                time.sleep(0.5)

            # Get current tip for reference
            db = self.db_manager.connect()
            try:
                with db.cursor() as cursor:
                    cursor.execute("SELECT MAX(block_index) FROM blocks")
                    result = cursor.fetchone()
                    current_tip = result[0] if result and result[0] else 0
            finally:
                db.close()

            # Cache the results
            with self._lock:
                self.dispense_cache = {
                    "data": all_dispenses,
                    "highest_block": highest_block,
                    "fetched_at_tip": current_tip,
                    "last_cpid_check_block": 0,
                }
                logger.debug(
                    f"Dispense cache populated: {len(all_dispenses)} items, "
                    f"memory usage: ~{len(str(all_dispenses)) / 1024 / 1024:.2f} MB"
                )

            logger.info(
                f"Full Catchup Mode fetch complete: {len(all_dispenses)} total dispenses, "
                f"highest block: {highest_block}, fetched at tip: {current_tip}"
            )

            return True

        except Exception as e:
            logger.error(f"Error fetching all dispenses: {e}")
            return False

    def _process_cached_dispenses(self, cpids: Optional[Set[str]] = None, after_block: int = 0) -> int:
        """
        Process dispenses from cache, filtering for our CPIDs.

        Args:
            cpids: Set of CPIDs to filter for. If None, uses current cache.
            after_block: Only process dispenses after this block

        Returns:
            Number of dispenses processed
        """
        if not self.dispense_cache["data"]:
            logger.warning("No cached dispenses to process")
            return 0

        # Use provided CPIDs or current cache
        if cpids is None:
            cpids = self.cpid_cache

        if not cpids:
            logger.warning("No CPIDs to filter for")
            return 0

        # Filter dispenses
        relevant_dispenses = []
        skipped_cpids = 0
        skipped_blocks = 0
        skipped_invalid = 0

        for dispense in self.dispense_cache["data"]:
            asset = dispense.get("asset")
            block_index = dispense.get("block_index", 0)

            # Skip if not our CPID or before cutoff block
            if asset not in cpids:
                skipped_cpids += 1
                continue
            if block_index <= after_block:
                skipped_blocks += 1
                continue

            # Skip if not a valid stamp CPID
            if not is_valid_counterparty_asset(asset):
                skipped_invalid += 1
                continue

            relevant_dispenses.append(dispense)

        logger.debug(
            f"Filtered {len(self.dispense_cache['data'])} cached dispenses: "
            f"{len(relevant_dispenses)} relevant, {skipped_cpids} not our CPIDs, "
            f"{skipped_blocks} before cutoff, {skipped_invalid} invalid assets"
        )

        if not relevant_dispenses:
            logger.info("No relevant dispenses found in cache")
            return 0

        # Process in batches
        logger.info(f"Processing {len(relevant_dispenses)} relevant dispenses from cache")

        batch_size = 1000
        for i in range(0, len(relevant_dispenses), batch_size):
            batch = relevant_dispenses[i : i + batch_size]
            self._store_dispenser_sales(batch)

        return len(relevant_dispenses)

    def _run_catchup(self):
        """Run the catchup process using the new simplified architecture."""
        try:
            # Lower thread priority to reduce impact on main indexer
            import os

            if hasattr(os, "nice"):
                try:
                    os.nice(10)  # Lower priority
                except BaseException:
                    pass  # Not critical if it fails

            db = self.db_manager.get_long_running_connection()

            # Update CPID cache
            self.update_cpid_cache(db)

            if self.mode == "FULL_CATCHUP":
                self._run_full_catchup(db)
            else:
                # Real-time mode doesn't need special catchup
                logger.info("In REALTIME mode - no bulk catchup needed")

        except Exception as e:
            logger.error(f"Error in sales history catchup: {e}")
            self.progress["errors"] = self.progress["errors"] + 1
        finally:
            # Flush any remaining buffered data
            if self.catchup_buffer:
                logger.info(f"Flushing final catchup buffer with {len(self.catchup_buffer)} sales")
                logger.debug(f"Final buffer contains blocks {self.last_buffer_flush_block} to latest")
                try:
                    self._flush_catchup_buffer(db if "db" in locals() else None)
                except Exception as e:
                    logger.error(f"Error flushing final buffer: {e}")

            if "db" in locals():
                db.close()
            self.catchup_running = False
            logger.info(f"Sales history catchup completed: {self.progress['total_sales']} sales processed")

    def _run_full_catchup(self, db):
        """
        Run Full Catchup Mode - fetch all dispenses once and filter locally.
        This replaces the old CPID-based approach with a much more efficient method.
        """
        logger.info("Starting Full Catchup Mode")

        # Get highest block we've already processed
        with db.cursor() as cursor:
            cursor.execute("SELECT MAX(block_index) FROM stamp_sales_history")
            result = cursor.fetchone()
            highest_processed_block = result[0] if result and result[0] else 0

        logger.info(f"Highest processed block in sales history: {highest_processed_block}")

        # Determine if we need to process from genesis or just continue from where we left off
        # Since sales history is a complete log, we should only process from genesis if:
        # 1. The table is empty (highest_processed_block == 0)
        # 2. We're explicitly forcing a rebuild via environment variable

        # Check for environment variable to force full rebuild
        if os.getenv("FORCE_SALES_HISTORY_REBUILD", "").lower() == "true":
            logger.warning("FORCE_SALES_HISTORY_REBUILD=true - will process ALL dispenses from genesis")
            process_from_block = 0  # Process everything
        elif highest_processed_block == 0:
            logger.info("No sales history found - will process from genesis")
            process_from_block = 0  # Start from beginning
        else:
            # Continue from where we left off
            logger.info(f"Sales history exists up to block {highest_processed_block} - will continue from there")
            process_from_block = highest_processed_block

        # Fetch all dispenses from API
        if not self._fetch_all_dispenses():
            logger.error("Failed to fetch dispenses, aborting catchup")
            return

        # Process dispenses starting from our determined block
        logger.info(f"Processing dispenses after block {process_from_block}")
        processed = self._process_cached_dispenses(after_block=process_from_block)

        self.progress["total_sales"] = processed

        logger.info(f"Initial processing complete: {processed} dispenses stored")

        # Mark where we started checking for new CPIDs
        self.dispense_cache["last_cpid_check_block"] = process_from_block

    def check_and_process_new_cpids(self, current_block: int):
        """
        Check for new CPIDs since last check and process their cached dispenses.
        Called periodically during main loop processing in Full Catchup Mode.

        Args:
            current_block: Current block being processed by main loop
        """
        if self.mode != "FULL_CATCHUP" or not self.dispense_cache["data"]:
            return

        # Only check every 100 blocks
        if current_block - self.dispense_cache["last_cpid_check_block"] < 100:
            return

        logger.info(f"Checking for new CPIDs at block {current_block}")

        # Get current CPID set
        old_cpids = self.cpid_cache.copy()

        # Update cache to get any new CPIDs
        self.update_cpid_cache()

        # Find new CPIDs
        new_cpids = self.cpid_cache - old_cpids

        if new_cpids:
            logger.info(f"Found {len(new_cpids)} new CPIDs to process")
            logger.debug(f"New CPIDs: {list(new_cpids)[:5]}..." if len(new_cpids) > 5 else f"New CPIDs: {list(new_cpids)}")

            # Process cached dispenses for new CPIDs only
            processed = self._process_cached_dispenses(
                cpids=new_cpids, after_block=self.dispense_cache["last_cpid_check_block"]
            )

            self.progress["total_sales"] += processed
            logger.info(f"Processed {processed} dispenses for new CPIDs")

        # Update last check block
        self.dispense_cache["last_cpid_check_block"] = current_block

        # Check if we should switch to real-time mode
        if current_block >= self.dispense_cache["highest_block"]:
            # Get current tip
            db = self.db_manager.connect()
            try:
                with db.cursor() as cursor:
                    cursor.execute("SELECT MAX(block_index) FROM blocks")
                    result = cursor.fetchone()
                    current_tip = result[0] if result and result[0] else 0
            finally:
                db.close()

            blocks_to_tip = current_tip - current_block

            if blocks_to_tip <= self.mode_threshold:
                logger.info(
                    f"Reached cached highest block {self.dispense_cache['highest_block']} "
                    f"and within {blocks_to_tip} blocks of tip - switching to REALTIME mode"
                )
                previous_mode = self.mode
                self.mode = "REALTIME"
                # Clear cache to free memory
                cache_size = len(self.dispense_cache["data"])
                self.dispense_cache["data"] = []
                logger.debug(
                    f"Mode switch: {previous_mode} -> {self.mode}, " f"cleared {cache_size} cached dispenses to free memory"
                )

    def _get_earliest_processed_block(self, db=None) -> Optional[int]:
        """Get the earliest block we've processed sales for."""
        if db is None:
            db = self.db_manager.connect()
            close_db = True
        else:
            close_db = False

        try:
            with db.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT MIN(block_index)
                    FROM stamp_sales_history
                """
                )
                result = cursor.fetchone()
                return result[0] if result and result[0] else None

        finally:
            if close_db:
                db.close()

    def _has_historical_data(self, db=None) -> bool:
        """
        Check if we have any historical sales data.
        Used to determine if catchup has been run.
        """
        if db is None:
            db = self.db_manager.connect()
            close_db = True
        else:
            close_db = False

        try:
            with db.cursor() as cursor:
                # Check if we have sales data from near the genesis block
                cursor.execute(
                    """
                    SELECT COUNT(*)
                    FROM stamp_sales_history
                    WHERE block_index < %s
                    LIMIT 1
                """,
                    (STAMPS_GENESIS_BLOCK + 1000,),
                )  # Check first 1000 blocks after genesis

                count = cursor.fetchone()[0]
                return count > 0

        finally:
            if close_db:
                db.close()

    def _store_dispenser_sales(self, dispenses: List[Dict], db=None, use_buffer=False):
        """
        Store dispenser sales in the sales history table.

        Args:
            dispenses: List of dispense records
            db: Optional database connection
            use_buffer: If True and in catchup mode, buffer writes for batch processing
        """
        if not dispenses:
            return

        # If we're in catchup mode and buffering is requested, accumulate data
        if use_buffer and self.catchup_running:
            with self.catchup_buffer_lock:
                for dispense in dispenses:
                    # Extract data from verbose dispense response
                    tx_hash = dispense.get("tx_hash")
                    block_index = dispense.get("block_index")
                    block_time = dispense.get("block_time")
                    cpid = dispense.get("asset")

                    # source = buyer (who received assets)
                    # destination = dispenser address
                    buyer_address = dispense.get("source")
                    seller_address = dispense.get("destination")

                    quantity = int(dispense.get("dispense_quantity", 0))
                    btc_amount = int(dispense.get("btc_amount", 0))
                    dispenser_tx = dispense.get("dispenser_tx_hash")

                    # Calculate unit price from dispenser data
                    unit_price_sats = 0
                    if "dispenser" in dispense and isinstance(dispense["dispenser"], dict):
                        satoshirate = int(dispense["dispenser"].get("satoshirate", 0))
                        unit_price_sats = satoshirate
                    elif quantity > 0:
                        # Fallback: calculate from total/quantity
                        unit_price_sats = btc_amount // quantity

                    self.catchup_buffer.append(
                        (
                            tx_hash,
                            block_index,
                            block_time,
                            cpid,
                            "dispenser",
                            buyer_address,
                            seller_address,
                            quantity,
                            btc_amount,
                            unit_price_sats,
                            dispenser_tx,
                            None,  # swap_contract_id
                            "counterparty",  # platform
                            None,  # external_id
                            "counterparty",  # data_source
                            None,  # notes
                        )
                    )

                # Check if we should flush based on block interval
                if dispenses:
                    max_block = max(d.get("block_index", 0) for d in dispenses)
                    if self.last_buffer_flush_block == 0:
                        self.last_buffer_flush_block = max_block
                    elif max_block - self.last_buffer_flush_block >= self.buffer_flush_interval:
                        logger.debug(
                            f"Buffer flush triggered: {len(self.catchup_buffer)} items, "
                            f"blocks {self.last_buffer_flush_block} -> {max_block}"
                        )
                        self._flush_catchup_buffer(db)
                        self.last_buffer_flush_block = max_block
            return

        logger.info(f"Storing {len(dispenses)} dispenser sales to database")

        if db is None:
            db = self.db_manager.connect()
            close_db = True
        else:
            close_db = False

        try:
            with db.cursor() as cursor:
                # Prepare batch insert data
                insert_data = []

                for dispense in dispenses:
                    # Extract data from verbose dispense response
                    tx_hash = dispense.get("tx_hash")
                    block_index = dispense.get("block_index")
                    block_time = dispense.get("block_time")
                    cpid = dispense.get("asset")

                    # source = buyer (who received assets)
                    # destination = dispenser address
                    buyer_address = dispense.get("source")
                    seller_address = dispense.get("destination")

                    quantity = int(dispense.get("dispense_quantity", 0))
                    btc_amount = int(dispense.get("btc_amount", 0))
                    dispenser_tx = dispense.get("dispenser_tx_hash")

                    # Calculate unit price from dispenser data
                    unit_price_sats = 0
                    if "dispenser" in dispense and isinstance(dispense["dispenser"], dict):
                        satoshirate = int(dispense["dispenser"].get("satoshirate", 0))
                        unit_price_sats = satoshirate
                    elif quantity > 0:
                        # Fallback: calculate from total/quantity
                        unit_price_sats = btc_amount // quantity

                    insert_data.append(
                        (
                            tx_hash,
                            block_index,
                            block_time,
                            cpid,
                            "dispenser",
                            buyer_address,
                            seller_address,
                            quantity,
                            btc_amount,
                            unit_price_sats,
                            dispenser_tx,
                            None,  # swap_contract_id
                            "counterparty",  # platform
                            None,  # external_id
                            "counterparty",  # data_source
                            None,  # notes
                        )
                    )

                # Batch insert with ON DUPLICATE KEY UPDATE
                # Process in smaller batches to avoid long-running transactions
                if insert_data:
                    total_inserted = 0
                    for i in range(0, len(insert_data), INSERT_BATCH_SIZE):
                        batch = insert_data[i : i + INSERT_BATCH_SIZE]
                        cursor.executemany(
                            """
                            INSERT INTO stamp_sales_history
                            (tx_hash, block_index, block_time, cpid, sale_type,
                             buyer_address, seller_address, quantity, btc_amount,
                             unit_price_sats, dispenser_tx_hash, swap_contract_id,
                             platform, external_id, data_source, notes)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON DUPLICATE KEY UPDATE
                            btc_amount = VALUES(btc_amount),
                            unit_price_sats = VALUES(unit_price_sats),
                            processed_at = CURRENT_TIMESTAMP
                        """,
                            batch,
                        )
                        db.commit()
                        total_inserted += len(batch)

                        # Small delay between batches to reduce contention
                        if i + INSERT_BATCH_SIZE < len(insert_data):
                            time.sleep(0.1)

                    logger.info(
                        f"Successfully stored {total_inserted} dispenser sales in {(len(insert_data) + INSERT_BATCH_SIZE - 1) // INSERT_BATCH_SIZE} batches"
                    )
                    logger.debug(f"Stored sales for CPIDs: {set(d[3] for d in insert_data)}")

        except Exception as e:
            logger.error(f"Error storing dispenser sales: {e}")
            if "db" in locals():
                db.rollback()
        finally:
            if close_db:
                db.close()

    def get_recent_sales(self, limit: int = 100, cpid: Optional[str] = None) -> List[Dict]:
        """
        Get recent sales from the history table.

        Args:
            limit: Maximum number of sales to return
            cpid: Optional CPID to filter by

        Returns:
            List of recent sales
        """
        db = self.db_manager.connect()
        try:
            with db.cursor() as cursor:
                if cpid:
                    query = """
                        SELECT ssh.*, s.stamp, s.stamp_url, s.stamp_mimetype
                        FROM stamp_sales_history ssh
                        JOIN StampTableV4 s ON ssh.cpid = s.cpid
                        WHERE ssh.cpid = %s
                        ORDER BY ssh.block_time DESC
                        LIMIT %s
                    """
                    cursor.execute(query, (cpid, limit))
                else:
                    query = """
                        SELECT ssh.*, s.stamp, s.stamp_url, s.stamp_mimetype
                        FROM stamp_sales_history ssh
                        JOIN StampTableV4 s ON ssh.cpid = s.cpid
                        ORDER BY ssh.block_time DESC
                        LIMIT %s
                    """
                    cursor.execute(query, (limit,))

                columns = [desc[0] for desc in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]

        finally:
            db.close()

    def calculate_volume_from_history(self, cpid: str, hours: int = 24) -> Dict[str, float]:
        """
        Calculate volume metrics from sales history.

        Args:
            cpid: The CPID to calculate volume for
            hours: Number of hours to look back

        Returns:
            Dictionary with volume metrics
        """
        db = self.db_manager.connect()
        try:
            with db.cursor() as cursor:
                query = """
                    SELECT
                        SUM(btc_amount) as total_volume_sats,
                        COUNT(*) as trade_count,
                        MAX(unit_price_sats) as high_price,
                        MIN(unit_price_sats) as low_price,
                        MAX(block_time) as last_sale_time
                    FROM stamp_sales_history
                    WHERE cpid = %s
                    AND block_time > UNIX_TIMESTAMP() - (%s * 3600)
                """

                cursor.execute(query, (cpid, hours))
                result = cursor.fetchone()

                if result:
                    return {
                        "volume_btc": float(result[0] or 0) / 100000000,
                        "trade_count": result[1] or 0,
                        "high_sats": result[2] or 0,
                        "low_sats": result[3] or 0,
                        "last_sale_time": result[4],
                    }
                else:
                    return {"volume_btc": 0.0, "trade_count": 0, "high_sats": 0, "low_sats": 0, "last_sale_time": 0}

        finally:
            db.close()

    def _flush_catchup_buffer(self, db=None):
        """Flush the catchup buffer to database in batches."""
        if not self.catchup_buffer:
            return

        with self.catchup_buffer_lock:
            if not self.catchup_buffer:
                return

            logger.info(f"Flushing catchup buffer with {len(self.catchup_buffer)} sales to database")

            if db is None:
                db = self.db_manager.connect()
                close_db = True
            else:
                close_db = False

            try:
                with db.cursor() as cursor:
                    # Process in batches to avoid long transactions
                    for i in range(0, len(self.catchup_buffer), INSERT_BATCH_SIZE):
                        batch = self.catchup_buffer[i : i + INSERT_BATCH_SIZE]

                        cursor.executemany(
                            """
                            INSERT INTO stamp_sales_history
                            (tx_hash, block_index, block_time, cpid, sale_type,
                             buyer_address, seller_address, quantity, btc_amount,
                             unit_price_sats, dispenser_tx_hash, swap_contract_id,
                             platform, external_id, data_source, notes)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON DUPLICATE KEY UPDATE
                            btc_amount = VALUES(btc_amount),
                            unit_price_sats = VALUES(unit_price_sats),
                            processed_at = CURRENT_TIMESTAMP
                        """,
                            batch,
                        )
                        db.commit()

                        # Small delay between batches
                        if i + INSERT_BATCH_SIZE < len(self.catchup_buffer):
                            time.sleep(0.1)

                    logger.info(
                        f"Successfully flushed {len(self.catchup_buffer)} sales in {(len(self.catchup_buffer) + INSERT_BATCH_SIZE - 1) // INSERT_BATCH_SIZE} batches"
                    )
                    logger.debug(f"Buffer memory freed: ~{len(str(self.catchup_buffer)) / 1024:.2f} KB")

                    # Clear the buffer
                    self.catchup_buffer.clear()

            except Exception as e:
                logger.error(f"Error flushing catchup buffer: {e}")
                if db:
                    db.rollback()
                raise
            finally:
                if close_db:
                    db.close()


# Global instance for easy access
sales_history_processor = SalesHistoryProcessor()
