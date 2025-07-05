"""
Activity level calculator for stamp market data optimization.

This module manages the activity-based update intervals for stamps,
dramatically reducing API calls by updating active stamps frequently
and inactive stamps rarely.
"""

import logging
from datetime import datetime
from enum import Enum
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class ActivityLevel(Enum):
    """Activity levels for stamps based on trading frequency"""

    HOT = "HOT"  # Active trading in last 24h
    WARM = "WARM"  # Trading in last 7d
    COOL = "COOL"  # Trading in last 30d
    DORMANT = "DORMANT"  # Has liquidity (dispensers) but no trades
    COLD = "COLD"  # No activity


class StampActivityCalculator:
    """Calculate and manage stamp activity levels"""

    # Update intervals in minutes
    UPDATE_INTERVALS = {
        ActivityLevel.HOT: 60,  # 1 hour
        ActivityLevel.WARM: 360,  # 6 hours
        ActivityLevel.COOL: 1440,  # 24 hours
        ActivityLevel.DORMANT: 2880,  # 48 hours
        ActivityLevel.COLD: 10080,  # 7 days
    }

    @staticmethod
    def calculate_activity_level(last_sale_time: Optional[int], has_active_dispensers: bool = False) -> ActivityLevel:
        """
        Calculate activity level based on trading metrics

        Args:
            last_sale_time: Unix timestamp of last sale
            has_active_dispensers: Whether stamp has open dispensers

        Returns:
            ActivityLevel enum value
        """
        if not last_sale_time:
            # No sales history
            if has_active_dispensers:
                return ActivityLevel.DORMANT
            return ActivityLevel.COLD

        now = datetime.now().timestamp()
        time_since_sale = now - last_sale_time

        # HOT: Sale in last 24h
        if time_since_sale < 86400:
            return ActivityLevel.HOT

        # WARM: Sale in last 7 days
        if time_since_sale < 604800:
            return ActivityLevel.WARM

        # COOL: Sale in last 30 days
        if time_since_sale < 2592000:
            return ActivityLevel.COOL

        # DORMANT: Has active dispensers but old sales
        if has_active_dispensers:
            return ActivityLevel.DORMANT

        # COLD: No recent activity
        return ActivityLevel.COLD

    @staticmethod
    def should_update_market_data(activity_level: ActivityLevel, last_updated: Optional[datetime]) -> bool:
        """
        Determine if market data should be updated based on activity level

        Args:
            activity_level: Current activity level
            last_updated: When market data was last updated

        Returns:
            True if update is needed
        """
        if not last_updated:
            return True  # Never updated

        interval_minutes = StampActivityCalculator.UPDATE_INTERVALS[activity_level]
        minutes_since_update = (datetime.now() - last_updated).total_seconds() / 60

        return minutes_since_update >= interval_minutes

    @staticmethod
    def get_stamps_needing_update(db, limit: int = 1000) -> Dict[str, Tuple[str, ActivityLevel]]:
        """
        Get stamps that need market data updates based on activity levels

        Args:
            db: Database connection
            limit: Maximum stamps to return

        Returns:
            Dict of cpid -> (stamp_id, activity_level)
        """
        try:
            with db.cursor() as cursor:
                query = """
                SELECT
                    s.cpid,
                    s.stamp,
                    COALESCE(smd.activity_level, 'COLD') as activity_level,
                    smd.last_updated
                FROM StampTableV4 s
                LEFT JOIN stamp_market_data smd ON s.cpid = smd.cpid
                WHERE s.ident IN ('STAMP', 'SRC-721')
                AND (
                    -- Never updated
                    smd.last_updated IS NULL
                    OR
                    -- HOT: Update every hour
                    (smd.activity_level = 'HOT' AND
                     smd.last_updated < DATE_SUB(NOW(), INTERVAL 60 MINUTE))
                    OR
                    -- WARM: Update every 6 hours
                    (smd.activity_level = 'WARM' AND
                     smd.last_updated < DATE_SUB(NOW(), INTERVAL 360 MINUTE))
                    OR
                    -- COOL: Update every 24 hours
                    (smd.activity_level = 'COOL' AND
                     smd.last_updated < DATE_SUB(NOW(), INTERVAL 1440 MINUTE))
                    OR
                    -- DORMANT: Update every 48 hours
                    (smd.activity_level = 'DORMANT' AND
                     smd.last_updated < DATE_SUB(NOW(), INTERVAL 2880 MINUTE))
                    OR
                    -- COLD: Update every 7 days
                    (smd.activity_level = 'COLD' AND
                     smd.last_updated < DATE_SUB(NOW(), INTERVAL 10080 MINUTE))
                )
                ORDER BY
                    -- Prioritize by activity level
                    CASE smd.activity_level
                        WHEN 'HOT' THEN 1
                        WHEN 'WARM' THEN 2
                        WHEN 'COOL' THEN 3
                        WHEN 'DORMANT' THEN 4
                        WHEN 'COLD' THEN 5
                        ELSE 6
                    END,
                    smd.last_updated ASC
                LIMIT %s
                """

                cursor.execute(query, (limit,))
                results = {}
                for cpid, stamp, level_str, _ in cursor.fetchall():
                    activity_level = ActivityLevel(level_str)
                    results[cpid] = (stamp, activity_level)

                logger.info(f"Found {len(results)} stamps needing updates")

                # Log distribution
                level_counts: Dict[str, int] = {}
                for _, (_, level) in results.items():
                    level_counts[level.value] = level_counts.get(level.value, 0) + 1

                logger.info(f"Update distribution: {level_counts}")

                return results

        except Exception as e:
            logger.error(f"Error getting stamps needing update: {e}")
            return {}

    @staticmethod
    def update_activity_on_sale(cpid: str, db) -> None:
        """
        Update stamp to HOT when a sale occurs

        Args:
            cpid: Stamp identifier
            db: Database connection
        """
        try:
            with db.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE stamp_market_data
                    SET
                        activity_level = 'HOT',
                        last_activity_time = UNIX_TIMESTAMP()
                    WHERE cpid = %s
                """,
                    (cpid,),
                )

                if cursor.rowcount > 0:
                    logger.debug(f"Updated {cpid} to HOT activity level after sale")

        except Exception as e:
            logger.error(f"Error updating activity level for {cpid}: {e}")

    @staticmethod
    def update_activity_on_dispenser_change(cpid: str, has_dispensers: bool, db) -> None:
        """
        Update activity level when dispenser status changes

        Args:
            cpid: Stamp identifier
            has_dispensers: Whether stamp now has active dispensers
            db: Database connection
        """
        try:
            with db.cursor() as cursor:
                if has_dispensers:
                    # Upgrade COLD stamps to DORMANT
                    cursor.execute(
                        """
                        UPDATE stamp_market_data
                        SET activity_level =
                            CASE
                                WHEN activity_level = 'COLD' THEN 'DORMANT'
                                ELSE activity_level
                            END
                        WHERE cpid = %s
                    """,
                        (cpid,),
                    )
                else:
                    # Downgrade DORMANT stamps with no recent sales to COLD
                    cursor.execute(
                        """
                        UPDATE stamp_market_data
                        SET activity_level =
                            CASE
                                WHEN activity_level = 'DORMANT'
                                AND NOT EXISTS (
                                    SELECT 1 FROM stamp_sales_history
                                    WHERE cpid = %s
                                    AND block_time > UNIX_TIMESTAMP() - 2592000
                                ) THEN 'COLD'
                                ELSE activity_level
                            END
                        WHERE cpid = %s
                    """,
                        (cpid, cpid),
                    )

        except Exception as e:
            logger.error(f"Error updating activity on dispenser change for {cpid}: {e}")

    @staticmethod
    def log_activity_stats(db) -> None:
        """Log current activity level distribution"""
        try:
            with db.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        activity_level,
                        COUNT(*) as count,
                        SUM(volume_24h_btc) as total_volume,
                        AVG(holder_count) as avg_holders
                    FROM stamp_market_data
                    WHERE activity_level IS NOT NULL
                    GROUP BY activity_level
                """
                )

                logger.info("Activity Level Distribution:")
                total_stamps = 0
                for level, count, volume, holders in cursor.fetchall():
                    total_stamps += count
                    logger.info(
                        f"  {level}: {count} stamps, " f"{volume or 0:.8f} BTC volume, " f"{holders or 0:.1f} avg holders"
                    )

                logger.info(f"Total stamps with activity levels: {total_stamps}")

        except Exception as e:
            logger.error(f"Error logging activity stats: {e}")
