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
        logger.info(f"ThreadPoolExecutor created with max_workers={self.executor._max_workers}")
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
                src20_is_due = self._is_job_due("src20_update", SRC20_UPDATE_INTERVAL, current_time)
                logger.info(f"SRC-20 job due check: {src20_is_due} (interval: {SRC20_UPDATE_INTERVAL}s)")
                logger.info(f"Last run times: {self.last_run_times}")
                logger.info(f"Current jobs: {list(self.job_futures.keys())}")
                if src20_is_due:
                    logger.info("=== SRC-20 JOB IS DUE, SUBMITTING ===")
                    self._submit_job("src20_update", self._update_src20_market_data_job)

                # Check if collection market data update is due
                if self._is_job_due("collection_update", COLLECTION_UPDATE_INTERVAL, current_time):
                    self._submit_job("collection_update", self._update_collection_market_data_job)

                # Clean up completed jobs
                self._cleanup_completed_jobs()

                # Log active jobs status
                active_jobs = []
                for job_name, future in self.job_futures.items():
                    if not future.done():
                        active_jobs.append(job_name)
                if active_jobs:
                    logger.info(f"Active jobs: {active_jobs}")

                # Sleep for a short interval before checking again
                self.shutdown_event.wait(timeout=5)  # Check every 5 seconds for faster updates

            except Exception as e:
                logger.error(f"Error in job scheduler loop: {e}")
                if not self.shutdown_event.is_set():
                    time.sleep(60)  # Wait before retrying

        logger.info("Market data job scheduler loop finished")

    def _is_job_due(self, job_name: str, interval: int, current_time: datetime) -> bool:
        """Check if a job is due to run based on its interval."""
        last_run = self.last_run_times.get(job_name)
        if last_run is None:
            logger.info(f"Job {job_name} has never run before, marking as due")
            return True  # Never run before

        time_since_last_run = (current_time - last_run).total_seconds()
        is_due = time_since_last_run >= interval
        if not is_due:
            logger.debug(f"Job {job_name} not due yet: {time_since_last_run:.1f}s since last run (interval: {interval}s)")
        return is_due

    def _submit_job(self, job_name: str, job_function):
        """Submit a job to the executor if it's not already running."""
        try:
            with self._lock:
                # Check if job is already running
                if job_name in self.job_futures:
                    future = self.job_futures[job_name]
                    if not future.done():
                        logger.debug(f"Job {job_name} is already running, skipping")
                        return

                # Submit the job
                if self.executor and self.running:
                    logger.info(f"=== SUBMITTING JOB: {job_name} ===")
                    logger.info(f"Executor state: {self.executor}")
                    logger.info(f"Running state: {self.running}")

                    try:
                        # Add debug wrapper to ensure job starts
                        def job_wrapper():
                            logger.info(f"=== JOB WRAPPER STARTING: {job_name} ===")
                            try:
                                result = job_function()
                                logger.info(f"=== JOB WRAPPER COMPLETED: {job_name} ===")
                                return result
                            except Exception as job_error:
                                logger.error(f"=== JOB WRAPPER ERROR: {job_name} ===")
                                logger.error(f"Job error: {job_error}")
                                import traceback

                                logger.error(f"Job traceback: {traceback.format_exc()}")
                                raise

                        future = self.executor.submit(job_wrapper)
                        self.job_futures[job_name] = future
                        self.last_run_times[job_name] = datetime.now()
                        logger.info(f"Job {job_name} submitted successfully, future: {future}")
                        logger.info(
                            f"Current executor stats: {self.executor._threads} threads, {len(self.job_futures)} tracked jobs"
                        )
                    except Exception as submit_error:
                        logger.error(f"Failed to submit job {job_name}: {submit_error}")
                        import traceback

                        logger.error(f"Submit traceback: {traceback.format_exc()}")
                        raise
                else:
                    logger.warning(f"Cannot submit job {job_name}: executor={self.executor}, running={self.running}")
        except Exception as e:
            logger.error(f"Error in _submit_job for {job_name}: {e}")
            import traceback

            logger.error(f"Full traceback: {traceback.format_exc()}")
            raise

    def _cleanup_completed_jobs(self):
        """Remove completed jobs from the tracking dictionary."""
        with self._lock:
            completed_jobs = []
            for job_name, future in self.job_futures.items():
                if future.done():
                    try:
                        # Check for exceptions
                        future.result()
                        logger.info(f"Job {job_name} completed successfully")
                    except Exception as e:
                        logger.error(f"Job {job_name} failed with error: {e}")
                        import traceback

                        logger.error(f"Job {job_name} traceback: {traceback.format_exc()}")
                    completed_jobs.append(job_name)

            for job_name in completed_jobs:
                del self.job_futures[job_name]

    def _update_stamp_market_data_job(self):
        """
        Background job to update stamp market data.

        Follows the pattern from update_cpids_async in blocks.py.
        """
        logger.info("=== STAMP JOB ENTRY POINT ===")
        logger.info("Starting stamp market data update job")
        logger.info(f"Thread ID: {threading.current_thread().ident}")
        logger.info(f"Thread Name: {threading.current_thread().name}")
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
                batches = self._split_into_batches(stamps_to_update, STAMP_BATCH_SIZE)
                total_batches = len(batches)
                logger.info(f"Processing {len(stamps_to_update)} stamps in {total_batches} batches of {STAMP_BATCH_SIZE}")

                for batch_num, batch in enumerate(batches, 1):
                    if self.shutdown_event.is_set():
                        logger.info("Shutdown requested, stopping stamp updates")
                        break

                    logger.info(f"Processing stamp batch {batch_num}/{total_batches}")
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
        try:
            logger.info("=== SRC-20 JOB ENTRY POINT ===")
            logger.info("Starting SRC-20 market data update job")
            logger.info(f"Thread ID: {threading.current_thread().ident}")
            logger.info(f"Thread Name: {threading.current_thread().name}")
            start_time = time.time()

            # Use existing database connection without initialization
            logger.info("SRC-20 job: Attempting database connection...")
            task_db = self.database_manager.connect()
            logger.info("SRC-20 job: Database connection established successfully")

            try:
                # Create a single worker instance
                src20_worker = SRC20Worker()

                # Fetch ALL market data from OpenStamp in ONE call
                logger.info("SRC-20 job: Fetching all market data from OpenStamp")
                openstamp_tokens = src20_worker.fetch_all_openstamp_data()

                if openstamp_tokens:
                    logger.info(f"SRC-20 job: Retrieved {len(openstamp_tokens)} tokens from OpenStamp")

                    # Process each token from OpenStamp
                    processed_count = 0
                    error_count = 0

                    for token_data in openstamp_tokens:
                        if self.shutdown_event.is_set():
                            logger.info("Shutdown requested, stopping SRC-20 updates")
                            break

                        try:
                            # Extract tick from token data
                            tick = token_data.get("name", "").upper()
                            if tick:
                                # Transform and store the market data
                                market_data = src20_worker.transform_openstamp_data(token_data)
                                if market_data:
                                    market_data_service.update_src20_market_data(tick, market_data)
                                    processed_count += 1

                                    if processed_count % 50 == 0:
                                        logger.debug(f"Processed {processed_count} tokens...")
                                else:
                                    error_count += 1
                        except Exception as e:
                            error_count += 1
                            logger.warning(f"Error processing token data: {e}")

                    logger.info(f"SRC-20 job: Processed {processed_count} tokens from OpenStamp ({error_count} errors)")
                else:
                    logger.warning("SRC-20 job: No data retrieved from OpenStamp")

                # Update STAMP token from KuCoin (only token we track there)
                logger.info("SRC-20 job: Updating STAMP token from KuCoin")
                try:
                    stamp_data = src20_worker.process_src20_market_data("STAMP")
                    if stamp_data:
                        market_data_service.update_src20_market_data("STAMP", stamp_data)
                        logger.info("SRC-20 job: Successfully updated STAMP from KuCoin")
                    else:
                        logger.warning("SRC-20 job: No market data returned for STAMP from KuCoin")
                except Exception as e:
                    logger.error(f"SRC-20 job: Error updating STAMP from KuCoin: {e}")

                elapsed_time = time.time() - start_time
                logger.info(f"SRC-20 market data update completed in {elapsed_time:.2f} seconds")

            finally:
                logger.info("SRC-20 job: Closing database connection")
                task_db.close()
                logger.info("SRC-20 job: Database connection closed")

        except Exception as e:
            logger.error("=== SRC-20 JOB EXCEPTION ===")
            logger.error(f"Error in SRC-20 market data update job: {e}")
            import traceback

            logger.error(f"Full traceback: {traceback.format_exc()}")
            if not config.FORCE:
                raise

    def _update_collection_market_data_job(self):
        """
        Background job to update collection market data.

        Aggregates individual asset data into collection-level metrics.
        """
        logger.info("=== COLLECTION JOB ENTRY POINT ===")
        logger.info("Starting collection market data update job")
        logger.info(f"Thread ID: {threading.current_thread().ident}")
        logger.info(f"Thread Name: {threading.current_thread().name}")
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
        from index_core.database import get_stamps_needing_market_update

        cpids = get_stamps_needing_market_update(
            db, update_interval_minutes=STAMP_UPDATE_INTERVAL // 60, limit=STAMP_SELECTION_LIMIT
        )

        logger.info(
            f"Found {len(cpids)} valid Counterparty assets needing market data updates (limit: {STAMP_SELECTION_LIMIT})"
        )
        return cpids

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
                        # Extract holder cache data if present
                        holder_cache_data = market_data.pop("_holder_cache_data", None)

                        # Debug logging for holder cache data
                        if holder_cache_data:
                            logger.debug(f"Found holder cache data for {cpid}: {len(holder_cache_data)} holders")
                        else:
                            logger.debug(f"No holder cache data found for {cpid}")

                        # Store the detailed market data using the service
                        market_data_service.update_stamp_market_data(cpid, market_data)
                        processed_count += 1

                        if processed_count % 5 == 0:  # Log every 5 successful updates
                            logger.debug(f"✅ Processed {processed_count}/{len(stamp_cpids)} stamps in batch")

                        # Populate holder cache if we have holder data
                        if holder_cache_data and isinstance(holder_cache_data, list):
                            logger.debug(f"Populating holder cache for {cpid} with {len(holder_cache_data)} holders")
                            self._populate_holder_cache(db, cpid, holder_cache_data)
                        else:
                            logger.debug(f"Skipping holder cache population for {cpid} - no valid data")
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

    def _process_src20_batch(self, db, token_ticks: List[str], src20_worker: Optional["SRC20Worker"] = None):
        """Process a batch of SRC-20 tokens for market data updates."""
        try:
            logger.debug(f"Processing SRC-20 market data for {len(token_ticks)} tokens")

            # Use provided worker or create new one (for backward compatibility)
            if src20_worker is None:
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
            logger.debug(f"Processing collection aggregation for {collection_id}")

            # Get all stamps in this collection
            with db.cursor() as cursor:
                # Get collection stamps with their market data
                query = """
                    SELECT
                        s.cpid,
                        s.stamp,
                        smd.floor_price_btc,
                        smd.holder_count,
                        smd.volume_24h_btc,
                        smd.volume_7d_btc,
                        smd.volume_30d_btc,
                        smd.total_volume_btc
                    FROM collection_stamps cs
                    JOIN StampTableV4 s ON cs.stamp = s.stamp
                    LEFT JOIN stamp_market_data smd ON s.cpid = smd.cpid
                    WHERE cs.collection_id = UNHEX(%s)
                """
                cursor.execute(query, (collection_id,))
                stamps = cursor.fetchall()

                if not stamps:
                    logger.debug(f"No stamps found for collection {collection_id}")
                    return

                logger.debug(f"Found {len(stamps)} stamps in collection {collection_id}")

                # Calculate aggregated metrics
                floor_prices = []
                volume_24h_values = []
                volume_7d_values = []
                volume_30d_values = []
                total_volume_values = []
                total_stamps = len(stamps)
                unique_holders = set()

                for stamp in stamps:
                    cpid, stamp_num, floor_price, holder_count, vol_24h, vol_7d, vol_30d, total_vol = stamp

                    # Collect floor prices (only from stamps that have active markets)
                    if floor_price is not None and float(floor_price) > 0:
                        floor_prices.append(float(floor_price))

                    # Aggregate volume data
                    if vol_24h is not None:
                        volume_24h_values.append(float(vol_24h))
                    if vol_7d is not None:
                        volume_7d_values.append(float(vol_7d))
                    if vol_30d is not None:
                        volume_30d_values.append(float(vol_30d))
                    if total_vol is not None:
                        total_volume_values.append(float(total_vol))

                    # Get unique holders for this stamp
                    if cpid:
                        holder_query = """
                            SELECT DISTINCT address
                            FROM stamp_holder_cache
                            WHERE cpid = %s AND quantity > 0
                        """
                        cursor.execute(holder_query, (cpid,))
                        stamp_holders = cursor.fetchall()
                        for holder in stamp_holders:
                            unique_holders.add(holder[0])

                # Calculate collection metrics
                collection_data = {
                    "total_stamps": total_stamps,
                    "floor_price_btc": min(floor_prices) if floor_prices else None,
                    "avg_price_btc": sum(floor_prices) / len(floor_prices) if floor_prices else None,
                    "unique_holders": len(unique_holders) if unique_holders else 0,
                    "volume_24h_btc": sum(volume_24h_values) if volume_24h_values else 0,
                    "volume_7d_btc": sum(volume_7d_values) if volume_7d_values else 0,
                    "volume_30d_btc": sum(volume_30d_values) if volume_30d_values else 0,
                    "total_volume_btc": sum(total_volume_values) if total_volume_values else 0,
                    "listed_stamps": len(floor_prices),  # Stamps with active markets
                }

                logger.debug(
                    f"Collection {collection_id} aggregation: {len(floor_prices)} listed stamps, "
                    f"floor: {collection_data['floor_price_btc']}, holders: {collection_data['unique_holders']}"
                )

            market_data_service.update_collection_market_data(collection_id, collection_data)
            logger.debug(f"Updated collection market data for {collection_id}")

        except Exception as e:
            logger.error(f"Error processing collection {collection_id}: {e}")

    def _split_into_batches(self, items: List, batch_size: int) -> List[List]:
        """Split a list into batches of specified size."""
        return [items[i : i + batch_size] for i in range(0, len(items), batch_size)]

    def _populate_holder_cache(self, db, cpid: str, holder_data: List[Dict]):
        """
        Populate the stamp_holder_cache table with individual holder data.

        Args:
            db: Database connection
            cpid: Counterparty asset ID
            holder_data: List of holder dictionaries with address and quantity
        """
        try:
            if not holder_data:
                logger.debug(f"No holder data provided for {cpid}")
                return

            logger.debug(f"Populating holder cache for {cpid} with {len(holder_data)} holders")

            # Sort holders by quantity (descending) to assign rank positions
            sorted_holders = sorted(holder_data, key=lambda x: x["quantity"], reverse=True)
            total_supply = sum(holder["quantity"] for holder in holder_data)

            # Perform the database operations
            with db.cursor() as cursor:
                # Clear existing cache for this stamp
                cursor.execute("DELETE FROM stamp_holder_cache WHERE cpid = %s", (cpid,))
                deleted_count = cursor.rowcount
                logger.debug(f"Deleted {deleted_count} existing holder cache records for {cpid}")

                # Insert new holder records
                insert_values = []
                for rank, holder in enumerate(sorted_holders, 1):
                    address = holder["address"]
                    quantity = holder["quantity"]
                    percentage = (quantity / total_supply * 100) if total_supply > 0 else 0

                    insert_values.append(
                        (
                            cpid,
                            address,
                            quantity,
                            percentage,
                            rank,
                            "counterparty",  # balance_source
                            None,  # last_tx_block (can be added later if needed)
                        )
                    )

                # Batch insert all holders
                if insert_values:
                    cursor.executemany(
                        """
                        INSERT INTO stamp_holder_cache
                        (cpid, address, quantity, percentage, rank_position, balance_source, last_tx_block)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                        insert_values,
                    )

                    inserted_count = cursor.rowcount
                    logger.debug(f"Inserted {inserted_count} holder cache records for {cpid}")

                    # Verify the insertion
                    cursor.execute("SELECT COUNT(*) FROM stamp_holder_cache WHERE cpid = %s", (cpid,))
                    final_count = cursor.fetchone()[0]
                    logger.debug(f"Final holder cache count for {cpid}: {final_count}")

                    if final_count != len(insert_values):
                        logger.warning(f"Expected {len(insert_values)} records but found {final_count} for {cpid}")
                else:
                    logger.debug(f"No valid holder records to insert for {cpid}")

            # Commit the transaction if not in autocommit mode
            try:
                db.commit()
                logger.debug(f"Successfully committed holder cache for {cpid}")
            except Exception as commit_error:
                logger.debug(f"Commit not needed (likely autocommit mode) for {cpid}: {commit_error}")

        except Exception as e:
            # Rollback on error if possible
            try:
                db.rollback()
                logger.debug(f"Rolled back holder cache transaction for {cpid}")
            except Exception as rollback_error:
                logger.debug(f"Rollback not needed (likely autocommit mode) for {cpid}: {rollback_error}")

            logger.error(f"Error populating holder cache for {cpid}: {e}")
            raise


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
