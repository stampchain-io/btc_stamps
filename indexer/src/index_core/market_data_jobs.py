"""
Market Data Job Scheduler for Bitcoin Stamps Indexer

This module provides background job scheduling for market data updates,
following the existing indexer patterns using concurrent.futures and
integrating with the existing database and API infrastructure.
"""

import concurrent.futures
import logging
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional

import config
from index_core.database_manager import DatabaseManager
from index_core.fetch_utils import RateLimiter
from index_core.market_data_service import market_data_service
from index_core.src20_worker import SRC20Worker
from index_core.stamp_worker import StampWorker

logger = logging.getLogger(__name__)

# Configuration constants for job scheduling
STAMP_UPDATE_INTERVAL = 900  # 15 minutes in seconds
SRC20_UPDATE_INTERVAL = 300  # 5 minutes in seconds
COLLECTION_UPDATE_INTERVAL = 1800  # 30 minutes in seconds

# Batch processing configuration - INCREASED FOR FULL COVERAGE
STAMP_BATCH_SIZE = 100  # Keep manageable for API rate limiting
SRC20_BATCH_SIZE = 50  # Keep manageable for exchange APIs

# DRAMATICALLY INCREASE SELECTION LIMITS FOR COMPREHENSIVE PROCESSING
STAMP_SELECTION_LIMIT = 10000  # Process up to 10K stamps per cycle (was 500)
SRC20_SELECTION_LIMIT = 1000  # Process up to 1K SRC-20 tokens per cycle (was 150)

# Rate limiting configuration
MAX_WORKERS = 3
DEFAULT_RATE_LIMIT = 1.5  # requests per second for Counterparty API

# Rate limiting for external APIs (workers have their own rate limiters)
COUNTERPARTY_RATE_LIMITER = RateLimiter(calls_per_second=2.0)


class MarketDataJobScheduler:
    """
    Job scheduler for market data updates using concurrent.futures.

    Follows the existing indexer pattern from update_cpids_async and integrates
    with the existing database and API infrastructure.
    """

    def __init__(self):
        self.executor: Optional[concurrent.futures.ThreadPoolExecutor] = None
        self.running = False
        self.shutdown_event = threading.Event()
        self.job_futures: Dict[str, concurrent.futures.Future] = {}
        self.last_run_times: Dict[str, datetime] = {}
        self._lock = threading.Lock()
        self.database_manager = DatabaseManager()

    def start(self, max_workers: int = MAX_WORKERS):
        """Start the job scheduler with the specified number of workers."""
        if self.running:
            logger.warning("Job scheduler is already running")
            return

        logger.info(f"Starting market data job scheduler with {max_workers} workers")
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        self.running = True
        self.shutdown_event.clear()

        # Start the main scheduling loop
        self.schedule_loop_future = self.executor.submit(self._schedule_loop)

    def stop(self, timeout: int = 30):
        """Stop the job scheduler and wait for running jobs to complete."""
        if not self.running:
            logger.warning("Job scheduler is not running")
            return

        logger.info("Stopping market data job scheduler...")
        self.running = False
        self.shutdown_event.set()

        # Wait for the scheduling loop to finish
        if hasattr(self, "schedule_loop_future"):
            try:
                self.schedule_loop_future.result(timeout=5)
            except concurrent.futures.TimeoutError:
                logger.warning("Schedule loop did not finish within timeout")

        # Wait for running jobs to complete
        with self._lock:
            running_jobs = list(self.job_futures.values())

        for future in running_jobs:
            try:
                future.result(timeout=timeout // len(running_jobs) if running_jobs else timeout)
            except concurrent.futures.TimeoutError:
                logger.warning(f"Job did not complete within timeout: {future}")
            except Exception as e:
                logger.error(f"Error waiting for job completion: {e}")

        # Shutdown the executor
        if self.executor:
            self.executor.shutdown(wait=True)
            self.executor = None

        logger.info("Market data job scheduler stopped")

    def _schedule_loop(self):
        """Main scheduling loop that runs jobs at their specified intervals."""
        logger.info("Market data job scheduler loop started")

        while self.running and not self.shutdown_event.is_set():
            try:
                current_time = datetime.now()

                # Check if stamp market data update is due
                if self._is_job_due("stamp_update", STAMP_UPDATE_INTERVAL, current_time):
                    self._submit_job("stamp_update", self._update_stamp_market_data_job)

                # Check if SRC-20 market data update is due
                if self._is_job_due("src20_update", SRC20_UPDATE_INTERVAL, current_time):
                    self._submit_job("src20_update", self._update_src20_market_data_job)

                # Check if collection market data update is due
                if self._is_job_due("collection_update", COLLECTION_UPDATE_INTERVAL, current_time):
                    self._submit_job("collection_update", self._update_collection_market_data_job)

                # Clean up completed jobs
                self._cleanup_completed_jobs()

                # Sleep for a short interval before checking again
                self.shutdown_event.wait(timeout=30)  # Check every 30 seconds

            except Exception as e:
                logger.error(f"Error in job scheduler loop: {e}")
                if not self.shutdown_event.is_set():
                    time.sleep(60)  # Wait before retrying

        logger.info("Market data job scheduler loop finished")

    def _is_job_due(self, job_name: str, interval: int, current_time: datetime) -> bool:
        """Check if a job is due to run based on its interval."""
        last_run = self.last_run_times.get(job_name)
        if last_run is None:
            return True  # Never run before

        time_since_last_run = (current_time - last_run).total_seconds()
        return time_since_last_run >= interval

    def _submit_job(self, job_name: str, job_function):
        """Submit a job to the executor if it's not already running."""
        with self._lock:
            # Check if job is already running
            if job_name in self.job_futures:
                future = self.job_futures[job_name]
                if not future.done():
                    logger.debug(f"Job {job_name} is already running, skipping")
                    return

            # Submit the job
            if self.executor and self.running:
                logger.info(f"Submitting job: {job_name}")
                future = self.executor.submit(job_function)
                self.job_futures[job_name] = future
                self.last_run_times[job_name] = datetime.now()

    def _cleanup_completed_jobs(self):
        """Remove completed jobs from the tracking dictionary."""
        with self._lock:
            completed_jobs = []
            for job_name, future in self.job_futures.items():
                if future.done():
                    try:
                        # Check for exceptions
                        future.result()
                        logger.debug(f"Job {job_name} completed successfully")
                    except Exception as e:
                        logger.error(f"Job {job_name} failed with error: {e}")
                    completed_jobs.append(job_name)

            for job_name in completed_jobs:
                del self.job_futures[job_name]

    def _update_stamp_market_data_job(self):
        """
        Background job to update stamp market data.

        Follows the pattern from update_cpids_async in blocks.py.
        """
        logger.info("Starting stamp market data update job")
        start_time = time.time()

        try:
            # Use existing database connection without initialization
            task_db = self.database_manager.connect()

            try:
                # Get stamps that need market data updates
                stamps_to_update = self._get_stamps_needing_update(task_db)

                if not stamps_to_update:
                    logger.info("No stamps need market data updates")
                    return

                logger.info(f"Updating market data for {len(stamps_to_update)} stamps")

                # Process stamps in batches to avoid overwhelming external APIs
                for batch in self._split_into_batches(stamps_to_update, STAMP_BATCH_SIZE):
                    if self.shutdown_event.is_set():
                        logger.info("Shutdown requested, stopping stamp updates")
                        break

                    self._process_stamp_batch(task_db, batch)

                    # Rate limiting between batches
                    if not self.shutdown_event.is_set():
                        time.sleep(2)  # 2 second delay between batches

                elapsed_time = time.time() - start_time
                logger.info(f"Stamp market data update completed in {elapsed_time:.2f} seconds")

            finally:
                task_db.close()

        except Exception as e:
            logger.error(f"Error in stamp market data update job: {e}")
            if not config.FORCE:
                raise

    def _update_src20_market_data_job(self):
        """
        Background job to update SRC-20 token market data.

        Uses exchange APIs for SRC-20 token data.
        """
        logger.info("Starting SRC-20 market data update job")
        start_time = time.time()

        try:
            # Use existing database connection without initialization
            task_db = self.database_manager.connect()

            try:
                # Get SRC-20 tokens that need market data updates
                tokens_to_update = self._get_src20_tokens_needing_update(task_db)

                if not tokens_to_update:
                    logger.info("No SRC-20 tokens need market data updates")
                    return

                logger.info(f"Updating market data for {len(tokens_to_update)} SRC-20 tokens")

                # Process tokens in batches
                for batch in self._split_into_batches(tokens_to_update, SRC20_BATCH_SIZE):
                    if self.shutdown_event.is_set():
                        logger.info("Shutdown requested, stopping SRC-20 updates")
                        break

                    self._process_src20_batch(task_db, batch)

                    # Rate limiting between batches (more frequent for SRC-20)
                    if not self.shutdown_event.is_set():
                        time.sleep(1)  # 1 second delay between batches

                elapsed_time = time.time() - start_time
                logger.info(f"SRC-20 market data update completed in {elapsed_time:.2f} seconds")

            finally:
                task_db.close()

        except Exception as e:
            logger.error(f"Error in SRC-20 market data update job: {e}")
            if not config.FORCE:
                raise

    def _update_collection_market_data_job(self):
        """
        Background job to update collection market data.

        Aggregates individual asset data into collection-level metrics.
        """
        logger.info("Starting collection market data update job")
        start_time = time.time()

        try:
            # Use existing database connection without initialization
            task_db = self.database_manager.connect()

            try:
                # Get collections that need market data updates
                collections_to_update = self._get_collections_needing_update(task_db)

                if not collections_to_update:
                    logger.info("No collections need market data updates")
                    return

                logger.info(f"Updating market data for {len(collections_to_update)} collections")

                # Process collections
                for collection_id in collections_to_update:
                    if self.shutdown_event.is_set():
                        logger.info("Shutdown requested, stopping collection updates")
                        break

                    self._process_collection_update(task_db, collection_id)

                elapsed_time = time.time() - start_time
                logger.info(f"Collection market data update completed in {elapsed_time:.2f} seconds")

            finally:
                task_db.close()

        except Exception as e:
            logger.error(f"Error in collection market data update job: {e}")
            if not config.FORCE:
                raise

    def _get_stamps_needing_update(self, db) -> List[str]:
        """Get list of stamp CPIDs that need market data updates."""
        try:
            # Query for stamps that haven't been updated recently or have no market data
            # SIMPLIFIED: Using basic patterns to avoid any string formatting issues
            query = """
            SELECT DISTINCT s.cpid
            FROM StampTableV4 s
            LEFT JOIN stamp_market_data smd ON s.cpid = smd.cpid
            WHERE (
                -- Traditional Counterparty assets: A + digits (13+ chars)
                (s.cpid LIKE 'A%' AND LENGTH(s.cpid) >= 13)
                OR 
                -- Named Counterparty assets: B-Z start (cursed stamps like FUCKTHAT, LEGENDARYBAR)
                (s.cpid LIKE 'B%' OR s.cpid LIKE 'C%' OR s.cpid LIKE 'D%' OR s.cpid LIKE 'E%' OR 
                 s.cpid LIKE 'F%' OR s.cpid LIKE 'G%' OR s.cpid LIKE 'H%' OR s.cpid LIKE 'I%' OR 
                 s.cpid LIKE 'J%' OR s.cpid LIKE 'K%' OR s.cpid LIKE 'L%' OR s.cpid LIKE 'M%' OR 
                 s.cpid LIKE 'N%' OR s.cpid LIKE 'O%' OR s.cpid LIKE 'P%' OR s.cpid LIKE 'Q%' OR 
                 s.cpid LIKE 'R%' OR s.cpid LIKE 'S%' OR s.cpid LIKE 'T%' OR s.cpid LIKE 'U%' OR 
                 s.cpid LIKE 'V%' OR s.cpid LIKE 'W%' OR s.cpid LIKE 'X%' OR s.cpid LIKE 'Y%' OR 
                 s.cpid LIKE 'Z%')
            )
            AND (
                smd.last_updated IS NULL
                OR smd.last_updated < DATE_SUB(NOW(), INTERVAL %s MINUTE)
            )
            ORDER BY s.block_index DESC
            LIMIT %s
            """

            cursor = db.cursor()
            cursor.execute(query, (STAMP_UPDATE_INTERVAL // 60, STAMP_SELECTION_LIMIT))
            results = cursor.fetchall()
            cursor.close()

            logger.info(
                f"Found {len(results)} valid Counterparty assets needing market data updates (limit: {STAMP_SELECTION_LIMIT})"
            )
            return [row[0] for row in results]

        except Exception as e:
            logger.error(f"Error getting stamps needing update: {e}")
            return []

    def _get_src20_tokens_needing_update(self, db) -> List[str]:
        """Get list of SRC-20 token ticks that need market data updates."""
        try:
            # Query for SRC-20 tokens that haven't been updated recently
            # IMPROVED: Much larger selection limit for comprehensive processing
            query = """
            SELECT DISTINCT s.tick
            FROM SRC20Valid s
            LEFT JOIN src20_market_data smd ON s.tick = smd.tick
            WHERE smd.last_updated IS NULL
               OR smd.last_updated < DATE_SUB(NOW(), INTERVAL %s MINUTE)
            ORDER BY s.block_index DESC
            LIMIT %s
            """

            cursor = db.cursor()
            cursor.execute(query, (SRC20_UPDATE_INTERVAL // 60, SRC20_SELECTION_LIMIT))
            results = cursor.fetchall()
            cursor.close()

            logger.info(f"Found {len(results)} SRC-20 tokens needing market data updates (limit: {SRC20_SELECTION_LIMIT})")
            return [row[0] for row in results]

        except Exception as e:
            logger.error(f"Error getting SRC-20 tokens needing update: {e}")
            return []

    def _get_collections_needing_update(self, db) -> List[str]:
        """Get list of collection IDs that need market data updates."""
        try:
            # Query for collections that haven't been updated recently
            query = """
            SELECT DISTINCT HEX(c.collection_id)
            FROM collections c
            LEFT JOIN collection_market_data cmd ON c.collection_id = cmd.collection_id
            WHERE cmd.last_updated IS NULL
               OR cmd.last_updated < DATE_SUB(NOW(), INTERVAL %s MINUTE)
            LIMIT %s
            """

            cursor = db.cursor()
            cursor.execute(query, (COLLECTION_UPDATE_INTERVAL // 60, 50))
            results = cursor.fetchall()
            cursor.close()

            return [row[0] for row in results]

        except Exception as e:
            logger.error(f"Error getting collections needing update: {e}")
            return []

    def _process_stamp_batch(self, db, stamp_cpids: List[str]):
        """Process a batch of stamps for market data updates with detailed analysis."""
        try:
            # All CPIDs are now pre-filtered as valid Counterparty assets in the SQL query
            # No need for additional Python-side filtering!
            logger.debug(f"Processing detailed market data for {len(stamp_cpids)} pre-validated stamps")

            # Use StampWorker for detailed market data processing
            # This provides comprehensive analysis: dispensers, dispenses, balances, volume metrics, etc.
            # StampWorker now uses a shared processor instance to avoid repeated initialization
            stamp_worker = StampWorker()
            processed_count = 0
            error_count = 0

            for cpid in stamp_cpids:
                if self.shutdown_event.is_set():
                    logger.info("Shutdown requested, stopping stamp processing")
                    break

                try:
                    # StampWorker.process_stamp_market_data() includes validation and comprehensive analysis
                    market_data = stamp_worker.process_stamp_market_data(cpid)

                    if market_data:
                        # Store the detailed market data using the service
                        market_data_service.update_stamp_market_data(cpid, market_data)
                        processed_count += 1

                        if processed_count % 5 == 0:  # Log every 5 successful updates
                            logger.debug(f"✅ Processed {processed_count}/{len(stamp_cpids)} stamps in batch")
                    else:
                        error_count += 1
                        logger.debug(f"No market data generated for {cpid}")

                except Exception as e:
                    error_count += 1
                    logger.warning(f"Error processing detailed market data for {cpid}: {e}")

            success_rate = (processed_count / len(stamp_cpids) * 100) if stamp_cpids else 0
            logger.debug(
                f"Batch complete: {processed_count}/{len(stamp_cpids)} stamps processed ({success_rate:.1f}% success)"
            )

        except Exception as e:
            logger.error(f"Error processing stamp batch: {e}")

    def _process_src20_batch(self, db, token_ticks: List[str]):
        """Process a batch of SRC-20 tokens for market data updates."""
        try:
            logger.debug(f"Processing SRC-20 market data for {len(token_ticks)} tokens")

            # Use SRC20Worker for consistent processing pattern
            src20_worker = SRC20Worker()
            processed_count = 0
            error_count = 0

            for tick in token_ticks:
                if self.shutdown_event.is_set():
                    logger.info("Shutdown requested, stopping SRC-20 processing")
                    break

                try:
                    # SRC20Worker currently has placeholder implementation
                    # TODO: This will be enhanced with real exchange API integration
                    market_data = src20_worker.process_src20_market_data(tick)

                    if market_data:
                        market_data_service.update_src20_market_data(tick, market_data)
                        processed_count += 1

                        if processed_count % 5 == 0:  # Log every 5 successful updates
                            logger.debug(f"✅ Processed {processed_count}/{len(token_ticks)} SRC-20 tokens in batch")
                    else:
                        error_count += 1
                        logger.debug(f"No market data generated for SRC-20 {tick}")

                except Exception as e:
                    error_count += 1
                    logger.warning(f"Error processing SRC-20 market data for {tick}: {e}")

            success_rate = (processed_count / len(token_ticks) * 100) if token_ticks else 0
            logger.debug(
                f"SRC-20 batch complete: {processed_count}/{len(token_ticks)} tokens processed ({success_rate:.1f}% success)"
            )

        except Exception as e:
            logger.error(f"Error processing SRC-20 batch: {e}")

    def _process_collection_update(self, db, collection_id: str):
        """Process collection market data aggregation."""
        try:
            # TODO: Implement collection aggregation logic
            # This will aggregate individual stamp/token data into collection metrics
            # For now, create placeholder data

            collection_data = {
                "floor_price_btc": None,
                "total_volume_btc": None,
                "unique_holders": None,
                "quality_score": 1.0,
            }

            market_data_service.update_collection_market_data(collection_id, collection_data)
            logger.debug(f"Updated collection market data for {collection_id}")

        except Exception as e:
            logger.error(f"Error processing collection {collection_id}: {e}")

    # Removed _transform_counterparty_asset_to_market_data method - now using StampWorker for detailed processing

    def _split_into_batches(self, items: List, batch_size: int) -> List[List]:
        """Split a list into batches of specified size."""
        return [items[i : i + batch_size] for i in range(0, len(items), batch_size)]


# Global job scheduler instance
market_data_job_scheduler = MarketDataJobScheduler()


def start_market_data_jobs(max_workers: int = MAX_WORKERS):
    """Start the market data job scheduler."""
    market_data_job_scheduler.start(max_workers)


def stop_market_data_jobs(timeout: int = 30):
    """Stop the market data job scheduler."""
    market_data_job_scheduler.stop(timeout)


def update_market_data_async(db):
    """
    Async function to trigger market data updates.

    This function can be called from the main indexer loop similar to update_cpids_async.
    """
    try:
        logger.info("Triggering market data updates")

        # Submit individual job updates if scheduler is not running
        if not market_data_job_scheduler.running:
            logger.warning("Job scheduler not running, starting individual updates")

            # Create executor for one-time updates
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                # Submit stamp and SRC-20 updates
                stamp_future = executor.submit(market_data_job_scheduler._update_stamp_market_data_job)
                src20_future = executor.submit(market_data_job_scheduler._update_src20_market_data_job)

                # Wait for completion
                stamp_future.result()
                src20_future.result()

                # Update collections after individual assets
                market_data_job_scheduler._update_collection_market_data_job()
        else:
            logger.info("Job scheduler is running, updates will be handled automatically")

    except Exception as e:
        logger.error(f"Error in update_market_data_async: {e}")
        if not config.FORCE:
            raise

    def start_background_jobs(self):
        """Start all background market data jobs"""
        if self.running:
            logger.warning("Background jobs already running")
            return

        self.running = True
        logger.info("🚀 Starting Market Data Background Jobs")
        logger.info(
            f"📊 Job Schedule: Stamps={self.stamp_interval}min, SRC-20={self.src20_interval}min, Collections={self.collection_interval}min"
        )
        logger.info(
            f"⚡ Rate Limits: Counterparty={self.counterparty_rate_limit}/sec, Exchange={self.exchange_rate_limit}/sec"
        )

        # Schedule initial jobs
        self.executor.submit(self._schedule_stamp_jobs)
        self.executor.submit(self._schedule_src20_jobs)
        self.executor.submit(self._schedule_collection_jobs)

        logger.info("✅ All background job schedulers started successfully")

    def _schedule_stamp_jobs(self):
        """Schedule stamp market data jobs"""
        logger.info("📈 Stamp Market Data Scheduler: Starting")

        while self.running:
            try:
                start_time = time.time()
                logger.info("🔄 Starting stamp market data update cycle")

                # Use existing database connection without initialization
                task_db = self.database_manager.connect()

                try:
                    # Get stamps needing updates
                    stamps_to_update = self._get_stamps_needing_update(task_db)
                    total_stamps = len(stamps_to_update)

                    if not stamps_to_update:
                        logger.info("No stamps need market data updates")
                        time.sleep(self.stamp_interval * 60)
                        continue

                    logger.info(f"📊 Processing {total_stamps} stamps for market data updates")

                    # Process in batches using the existing validated batch processing method
                    batches = self._split_into_batches(stamps_to_update, STAMP_BATCH_SIZE)
                    total_batches = len(batches)

                    for batch_num, batch in enumerate(batches, 1):
                        if self.shutdown_event.is_set():
                            logger.info("Shutdown requested, stopping stamp updates")
                            break

                        logger.info(f"🔄 Processing batch {batch_num}/{total_batches} ({len(batch)} stamps)")

                        # Use the existing batch processing method (which includes validation)
                        self._process_stamp_batch(task_db, batch)

                        # Rate limiting between batches
                        if not self.shutdown_event.is_set():
                            time.sleep(2.0)  # 2 second delay between batches

                    duration = time.time() - start_time
                    logger.info("📊 Stamp Update Cycle Complete:")
                    logger.info(f"   📊 Total stamps processed: {total_stamps}")
                    logger.info(f"   📦 Total batches: {total_batches}")
                    logger.info(f"   ⏱️  Duration: {duration:.1f}s")
                    logger.info(f"   🔄 Next cycle in {self.stamp_interval} minutes")

                finally:
                    task_db.close()

                # Wait for next cycle
                time.sleep(self.stamp_interval * 60)

            except Exception as e:
                logger.error(f"❌ Stamp scheduler error: {str(e)}")
                time.sleep(60)  # Wait 1 minute before retry

    def _schedule_src20_jobs(self):
        """Schedule SRC-20 market data jobs"""
        logger.info("🪙 SRC-20 Market Data Scheduler: Starting")

        while self.running:
            try:
                start_time = time.time()
                logger.info("🔄 Starting SRC-20 market data update cycle")

                # Use existing database connection without initialization
                task_db = self.database_manager.connect()

                try:
                    # Get SRC-20 tokens needing updates
                    tokens_to_update = self._get_src20_tokens_needing_update(task_db)
                    total_tokens = len(tokens_to_update)

                    if not tokens_to_update:
                        logger.info("No SRC-20 tokens need market data updates")
                        time.sleep(self.src20_interval * 60)
                        continue

                    logger.info(f"🪙 Processing {total_tokens} SRC-20 tokens for market data updates")

                    # Process in batches using the existing batch processing method
                    batches = self._split_into_batches(tokens_to_update, SRC20_BATCH_SIZE)
                    total_batches = len(batches)

                    for batch_num, batch in enumerate(batches, 1):
                        if self.shutdown_event.is_set():
                            logger.info("Shutdown requested, stopping SRC-20 updates")
                            break

                        logger.info(f"🔄 Processing SRC-20 batch {batch_num}/{total_batches} ({len(batch)} tokens)")

                        # Use the existing batch processing method
                        self._process_src20_batch(task_db, batch)

                        # Rate limiting between batches
                        if not self.shutdown_event.is_set():
                            time.sleep(1.0)  # 1 second delay between batches

                    duration = time.time() - start_time
                    logger.info("🪙 SRC-20 Update Cycle Complete:")
                    logger.info(f"   🪙 Total tokens processed: {total_tokens}")
                    logger.info(f"   📦 Total batches: {total_batches}")
                    logger.info(f"   ⏱️  Duration: {duration:.1f}s")
                    logger.info(f"   🔄 Next cycle in {self.src20_interval} minutes")

                finally:
                    task_db.close()

                # Wait for next cycle
                time.sleep(self.src20_interval * 60)

            except Exception as e:
                logger.error(f"❌ SRC-20 scheduler error: {str(e)}")
                time.sleep(60)  # Wait 1 minute before retry

    def stop_background_jobs(self):
        """Stop all background jobs gracefully"""
        if not self.running:
            logger.warning("Background jobs not running")
            return

        logger.info("🛑 Stopping Market Data Background Jobs...")
        self.running = False

        # Wait for current jobs to complete
        logger.info("⏳ Waiting for current jobs to complete...")
        self.executor.shutdown(wait=True)

        logger.info("✅ All background jobs stopped successfully")
