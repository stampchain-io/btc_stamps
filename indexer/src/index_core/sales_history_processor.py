"""
Sales History Processor - handles all stamp sales tracking
"""

import logging
import os
import queue
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from config import CP_STAMP_GENESIS_BLOCK
from index_core.backend import Backend
from index_core.database_manager import DatabaseManager

# Configure logging
logger = logging.getLogger(__name__)

# Constants for chunk processing
CHUNK_SIZE = int(os.environ.get("SALES_HISTORY_CHUNK_SIZE", "25"))  # Commit chunk size
BUFFER_SIZE = int(os.environ.get("SALES_HISTORY_BUFFER_SIZE", "50"))  # Buffer flush threshold
BATCH_SIZE = int(os.environ.get("SALES_HISTORY_BATCH_SIZE", "50"))  # Database batch size
PAGE_SIZE = int(os.environ.get("SALES_HISTORY_PAGE_SIZE", "500"))  # API page size
PAGES_PER_BATCH = int(os.environ.get("SALES_HISTORY_PAGES_PER_BATCH", "5"))  # Pages before commit
MAX_WORKERS = int(os.environ.get("SALES_HISTORY_MAX_WORKERS", "3"))  # Concurrent workers
MAX_PAGES = 30  # Stop after 30 pages for memory management
RATE_LIMIT = float(os.environ.get("SALES_HISTORY_RATE_LIMIT", "1.0"))  # API requests per second

# Enable/disable catchup process
ENABLE_SALES_HISTORY_CATCHUP = os.environ.get("ENABLE_SALES_HISTORY_CATCHUP", "false").lower() == "true"

# Force rebuild from genesis
FORCE_SALES_HISTORY_REBUILD = os.environ.get("FORCE_SALES_HISTORY_REBUILD", "false").lower() == "true"


class SalesHistoryProcessor:
    """Unified processor for all stamp sales types."""

    def __init__(self):
        self.db_manager = DatabaseManager()
        self.backend = Backend()
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
            "api_requests": 0,
            "db_inserts": 0,
            "catchup_start_time": 0,
        }
        self.mode = "REALTIME"  # REALTIME or FULL_CATCHUP

    def update_cpid_cache(self, db=None):
        """Update the CPID cache from the database."""
        current_time = time.time()
        if current_time - self.last_cache_update < self.cache_update_interval:
            return

        close_db = False
        if db is None:
            db = self.db_manager.connect()
            close_db = True

        try:
            with db.cursor() as cursor:
                cursor.execute("SELECT DISTINCT cpid FROM StampTableV4 WHERE stamp IS NOT NULL")
                self.cpid_cache = {row[0] for row in cursor.fetchall()}
                self.last_cache_update = current_time
                logger.debug(f"Updated CPID cache with {len(self.cpid_cache)} entries")
        finally:
            if close_db:
                db.close()

    def get_checkpoint(self, checkpoint_type: str) -> int:
        """Get a checkpoint value from the database."""
        db = self.db_manager.connect()
        try:
            with db.cursor() as cursor:
                cursor.execute(
                    "SELECT checkpoint_value FROM sales_history_checkpoints WHERE checkpoint_type = %s", (checkpoint_type,)
                )
                result = cursor.fetchone()
                return int(result[0]) if result else 0
        finally:
            db.close()

    def update_checkpoint(self, checkpoint_type: str, value: int, db=None):
        """Update a checkpoint value in the database."""
        close_db = False
        if db is None:
            db = self.db_manager.connect()
            close_db = True

        try:
            with db.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO sales_history_checkpoints (checkpoint_type, checkpoint_value, last_updated)
                    VALUES (%s, %s, NOW())
                    ON DUPLICATE KEY UPDATE checkpoint_value = VALUES(checkpoint_value), last_updated = NOW()
                """,
                    (checkpoint_type, value),
                )
                db.commit()
        finally:
            if close_db:
                db.close()

    def process_block_dispenses(self, block_index: int, db=None) -> int:
        """Process dispenses from a specific block in real-time by fetching from Counterparty API."""
        if self.catchup_running:
            # Skip real-time processing during catchup
            return 0

        close_db = False
        if db is None:
            db = self.db_manager.connect()
            close_db = True

        dispense_count = 0
        try:
            # Fetch dispenses from Counterparty API
            from index_core.fetch_utils import fetch_xcp

            response = fetch_xcp(f"/blocks/{block_index}/dispenses", {"verbose": "true", "show_unconfirmed": "false"})

            if not response or "result" not in response:
                logger.debug(f"No dispenses found in block {block_index}")
                return 0

            dispenses = response["result"]

            with db.cursor() as cursor:
                for dispense in dispenses:
                    # Extract dispense data from API response
                    tx_hash = dispense.get("tx_hash")
                    asset = dispense.get("asset")
                    source = dispense.get("source")  # This is the buyer
                    destination = dispense.get("destination")  # This is the dispenser address
                    quantity = dispense.get("dispense_quantity", 0)
                    btc_amount = dispense.get("btc_amount", 0)
                    dispenser_tx_hash = dispense.get("dispenser_tx_hash")
                    block_time = dispense.get("block_time")

                    # Check if this asset is a stamp
                    cursor.execute("SELECT cpid, stamp FROM StampTableV4 WHERE cpid = %s", (asset,))
                    stamp_data = cursor.fetchone()

                    # Only process if it's a stamp
                    if stamp_data:
                        cpid, stamp_num = stamp_data

                        # Get satoshirate from dispenser data if available
                        satoshirate = 0
                        if "dispenser" in dispense and isinstance(dispense["dispenser"], dict):
                            satoshirate = dispense["dispenser"].get("satoshirate", 0)
                        elif btc_amount and quantity:
                            # Calculate satoshirate from btc_amount if not provided
                            satoshirate = btc_amount // quantity if quantity > 0 else 0

                        # Store btc_amount as raw satoshis (BIGINT column)
                        btc_amount_sats = btc_amount if btc_amount else 0

                        # Insert into sales history
                        self._insert_sale(
                            db,
                            {
                                "tx_hash": tx_hash,
                                "block_index": block_index,
                                "block_time": block_time,
                                "cpid": cpid,
                                "buyer_address": source,  # source is the buyer
                                "seller_address": destination,  # destination is the dispenser
                                "btc_amount": btc_amount_sats,
                                "sale_type": "dispenser",  # lowercase to match ENUM
                                "dispenser_tx_hash": dispenser_tx_hash,
                                "quantity": quantity,
                                "unit_price_sats": satoshirate,
                            },
                        )
                        dispense_count += 1

            db.commit()

            if dispense_count > 0:
                logger.debug(f"Stored {dispense_count} dispenser sales in block {block_index}")

        except Exception as e:
            logger.error(f"Error processing block {block_index} dispenses: {e}")
            db.rollback()
        finally:
            if close_db:
                db.close()

        return dispense_count

    def determine_processing_mode(self) -> str:
        """Determine if we should run in FULL_CATCHUP or REALTIME mode."""
        if FORCE_SALES_HISTORY_REBUILD:
            logger.info("FORCE_SALES_HISTORY_REBUILD is set - using FULL_CATCHUP mode")
            return "FULL_CATCHUP"

        db = self.db_manager.connect()
        try:
            # Get our last processed checkpoint
            last_checkpoint = self.get_checkpoint("last_catchup_completion")

            # Get the current block
            current_block = self.backend.getblockcount()

            # If we've never run catchup or are more than 200 blocks behind, do full catchup
            if last_checkpoint == 0 or (current_block - last_checkpoint) > 200:
                logger.debug(f"Need FULL_CATCHUP mode (last: {last_checkpoint}, current: {current_block})")
                return "FULL_CATCHUP"
            else:
                logger.debug(f"Using REALTIME mode (last: {last_checkpoint}, current: {current_block})")
                return "REALTIME"

        finally:
            db.close()

    def start_catchup_mode(self, mode: Optional[str] = None):
        """Start the catchup mode in a background thread.

        Args:
            mode: Optional mode to use ("FULL_CATCHUP" or "REALTIME").
                  If not provided, will determine automatically.
                  Passing the mode avoids race conditions from re-determining.
        """
        # Check if we're in a testing environment
        if os.environ.get("TESTING") == "1":
            logger.debug("Skipping sales history catchup in test environment")
            return

        if not ENABLE_SALES_HISTORY_CATCHUP:
            logger.debug("Sales history catchup is disabled")
            return

        if self.catchup_running:
            logger.warning("Catchup mode already running")
            return

        self.catchup_running = True
        self.catchup_executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
        self.progress["catchup_start_time"] = int(datetime.now().timestamp())

        # Use provided mode or determine it (but prefer provided to avoid race conditions)
        if mode is not None:
            self.mode = mode
            logger.debug(f"Using provided mode: {self.mode}")
        else:
            self.mode = self.determine_processing_mode()

        logger.debug(f"Starting sales history catchup in {self.mode} mode")

        # Start the catchup in a background thread
        threading.Thread(target=self._run_catchup, daemon=True).start()

        logger.debug("Started sales history catchup mode in background")

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

    def _insert_sale(self, db, sale_data: Dict[str, Any]):
        """Insert a single sale into the database."""
        try:
            with db.cursor() as cursor:
                # Check if already exists
                cursor.execute("SELECT id FROM stamp_sales_history WHERE tx_hash = %s", (sale_data["tx_hash"],))
                if cursor.fetchone():
                    return  # Already processed

                cursor.execute(
                    """
                    INSERT INTO stamp_sales_history
                    (tx_hash, block_index, block_time, cpid, buyer_address,
                     seller_address, btc_amount, sale_type, quantity, unit_price_sats,
                     dispenser_tx_hash, processed_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                """,
                    (
                        sale_data["tx_hash"],
                        sale_data["block_index"],
                        sale_data["block_time"],
                        sale_data["cpid"],
                        sale_data["buyer_address"],
                        sale_data["seller_address"],
                        sale_data["btc_amount"],
                        sale_data["sale_type"],
                        sale_data.get("quantity", 1),
                        sale_data.get("unit_price_sats", 0),
                        sale_data.get("dispenser_tx_hash"),
                    ),
                )
                self.progress["db_inserts"] += 1

        except Exception as e:
            logger.error(f"Error inserting sale {sale_data['tx_hash']}: {e}")
            raise

    def _process_sale_batch(self, sales: List[Dict[str, Any]], db):
        """Process a batch of sales."""
        if not sales:
            return

        try:
            # Build batch insert
            values = []
            for sale in sales:
                values.append(
                    (
                        sale["tx_hash"],
                        sale["block_index"],
                        sale["block_time"],
                        sale["cpid"],
                        sale["buyer_address"],
                        sale["seller_address"],
                        sale["btc_amount"],
                        sale["sale_type"],
                        sale.get("quantity", 1),
                        sale.get("unit_price_sats", 0),
                        sale.get("dispenser_tx_hash"),
                    )
                )

            with db.cursor() as cursor:
                # Use INSERT IGNORE to skip duplicates
                cursor.executemany(
                    """
                    INSERT IGNORE INTO stamp_sales_history
                    (tx_hash, block_index, block_time, cpid, buyer_address,
                     seller_address, btc_amount, sale_type, quantity, unit_price_sats,
                     dispenser_tx_hash, processed_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                """,
                    values,
                )

                inserted = cursor.rowcount
                self.progress["db_inserts"] += inserted
                self.progress["total_sales"] += inserted

                if inserted > 0:
                    logger.debug(f"Inserted {inserted} sales")

        except Exception as e:
            logger.error(f"Error processing sale batch: {e}")
            raise

    def _fetch_all_dispenses(self) -> bool:
        """Fetch all dispenses from the API and store them."""
        logger.debug("Starting bulk dispense catchup from Counterparty API...")

        try:
            # Get the block range to process
            last_block = self.get_checkpoint("dispenser_block")
            current_block = self.backend.getblockcount()

            # Start from stamps genesis if checkpoint is 0 (never processed)
            # Dispensers didn't exist before stamps anyway
            if last_block == 0:
                last_block = CP_STAMP_GENESIS_BLOCK - 1
                logger.debug(f"Starting from stamps genesis block {CP_STAMP_GENESIS_BLOCK} instead of block 0")

            if last_block >= current_block:
                logger.debug(f"Dispenses already up to date at block {last_block}")
                return True

            logger.debug(f"Processing dispenses from block {last_block + 1} to {current_block}")

            # Check if the range is too large (optional safety check)
            blocks_to_process = current_block - last_block
            if blocks_to_process > 100000:  # More than 100k blocks
                logger.warning(f"Would need to process {blocks_to_process:,} blocks for dispenser catchup")
                logger.warning(
                    "This will take a very long time. Consider manually setting the checkpoint to a more recent block."
                )
                logger.warning("Proceeding anyway... (press Ctrl+C to cancel)")

            # Get a database connection for bulk processing
            db = self.db_manager.connect()
            try:
                # Process blocks in chunks
                blocks_processed = 0
                dispense_total = 0

                for block_idx in range(last_block + 1, current_block + 1):
                    if not self.catchup_running:
                        logger.debug("Catchup stopped")
                        break

                    # Use the existing process_block_dispenses method which fetches from CP API
                    dispense_count = self.process_block_dispenses(block_idx, db)
                    blocks_processed += 1
                    dispense_total += dispense_count

                    # Update checkpoint every 100 blocks
                    if blocks_processed % 100 == 0:
                        self.update_checkpoint("dispenser_block", block_idx, db)
                        logger.debug(
                            f"Processed {blocks_processed} blocks, {dispense_total} dispenses up to block {block_idx}"
                        )

                    # Rate limiting
                    if dispense_count > 0:
                        time.sleep(1.0 / RATE_LIMIT)

                # Final checkpoint update
                self.update_checkpoint("dispenser_block", min(current_block, block_idx), db)
                logger.debug(f"✅ Completed dispense catchup - {dispense_total} dispenses in {blocks_processed} blocks")
                return True

            finally:
                db.close()

        except Exception as e:
            logger.error(f"Error fetching dispenses: {e}")
            logger.error(traceback.format_exc())
            return False

    def _fetch_all_orders(self) -> bool:
        """Fetch all orders from the API and store them.

        Note: Bulk order/swap catchup is not yet implemented.
        This would require fetching order matches from Counterparty API for stamp assets.
        """
        # For catchup mode, we should fetch orders/matches from Counterparty API
        # This would involve fetching order matches for stamp assets
        # For now, we'll skip bulk order catchup
        logger.debug("Skipping bulk order catchup - orders/swaps need proper implementation")
        return True

    def _run_catchup(self):
        """Run the catchup process in background."""
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries and self.catchup_running:
            try:
                with self._lock:
                    logger.debug(f"Starting sales history catchup (attempt {retry_count + 1}/{max_retries})")

                    # Lower thread priority to reduce impact on main indexer
                    import os

                    if hasattr(os, "nice"):
                        try:
                            os.nice(10)  # Lower priority
                            logger.debug("Lowered catchup thread priority")
                        except BaseException:
                            pass  # Not critical if it fails

                    # Try to get database connection with logging
                    logger.debug("Attempting to get database connection for catchup...")
                    connection_start = time.time()

                    try:
                        db = self.db_manager.get_long_running_connection()
                        logger.debug(f"Got database connection in {time.time() - connection_start:.2f}s")
                    except Exception as conn_error:
                        logger.error(f"Failed to get database connection: {conn_error}")
                        if "exhausted" in str(conn_error).lower() or "timeout" in str(conn_error).lower():
                            logger.error(
                                f"Connection pool exhausted. DB_MAX_CONNECTIONS={os.getenv('DB_MAX_CONNECTIONS', '10')}"
                            )
                        raise

                    # Update CPID cache
                    logger.debug("Updating CPID cache...")
                    self.update_cpid_cache(db)

                    if self.mode == "FULL_CATCHUP":
                        logger.debug("Starting FULL_CATCHUP mode")
                        success = self._run_full_catchup(db)

                        if success:
                            logger.debug("✅ Full catchup completed successfully")
                            return  # Success, exit retry loop
                        else:
                            raise Exception("Full catchup failed")
                    else:
                        logger.debug("In REALTIME mode - no bulk catchup needed")
                        # Update checkpoint to current block so future mode checks stay in REALTIME
                        current_block = self.backend.getblockcount()
                        self.update_checkpoint("last_catchup_completion", current_block, db)
                        return

            except queue.Empty:
                logger.error("Connection pool exhausted")
                retry_count += 1
                if retry_count < max_retries:
                    wait_time = retry_count * 30
                    logger.debug(f"Waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Failed after {max_retries} attempts - connection pool issues")

            except Exception as e:
                logger.error(f"Catchup error: {e}")
                logger.error(traceback.format_exc())
                retry_count += 1
                if retry_count < max_retries:
                    wait_time = retry_count * 10
                    logger.debug(f"Waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Failed after {max_retries} attempts")

            finally:
                self.catchup_running = False
                if self.catchup_executor:
                    try:
                        self.catchup_executor.shutdown(wait=False)
                    except BaseException:
                        pass
                self.catchup_executor = None

                # Clean up any db connection
                try:
                    if "db" in locals() and db:
                        db.close()
                except BaseException:
                    pass

                # Log final progress
                logger.debug(f"Final catchup progress: {self.progress}")

        logger.debug("Catchup thread exiting")

    def _run_full_catchup(self, db) -> bool:
        """Run full catchup from beginning."""
        try:
            logger.debug("=" * 60)
            logger.debug("STARTING FULL SALES HISTORY CATCHUP")
            logger.debug("=" * 60)

            # Clear existing data if forced
            if FORCE_SALES_HISTORY_REBUILD:
                logger.warning("FORCE_SALES_HISTORY_REBUILD is set - clearing existing sales data")
                with db.cursor() as cursor:
                    cursor.execute("DELETE FROM stamp_sales_history")
                    deleted = cursor.rowcount
                    db.commit()
                    logger.debug(f"Cleared {deleted} existing sales records")

            # Fetch all dispenses
            logger.debug("\n📦 PHASE 1: Fetching dispenser sales...")
            if not self._fetch_all_dispenses():
                logger.error("Failed to fetch dispenses")
                return False

            # Fetch all orders
            logger.debug("\n📊 PHASE 2: Fetching order sales...")
            if not self._fetch_all_orders():
                logger.error("Failed to fetch orders")
                return False

            # Update checkpoint
            current_block = self.backend.getblockcount()
            self.update_checkpoint("last_catchup_completion", current_block, db)

            logger.debug("\n✅ FULL CATCHUP COMPLETED SUCCESSFULLY")
            logger.debug(f"Total API requests: {self.progress['api_requests']}")
            logger.debug(f"Total DB inserts: {self.progress['db_inserts']}")
            logger.debug(f"Total sales: {self.progress['total_sales']}")

            return True

        except Exception as e:
            logger.error(f"Full catchup failed: {e}")
            logger.error(traceback.format_exc())
            return False

    def get_sales_history(
        self, cpid: Optional[str] = None, stamp: Optional[int] = None, limit: int = 100, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get sales history for a specific stamp or all stamps."""
        db = self.db_manager.connect()
        try:
            with db.cursor() as cursor:
                base_query = """
                    SELECT
                        ssh.tx_hash,
                        ssh.block_index,
                        ssh.block_time,
                        ssh.cpid,
                        s.stamp,
                        ssh.buyer_address,
                        ssh.seller_address,
                        ssh.btc_amount,
                        ssh.sale_type,
                        ssh.processed_at,
                        s.stamp_base64,
                        s.stamp_url,
                        s.stamp_mimetype
                    FROM stamp_sales_history ssh
                    LEFT JOIN StampTableV4 s ON ssh.cpid = s.cpid
                    WHERE 1=1
                """

                params: List[Any] = []
                if cpid:
                    base_query += " AND ssh.cpid = %s"
                    params.append(cpid)
                elif stamp is not None:
                    base_query += " AND s.stamp = %s"
                    params.append(stamp)

                base_query += " ORDER BY ssh.block_time DESC LIMIT %s OFFSET %s"
                params.extend([limit, offset])

                cursor.execute(base_query, params)

                sales = []
                for row in cursor.fetchall():
                    sale = {
                        "tx_hash": row[0],
                        "block_index": row[1],
                        "block_time": row[2],
                        "cpid": row[3],
                        "stamp": row[4],
                        "buyer_address": row[5],
                        "seller_address": row[6],
                        "btc_amount": float(row[7]) if row[7] else 0,
                        "sale_type": row[8],
                        "processed_at": (
                            row[9].isoformat() if row[9] and hasattr(row[9], "isoformat") else str(row[9]) if row[9] else None
                        ),
                        "stamp_base64": row[10],
                        "stamp_url": row[11],
                        "stamp_mimetype": row[12],
                    }
                    sales.append(sale)

                return sales

        finally:
            db.close()

    def get_recent_sales(self, limit: int = 20, cpid: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get recent sales across all stamps or for a specific stamp."""
        return self.get_sales_history(cpid=cpid, limit=limit)

    def calculate_volume_from_history(self, cpid: str, hours: int = 24) -> float:
        """Calculate volume for a stamp from sales history."""
        db = self.db_manager.connect()
        try:
            with db.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT COALESCE(SUM(btc_amount), 0) as volume
                    FROM stamp_sales_history
                    WHERE cpid = %s
                    AND block_time >= UNIX_TIMESTAMP(NOW() - INTERVAL %s HOUR)
                """,
                    (cpid, hours),
                )

                result = cursor.fetchone()
                return float(result[0]) if result and result[0] else 0.0

        finally:
            db.close()


# Global instance for easy access
sales_history_processor = SalesHistoryProcessor()
