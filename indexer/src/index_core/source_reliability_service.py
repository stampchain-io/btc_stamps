"""
Source Reliability Service for Bitcoin Stamps Indexer

This module implements a comprehensive system to track and score the reliability
of different market data sources based on historical performance metrics.

Features:
- Track API response times and success rates
- Calculate reliability scores (0-10) using sliding window algorithms
- Update market_data_sources table with latest reliability metrics
- Automatic alerts for consistently low-scoring sources
- Integration with existing market data workers
"""

import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Union

import index_core.exceptions as exceptions
import index_core.log as log
from config import MARKET_DATA_SOURCES_TABLE
from index_core.database_manager import DatabaseManager

logger = logging.getLogger(__name__)
log.set_logger(logger)

# Reliability scoring constants
MIN_RELIABILITY_SCORE = 0.0
MAX_RELIABILITY_SCORE = 10.0
DEFAULT_RELIABILITY_SCORE = 5.0

# Alert thresholds
LOW_RELIABILITY_THRESHOLD = 3.0
CRITICAL_RELIABILITY_THRESHOLD = 1.0
MAX_CONSECUTIVE_FAILURES = 5

# Sliding window parameters
DEFAULT_WINDOW_HOURS = 24
MAX_SAMPLES_PER_WINDOW = 100
MIN_SAMPLES_FOR_SCORE = 3

# Scoring weights
RESPONSE_TIME_WEIGHT = 0.3
SUCCESS_RATE_WEIGHT = 0.5
CONSECUTIVE_FAILURES_WEIGHT = 0.2

# Response time thresholds (milliseconds)
EXCELLENT_RESPONSE_TIME = 500
GOOD_RESPONSE_TIME = 2000
POOR_RESPONSE_TIME = 10000


class SourceReliabilityTracker:
    """
    Tracks and records reliability metrics for a single data source.

    This class is used to capture performance data during API calls and
    calculate reliability scores based on historical performance.
    """

    def __init__(self, source_name: str, asset_type: str, asset_id: str):
        """
        Initialize a reliability tracker for a specific source.

        Args:
            source_name: Name of the data source (e.g., 'kucoin', 'openstamp')
            asset_type: Type of asset ('stamp' or 'src20')
            asset_id: Asset identifier (cpid for stamps, tick for src20)
        """
        self.source_name = source_name
        self.asset_type = asset_type
        self.asset_id = asset_id
        self.start_time: Optional[float] = None
        self.response_time_ms: Optional[int] = None
        self.success: Optional[bool] = None
        self.error_message: Optional[str] = None

    def start_tracking(self) -> None:
        """Start tracking an API call."""
        self.start_time = time.time()
        self.response_time_ms = None
        self.success = None
        self.error_message = None

    def record_success(self, data_quality: Optional[float] = None) -> None:
        """
        Record a successful API call.

        Args:
            data_quality: Optional quality score for the received data (0-10)
        """
        if self.start_time is None:
            logger.warning(f"Cannot record success for {self.source_name}: tracking not started")
            return

        self.response_time_ms = int((time.time() - self.start_time) * 1000)
        self.success = True
        self.error_message = None

        logger.debug(
            f"Success recorded for {self.source_name} ({self.asset_type}:{self.asset_id}): " f"{self.response_time_ms}ms"
        )

    def record_failure(self, error_message: str) -> None:
        """
        Record a failed API call.

        Args:
            error_message: Description of the failure
        """
        if self.start_time is None:
            logger.warning(f"Cannot record failure for {self.source_name}: tracking not started")
            return

        self.response_time_ms = int((time.time() - self.start_time) * 1000)
        self.success = False
        self.error_message = error_message

        logger.debug(
            f"Failure recorded for {self.source_name} ({self.asset_type}:{self.asset_id}): "
            f"{error_message} after {self.response_time_ms}ms"
        )

    def get_metrics(self) -> Dict[str, Union[str, int, bool, None]]:
        """
        Get the recorded metrics for this tracking session.

        Returns:
            Dictionary containing the recorded metrics
        """
        return {
            "source_name": self.source_name,
            "asset_type": self.asset_type,
            "asset_id": self.asset_id,
            "response_time_ms": self.response_time_ms,
            "success": self.success,
            "error_message": self.error_message,
        }


class SourceReliabilityService:
    """
    Service for tracking and scoring the reliability of market data sources.

    This service implements a sliding window algorithm to calculate reliability scores
    based on historical performance metrics including response times, success rates,
    and consecutive failures.
    """

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        """Initialize the SourceReliabilityService."""
        self.db_manager = db_manager or DatabaseManager()
        logger.info("SourceReliabilityService initialized")

    def create_tracker(self, source_name: str, asset_type: str, asset_id: str) -> SourceReliabilityTracker:
        """
        Create a new reliability tracker for a source.

        Args:
            source_name: Name of the data source
            asset_type: Type of asset ('stamp' or 'src20')
            asset_id: Asset identifier

        Returns:
            New SourceReliabilityTracker instance
        """
        return SourceReliabilityTracker(source_name, asset_type, asset_id)

    def record_call_metrics(self, tracker: SourceReliabilityTracker) -> None:
        """
        Record API call metrics in the database and update reliability scores.

        Args:
            tracker: SourceReliabilityTracker with recorded metrics

        Raises:
            DatabaseError: If database operation fails
        """
        try:
            metrics = tracker.get_metrics()

            if metrics["success"] is None:
                logger.warning(f"Cannot record metrics: no success/failure recorded for {tracker.source_name}")
                return

            # Record the individual call metrics
            self._insert_call_record(metrics)

            # Update the aggregated source reliability data
            self._update_source_reliability(
                metrics["source_name"],
                metrics["asset_type"],
                metrics["asset_id"],
                metrics["response_time_ms"],
                metrics["success"],
            )

            # Check for alerts
            self._check_reliability_alerts(metrics["source_name"], metrics["asset_type"], metrics["asset_id"])

            logger.debug(f"Recorded call metrics for {tracker.source_name} ({tracker.asset_type}:{tracker.asset_id})")

        except Exception as e:
            logger.error(f"Error recording call metrics: {e}")
            raise exceptions.DatabaseError(f"Failed to record call metrics: {e}")

    def get_source_reliability(self, source_name: str, asset_type: str, asset_id: str) -> Optional[Dict]:
        """
        Get current reliability data for a specific source.

        Args:
            source_name: Name of the data source
            asset_type: Type of asset
            asset_id: Asset identifier

        Returns:
            Dictionary with reliability data or None if not found
        """
        try:
            db = self.db_manager.connect()
            try:
                with db.cursor() as cursor:
                    query = f"""
                        SELECT
                            source_name, asset_type, asset_id,
                            source_confidence, api_response_time_ms, success_rate_24h,
                            last_success, last_failure, consecutive_failures,
                            last_updated, update_count_24h
                        FROM {MARKET_DATA_SOURCES_TABLE}
                        WHERE source_name = %s AND asset_type = %s AND asset_id = %s
                    """
                    cursor.execute(query, (source_name, asset_type, asset_id))
                    result = cursor.fetchone()

                    if result is None:
                        return None

                    return {
                        "source_name": result[0],
                        "asset_type": result[1],
                        "asset_id": result[2],
                        "source_confidence": float(result[3]) if result[3] is not None else None,
                        "api_response_time_ms": result[4],
                        "success_rate_24h": float(result[5]) if result[5] is not None else None,
                        "last_success": result[6],
                        "last_failure": result[7],
                        "consecutive_failures": result[8],
                        "last_updated": result[9],
                        "update_count_24h": result[10],
                    }

            finally:
                db.close()

        except Exception as e:
            logger.error(f"Error getting source reliability for {source_name}: {e}")
            raise exceptions.DatabaseError(f"Failed to get source reliability: {e}")

    def get_all_source_reliabilities(self, asset_type: Optional[str] = None) -> List[Dict]:
        """
        Get reliability data for all sources, optionally filtered by asset type.

        Args:
            asset_type: Optional filter by asset type ('stamp' or 'src20')

        Returns:
            List of dictionaries with reliability data
        """
        try:
            db = self.db_manager.connect()
            try:
                with db.cursor() as cursor:
                    if asset_type:
                        query = f"""
                            SELECT
                                source_name, asset_type, asset_id,
                                source_confidence, api_response_time_ms, success_rate_24h,
                                last_success, last_failure, consecutive_failures,
                                last_updated, update_count_24h
                            FROM {MARKET_DATA_SOURCES_TABLE}
                            WHERE asset_type = %s
                            ORDER BY source_confidence DESC, success_rate_24h DESC
                        """
                        cursor.execute(query, (asset_type,))
                    else:
                        query = f"""
                            SELECT
                                source_name, asset_type, asset_id,
                                source_confidence, api_response_time_ms, success_rate_24h,
                                last_success, last_failure, consecutive_failures,
                                last_updated, update_count_24h
                            FROM {MARKET_DATA_SOURCES_TABLE}
                            ORDER BY source_confidence DESC, success_rate_24h DESC
                        """
                        cursor.execute(query)

                    results = cursor.fetchall()

                    return [
                        {
                            "source_name": row[0],
                            "asset_type": row[1],
                            "asset_id": row[2],
                            "source_confidence": float(row[3]) if row[3] is not None else None,
                            "api_response_time_ms": row[4],
                            "success_rate_24h": float(row[5]) if row[5] is not None else None,
                            "last_success": row[6],
                            "last_failure": row[7],
                            "consecutive_failures": row[8],
                            "last_updated": row[9],
                            "update_count_24h": row[10],
                        }
                        for row in results
                    ]

            finally:
                db.close()

        except Exception as e:
            logger.error(f"Error getting all source reliabilities: {e}")
            raise exceptions.DatabaseError(f"Failed to get source reliabilities: {e}")

    def calculate_reliability_score(self, success_rate: float, avg_response_time_ms: int, consecutive_failures: int) -> float:
        """
        Calculate reliability score based on performance metrics.

        Uses a weighted algorithm combining success rate, response time, and failure streak.

        Args:
            success_rate: Success rate percentage (0-100)
            avg_response_time_ms: Average response time in milliseconds
            consecutive_failures: Number of consecutive failures

        Returns:
            Reliability score from 0.0 to 10.0
        """
        # Success rate component (0-10)
        success_score = (success_rate / 100.0) * MAX_RELIABILITY_SCORE

        # Response time component (0-10)
        if avg_response_time_ms <= EXCELLENT_RESPONSE_TIME:
            response_score = MAX_RELIABILITY_SCORE
        elif avg_response_time_ms <= GOOD_RESPONSE_TIME:
            # Linear interpolation between excellent and good (10 -> 8)
            response_score = MAX_RELIABILITY_SCORE - 2.0 * (
                (avg_response_time_ms - EXCELLENT_RESPONSE_TIME) / (GOOD_RESPONSE_TIME - EXCELLENT_RESPONSE_TIME)
            )
        elif avg_response_time_ms <= POOR_RESPONSE_TIME:
            # Linear interpolation between good and poor (8 -> 6)
            response_score = 8.0 - 2.0 * (
                (avg_response_time_ms - GOOD_RESPONSE_TIME) / (POOR_RESPONSE_TIME - GOOD_RESPONSE_TIME)
            )
        else:
            response_score = MIN_RELIABILITY_SCORE  # Very poor response time

        # Consecutive failures penalty (0-10)
        if consecutive_failures == 0:
            failure_score = MAX_RELIABILITY_SCORE
        elif consecutive_failures <= 2:
            failure_score = 8.0
        elif consecutive_failures <= 5:
            failure_score = 5.0
        else:
            failure_score = 0.0  # Too many consecutive failures

        # Weighted average
        total_score = (
            success_score * SUCCESS_RATE_WEIGHT
            + response_score * RESPONSE_TIME_WEIGHT
            + failure_score * CONSECUTIVE_FAILURES_WEIGHT
        )

        # Clamp to valid range
        return max(MIN_RELIABILITY_SCORE, min(MAX_RELIABILITY_SCORE, total_score))

    def get_low_reliability_sources(self, threshold: float = LOW_RELIABILITY_THRESHOLD) -> List[Dict]:
        """
        Get sources with reliability scores below the threshold.

        Args:
            threshold: Minimum acceptable reliability score

        Returns:
            List of sources with low reliability scores
        """
        try:
            all_sources = self.get_all_source_reliabilities()
            return [
                source
                for source in all_sources
                if source["source_confidence"] is not None and source["source_confidence"] < threshold
            ]
        except Exception as e:
            logger.error(f"Error getting low reliability sources: {e}")
            return []

    def _insert_call_record(self, metrics: Dict) -> None:
        """Insert a record of an individual API call (not implemented - for future historical tracking)."""
        # This could be implemented to store detailed call history in a separate table
        # For now, we only update the aggregated metrics in market_data_sources
        pass

    def _update_source_reliability(
        self, source_name: str, asset_type: str, asset_id: str, response_time_ms: int, success: bool
    ) -> None:
        """
        Update aggregated reliability data for a source.

        Args:
            source_name: Name of the data source
            asset_type: Type of asset
            asset_id: Asset identifier
            response_time_ms: Response time for this call
            success: Whether the call was successful
        """
        try:
            db = self.db_manager.connect()
            try:
                with db.cursor() as cursor:
                    # Get current metrics within the sliding window
                    # TODO: Implement time window filtering for historical metrics

                    # First, try to get existing record
                    cursor.execute(
                        f"""
                        SELECT
                            api_response_time_ms, success_rate_24h, consecutive_failures,
                            last_success, last_failure, update_count_24h
                        FROM {MARKET_DATA_SOURCES_TABLE}
                        WHERE source_name = %s AND asset_type = %s AND asset_id = %s
                        """,
                        (source_name, asset_type, asset_id),
                    )
                    existing = cursor.fetchone()

                    if existing and len(existing) >= 6:
                        # Update existing record
                        (
                            current_avg_time,
                            current_success_rate,
                            consecutive_failures,
                            last_success,
                            last_failure,
                            update_count,
                        ) = existing

                        # Update consecutive failures
                        if success:
                            consecutive_failures = 0
                            last_success = datetime.now()
                        else:
                            consecutive_failures = (consecutive_failures or 0) + 1
                            last_failure = datetime.now()

                        # Calculate new moving averages (simplified - could be enhanced with more sophisticated sliding window)
                        # For now, use simple weighted average favoring recent data
                        new_avg_time = (
                            int((current_avg_time * 0.8 + response_time_ms * 0.2)) if current_avg_time else response_time_ms
                        )

                        # Update success rate (simplified calculation)
                        update_count = (update_count or 0) + 1
                        if current_success_rate is not None:
                            # Weighted moving average for success rate
                            success_value = 100.0 if success else 0.0
                            new_success_rate = current_success_rate * 0.9 + success_value * 0.1
                        else:
                            new_success_rate = 100.0 if success else 0.0

                        # Calculate new reliability score
                        new_confidence = self.calculate_reliability_score(new_success_rate, new_avg_time, consecutive_failures)

                        # Update the record
                        cursor.execute(
                            f"""
                            UPDATE {MARKET_DATA_SOURCES_TABLE}
                            SET
                                api_response_time_ms = %s,
                                success_rate_24h = %s,
                                source_confidence = %s,
                                consecutive_failures = %s,
                                last_success = %s,
                                last_failure = %s,
                                update_count_24h = %s,
                                last_updated = NOW()
                            WHERE source_name = %s AND asset_type = %s AND asset_id = %s
                            """,
                            (
                                new_avg_time,
                                new_success_rate,
                                new_confidence,
                                consecutive_failures,
                                last_success,
                                last_failure,
                                update_count,
                                source_name,
                                asset_type,
                                asset_id,
                            ),
                        )
                    else:
                        # Create new record
                        consecutive_failures = 0 if success else 1
                        success_rate = 100.0 if success else 0.0
                        confidence = self.calculate_reliability_score(success_rate, response_time_ms, consecutive_failures)

                        cursor.execute(
                            f"""
                            INSERT INTO {MARKET_DATA_SOURCES_TABLE}
                            (asset_type, asset_id, source_name, api_response_time_ms, success_rate_24h,
                             source_confidence, consecutive_failures, last_success, last_failure,
                             update_count_24h, last_updated, created_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                            """,
                            (
                                asset_type,
                                asset_id,
                                source_name,
                                response_time_ms,
                                success_rate,
                                confidence,
                                consecutive_failures,
                                datetime.now() if success else None,
                                datetime.now() if not success else None,
                                1,
                            ),
                        )

                    db.commit()

            finally:
                db.close()

        except Exception as e:
            logger.error(f"Error updating source reliability: {e}")
            raise

    def _check_reliability_alerts(self, source_name: str, asset_type: str, asset_id: str) -> None:
        """
        Check if alerts should be triggered for a source.

        Args:
            source_name: Name of the data source
            asset_type: Type of asset
            asset_id: Asset identifier
        """
        try:
            reliability_data = self.get_source_reliability(source_name, asset_type, asset_id)
            if not reliability_data:
                return

            confidence = reliability_data.get("source_confidence", 0)
            consecutive_failures = reliability_data.get("consecutive_failures", 0)

            # Critical reliability alert
            if confidence < CRITICAL_RELIABILITY_THRESHOLD:
                logger.error(
                    f"CRITICAL: Source {source_name} ({asset_type}:{asset_id}) has reliability score {confidence:.1f} "
                    f"(threshold: {CRITICAL_RELIABILITY_THRESHOLD})"
                )

            # Low reliability warning
            elif confidence < LOW_RELIABILITY_THRESHOLD:
                logger.warning(
                    f"WARNING: Source {source_name} ({asset_type}:{asset_id}) has low reliability score {confidence:.1f} "
                    f"(threshold: {LOW_RELIABILITY_THRESHOLD})"
                )

            # Consecutive failures alert
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                logger.error(
                    f"ALERT: Source {source_name} ({asset_type}:{asset_id}) has {consecutive_failures} "
                    f"consecutive failures (max: {MAX_CONSECUTIVE_FAILURES})"
                )

        except Exception as e:
            logger.error(f"Error checking reliability alerts: {e}")


# Module-level service instance for easy import
source_reliability_service = SourceReliabilityService()


def create_reliability_tracker(source_name: str, asset_type: str, asset_id: str) -> SourceReliabilityTracker:
    """
    Create a reliability tracker for a data source.

    Args:
        source_name: Name of the data source
        asset_type: Type of asset ('stamp' or 'src20')
        asset_id: Asset identifier

    Returns:
        New SourceReliabilityTracker instance
    """
    return source_reliability_service.create_tracker(source_name, asset_type, asset_id)


def record_call_metrics(tracker: SourceReliabilityTracker) -> None:
    """
    Record API call metrics using the module-level service.

    Args:
        tracker: SourceReliabilityTracker with recorded metrics
    """
    source_reliability_service.record_call_metrics(tracker)


def get_source_reliability(source_name: str, asset_type: str, asset_id: str) -> Optional[Dict]:
    """
    Get reliability data for a specific source.

    Args:
        source_name: Name of the data source
        asset_type: Type of asset
        asset_id: Asset identifier

    Returns:
        Dictionary with reliability data or None if not found
    """
    return source_reliability_service.get_source_reliability(source_name, asset_type, asset_id)


def get_all_source_reliabilities(asset_type: Optional[str] = None) -> List[Dict]:
    """
    Get reliability data for all sources.

    Args:
        asset_type: Optional filter by asset type

    Returns:
        List of dictionaries with reliability data
    """
    return source_reliability_service.get_all_source_reliabilities(asset_type)


def get_low_reliability_sources(threshold: float = LOW_RELIABILITY_THRESHOLD) -> List[Dict]:
    """
    Get sources with low reliability scores.

    Args:
        threshold: Minimum acceptable reliability score

    Returns:
        List of sources with low reliability scores
    """
    return source_reliability_service.get_low_reliability_sources(threshold)
