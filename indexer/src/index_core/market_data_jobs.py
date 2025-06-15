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
from index_core.database import initialize_db
from index_core.fetch_utils import RateLimiter, get_xcp_assets_by_cpids, is_valid_counterparty_asset
from index_core.market_data_service import market_data_service
from index_core.src20_worker import SRC20Worker
from index_core.stamp_worker import StampWorker

logger = logging.getLogger(__name__)

# Job scheduling constants
STAMP_UPDATE_INTERVAL = 15 * 60  # 15 minutes in seconds
SRC20_UPDATE_INTERVAL = 5 * 60  # 5 minutes in seconds
COLLECTION_UPDATE_INTERVAL = 30 * 60  # 30 minutes in seconds

# Batch processing constants
STAMP_BATCH_SIZE = 100
SRC20_BATCH_SIZE = 50
MAX_WORKERS = 3

# Rate limiting for external APIs
COUNTERPARTY_RATE_LIMITER = RateLimiter(calls_per_second=2.0)
EXCHANGE_RATE_LIMITER = RateLimiter(calls_per_second=1.0)


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
            # Create a new database connection for this job
            task_db = initialize_db()

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
            # Create a new database connection for this job
            task_db = initialize_db()

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
            # Create a new database connection for this job
            task_db = initialize_db()

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
            query = """
            SELECT DISTINCT s.cpid
            FROM StampTableV4 s
            LEFT JOIN stamp_market_data smd ON s.cpid = smd.cpid
            WHERE smd.last_updated IS NULL
               OR smd.last_updated < DATE_SUB(NOW(), INTERVAL %s MINUTE)
            ORDER BY s.block_index DESC
            LIMIT %s
            """

            cursor = db.cursor()
            cursor.execute(query, (STAMP_UPDATE_INTERVAL // 60, STAMP_BATCH_SIZE * 5))
            results = cursor.fetchall()
            cursor.close()

            return [row[0] for row in results]

        except Exception as e:
            logger.error(f"Error getting stamps needing update: {e}")
            return []

    def _get_src20_tokens_needing_update(self, db) -> List[str]:
        """Get list of SRC-20 token ticks that need market data updates."""
        try:
            # Query for SRC-20 tokens that haven't been updated recently
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
            cursor.execute(query, (SRC20_UPDATE_INTERVAL // 60, SRC20_BATCH_SIZE * 3))
            results = cursor.fetchall()
            cursor.close()

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
        """Process a batch of stamps for market data updates."""
        try:
            # Filter out SRC-20 hash tokens that don't exist in Counterparty API
            # Separate valid Counterparty assets from SRC-20 hash tokens
            valid_cpids = [cpid for cpid in stamp_cpids if is_valid_counterparty_asset(cpid)]
            invalid_cpids = [cpid for cpid in stamp_cpids if not is_valid_counterparty_asset(cpid)]

            if invalid_cpids:
                logger.debug(
                    f"Filtered out {len(invalid_cpids)} SRC-20 hash tokens from Counterparty API fetch: {invalid_cpids[:5]}..."
                )

            if not valid_cpids:
                logger.debug("No valid Counterparty assets in batch, skipping API call")
                return

            # Rate limiting for Counterparty API
            COUNTERPARTY_RATE_LIMITER.acquire(len(valid_cpids))

            # Get asset details from Counterparty API (following existing pattern)
            assets_details = get_xcp_assets_by_cpids(valid_cpids, chunk_size=50, delay_between_chunks=3, max_workers=2)

            if assets_details:
                # Process each asset and update market data
                for asset in assets_details:
                    if self.shutdown_event.is_set():
                        break

                    cpid = asset.get("asset")
                    if cpid:
                        # Use the market data service to update stamp data
                        market_data = self._transform_counterparty_asset_to_market_data(asset)
                        if market_data:
                            market_data_service.update_stamp_market_data(cpid, market_data)

                logger.debug(f"Processed {len(assets_details)} stamps in batch")
            else:
                logger.warning("No asset details retrieved for stamp batch")

        except Exception as e:
            logger.error(f"Error processing stamp batch: {e}")

    def _process_src20_batch(self, db, token_ticks: List[str]):
        """Process a batch of SRC-20 tokens for market data updates."""
        try:
            # Rate limiting for exchange APIs
            EXCHANGE_RATE_LIMITER.acquire(len(token_ticks))

            # TODO: Implement exchange API calls for SRC-20 tokens
            # This will be implemented in subsequent subtasks (3.3)
            # For now, create placeholder market data

            for tick in token_ticks:
                if self.shutdown_event.is_set():
                    break

                # Placeholder market data (will be replaced with real exchange data)
                market_data = {
                    "floor_price_btc": None,
                    "volume_24h_btc": None,
                    "holder_count": None,
                    "primary_exchange": "placeholder",
                    "data_quality_score": 1.0,
                }

                market_data_service.update_src20_market_data(tick, market_data)

            logger.debug(f"Processed {len(token_ticks)} SRC-20 tokens in batch")

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

    def _transform_counterparty_asset_to_market_data(self, asset: Dict) -> Optional[Dict]:
        """Transform Counterparty asset data to market data format."""
        try:
            # Extract relevant data from Counterparty asset
            cpid = asset.get("asset")
            if not cpid:
                return None

            # Basic market data structure
            market_data = {
                "floor_price_btc": None,  # Will be calculated from dispensers
                "volume_24h_btc": None,  # Will be calculated from dispenses
                "holder_count": None,  # Will be calculated from balances
                "price_source": "counterparty",
                "data_quality_score": 8.0,  # High quality for Counterparty data
            }

            # TODO: Add more sophisticated data transformation
            # This will be enhanced in subsequent subtasks

            return market_data

        except Exception as e:
            logger.error(f"Error transforming asset data: {e}")
            return None

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

                # Process stamps in batches
                processed_count = 0
                error_count = 0

                # Get stamps needing updates (simplified for example)
                stamps_to_update = self._get_stamps_needing_update()
                total_stamps = len(stamps_to_update)

                logger.info(f"📊 Processing {total_stamps} stamps for market data updates")

                for batch_start in range(0, total_stamps, 50):  # Process in batches of 50
                    batch = stamps_to_update[batch_start : batch_start + 50]
                    batch_num = (batch_start // 50) + 1
                    total_batches = (total_stamps + 49) // 50

                    logger.info(f"🔄 Processing batch {batch_num}/{total_batches} ({len(batch)} stamps)")

                    for stamp in batch:
                        try:
                            worker = StampWorker()
                            success = worker.process_stamp_market_data(stamp["cpid"])

                            if success:
                                processed_count += 1
                                if processed_count % 10 == 0:  # Log every 10 successful updates
                                    logger.info(f"✅ Processed {processed_count}/{total_stamps} stamps successfully")
                            else:
                                error_count += 1

                        except Exception as e:
                            error_count += 1
                            logger.error(f"❌ Error processing stamp {stamp['cpid']}: {str(e)}")

                    # Rate limiting between batches
                    time.sleep(2.0)  # 2 second delay between batches

                duration = time.time() - start_time
                success_rate = (processed_count / total_stamps * 100) if total_stamps > 0 else 0

                logger.info("📊 Stamp Update Cycle Complete:")
                logger.info(f"   ✅ Processed: {processed_count}/{total_stamps} stamps ({success_rate:.1f}% success)")
                logger.info(f"   ❌ Errors: {error_count}")
                logger.info(f"   ⏱️  Duration: {duration:.1f}s")
                logger.info(f"   🔄 Next cycle in {self.stamp_interval} minutes")

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

                # Get SRC-20 tokens needing updates
                tokens_to_update = self._get_src20_tokens_needing_update()
                total_tokens = len(tokens_to_update)

                logger.info(f"🪙 Processing {total_tokens} SRC-20 tokens for market data updates")

                processed_count = 0
                error_count = 0

                for token in tokens_to_update:
                    try:
                        worker = SRC20Worker()
                        success = worker.process_src20_market_data(token["tick"])

                        if success:
                            processed_count += 1
                            logger.info(f"✅ Updated {token['tick']} market data")
                        else:
                            error_count += 1

                    except Exception as e:
                        error_count += 1
                        logger.error(f"❌ Error processing SRC-20 {token['tick']}: {str(e)}")

                    # Rate limiting between tokens
                    time.sleep(1.0 / self.exchange_rate_limit)

                duration = time.time() - start_time
                success_rate = (processed_count / total_tokens * 100) if total_tokens > 0 else 0

                logger.info("🪙 SRC-20 Update Cycle Complete:")
                logger.info(f"   ✅ Processed: {processed_count}/{total_tokens} tokens ({success_rate:.1f}% success)")
                logger.info(f"   ❌ Errors: {error_count}")
                logger.info(f"   ⏱️  Duration: {duration:.1f}s")
                logger.info(f"   🔄 Next cycle in {self.src20_interval} minutes")

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
