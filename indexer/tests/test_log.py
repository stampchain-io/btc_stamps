"""Tests for the logging module."""

import logging
import os
import tempfile
from unittest.mock import MagicMock, patch

from index_core import log


class TestModuleLoggingFilter:
    """Test cases for ModuleLoggingFilter class."""

    def test_init_with_simple_filters(self):
        """Test filter initialization with simple filters."""
        filter_obj = log.ModuleLoggingFilter("module1,module2")
        assert filter_obj.filters == ["module1", "module2"]
        assert filter_obj.catchall is False

    def test_init_with_catchall(self):
        """Test filter initialization with catchall wildcard."""
        filter_obj = log.ModuleLoggingFilter("*,-module1,module2")
        assert filter_obj.filters == ["-module1", "module2"]
        assert filter_obj.catchall is True

    def test_filter_exact_match(self):
        """Test filtering with exact module name match."""
        filter_obj = log.ModuleLoggingFilter("test.module")
        record = MagicMock()
        record.name = "test.module"
        assert filter_obj.filter(record) is True

    def test_filter_prefix_match(self):
        """Test filtering with module name prefix match."""
        filter_obj = log.ModuleLoggingFilter("test.module")
        record = MagicMock()
        record.name = "test.module.submodule"
        assert filter_obj.filter(record) is True

    def test_filter_no_match(self):
        """Test filtering with no match."""
        filter_obj = log.ModuleLoggingFilter("test.module")
        record = MagicMock()
        record.name = "other.module"
        assert filter_obj.filter(record) is False

    def test_filter_negative_match(self):
        """Test filtering with negative match."""
        filter_obj = log.ModuleLoggingFilter("-test.module")
        record = MagicMock()
        record.name = "test.module"
        assert filter_obj.filter(record) is False

    def test_filter_catchall_with_exceptions(self):
        """Test filtering with catchall and exceptions."""
        filter_obj = log.ModuleLoggingFilter("*,-test.module")

        # Should allow most modules
        record1 = MagicMock()
        record1.name = "other.module"
        assert filter_obj.filter(record1) is True

        # Should block excluded module
        record2 = MagicMock()
        record2.name = "test.module"
        assert filter_obj.filter(record2) is False

    def test_ismatch_empty_name(self):
        """Test ismatch with empty name."""
        record = MagicMock()
        record.name = "test.module"
        assert log.ModuleLoggingFilter.ismatch(record, "") is True

    def test_ismatch_exact(self):
        """Test ismatch with exact match."""
        record = MagicMock()
        record.name = "test.module"
        assert log.ModuleLoggingFilter.ismatch(record, "test.module") is True

    def test_ismatch_prefix(self):
        """Test ismatch with prefix match."""
        record = MagicMock()
        record.name = "test.module.submodule"
        assert log.ModuleLoggingFilter.ismatch(record, "test.module") is True

    def test_ismatch_no_match(self):
        """Test ismatch with no match."""
        record = MagicMock()
        record.name = "other.module"
        assert log.ModuleLoggingFilter.ismatch(record, "test.module") is False


class TestBlockStatusLogging:
    """Test cases for custom block status logging."""

    def test_block_status_level_defined(self):
        """Test that BLOCK_STATUS level is properly defined."""
        assert log.BLOCK_STATUS == 25
        assert logging.getLevelName(log.BLOCK_STATUS) == "BLOCK"

    def test_block_status_method_exists(self):
        """Test that block_status method is added to Logger."""
        logger = logging.getLogger("test")
        assert hasattr(logger, "block_status")

    def test_block_status_method_logs(self):
        """Test that block_status method actually logs."""
        logger = logging.getLogger("test")
        logger.setLevel(logging.DEBUG)

        with patch.object(logger, "_log") as mock_log:
            logger.block_status("Test message")  # type: ignore[attr-defined]
            mock_log.assert_called_once()
            assert mock_log.call_args[0][0] == log.BLOCK_STATUS


class TestSetUp:
    """Test cases for set_up function."""

    def setup_method(self):
        """Reset logging state before each test."""
        log.LOGGING_SETUP = False
        log.LOGGING_TOFILE_SETUP = False
        log.ROOT_LOGGER = None

    def test_basic_setup(self):
        """Test basic logger setup."""
        logger = logging.getLogger("test_setup")
        result = log.set_up(logger)

        assert result == logger
        assert log.LOGGING_SETUP is True
        assert len(logger.handlers) > 0

    def test_verbose_setup(self):
        """Test logger setup with verbose mode."""
        logger = logging.getLogger("test_verbose")
        log.set_up(logger, verbose=True)

        assert logger.level == logging.DEBUG

    def test_setup_with_env_debug(self):
        """Test logger setup with DEBUG environment variable."""
        logger = logging.getLogger("test_env_debug")
        with patch.dict(os.environ, {"DEBUG": "true"}):
            log.set_up(logger)

        assert logger.level == logging.DEBUG

    def test_setup_with_logfile(self):
        """Test logger setup with log file."""
        logger = logging.getLogger("test_logfile")

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            logfile_path = tmp.name

        try:
            log.set_up(logger, logfile=logfile_path)
            assert log.LOGGING_TOFILE_SETUP is True

            # Check that file handler was added
            file_handlers = [h for h in logger.handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
            assert len(file_handlers) > 0
        finally:
            if os.path.exists(logfile_path):
                os.unlink(logfile_path)

    def test_setup_with_console_filter(self):
        """Test logger setup with console log filter."""
        logger = logging.getLogger("test_filter")
        log.set_up(logger, console_logfilter="test.module,-other.module")

        # Check that filter was added to console handler
        console_handlers = [h for h in logger.handlers if isinstance(h, logging.StreamHandler)]
        assert len(console_handlers) > 0
        assert any(isinstance(f, log.ModuleLoggingFilter) for f in console_handlers[0].filters)

    def test_setup_already_configured(self):
        """Test that repeated setup calls don't duplicate handlers."""
        logger = logging.getLogger("test_repeat")

        # First setup
        log.set_up(logger)
        handler_count = len(logger.handlers)

        # Second setup
        log.set_up(logger)
        assert len(logger.handlers) == handler_count

    def test_setup_quietens_noisy_libraries(self):
        """Test that setup quietens requests and urllib3 loggers."""
        logger = logging.getLogger("test_quiet")
        log.set_up(logger)

        requests_logger = logging.getLogger("requests")
        urllib3_logger = logging.getLogger("urllib3")

        assert requests_logger.level == logging.WARNING
        assert urllib3_logger.level == logging.WARNING
        assert requests_logger.propagate is False
        assert urllib3_logger.propagate is False


class TestUtilityFunctions:
    """Test cases for utility functions."""

    def test_create_progress_bar(self):
        """Test progress bar creation."""
        # Test empty progress
        assert log.create_progress_bar(0.0, 10) == "[░░░░░░░░░░]"

        # Test half progress
        assert log.create_progress_bar(0.5, 10) == "[█████░░░░░]"

        # Test full progress
        assert log.create_progress_bar(1.0, 10) == "[██████████]"

        # Test custom width
        assert log.create_progress_bar(0.5, 20) == "[██████████░░░░░░░░░░]"

    def test_get_speed_indicator(self):
        """Test speed indicator selection."""
        assert log.get_speed_indicator(0.05) == "🚀"  # Very fast
        assert log.get_speed_indicator(0.3) == "⚡"  # Fast
        assert log.get_speed_indicator(1.0) == "🏃"  # Normal
        assert log.get_speed_indicator(3.0) == "🚶"  # Slow
        assert log.get_speed_indicator(10.0) == "🐌"  # Very slow

    def test_get_activity_indicator(self):
        """Test activity indicator selection."""
        assert log.get_activity_indicator(0, 0, 0) == "💤"  # No activity
        assert log.get_activity_indicator(1, 0, 0) == "📝"  # Light
        assert log.get_activity_indicator(3, 2, 0) == "📊"  # Moderate
        assert log.get_activity_indicator(20, 5, 0) == "🔥"  # High
        assert log.get_activity_indicator(40, 20, 0) == "💥"  # Very high

    def test_format_eta(self):
        """Test ETA formatting."""
        assert log.format_eta(30) == "30s"
        assert log.format_eta(90) == "1m"
        assert log.format_eta(3600) == "1h 00m"
        assert log.format_eta(3750) == "1h 02m"
        assert log.format_eta(7200) == "2h 00m"


class TestLogEnhancedBlockStatus:
    """Test cases for log_enhanced_block_status function."""

    @patch("logging.getLogger")
    def test_compact_mode_at_tip(self, mock_get_logger):
        """Test enhanced block status logging in compact mode at tip."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        log.log_enhanced_block_status(
            block_index=1000,
            block_tip=1002,  # Within 5 blocks - at tip
            processing_time=0.5,
            avg_time="0.6s",
            stamps_in_block=5,
            src20_in_block=3,
            src101_in_block=1,
            display_mode="compact",
        )

        mock_logger.block_status.assert_called_once()
        call_args = mock_logger.block_status.call_args[0]
        # Check individual arguments instead of formatted string
        assert call_args[1] == "1000"
        assert call_args[2] == "1002"
        assert call_args[3] == "0.50"
        assert call_args[4] == "0.6s"
        assert call_args[6] == 5  # stamps
        assert call_args[7] == 3  # src20
        assert call_args[8] == 1  # src101

    @patch("logging.getLogger")
    def test_compact_mode_with_eta(self, mock_get_logger):
        """Test enhanced block status logging in compact mode with ETA."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        log.log_enhanced_block_status(
            block_index=900,
            block_tip=1000,
            processing_time=0.5,
            avg_time="0.6s",
            stamps_in_block=5,
            src20_in_block=3,
            src101_in_block=1,
            eta_seconds=120,
            display_mode="compact",
        )

        mock_logger.block_status.assert_called_once()
        call_args = mock_logger.block_status.call_args[0]
        # Check that ETA is formatted correctly
        assert call_args[5] == "2m"  # ETA argument

    @patch("logging.getLogger")
    def test_enhanced_mode(self, mock_get_logger):
        """Test enhanced block status logging in enhanced mode."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        log.log_enhanced_block_status(
            block_index=500,
            block_tip=1000,
            processing_time=0.3,
            avg_time="0.4s",
            stamps_in_block=10,
            src20_in_block=5,
            src101_in_block=2,
            display_mode="enhanced",
        )

        mock_logger.block_status.assert_called_once()
        call_args = mock_logger.block_status.call_args[0]
        assert "🔗 Block" in call_args[0]
        assert "⚡" in call_args[0]  # Speed indicator for fast processing

    @patch("logging.getLogger")
    def test_detailed_mode(self, mock_get_logger):
        """Test enhanced block status logging in detailed mode."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        log.log_enhanced_block_status(
            block_index=800,
            block_tip=1000,
            processing_time=2.0,
            avg_time="1.5s",
            stamps_in_block=15,
            src20_in_block=10,
            src101_in_block=5,
            eta_seconds=300,
            display_mode="detailed",
        )

        # In detailed mode, multiple log calls are made
        assert mock_logger.block_status.call_count >= 3

    @patch("logging.getLogger")
    def test_zmq_indicator(self, mock_get_logger):
        """Test ZMQ indicator in block status."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        log.log_enhanced_block_status(
            block_index=1000,
            block_tip=1000,
            processing_time=0.1,
            avg_time="0.2s",
            stamps_in_block=1,
            src20_in_block=0,
            is_zmq=True,
            display_mode="compact",
        )

        mock_logger.block_status.assert_called_once()
        call_args = mock_logger.block_status.call_args[0]
        assert "(ZMQ)" in str(call_args) or "📡" in str(call_args)

    @patch("logging.getLogger")
    def test_progress_calculation_with_start_block(self, mock_get_logger):
        """Test progress calculation with custom start block."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        log.log_enhanced_block_status(
            block_index=750,
            block_tip=1000,
            processing_time=0.5,
            avg_time="0.6s",
            stamps_in_block=5,
            src20_in_block=3,
            start_block=500,
            display_mode="compact",
        )

        mock_logger.block_status.assert_called_once()
        call_args = mock_logger.block_status.call_args[0]
        # Progress should be 50% ((750-500)/(1000-500))
        assert "50.0%" in str(call_args) or "50%" in str(call_args)


class TestSetLogger:
    """Test cases for set_logger function."""

    def setup_method(self):
        """Reset logger state before each test."""
        log.ROOT_LOGGER = None

    def test_set_logger_first_time(self):
        """Test setting logger for the first time."""
        test_logger = logging.getLogger("test_root")
        log.set_logger(test_logger)
        assert log.ROOT_LOGGER == test_logger

    def test_set_logger_already_set(self):
        """Test that logger is not overwritten once set."""
        first_logger = logging.getLogger("first")
        second_logger = logging.getLogger("second")

        log.set_logger(first_logger)
        log.set_logger(second_logger)

        assert log.ROOT_LOGGER == first_logger
