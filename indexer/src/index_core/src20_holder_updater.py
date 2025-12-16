"""
SRC-20 Holder Count Updater

Efficiently tracks and updates holder counts for SRC-20 tokens
affected by operations in each block.
"""

import logging
import threading
import time
from typing import Optional, Set

from index_core.database_manager import DatabaseManager

logger = logging.getLogger(__name__)

# Global lock to prevent concurrent holder updates
_holder_update_lock = threading.Lock()


class SRC20HolderCountUpdater:
    """Updates holder counts for SRC-20 tokens affected in each block."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db_manager = db_manager or DatabaseManager()
        self.affected_tokens: Set[str] = set()
        self.last_update_block: Optional[int] = None

    def track_affected_token(self, tick: str):
        """
        Track a token that needs holder count update.

        Args:
            tick: The token ticker (will be uppercased)
        """
        if tick:
            self.affected_tokens.add(tick.upper())
            logger.debug(f"Tracking token {tick.upper()} for holder count update")

    def track_operation(self, operation: dict):
        """
        Track tokens affected by a SRC-20 operation.

        Args:
            operation: SRC-20 operation dict with 'op' and 'tick' fields
        """
        op_type = operation.get("op", "").upper()
        tick = operation.get("tick", "")

        # Track tokens for operations that affect holder counts
        if op_type in ["DEPLOY", "MINT", "TRANSFER"] and tick:
            self.track_affected_token(tick)

    def update_holder_counts(self, block_index: int, force: bool = False, db_connection=None) -> int:
        """
        Update holder counts for all affected tokens in this block.

        Args:
            block_index: Current block index
            force: Force update even if no tokens are tracked
            db_connection: Optional database connection to use (for transaction consistency)

        Returns:
            Number of tokens updated
        """
        if not self.affected_tokens and not force:
            return 0

        # Prevent concurrent holder updates
        if not _holder_update_lock.acquire(blocking=False):
            logger.warning(f"Holder update already in progress, skipping update for block {block_index}")
            return 0

        try:
            tokens_to_update = list(self.affected_tokens)
            if not tokens_to_update and not force:
                _holder_update_lock.release()
                return 0

            # Use provided connection or create a new one
            own_connection = db_connection is None
            db = self.db_manager.connect() if own_connection else db_connection
            updated_count = 0

            # Set optimized connection parameters for tip processing
            cursor = db.cursor()
            cursor.execute("SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED")
            cursor.execute("SET SESSION innodb_lock_wait_timeout = 120")

            if force:
                # Force mode: update all tokens that need it
                logger.info("Force updating all SRC-20 holder counts and progress data")
                cursor = db.cursor()
                # Optimized query - split mint count into separate join
                cursor.execute(
                    """
                    UPDATE src20_market_data smd
                    JOIN (
                        SELECT
                            b.tick,
                            COUNT(DISTINCT b.address) as holder_count,
                            COALESCE(SUM(b.amt), 0) as total_minted,
                            ROUND(COALESCE(SUM(b.amt), 0) / NULLIF(d.max, 0) * 100, 2) as progress_percentage,
                            d.max as max_supply,
                            COALESCE(m.mint_count, 0) as mint_count
                        FROM balances b
                        LEFT JOIN SRC20Valid d ON d.tick = b.tick AND d.op = 'DEPLOY'
                        LEFT JOIN (
                            SELECT tick, COUNT(*) as mint_count
                            FROM SRC20Valid
                            WHERE op = 'MINT'
                            GROUP BY tick
                        ) m ON m.tick = b.tick
                        WHERE b.amt > 0
                        GROUP BY b.tick, d.max, m.mint_count
                    ) counts ON smd.tick = counts.tick
                    SET
                        smd.holder_count = counts.holder_count,
                        smd.total_minted = counts.total_minted,
                        smd.progress_percentage = COALESCE(counts.progress_percentage, 0),
                        smd.total_mints = counts.mint_count,
                        smd.last_updated = NOW()
                    WHERE smd.holder_count IS NULL
                       OR smd.holder_count != counts.holder_count
                       OR smd.total_minted IS NULL
                       OR smd.total_minted != counts.total_minted
                       OR smd.progress_percentage IS NULL
                       OR smd.progress_percentage != COALESCE(counts.progress_percentage, 0)
                       OR smd.total_mints IS NULL
                       OR smd.total_mints != counts.mint_count
                """
                )

                # Also set 0 for tokens with no holders
                cursor.execute(
                    """
                    UPDATE src20_market_data smd
                    LEFT JOIN (
                        SELECT DISTINCT tick
                        FROM balances
                        WHERE amt > 0
                    ) active ON smd.tick = active.tick
                    SET
                        smd.holder_count = 0,
                        smd.total_minted = 0,
                        smd.progress_percentage = 0.00,
                        smd.last_updated = NOW()
                    WHERE active.tick IS NULL
                      AND (smd.holder_count IS NULL OR smd.holder_count > 0
                           OR smd.total_minted IS NULL OR smd.total_minted > 0)
                """
                )

                updated_count = cursor.rowcount
            else:
                # Normal mode: update only affected tokens
                # Split into batches for better performance
                cursor = db.cursor()
                batch_size = 10 if len(tokens_to_update) < 50 else 25  # Smaller batches at tip
                for i in range(0, len(tokens_to_update), batch_size):
                    batch = tokens_to_update[i : i + batch_size]
                    placeholders = ",".join(["%s"] * len(batch))

                    # Update tokens with holders - with retry logic
                    max_retries = 3
                    retry_delay = 0.5

                    for attempt in range(max_retries):
                        try:
                            # Optimized query - split mint count into separate join
                            cursor.execute(
                                f"""
                                UPDATE src20_market_data smd
                                JOIN (
                                    SELECT
                                        b.tick,
                                        COUNT(DISTINCT b.address) as holder_count,
                                        COALESCE(SUM(b.amt), 0) as total_minted,
                                        ROUND(COALESCE(SUM(b.amt), 0) / NULLIF(d.max, 0) * 100, 2) as progress_percentage,
                                        COALESCE(m.mint_count, 0) as mint_count
                                    FROM balances b
                                    LEFT JOIN SRC20Valid d ON d.tick = b.tick AND d.op = 'DEPLOY'
                                    LEFT JOIN (
                                        SELECT tick, COUNT(*) as mint_count
                                        FROM SRC20Valid
                                        WHERE tick IN ({placeholders}) AND op = 'MINT'
                                        GROUP BY tick
                                    ) m ON m.tick = b.tick
                                    WHERE b.tick IN ({placeholders})
                                    AND b.amt > 0
                                    GROUP BY b.tick, d.max, m.mint_count
                                ) counts ON smd.tick = counts.tick
                                SET
                                    smd.holder_count = counts.holder_count,
                                    smd.total_minted = counts.total_minted,
                                    smd.progress_percentage = COALESCE(counts.progress_percentage, 0),
                                    smd.total_mints = counts.mint_count,
                                    smd.last_updated = NOW()
                                WHERE smd.tick IN ({placeholders})
                            """,
                                batch + batch + batch,
                            )
                            break  # Success, exit retry loop
                        except Exception as e:
                            if "Lock wait timeout" in str(e) and attempt < max_retries - 1:
                                logger.warning(f"Lock wait timeout on batch update, retrying in {retry_delay}s...")
                                time.sleep(retry_delay * 2)  # More aggressive backoff
                                retry_delay *= 2  # Exponential backoff
                            else:
                                raise  # Re-raise if not a lock timeout or out of retries

                    # Update tokens with 0 holders - with retry logic
                    for attempt in range(max_retries):
                        try:
                            cursor.execute(
                                f"""
                                UPDATE src20_market_data smd
                                LEFT JOIN (
                                    SELECT DISTINCT tick
                                    FROM balances
                                    WHERE tick IN ({placeholders})
                                    AND amt > 0
                                ) active ON smd.tick = active.tick
                                LEFT JOIN (
                                    SELECT tick, COUNT(*) as mint_count
                                    FROM SRC20Valid
                                    WHERE tick IN ({placeholders})
                                    AND op = 'MINT'
                                    GROUP BY tick
                                ) mints ON smd.tick = mints.tick
                                SET
                                    smd.holder_count = 0,
                                    smd.total_minted = 0,
                                    smd.progress_percentage = 0.00,
                                    smd.total_mints = COALESCE(mints.mint_count, 0),
                                    smd.last_updated = NOW()
                                WHERE smd.tick IN ({placeholders})
                                  AND active.tick IS NULL
                            """,
                                batch + batch + batch,
                            )
                            break
                        except Exception as e:
                            if "Lock wait timeout" in str(e) and attempt < max_retries - 1:
                                logger.warning("Lock wait timeout on zero balance update, retrying...")
                                time.sleep(retry_delay * 2)  # More aggressive backoff
                                retry_delay *= 2
                            else:
                                raise

                    updated_count += len(batch)

            # Only commit if we own the connection
            if own_connection:
                db.commit()

            if updated_count > 0:
                logger.info(f"Updated holder counts for {updated_count} tokens at block {block_index}")

            self.last_update_block = block_index

        except Exception as e:
            # Only rollback if we own the connection
            if own_connection:
                db.rollback()
            logger.error(f"Error updating holder counts at block {block_index}: {e}")
            raise
        finally:
            # Only close if we created the connection
            if own_connection:
                db.close()
            self.affected_tokens.clear()
            # Always release the lock
            _holder_update_lock.release()

        return updated_count

    def get_affected_token_count(self) -> int:
        """Get the number of tokens currently tracked for updates."""
        return len(self.affected_tokens)

    def clear(self):
        """Clear all tracked tokens."""
        self.affected_tokens.clear()

    def ensure_market_data_exists(self, tick: str, db_connection=None):
        """
        Ensure a token has an entry in src20_market_data table.

        Args:
            tick: The token ticker
            db_connection: Optional database connection to use
        """
        own_connection = db_connection is None
        db = self.db_manager.connect() if own_connection else db_connection
        try:
            # Check if entry exists
            cursor = db.cursor()
            cursor.execute(
                """
                SELECT 1 FROM src20_market_data WHERE tick = %s
            """,
                (tick.upper(),),
            )

            if not cursor.fetchone():
                # Create entry with default values
                cursor.execute(
                    """
                    INSERT INTO src20_market_data (tick, holder_count, total_minted, progress_percentage, total_mints, price_source_type, last_updated)
                    VALUES (%s, 0, 0, 0.00, 0, 'unknown', NOW())
                    ON DUPLICATE KEY UPDATE last_updated = NOW()
                """,
                    (tick.upper(),),
                )
                if own_connection:
                    db.commit()
                logger.debug(f"Created market data entry for {tick}")

        finally:
            if own_connection:
                db.close()


# Global instance for easy integration
_holder_updater_instance: Optional[SRC20HolderCountUpdater] = None


def get_holder_updater() -> SRC20HolderCountUpdater:
    """Get or create the global holder count updater instance."""
    global _holder_updater_instance
    if _holder_updater_instance is None:
        _holder_updater_instance = SRC20HolderCountUpdater()
    return _holder_updater_instance
