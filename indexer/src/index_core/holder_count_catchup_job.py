"""
Holder Count Catchup Job for Bitcoin Stamps Indexer

This module provides background job scheduling for SRC-20 holder count updates,
following the existing market data job patterns using concurrent.futures and
integrating with the existing database and indexer infrastructure.
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import config
from index_core.database_manager import DatabaseManager
from index_core.src20_holder_updater import SRC20HolderCountUpdater

logger = logging.getLogger(__name__)

# Configuration constants
HOLDER_COUNT_UPDATE_INTERVAL = 300  # 5 minutes in seconds
HOLDER_COUNT_BATCH_SIZE = 20  # Process 20 tokens at a time
HOLDER_COUNT_SELECTION_LIMIT = 200  # Max tokens to select per cycle
STALE_DATA_HOURS = 24  # Consider data stale after 24 hours

# Distance from chain tip to consider "near tip"
NEAR_TIP_BLOCKS = 100


class HolderCountCatchupJob:
    """
    Job for catching up holder count data for SRC-20 tokens.

    This job runs periodically to find and update tokens with missing or outdated
    holder count, total_minted, or progress_percentage data.
    """

    def __init__(self):
        self.database_manager = DatabaseManager()
        self.last_run_time: Optional[datetime] = None
        self.running = False

    def should_run(self, current_block: int, tip_block: int) -> bool:
        """
        Determine if the job should run based on current conditions.

        Args:
            current_block: Current indexed block height
            tip_block: Current blockchain tip height

        Returns:
            True if the job should run, False otherwise
        """
        # Only run when near the chain tip
        blocks_behind = tip_block - current_block
        if blocks_behind > NEAR_TIP_BLOCKS:
            logger.debug(
                f"Holder count catchup skipped - too far from tip "
                f"({blocks_behind} blocks behind, threshold: {NEAR_TIP_BLOCKS})"
            )
            return False

        # Check if enough time has passed since last run
        if self.last_run_time:
            time_since_last_run = (datetime.now() - self.last_run_time).total_seconds()
            if time_since_last_run < HOLDER_COUNT_UPDATE_INTERVAL:
                logger.debug(
                    f"Holder count catchup not due yet - "
                    f"{time_since_last_run:.0f}s since last run (interval: {HOLDER_COUNT_UPDATE_INTERVAL}s)"
                )
                return False

        return True

    def run(self, current_block: int, tip_block: int) -> int:
        """
        Run the holder count catchup job.

        Args:
            current_block: Current indexed block height
            tip_block: Current blockchain tip height

        Returns:
            Number of tokens updated
        """
        if self.running:
            logger.warning("Holder count catchup job is already running, skipping")
            return 0

        if not self.should_run(current_block, tip_block):
            return 0

        self.running = True
        start_time = time.time()
        total_updated = 0

        try:
            logger.info("Starting holder count catchup job")

            # Get tokens needing updates
            tokens_to_update = self._get_tokens_needing_update()

            if not tokens_to_update:
                logger.debug("No tokens need holder count updates at this time")
                return 0

            logger.info(f"Found {len(tokens_to_update)} tokens needing holder count updates")

            # Process in batches
            batches = self._split_into_batches(tokens_to_update, HOLDER_COUNT_BATCH_SIZE)

            for batch_num, batch in enumerate(batches, 1):
                try:
                    logger.debug(f"Processing holder count batch {batch_num}/{len(batches)} ({len(batch)} tokens)")
                    updated = self._process_batch(batch, current_block)
                    total_updated += updated

                    # Small delay between batches to avoid overwhelming the database
                    if batch_num < len(batches):
                        time.sleep(0.5)

                except Exception as e:
                    logger.error(f"Error processing holder count batch {batch_num}: {e}")
                    # Continue with next batch

            elapsed_time = time.time() - start_time
            logger.info(f"Holder count catchup complete: {total_updated} tokens updated in {elapsed_time:.1f}s")

            self.last_run_time = datetime.now()
            return total_updated

        except Exception as e:
            logger.error(f"Error in holder count catchup job: {e}")
            if not config.FORCE:
                raise
            return 0
        finally:
            self.running = False

    def _get_tokens_needing_update(self) -> List[str]:
        """
        Get list of tokens that need holder count updates.

        Returns:
            List of token tickers needing updates
        """
        db = self.database_manager.connect()
        try:
            with db.cursor() as cursor:
                # Find tokens with missing or stale holder count data
                stale_threshold = datetime.now() - timedelta(hours=STALE_DATA_HOURS)

                cursor.execute(
                    """
                    SELECT DISTINCT sv.tick
                    FROM SRC20Valid sv
                    LEFT JOIN src20_market_data smd ON sv.tick = smd.tick
                    WHERE sv.op = 'DEPLOY'
                    AND (
                        -- No market data entry
                        smd.tick IS NULL
                        -- Missing holder count
                        OR smd.holder_count IS NULL
                        -- Missing total minted
                        OR smd.total_minted IS NULL
                        -- Missing progress percentage
                        OR smd.progress_percentage IS NULL
                        -- Stale data
                        OR smd.last_updated < %s
                    )
                    -- Prioritize tokens with recent activity
                    ORDER BY
                        CASE
                            WHEN smd.last_updated IS NULL THEN 0
                            ELSE 1
                        END,
                        smd.last_updated ASC
                    LIMIT %s
                """,
                    (stale_threshold, HOLDER_COUNT_SELECTION_LIMIT),
                )

                results = cursor.fetchall()
                tokens = [row[0] for row in results]

                # Log distribution for monitoring
                if tokens:
                    cursor.execute(
                        """
                        SELECT
                            COUNT(CASE WHEN smd.tick IS NULL THEN 1 END) as no_entry,
                            COUNT(CASE WHEN smd.holder_count IS NULL THEN 1 END) as no_holder_count,
                            COUNT(CASE WHEN smd.total_minted IS NULL THEN 1 END) as no_total_minted,
                            COUNT(CASE WHEN smd.progress_percentage IS NULL THEN 1 END) as no_progress,
                            COUNT(CASE WHEN smd.last_updated < %s THEN 1 END) as stale
                        FROM SRC20Valid sv
                        LEFT JOIN src20_market_data smd ON sv.tick = smd.tick
                        WHERE sv.op = 'DEPLOY'
                        AND sv.tick IN ({})
                    """.format(
                            ",".join(["%s"] * len(tokens))
                        ),
                        [stale_threshold] + tokens,
                    )

                    stats = cursor.fetchone()
                    if stats:
                        logger.debug(
                            f"Token update reasons - No entry: {stats[0]}, "
                            f"No holder count: {stats[1]}, No total minted: {stats[2]}, "
                            f"No progress: {stats[3]}, Stale: {stats[4]}"
                        )

                return tokens

        finally:
            db.close()

    def _process_batch(self, tokens: List[str], current_block: int) -> int:
        """
        Process a batch of tokens for holder count updates.

        Args:
            tokens: List of token tickers to update
            current_block: Current block height

        Returns:
            Number of tokens successfully updated
        """
        # Create a dedicated holder updater instance
        holder_updater = SRC20HolderCountUpdater()

        # Track all tokens in the batch
        for token in tokens:
            holder_updater.track_affected_token(token)

        # Ensure market data entries exist
        db = self.database_manager.connect()
        try:
            for token in tokens:
                holder_updater.ensure_market_data_exists(token, db)

            # Force update the tracked tokens
            updated_count = holder_updater.update_holder_counts(current_block, force=True, db_connection=db)

            db.commit()
            return updated_count

        except Exception as e:
            db.rollback()
            logger.error(f"Error updating holder counts for batch: {e}")
            raise
        finally:
            db.close()

    def _split_into_batches(self, items: List, batch_size: int) -> List[List]:
        """Split a list into batches of specified size."""
        return [items[i : i + batch_size] for i in range(0, len(items), batch_size)]

    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about tokens needing holder count updates.

        Returns:
            Dictionary with statistics
        """
        db = self.database_manager.connect()
        try:
            with db.cursor() as cursor:
                # Get overall stats
                cursor.execute(
                    """
                    SELECT
                        COUNT(DISTINCT sv.tick) as total_tokens,
                        COUNT(DISTINCT CASE WHEN smd.tick IS NULL THEN sv.tick END) as no_market_data,
                        COUNT(DISTINCT CASE WHEN smd.holder_count IS NULL THEN sv.tick END) as no_holder_count,
                        COUNT(DISTINCT CASE WHEN smd.total_minted IS NULL THEN sv.tick END) as no_total_minted,
                        COUNT(DISTINCT CASE WHEN smd.progress_percentage IS NULL THEN sv.tick END) as no_progress
                    FROM SRC20Valid sv
                    LEFT JOIN src20_market_data smd ON sv.tick = smd.tick
                    WHERE sv.op = 'DEPLOY'
                """
                )

                stats = cursor.fetchone()

                return {
                    "total_tokens": stats[0],
                    "missing_market_data": stats[1],
                    "missing_holder_count": stats[2],
                    "missing_total_minted": stats[3],
                    "missing_progress_percentage": stats[4],
                    "last_run_time": self.last_run_time.isoformat() if self.last_run_time else None,
                    "is_running": self.running,
                }

        finally:
            db.close()


# Global instance
holder_count_catchup_job = HolderCountCatchupJob()
