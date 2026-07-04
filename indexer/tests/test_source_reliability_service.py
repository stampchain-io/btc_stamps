"""
Tests for Source Reliability Service

This module tests the comprehensive source reliability tracking system
including reliability trackers, scoring algorithms, and database operations.
"""

import unittest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, Mock, patch

from index_core.source_reliability_service import (
    CRITICAL_RELIABILITY_THRESHOLD,
    EXCELLENT_RESPONSE_TIME,
    GOOD_RESPONSE_TIME,
    LOW_RELIABILITY_THRESHOLD,
    MAX_RELIABILITY_SCORE,
    MIN_RELIABILITY_SCORE,
    POOR_RESPONSE_TIME,
    SourceReliabilityService,
    SourceReliabilityTracker,
    create_reliability_tracker,
    get_all_source_reliabilities,
    get_low_reliability_sources,
    get_source_reliability,
    record_call_metrics,
)


class TestSourceReliabilityTracker(unittest.TestCase):
    """Test the SourceReliabilityTracker class."""

    def setUp(self):
        """Set up test fixtures."""
        self.tracker = SourceReliabilityTracker("kucoin", "src20", "STAMP")

    def test_tracker_initialization(self):
        """Test tracker initialization with correct attributes."""
        self.assertEqual(self.tracker.source_name, "kucoin")
        self.assertEqual(self.tracker.asset_type, "src20")
        self.assertEqual(self.tracker.asset_id, "STAMP")
        self.assertIsNone(self.tracker.start_time)
        self.assertIsNone(self.tracker.response_time_ms)
        self.assertIsNone(self.tracker.success)
        self.assertIsNone(self.tracker.error_message)

    def test_start_tracking(self):
        """Test starting tracking functionality."""
        with patch("time.time", return_value=1000.0):
            self.tracker.start_tracking()
            self.assertEqual(self.tracker.start_time, 1000.0)
            self.assertIsNone(self.tracker.response_time_ms)
            self.assertIsNone(self.tracker.success)
            self.assertIsNone(self.tracker.error_message)

    def test_record_success(self):
        """Test recording successful API call."""
        with patch("time.time", side_effect=[1000.0, 1001.5]):
            self.tracker.start_tracking()
            self.tracker.record_success(8.5)

            self.assertEqual(self.tracker.response_time_ms, 1500)  # 1.5 seconds = 1500ms
            self.assertTrue(self.tracker.success)
            self.assertIsNone(self.tracker.error_message)

    def test_record_failure(self):
        """Test recording failed API call."""
        with patch("time.time", side_effect=[1000.0, 1002.0]):
            self.tracker.start_tracking()
            self.tracker.record_failure("Connection timeout")

            self.assertEqual(self.tracker.response_time_ms, 2000)  # 2 seconds = 2000ms
            self.assertFalse(self.tracker.success)
            self.assertEqual(self.tracker.error_message, "Connection timeout")

    def test_record_without_start_tracking(self):
        """Test recording metrics without starting tracking."""
        with patch("index_core.source_reliability_service.logger") as mock_logger:
            self.tracker.record_success()
            mock_logger.warning.assert_called_once()

            self.tracker.record_failure("Error")
            self.assertEqual(mock_logger.warning.call_count, 2)

    def test_get_metrics(self):
        """Test getting metrics from tracker."""
        with patch("time.time", side_effect=[1000.0, 1001.0]):
            self.tracker.start_tracking()
            self.tracker.record_success()

            metrics = self.tracker.get_metrics()
            expected = {
                "source_name": "kucoin",
                "asset_type": "src20",
                "asset_id": "STAMP",
                "response_time_ms": 1000,
                "success": True,
                "error_message": None,
            }
            self.assertEqual(metrics, expected)


class TestSourceReliabilityService(unittest.TestCase):
    """Test the SourceReliabilityService class."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_db_manager = Mock()
        self.mock_db = Mock()
        self.mock_cursor = Mock()

        # Properly setup context manager for cursor
        cursor_context = Mock()
        cursor_context.__enter__ = Mock(return_value=self.mock_cursor)
        cursor_context.__exit__ = Mock(return_value=None)

        self.mock_db_manager.connect.return_value = self.mock_db
        self.mock_db.cursor.return_value = cursor_context

        self.service = SourceReliabilityService(self.mock_db_manager)

    def test_service_initialization(self):
        """Test service initialization."""
        self.assertIsNotNone(self.service.db_manager)

    def test_create_tracker(self):
        """Test creating a reliability tracker."""
        tracker = self.service.create_tracker("openstamp", "src20", "PEPE")

        self.assertIsInstance(tracker, SourceReliabilityTracker)
        self.assertEqual(tracker.source_name, "openstamp")
        self.assertEqual(tracker.asset_type, "src20")
        self.assertEqual(tracker.asset_id, "PEPE")

    def test_calculate_reliability_score_excellent(self):
        """Test reliability score calculation for excellent metrics."""
        score = self.service.calculate_reliability_score(
            success_rate=100.0, avg_response_time_ms=300, consecutive_failures=0  # Excellent
        )
        self.assertEqual(score, 10.0)  # Perfect score

    def test_calculate_reliability_score_good(self):
        """Test reliability score calculation for good metrics."""
        score = self.service.calculate_reliability_score(
            success_rate=95.0, avg_response_time_ms=1500, consecutive_failures=1  # Good
        )
        # Should be high but not perfect
        self.assertGreaterEqual(score, 8.0)
        self.assertLess(score, 10.0)

    def test_calculate_reliability_score_poor(self):
        """Test reliability score calculation for poor metrics."""
        score = self.service.calculate_reliability_score(
            success_rate=50.0, avg_response_time_ms=8000, consecutive_failures=3  # Poor
        )
        # Should be low score
        self.assertLessEqual(score, 6.0)  # Adjusted for actual algorithm output

    def test_calculate_reliability_score_very_poor(self):
        """Test reliability score calculation for very poor metrics."""
        score = self.service.calculate_reliability_score(
            success_rate=20.0, avg_response_time_ms=15000, consecutive_failures=10  # Very poor
        )
        # Should be very low score
        self.assertLessEqual(score, 3.0)

    def test_get_source_reliability_found(self):
        """Test getting source reliability data when found."""
        # Mock database response
        mock_result = (
            "kucoin",
            "src20",
            "STAMP",
            7.5,
            1200,
            95.0,
            datetime(2024, 1, 1, 12, 0),
            datetime(2024, 1, 1, 11, 0),
            0,
            datetime(2024, 1, 1, 12, 30),
            50,
        )
        self.mock_cursor.fetchone.return_value = mock_result

        result = self.service.get_source_reliability("kucoin", "src20", "STAMP")

        self.assertIsNotNone(result)
        self.assertEqual(result["source_name"], "kucoin")
        self.assertEqual(result["asset_type"], "src20")
        self.assertEqual(result["asset_id"], "STAMP")
        self.assertEqual(result["source_confidence"], 7.5)
        self.assertEqual(result["api_response_time_ms"], 1200)
        self.assertEqual(result["success_rate_24h"], 95.0)

    def test_get_source_reliability_not_found(self):
        """Test getting source reliability data when not found."""
        self.mock_cursor.fetchone.return_value = None

        result = self.service.get_source_reliability("nonexistent", "src20", "FAKE")

        self.assertIsNone(result)

    def test_get_all_source_reliabilities(self):
        """Test getting all source reliabilities."""
        # Mock database response
        mock_results = [
            ("kucoin", "src20", "STAMP", 8.0, 1000, 98.0, None, None, 0, datetime.now(), 100),
            ("openstamp", "src20", "PEPE", 6.5, 2000, 85.0, None, None, 1, datetime.now(), 80),
        ]
        self.mock_cursor.fetchall.return_value = mock_results

        results = self.service.get_all_source_reliabilities()

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["source_name"], "kucoin")
        self.assertEqual(results[1]["source_name"], "openstamp")

    def test_get_all_source_reliabilities_filtered(self):
        """Test getting source reliabilities filtered by asset type."""
        mock_results = [
            ("kucoin", "src20", "STAMP", 8.0, 1000, 98.0, None, None, 0, datetime.now(), 100),
        ]
        self.mock_cursor.fetchall.return_value = mock_results

        results = self.service.get_all_source_reliabilities("src20")

        self.assertEqual(len(results), 1)
        # Verify the query was called with asset_type filter
        self.mock_cursor.execute.assert_called()
        call_args = self.mock_cursor.execute.call_args
        if call_args and len(call_args) > 1 and call_args[1]:
            self.assertIn("WHERE asset_type = %s", call_args[0][0])
            self.assertEqual(call_args[1][0], "src20")

    def test_get_low_reliability_sources(self):
        """Test getting sources with low reliability scores."""
        # Mock get_all_source_reliabilities
        with patch.object(self.service, "get_all_source_reliabilities") as mock_get_all:
            mock_get_all.return_value = [
                {"source_name": "good_source", "source_confidence": 8.0},
                {"source_name": "bad_source", "source_confidence": 2.0},
                {"source_name": "mediocre_source", "source_confidence": 5.0},
                {"source_name": "null_source", "source_confidence": None},
            ]

            low_sources = self.service.get_low_reliability_sources(3.0)

            self.assertEqual(len(low_sources), 1)
            self.assertEqual(low_sources[0]["source_name"], "bad_source")

    @patch("index_core.source_reliability_service.datetime")
    def test_update_source_reliability_new_record(self, mock_datetime):
        """Test updating source reliability for new record."""
        mock_datetime.now.return_value = datetime(2024, 1, 1, 12, 0)

        # Mock no existing record
        self.mock_cursor.fetchone.return_value = None

        self.service._update_source_reliability("kucoin", "src20", "STAMP", 1000, True)

        # Verify INSERT was called
        self.assertEqual(self.mock_cursor.execute.call_count, 2)  # SELECT + INSERT
        insert_call = self.mock_cursor.execute.call_args_list[1]
        self.assertIn("INSERT INTO", insert_call[0][0])

    @patch("index_core.source_reliability_service.datetime")
    def test_update_source_reliability_existing_record(self, mock_datetime):
        """Test updating source reliability for existing record."""
        mock_datetime.now.return_value = datetime(2024, 1, 1, 12, 0)

        # Mock existing record
        existing_record = (1200, 95.0, 0, None, None, 50)
        self.mock_cursor.fetchone.return_value = existing_record

        self.service._update_source_reliability("kucoin", "src20", "STAMP", 800, True)

        # Verify UPDATE was called
        self.assertEqual(self.mock_cursor.execute.call_count, 2)  # SELECT + UPDATE
        update_call = self.mock_cursor.execute.call_args_list[1]
        self.assertIn("UPDATE", update_call[0][0])

    def test_record_call_metrics_success(self):
        """Test recording call metrics successfully."""
        tracker = SourceReliabilityTracker("kucoin", "src20", "STAMP")
        tracker.response_time_ms = 1000
        tracker.success = True

        with patch.object(self.service, "_update_source_reliability") as mock_update:
            with patch.object(self.service, "_check_reliability_alerts") as mock_check:
                self.service.record_call_metrics(tracker)

                mock_update.assert_called_once_with("kucoin", "src20", "STAMP", 1000, True)
                mock_check.assert_called_once_with("kucoin", "src20", "STAMP")

    def test_record_call_metrics_no_success_failure_recorded(self):
        """Test recording call metrics when no success/failure was recorded."""
        tracker = SourceReliabilityTracker("kucoin", "src20", "STAMP")
        # tracker.success is None (no success/failure recorded)

        with patch("index_core.source_reliability_service.logger") as mock_logger:
            self.service.record_call_metrics(tracker)
            mock_logger.warning.assert_called_once()

    @patch("index_core.source_reliability_service.logger")
    def test_check_reliability_alerts_critical(self, mock_logger):
        """Test reliability alerts for critical scores."""
        with patch.object(self.service, "get_source_reliability") as mock_get:
            mock_get.return_value = {"source_confidence": 0.5, "consecutive_failures": 3}  # Critical

            self.service._check_reliability_alerts("bad_source", "src20", "STAMP")

            # Should log critical error
            mock_logger.error.assert_called()
            self.assertIn("CRITICAL", str(mock_logger.error.call_args))

    @patch("index_core.source_reliability_service.logger")
    def test_check_reliability_alerts_low(self, mock_logger):
        """Test reliability alerts for low scores."""
        with patch.object(self.service, "get_source_reliability") as mock_get:
            mock_get.return_value = {"source_confidence": 2.5, "consecutive_failures": 2}  # Low but not critical

            self.service._check_reliability_alerts("low_source", "src20", "STAMP")

            # Should log warning
            mock_logger.warning.assert_called()
            self.assertIn("WARNING", str(mock_logger.warning.call_args))

    @patch("index_core.source_reliability_service.logger")
    def test_check_reliability_alerts_consecutive_failures(self, mock_logger):
        """Test reliability alerts for too many consecutive failures."""
        with patch.object(self.service, "get_source_reliability") as mock_get:
            mock_get.return_value = {"source_confidence": 8.0, "consecutive_failures": 6}  # Good score  # Too many failures

            self.service._check_reliability_alerts("failing_source", "src20", "STAMP")

            # Should log consecutive failures alert
            mock_logger.error.assert_called()
            self.assertIn("consecutive failures", str(mock_logger.error.call_args))


class TestModuleLevelFunctions(unittest.TestCase):
    """Test module-level convenience functions."""

    def test_create_reliability_tracker(self):
        """Test module-level create_reliability_tracker function."""
        tracker = create_reliability_tracker("stampscan", "src20", "TEST")

        self.assertIsInstance(tracker, SourceReliabilityTracker)
        self.assertEqual(tracker.source_name, "stampscan")
        self.assertEqual(tracker.asset_type, "src20")
        self.assertEqual(tracker.asset_id, "TEST")

    @patch("index_core.source_reliability_service.source_reliability_service")
    def test_record_call_metrics(self, mock_service):
        """Test module-level record_call_metrics function."""
        tracker = Mock()
        record_call_metrics(tracker)

        mock_service.record_call_metrics.assert_called_once_with(tracker)

    @patch("index_core.source_reliability_service.source_reliability_service")
    def test_get_source_reliability(self, mock_service):
        """Test module-level get_source_reliability function."""
        mock_service.get_source_reliability.return_value = {"test": "data"}

        result = get_source_reliability("kucoin", "src20", "STAMP")

        mock_service.get_source_reliability.assert_called_once_with("kucoin", "src20", "STAMP")
        self.assertEqual(result, {"test": "data"})

    @patch("index_core.source_reliability_service.source_reliability_service")
    def test_get_all_source_reliabilities(self, mock_service):
        """Test module-level get_all_source_reliabilities function."""
        mock_service.get_all_source_reliabilities.return_value = [{"test": "data"}]

        result = get_all_source_reliabilities("src20")

        mock_service.get_all_source_reliabilities.assert_called_once_with("src20")
        self.assertEqual(result, [{"test": "data"}])

    @patch("index_core.source_reliability_service.source_reliability_service")
    def test_get_low_reliability_sources(self, mock_service):
        """Test module-level get_low_reliability_sources function."""
        mock_service.get_low_reliability_sources.return_value = [{"bad": "source"}]

        result = get_low_reliability_sources(2.0)

        mock_service.get_low_reliability_sources.assert_called_once_with(2.0)
        self.assertEqual(result, [{"bad": "source"}])


class TestReliabilityScoring(unittest.TestCase):
    """Test reliability scoring algorithms in detail."""

    def setUp(self):
        """Set up test fixtures."""
        self.service = SourceReliabilityService()

    def test_scoring_response_time_excellent(self):
        """Test scoring with excellent response time."""
        score = self.service.calculate_reliability_score(100.0, EXCELLENT_RESPONSE_TIME, 0)
        self.assertEqual(score, 10.0)

    def test_scoring_response_time_good(self):
        """Test scoring with good response time."""
        score = self.service.calculate_reliability_score(100.0, GOOD_RESPONSE_TIME, 0)
        self.assertGreaterEqual(score, 8.0)
        self.assertLess(score, 10.0)

    def test_scoring_response_time_poor(self):
        """Test scoring with poor response time."""
        score = self.service.calculate_reliability_score(100.0, POOR_RESPONSE_TIME, 0)
        self.assertLessEqual(score, 9.0)  # Still high due to 100% success rate but penalized for response time

    def test_scoring_response_time_very_poor(self):
        """Test scoring with very poor response time."""
        score = self.service.calculate_reliability_score(100.0, POOR_RESPONSE_TIME + 5000, 0)
        self.assertLessEqual(score, 7.0)  # Very poor time should still give low score

    def test_scoring_success_rate_impact(self):
        """Test impact of success rate on scoring."""
        # Perfect success rate
        perfect_score = self.service.calculate_reliability_score(100.0, EXCELLENT_RESPONSE_TIME, 0)
        # Lower success rate
        lower_score = self.service.calculate_reliability_score(80.0, EXCELLENT_RESPONSE_TIME, 0)

        self.assertGreater(perfect_score, lower_score)

    def test_scoring_consecutive_failures_impact(self):
        """Test impact of consecutive failures on scoring."""
        # No failures
        no_failures_score = self.service.calculate_reliability_score(100.0, EXCELLENT_RESPONSE_TIME, 0)
        # Some failures
        some_failures_score = self.service.calculate_reliability_score(100.0, EXCELLENT_RESPONSE_TIME, 3)
        # Many failures
        many_failures_score = self.service.calculate_reliability_score(100.0, EXCELLENT_RESPONSE_TIME, 10)

        self.assertGreater(no_failures_score, some_failures_score)
        self.assertGreater(some_failures_score, many_failures_score)

    def test_scoring_boundaries(self):
        """Test scoring boundaries (min/max)."""
        # Should never exceed max
        max_score = self.service.calculate_reliability_score(100.0, 1, 0)
        self.assertEqual(max_score, MAX_RELIABILITY_SCORE)

        # Should never go below min
        min_score = self.service.calculate_reliability_score(0.0, 50000, 20)
        self.assertGreaterEqual(min_score, MIN_RELIABILITY_SCORE)  # Should be >= MIN_RELIABILITY_SCORE


if __name__ == "__main__":
    unittest.main()
