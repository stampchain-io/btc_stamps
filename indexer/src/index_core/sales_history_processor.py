"""
Sales History Processor for Bitcoin Stamps

This module handles fetching and processing all types of stamp sales data:
- Dispenser sales (from Counterparty)
- Atomic swaps (future)
- OTC/Private sales (future)

Provides two modes:
1. Catchup mode: Fetches historical sales by CPID (for backfilling)
2. Real-time mode: Fetches sales by block (for new blocks at tip)

Stores all sales in stamp_sales_history table for charting, recent sales, and analytics.
"""

import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from index_core.database_manager import DatabaseManager
from index_core.fetch_utils import fetch_xcp, RateLimiter

logger = logging.getLogger(__name__)

# Constants
STAMPS_GENESIS_BLOCK = 779652
CATCHUP_BATCH_SIZE = 100  # Number of CPIDs to process per batch
MAX_WORKERS = 5  # Concurrent workers for catchup mode
RATE_LIMIT = 2.0  # Requests per second to Counterparty API

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
        self.progress = {
            'total_cpids': 0,
            'processed_cpids': 0,
            'total_sales': 0,
            'last_block_processed': 0,
            'catchup_start_time': None,
            'errors': 0
        }
        
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
                    AND cpid IS NOT NULL
                """)
                
                cpids = {row[0] for row in cursor.fetchall() if row[0]}
                
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
            # Fetch all dispenses in the block with verbose data
            response = fetch_xcp(
                f"/blocks/{block_index}/dispenses",
                {"verbose": "true", "show_unconfirmed": "false"}
            )
            
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
                self._store_dispenser_sales(stamp_dispenses, db)
                
            return len(stamp_dispenses)
            
        except Exception as e:
            logger.error(f"Error processing block {block_index} dispenses: {e}")
            self.progress['errors'] += 1
            return 0
    
    def start_catchup_mode(self, start_block: Optional[int] = None, end_block: Optional[int] = None):
        """
        Start catchup mode to backfill historical sales.
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
        self.progress['catchup_start_time'] = datetime.now()
        
        # Start the catchup in a background thread
        threading.Thread(
            target=self._run_catchup,
            args=(start_block, end_block),
            daemon=True
        ).start()
        
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
    
    def _run_catchup(self, start_block: Optional[int], end_block: Optional[int]):
        """Run the catchup process (internal method)."""
        try:
            db = self.db_manager.get_long_running_connection()
            
            # Update CPID cache
            self.update_cpid_cache(db)
            
            # Get CPIDs that need processing
            cpids_to_process = self._get_cpids_needing_catchup(db, start_block, end_block)
            
            if not cpids_to_process:
                logger.info("No CPIDs need sales history catchup")
                return
                
            self.progress['total_cpids'] = len(cpids_to_process)
            logger.info(f"Starting sales history catchup for {len(cpids_to_process)} CPIDs")
            
            # Process in batches
            for i in range(0, len(cpids_to_process), CATCHUP_BATCH_SIZE):
                if not self.catchup_running:
                    break
                    
                batch = cpids_to_process[i:i + CATCHUP_BATCH_SIZE]
                self._process_cpid_batch(batch, db)
                
                self.progress['processed_cpids'] = min(i + CATCHUP_BATCH_SIZE, len(cpids_to_process))
                
                logger.info(f"Catchup progress: {self.progress['processed_cpids']}/{self.progress['total_cpids']} CPIDs, "
                           f"{self.progress['total_sales']} total sales found")
            
        except Exception as e:
            logger.error(f"Error in sales history catchup: {e}")
            self.progress['errors'] += 1
        finally:
            if 'db' in locals():
                db.close()
            self.catchup_running = False
            logger.info(f"Sales history catchup completed: {self.progress['total_sales']} sales processed")
    
    def _get_cpids_needing_catchup(self, db, start_block: Optional[int], end_block: Optional[int]) -> List[str]:
        """Get list of CPIDs that need sales history catchup."""
        with db.cursor() as cursor:
            # Get CPIDs that don't have complete sales data
            query = """
                SELECT DISTINCT s.cpid
                FROM StampTableV4 s
                LEFT JOIN (
                    SELECT cpid, MAX(block_index) as last_sale_block
                    FROM stamp_sales_history
                    WHERE sale_type = 'dispenser'
                    GROUP BY cpid
                ) ssh ON s.cpid = ssh.cpid
                WHERE s.ident IN ('STAMP', 'SRC-721')
                AND s.cpid IS NOT NULL
                AND s.block_index >= %s
                AND (ssh.last_sale_block IS NULL OR ssh.last_sale_block < %s)
                ORDER BY s.block_index
            """
            
            cursor.execute(query, (
                start_block or STAMPS_GENESIS_BLOCK,
                end_block or 999999999
            ))
            
            return [row[0] for row in cursor.fetchall() if row[0]]
    
    def _process_cpid_batch(self, cpids: List[str], db):
        """Process a batch of CPIDs in parallel."""
        futures = []
        
        for cpid in cpids:
            if not self.catchup_running:
                break
                
            future = self.catchup_executor.submit(self._process_single_cpid_dispenses, cpid)
            futures.append((cpid, future))
        
        # Wait for completion
        for cpid, future in futures:
            try:
                dispense_count = future.result(timeout=60)
                if dispense_count > 0:
                    logger.debug(f"Processed {dispense_count} dispenser sales for {cpid}")
                    self.progress['total_sales'] += dispense_count
            except Exception as e:
                logger.error(f"Error processing CPID {cpid}: {e}")
                self.progress['errors'] += 1
    
    def _process_single_cpid_dispenses(self, cpid: str) -> int:
        """Process all dispenser sales for a single CPID."""
        total_sales = 0
        
        try:
            # Step 1: Get all dispensers for this CPID
            rate_limiter.acquire()
            response = fetch_xcp(
                f"/assets/{cpid}/dispensers",
                {"show_unconfirmed": "false"}
            )
            
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
                dispense_response = fetch_xcp(
                    f"/addresses/{source}/dispenses",
                    {
                        "asset": cpid,
                        "verbose": "true",
                        "show_unconfirmed": "false"
                    }
                )
                
                if dispense_response and "result" in dispense_response:
                    dispenses = dispense_response["result"]
                    if dispenses:
                        # Filter for blocks after genesis
                        valid_dispenses = [
                            d for d in dispenses 
                            if d.get("block_index", 0) >= STAMPS_GENESIS_BLOCK
                        ]
                        
                        if valid_dispenses:
                            self._store_dispenser_sales(valid_dispenses)
                            total_sales += len(valid_dispenses)
            
            return total_sales
            
        except Exception as e:
            logger.error(f"Error processing CPID {cpid}: {e}")
            return 0
    
    def _store_dispenser_sales(self, dispenses: List[Dict], db=None):
        """Store dispenser sales in the sales history table."""
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
                    
                    insert_data.append((
                        tx_hash, block_index, block_time, cpid, 'dispenser',
                        buyer_address, seller_address, quantity, btc_amount, 
                        unit_price_sats, dispenser_tx, None, None, None,
                        'counterparty', None
                    ))
                
                # Batch insert with ON DUPLICATE KEY UPDATE
                if insert_data:
                    cursor.executemany("""
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
                    """, insert_data)
                    
                    db.commit()
                    logger.debug(f"Stored {len(insert_data)} dispenser sales")
                    
        except Exception as e:
            logger.error(f"Error storing dispenser sales: {e}")
            if 'db' in locals():
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
                        'volume_btc': float(result[0] or 0) / 100000000,
                        'trade_count': result[1] or 0,
                        'high_sats': result[2] or 0,
                        'low_sats': result[3] or 0,
                        'last_sale_time': result[4]
                    }
                else:
                    return {
                        'volume_btc': 0.0,
                        'trade_count': 0,
                        'high_sats': 0,
                        'low_sats': 0,
                        'last_sale_time': None
                    }
                    
        finally:
            db.close()


# Global instance for easy access
sales_history_processor = SalesHistoryProcessor()