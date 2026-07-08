"""
Dispense Processor for Bitcoin Stamps

This module handles fetching and processing dispense data using two modes:
1. Catchup mode: Fetches historical dispenses by CPID (for backfilling)
2. Real-time mode: Fetches dispenses by block (for new blocks at tip)

Integrates with the rollback system to ensure dispenses are purged during reorgs.
"""

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Set

from index_core.database_manager import DatabaseManager
from index_core.fetch_utils import RateLimiter, fetch_xcp

logger = logging.getLogger(__name__)

# Constants
STAMPS_GENESIS_BLOCK = 779652
CATCHUP_BATCH_SIZE = 100  # Number of CPIDs to process per batch
MAX_WORKERS = 5  # Concurrent workers for catchup mode
RATE_LIMIT = 2.0  # Requests per second to Counterparty API

# Rate limiter for API calls
rate_limiter = RateLimiter(calls_per_second=RATE_LIMIT)


class DispenseProcessor:
    """Processes dispense data for stamps market data."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db_manager = db_manager or DatabaseManager()
        self.cpid_cache: Set[str] = set()
        self.last_cache_update = 0
        self.cache_update_interval = 300  # 5 minutes
        self._lock = threading.Lock()
        self.catchup_running = False
        self.catchup_executor: Optional[ThreadPoolExecutor] = None

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
                cursor.execute("""
                    SELECT DISTINCT cpid
                    FROM StampTableV4
                    WHERE ident IN ('STAMP', 'SRC-721')
                """)

                cpids = {row[0] for row in cursor.fetchall()}

                with self._lock:
                    self.cpid_cache = cpids
                    self.last_cache_update = current_time

                logger.info(f"Updated CPID cache with {len(cpids)} stamps")

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

        # Ensure cache is updated
        self.update_cpid_cache(db)

        # Rate limiting
        rate_limiter.acquire()

        try:
            # Fetch all dispenses in the block with verbose data.
            # NB: no show_unconfirmed here — CP v11.2 strict-validates params and the
            # dispenses endpoints reject it (they read the confirmed-only dispenses table).
            response = fetch_xcp(f"/blocks/{block_index}/dispenses", {"verbose": "true"})

            if not response or "result" not in response:
                return 0

            dispenses = response["result"]

            # Filter for stamp CPIDs
            stamp_dispenses = []
            with self._lock:
                for dispense in dispenses:
                    asset = dispense.get("asset")
                    if asset in self.cpid_cache:
                        stamp_dispenses.append(dispense)

            if stamp_dispenses:
                logger.info(f"Found {len(stamp_dispenses)} stamp dispenses in block {block_index}")
                self._store_dispenses(stamp_dispenses, db)

            return len(stamp_dispenses)

        except Exception as e:
            logger.error(f"Error processing block {block_index} dispenses: {e}")
            return 0

    def start_catchup_mode(self, start_block: Optional[int] = None, end_block: Optional[int] = None):
        """
        Start catchup mode to backfill historical dispenses.
        Runs asynchronously in the background.

        Args:
            start_block: Starting block (default: STAMPS_GENESIS_BLOCK)
            end_block: Ending block (default: current tip)
        """
        if self.catchup_running:
            logger.warning("Catchup mode already running")
            return

        self.catchup_running = True
        self.catchup_executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

        # Start the catchup in a background thread
        threading.Thread(target=self._run_catchup, args=(start_block, end_block), daemon=True).start()

        logger.info("Started dispense catchup mode in background")

    def stop_catchup_mode(self):
        """Stop the catchup mode if running."""
        if not self.catchup_running:
            return

        logger.info("Stopping dispense catchup mode...")
        self.catchup_running = False

        if self.catchup_executor:
            self.catchup_executor.shutdown(wait=True)
            self.catchup_executor = None

        logger.info("Dispense catchup mode stopped")

    def _run_catchup(self, start_block: Optional[int], end_block: Optional[int]):
        """Run the catchup process (internal method)."""
        try:
            db = self.db_manager.get_long_running_connection()

            # Update CPID cache
            self.update_cpid_cache(db)

            # Get CPIDs that need processing
            cpids_to_process = self._get_cpids_needing_catchup(db, start_block, end_block)

            if not cpids_to_process:
                logger.info("No CPIDs need dispense catchup")
                return

            logger.info(f"Starting dispense catchup for {len(cpids_to_process)} CPIDs")

            # Process in batches
            for i in range(0, len(cpids_to_process), CATCHUP_BATCH_SIZE):
                if not self.catchup_running:
                    break

                batch = cpids_to_process[i : i + CATCHUP_BATCH_SIZE]
                self._process_cpid_batch(batch, db)

                logger.info(
                    f"Catchup progress: {min(i + CATCHUP_BATCH_SIZE, len(cpids_to_process))}/{len(cpids_to_process)} CPIDs"
                )

        except Exception as e:
            logger.error(f"Error in dispense catchup: {e}")
        finally:
            if "db" in locals():
                db.close()
            self.catchup_running = False
            logger.info("Dispense catchup completed")

    def _get_cpids_needing_catchup(self, db, start_block: Optional[int], end_block: Optional[int]) -> List[str]:
        """Get list of CPIDs that need dispense catchup."""
        with db.cursor() as cursor:
            # Get CPIDs that don't have complete dispense data
            query = """
                SELECT DISTINCT s.cpid
                FROM StampTableV4 s
                LEFT JOIN (
                    SELECT cpid, MAX(block_index) as last_dispense_block
                    FROM stamp_dispenses
                    GROUP BY cpid
                ) d ON s.cpid = d.cpid
                WHERE s.ident IN ('STAMP', 'SRC-721')
                AND s.block_index >= %s
                AND (d.last_dispense_block IS NULL OR d.last_dispense_block < %s)
                ORDER BY s.block_index
            """

            cursor.execute(query, (start_block or STAMPS_GENESIS_BLOCK, end_block or 999999999))

            return [row[0] for row in cursor.fetchall()]

    def _process_cpid_batch(self, cpids: List[str], db):
        """Process a batch of CPIDs in parallel."""
        futures = []

        if not self.catchup_executor:
            return

        with self.catchup_executor as executor:
            for cpid in cpids:
                if not self.catchup_running:
                    break

                future = executor.submit(self._process_single_cpid, cpid)
                futures.append((cpid, future))

            # Wait for completion
            for cpid, future in futures:
                try:
                    dispense_count = future.result(timeout=60)
                    if dispense_count > 0:
                        logger.debug(f"Processed {dispense_count} dispenses for {cpid}")
                except Exception as e:
                    logger.error(f"Error processing CPID {cpid}: {e}")

    def _process_single_cpid(self, cpid: str) -> int:
        """Process all dispenses for a single CPID."""
        total_dispenses = 0

        try:
            # Step 1: Get all dispensers for this CPID
            rate_limiter.acquire()
            response = fetch_xcp(f"/assets/{cpid}/dispensers", {})

            if not response or "result" not in response:
                return 0

            dispensers = response["result"]

            # Step 2: For each dispenser, get its dispenses
            for dispenser in dispensers:
                source = dispenser.get("source")
                if not source:
                    continue

                # Get dispenses for this dispenser/asset combination
                rate_limiter.acquire()
                dispense_response = fetch_xcp(f"/addresses/{source}/dispenses", {"asset": cpid, "verbose": "true"})

                if dispense_response and "result" in dispense_response:
                    dispenses = dispense_response["result"]
                    if dispenses:
                        # Filter for blocks after genesis
                        valid_dispenses = [d for d in dispenses if d.get("block_index", 0) >= STAMPS_GENESIS_BLOCK]

                        if valid_dispenses:
                            self._store_dispenses(valid_dispenses)
                            total_dispenses += len(valid_dispenses)

            return total_dispenses

        except Exception as e:
            logger.error(f"Error processing CPID {cpid}: {e}")
            return 0

    def _store_dispenses(self, dispenses: List[Dict], db=None):
        """Store dispense data in the database."""
        if not dispenses:
            return

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
                    # Extract data with verbose response structure
                    tx_hash = dispense.get("tx_hash")
                    block_index = dispense.get("block_index")
                    cpid = dispense.get("asset")
                    source = dispense.get("source")  # Buyer
                    destination = dispense.get("destination")  # Dispenser address
                    quantity = dispense.get("dispense_quantity", 0)
                    btc_amount = dispense.get("btc_amount", 0)
                    dispenser_tx = dispense.get("dispenser_tx_hash")
                    block_time = dispense.get("block_time")

                    # Get satoshirate from nested dispenser data if available
                    satoshirate = 0
                    if "dispenser" in dispense and isinstance(dispense["dispenser"], dict):
                        satoshirate = dispense["dispenser"].get("satoshirate", 0)

                    insert_data.append(
                        (
                            tx_hash,
                            block_index,
                            cpid,
                            source,
                            destination,
                            quantity,
                            btc_amount,
                            satoshirate,
                            dispenser_tx,
                            block_time,
                        )
                    )

                # Batch insert with ON DUPLICATE KEY UPDATE
                if insert_data:
                    cursor.executemany(
                        """
                        INSERT INTO stamp_dispenses
                        (tx_hash, block_index, cpid, source_address, destination_address,
                         dispense_quantity, btc_amount, satoshirate, dispenser_tx_hash, block_time)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        AS new_row ON DUPLICATE KEY UPDATE
                        btc_amount = new_row.btc_amount,
                        satoshirate = new_row.satoshirate
                    """,
                        insert_data,
                    )

                    db.commit()
                    logger.debug(f"Stored {len(insert_data)} dispenses")

        except Exception as e:
            logger.error(f"Error storing dispenses: {e}")
            if "db" in locals():
                db.rollback()
        finally:
            if close_db:
                db.close()


# Global instance for easy access
dispense_processor = DispenseProcessor()
