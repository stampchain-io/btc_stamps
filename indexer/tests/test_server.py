"""Comprehensive tests for server.py module."""

import logging
import os
import signal
import sys
import threading
from unittest import mock

import pytest


# Test fixtures to set up test environment
@pytest.fixture(autouse=True)
def mock_config():
    """Mock config values for tests."""
    with mock.patch("src.index_core.server.config") as mock_cfg:
        # Set default test values
        mock_cfg.TESTNET = False
        mock_cfg.BLOCK_FIRST = 0
        mock_cfg.BLOCK_FIRST_TESTNET = 1000
        mock_cfg.BLOCK_FIRST_REGTEST = 2000
        mock_cfg.BLOCK_FIRST_MAINNET = 0
        mock_cfg.DEFAULT_BACKEND_PORT = 8332
        mock_cfg.DEFAULT_BACKEND_PORT_TESTNET = 18332
        mock_cfg.DEFAULT_BACKEND_PORT_REGTEST = 18443
        mock_cfg.DEFAULT_REQUESTS_TIMEOUT = 10
        mock_cfg.DEFAULT_ESTIMATE_FEE_PER_KB = 1000
        mock_cfg.STAMPS_NAME = "stamps"
        mock_cfg.APP_NAME = "bitcoin-stamps"
        mock_cfg.USE_ASYNC_UPLOADS = False
        mock_cfg.STORE_FILES = False
        mock_cfg.AWS_SECRET_ACCESS_KEY = None
        mock_cfg.AWS_ACCESS_KEY_ID = None
        mock_cfg.AWS_S3_BUCKETNAME = None
        mock_cfg.AWS_S3_CLIENT = None
        mock_cfg.CHECKDB = False
        mock_cfg.CUSTOMNET = False
        mock_cfg.REGTEST = False
        mock_cfg.BACKEND_NAME = "bitcoincore"
        mock_cfg.BACKEND_CONNECT = "localhost"
        mock_cfg.BACKEND_PORT = 8332
        mock_cfg.BACKEND_SSL = False
        mock_cfg.BACKEND_SSL_NO_VERIFY = False
        mock_cfg.BACKEND_POLL_INTERVAL = 1.0
        mock_cfg.FORCE = False
        mock_cfg.PREFIX = b"stamp:"
        mock_cfg.CP_PREFIX = b"CNTRPRTY"
        mock_cfg.REQUESTS_TIMEOUT = 10
        mock_cfg.ESTIMATE_FEE_PER_KB = 1000
        mock_cfg.LOG = None
        mock_cfg.S3_OBJECTS = None
        mock_cfg.ZMQ_HOST = "tcp://localhost"
        mock_cfg.ZMQ_PORT_MAINNET_TX = 28332
        mock_cfg.ZMQ_PORT_MAINNET_BLOCK = 28333
        mock_cfg.ZMQ_PORT_TESTNET_TX = 38332
        mock_cfg.ZMQ_PORT_TESTNET_BLOCK = 38333
        mock_cfg.ZMQ_PORT_REGTEST_TX = 48332
        mock_cfg.ZMQ_PORT_REGTEST_BLOCK = 48333
        mock_cfg.ZMQ_TX_PORT = 28332
        mock_cfg.ZMQ_BLOCK_PORT = 28333
        yield mock_cfg


@pytest.fixture
def mock_backend():
    """Mock Backend instance."""
    with mock.patch("src.index_core.server.Backend") as mock_backend_cls:
        mock_instance = mock.MagicMock()
        mock_backend_cls.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_logger():
    """Mock logger."""
    with mock.patch("src.index_core.server.logger") as mock_log:
        yield mock_log


@pytest.fixture
def mock_appdirs():
    """Mock appdirs functions."""
    with mock.patch("src.index_core.server.appdirs") as mock_appdirs:
        mock_appdirs.user_data_dir.return_value = "/tmp/test_data"
        mock_appdirs.user_log_dir.return_value = "/tmp/test_log"
        yield mock_appdirs


@pytest.fixture
def mock_os():
    """Mock os functions."""
    with mock.patch("src.index_core.server.os") as mock_os:
        mock_os.path.isdir.return_value = True
        mock_os.environ.get.return_value = "0.5"
        yield mock_os


class TestSignalHandlers:
    """Test signal handler functions."""

    def test_sigterm_handler(self, mock_logger):
        """Test SIGTERM signal handler."""
        from src.index_core.server import shutdown_flag, sigterm_handler

        # Reset shutdown flag
        shutdown_flag.clear()

        # Test SIGTERM
        with pytest.raises(SystemExit) as exc_info:
            sigterm_handler(signal.SIGTERM, None)

        assert exc_info.value.code == 143
        assert shutdown_flag.is_set()
        mock_logger.info.assert_called()

    def test_sigint_handler(self, mock_logger):
        """Test SIGINT signal handler."""
        from src.index_core.server import shutdown_flag, sigterm_handler

        # Reset shutdown flag
        shutdown_flag.clear()

        # Test SIGINT
        with pytest.raises(SystemExit) as exc_info:
            sigterm_handler(signal.SIGINT, None)

        assert exc_info.value.code == 130
        assert shutdown_flag.is_set()

    def test_unknown_signal_handler(self, mock_logger):
        """Test unknown signal handler."""
        from src.index_core.server import shutdown_flag, sigterm_handler

        # Reset shutdown flag
        shutdown_flag.clear()

        # Test unknown signal
        with pytest.raises(SystemExit) as exc_info:
            sigterm_handler(999, None)

        assert exc_info.value.code == 1
        assert shutdown_flag.is_set()

    def test_signal_handler_with_async_uploads(self, mock_logger, mock_config):
        """Test signal handler with async uploads enabled."""
        from src.index_core.server import shutdown_flag, sigterm_handler

        # Mock async upload functions
        with mock.patch("src.index_core.server.wait_for_uploads") as mock_wait:
            with mock.patch("src.index_core.server.stop_upload_worker") as mock_stop:
                mock_config.USE_ASYNC_UPLOADS = True
                mock_config.STORE_FILES = True
                mock_wait.return_value = True

                # Reset shutdown flag
                shutdown_flag.clear()

                with pytest.raises(SystemExit):
                    sigterm_handler(signal.SIGTERM, None)

                mock_wait.assert_called_once_with(timeout=10.0)
                mock_stop.assert_called_once()

    def test_signal_handler_with_upload_timeout(self, mock_logger, mock_config):
        """Test signal handler when upload wait times out."""
        from src.index_core.server import shutdown_flag, sigterm_handler

        with mock.patch("src.index_core.server.wait_for_uploads") as mock_wait:
            with mock.patch("src.index_core.server.stop_upload_worker") as mock_stop:
                mock_config.USE_ASYNC_UPLOADS = True
                mock_config.STORE_FILES = True
                mock_wait.return_value = False  # Timeout

                # Reset shutdown flag
                shutdown_flag.clear()

                with pytest.raises(SystemExit):
                    sigterm_handler(signal.SIGTERM, None)

                mock_logger.warning.assert_called_with("Timed out waiting for uploads to complete. Some uploads may be lost.")


class TestInitializeFunctions:
    """Test initialization functions."""

    def test_initialize(self):
        """Test main initialize function."""
        from src.index_core.server import initialize

        with mock.patch("src.index_core.server.initialize_config") as mock_init_config:
            with mock.patch("src.index_core.server.initialize_db") as mock_init_db:
                mock_init_db.return_value = "test_db"

                result = initialize(testnet=True, verbose=True)

                assert result == "test_db"
                mock_init_config.assert_called_once_with(testnet=True, verbose=True)
                mock_init_db.assert_called_once()

    def test_initialize_config_mainnet(self, mock_config, mock_appdirs, mock_os, mock_logger):
        """Test initialize_config for mainnet."""
        from src.index_core.server import initialize_config

        with mock.patch("src.index_core.server.SelectParams") as mock_select:
            with mock.patch("src.index_core.server.log") as mock_log:
                with mock.patch("src.index_core.server.software_version"):
                    with mock.patch("src.index_core.server.cp_version"):
                        initialize_config()

                        mock_select.assert_called_once_with("mainnet")
                        assert mock_config.BLOCK_FIRST == mock_config.BLOCK_FIRST_MAINNET
                        assert mock_config.BACKEND_NAME == "bitcoincore"
                        assert mock_config.BACKEND_CONNECT == "localhost"
                        assert mock_config.BACKEND_PORT == mock_config.DEFAULT_BACKEND_PORT

    def test_initialize_config_testnet(self, mock_config, mock_appdirs, mock_os, mock_logger):
        """Test initialize_config for testnet."""
        from src.index_core.server import initialize_config

        # Set TESTNET to True before initialization
        mock_config.TESTNET = True

        with mock.patch("src.index_core.server.SelectParams") as mock_select:
            with mock.patch("src.index_core.server.log") as mock_log:
                with mock.patch("src.index_core.server.software_version"):
                    with mock.patch("src.index_core.server.cp_version"):
                        initialize_config(testnet=True)

                        mock_select.assert_called_once_with("testnet")
                        assert mock_config.BLOCK_FIRST == mock_config.BLOCK_FIRST_TESTNET
                        # The backend port gets set to the default testnet port value, then converted to int
                        assert mock_config.BACKEND_PORT == 18332
                        assert mock_config.ZMQ_TX_PORT == mock_config.ZMQ_PORT_TESTNET_TX
                        assert mock_config.ZMQ_BLOCK_PORT == mock_config.ZMQ_PORT_TESTNET_BLOCK

    def test_initialize_config_regtest(self, mock_config, mock_appdirs, mock_os, mock_logger):
        """Test initialize_config for regtest."""
        from src.index_core.server import initialize_config

        with mock.patch("src.index_core.server.SelectParams") as mock_select:
            with mock.patch("src.index_core.server.log") as mock_log:
                with mock.patch("src.index_core.server.software_version"):
                    with mock.patch("src.index_core.server.cp_version"):
                        initialize_config(regtest=True)

                        mock_select.assert_called_once_with("regtest")
                        assert mock_config.BLOCK_FIRST == mock_config.BLOCK_FIRST_REGTEST
                        assert mock_config.BACKEND_PORT == mock_config.DEFAULT_BACKEND_PORT_REGTEST
                        assert mock_config.REGTEST is True
                        assert mock_config.ZMQ_TX_PORT == mock_config.ZMQ_PORT_REGTEST_TX
                        assert mock_config.ZMQ_BLOCK_PORT == mock_config.ZMQ_PORT_REGTEST_BLOCK

    def test_initialize_config_with_backend_params(self, mock_config, mock_appdirs, mock_os, mock_logger):
        """Test initialize_config with backend parameters."""
        from src.index_core.server import initialize_config

        with mock.patch("src.index_core.server.SelectParams"):
            with mock.patch("src.index_core.server.log"):
                with mock.patch("src.index_core.server.software_version"):
                    with mock.patch("src.index_core.server.cp_version"):
                        initialize_config(
                            backend_connect="192.168.1.100",
                            backend_port="9999",
                            backend_ssl=True,
                            backend_ssl_no_verify=True,
                            backend_poll_interval="2.5",
                        )

                        assert mock_config.BACKEND_CONNECT == "192.168.1.100"
                        assert mock_config.BACKEND_PORT == 9999
                        assert mock_config.BACKEND_SSL is True
                        assert mock_config.BACKEND_SSL_NO_VERIFY is True
                        # Backend poll interval is stored as string initially, then converted
                        assert mock_config.BACKEND_POLL_INTERVAL == "2.5"

    def test_initialize_config_with_log_file(self, mock_config, mock_appdirs, mock_os, mock_logger):
        """Test initialize_config with custom log file."""
        from src.index_core.server import initialize_config

        with mock.patch("src.index_core.server.SelectParams"):
            with mock.patch("src.index_core.server.log") as mock_log:
                with mock.patch("src.index_core.server.software_version"):
                    with mock.patch("src.index_core.server.cp_version"):
                        initialize_config(log_file="/custom/path/log.txt")

                        assert mock_config.LOG == "/custom/path/log.txt"
                        mock_log.set_up.assert_called_once()

    def test_initialize_config_no_log_file(self, mock_config, mock_appdirs, mock_os, mock_logger):
        """Test initialize_config with logging disabled."""
        from src.index_core.server import initialize_config

        with mock.patch("src.index_core.server.SelectParams"):
            with mock.patch("src.index_core.server.log") as mock_log:
                with mock.patch("src.index_core.server.software_version"):
                    with mock.patch("src.index_core.server.cp_version"):
                        initialize_config(log_file=False)

                        assert mock_config.LOG is None

    def test_initialize_config_hash_check_failure(self, mock_config, mock_appdirs, mock_os):
        """Test initialize_config with hash check failure."""
        from src.index_core.server import initialize_config

        with mock.patch("src.index_core.server.SelectParams"):
            with mock.patch("src.index_core.server.hashlib.sha3_256") as mock_sha3:
                mock_sha3.return_value.hexdigest.return_value = "wrong_hash"

                with pytest.raises(ValueError, match="SHA3-256 hash mismatch"):
                    initialize_config()

    def test_initialize_config_invalid_port(self, mock_config, mock_appdirs, mock_os):
        """Test initialize_config with invalid port."""
        from exceptions import ConfigurationError
        from src.index_core.server import initialize_config

        with mock.patch("src.index_core.server.SelectParams"):
            with mock.patch("src.index_core.server.log"):
                with mock.patch("src.index_core.server.software_version"):
                    with mock.patch("src.index_core.server.cp_version"):
                        with pytest.raises(ConfigurationError, match="invalid backend API port"):
                            initialize_config(backend_port="99999")

    def test_initialize_config_creates_directories(self, mock_config, mock_appdirs, mock_os):
        """Test that initialize_config creates necessary directories."""
        from src.index_core.server import initialize_config

        mock_os.path.isdir.return_value = False

        with mock.patch("src.index_core.server.SelectParams"):
            with mock.patch("src.index_core.server.log"):
                with mock.patch("src.index_core.server.software_version"):
                    with mock.patch("src.index_core.server.cp_version"):
                        initialize_config()

                        mock_os.makedirs.assert_called()

    def test_initialize_config_backend_ssl_verify_deprecated(self, mock_config, mock_appdirs, mock_os, mock_logger):
        """Test deprecated backend_ssl_verify parameter."""
        from src.index_core.server import initialize_config

        with mock.patch("src.index_core.server.SelectParams"):
            with mock.patch("src.index_core.server.log"):
                with mock.patch("src.index_core.server.software_version"):
                    with mock.patch("src.index_core.server.cp_version"):
                        initialize_config(backend_ssl_verify=False)

                        mock_logger.warning.assert_called_with(
                            "The server parameter `backend_ssl_verify` is deprecated. Use `backend_ssl_no_verify` instead."
                        )
                        assert mock_config.BACKEND_SSL_NO_VERIFY is True

    def test_initialize_config_customnet(self, mock_config, mock_appdirs, mock_os):
        """Test initialize_config with customnet."""
        from src.index_core.server import initialize_config

        with mock.patch("src.index_core.server.SelectParams"):
            with mock.patch("src.index_core.server.log"):
                with mock.patch("src.index_core.server.software_version"):
                    with mock.patch("src.index_core.server.cp_version"):
                        initialize_config(customnet="mynet")

                        assert mock_config.CUSTOMNET is True
                        assert mock_config.REGTEST is True

    def test_initialize_config_checkdb(self, mock_config, mock_appdirs, mock_os):
        """Test initialize_config with checkdb flag."""
        from src.index_core.server import initialize_config

        with mock.patch("src.index_core.server.SelectParams"):
            with mock.patch("src.index_core.server.log"):
                with mock.patch("src.index_core.server.software_version"):
                    with mock.patch("src.index_core.server.cp_version"):
                        initialize_config(checkdb=True)

                        assert mock_config.CHECKDB is True

    def test_initialize_config_exception_hook(self, mock_config, mock_appdirs, mock_os):
        """Test that exception hook is installed."""
        from src.index_core.server import initialize_config

        with mock.patch("src.index_core.server.SelectParams"):
            with mock.patch("src.index_core.server.log"):
                with mock.patch("src.index_core.server.software_version"):
                    with mock.patch("src.index_core.server.cp_version"):
                        with mock.patch("src.index_core.server.sys") as mock_sys:
                            initialize_config()

                            # Check that excepthook was set
                            assert mock_sys.excepthook is not None


class TestConnectToBackend:
    """Test connect_to_backend function."""

    def test_connect_to_backend(self, mock_backend):
        """Test connect_to_backend returns Backend instance."""
        from src.index_core.server import connect_to_backend

        result = connect_to_backend()
        assert result == mock_backend


class TestStartAll:
    """Test start_all function."""

    def test_start_all_basic(self, mock_config, mock_backend, mock_logger):
        """Test basic start_all functionality."""
        from src.index_core.server import shutdown_flag, start_all

        mock_db = mock.MagicMock()
        shutdown_flag.clear()

        with mock.patch("src.index_core.server.concurrent.futures.ThreadPoolExecutor") as mock_executor:
            with mock.patch("src.index_core.server.blocks") as mock_blocks:
                start_all(mock_db)

                mock_executor.assert_called_once()
                mock_blocks.follow.assert_called_once_with(mock_db)
                assert shutdown_flag.is_set()

    def test_start_all_with_s3(self, mock_config, mock_backend, mock_logger):
        """Test start_all with S3 configuration."""
        from src.index_core.server import shutdown_flag, start_all

        mock_config.STORE_FILES = True
        mock_config.AWS_SECRET_ACCESS_KEY = "secret"
        mock_config.AWS_ACCESS_KEY_ID = "access"
        mock_config.AWS_S3_BUCKETNAME = "test-bucket"
        mock_config.USE_ASYNC_UPLOADS = True

        mock_db = mock.MagicMock()
        shutdown_flag.clear()

        with mock.patch("src.index_core.server.concurrent.futures.ThreadPoolExecutor"):
            with mock.patch("src.index_core.server.blocks"):
                with mock.patch("src.index_core.server.get_s3_objects") as mock_s3:
                    with mock.patch("src.index_core.server.start_upload_worker") as mock_start_worker:
                        with mock.patch("src.index_core.server.wait_for_uploads") as mock_wait:
                            with mock.patch("src.index_core.server.stop_upload_worker") as mock_stop:
                                mock_wait.return_value = True

                                start_all(mock_db)

                                mock_s3.assert_called_once()
                                mock_start_worker.assert_called_once()
                                mock_wait.assert_called_once()
                                mock_stop.assert_called_once()

    def test_start_all_with_exception(self, mock_config, mock_backend, mock_logger):
        """Test start_all with exception handling."""
        from src.index_core.server import shutdown_flag, start_all

        mock_db = mock.MagicMock()
        shutdown_flag.clear()

        with mock.patch("src.index_core.server.concurrent.futures.ThreadPoolExecutor"):
            with mock.patch("src.index_core.server.blocks") as mock_blocks:
                mock_blocks.follow.side_effect = Exception("Test error")

                start_all(mock_db)

                mock_logger.error.assert_called_with("Error in main server loop: Test error")
                assert shutdown_flag.is_set()

    def test_start_all_upload_timeout(self, mock_config, mock_backend, mock_logger):
        """Test start_all with upload timeout."""
        from src.index_core.server import shutdown_flag, start_all

        mock_config.STORE_FILES = True
        mock_config.USE_ASYNC_UPLOADS = True

        mock_db = mock.MagicMock()
        shutdown_flag.clear()

        with mock.patch("src.index_core.server.concurrent.futures.ThreadPoolExecutor"):
            with mock.patch("src.index_core.server.blocks"):
                with mock.patch("src.index_core.server.wait_for_uploads") as mock_wait:
                    with mock.patch("src.index_core.server.stop_upload_worker"):
                        mock_wait.return_value = False  # Timeout

                        start_all(mock_db)

                        mock_logger.warning.assert_called_with(
                            "Timed out waiting for uploads to complete. Some uploads may be lost."
                        )


class TestReparse:
    """Test reparse function."""

    def test_reparse(self, mock_backend):
        """Test reparse function."""
        from src.index_core.server import reparse

        mock_db = mock.MagicMock()

        with mock.patch("src.index_core.server.blocks") as mock_blocks:
            reparse(mock_db, block_index=12345, quiet=False)

            mock_blocks.reparse.assert_called_once_with(mock_db, block_index=12345, quiet=False)

    def test_reparse_default_params(self, mock_backend):
        """Test reparse with default parameters."""
        from src.index_core.server import reparse

        mock_db = mock.MagicMock()

        with mock.patch("src.index_core.server.blocks") as mock_blocks:
            reparse(mock_db)

            mock_blocks.reparse.assert_called_once_with(mock_db, block_index=None, quiet=True)


class TestGlobalVariables:
    """Test global variables and their usage."""

    def test_shutdown_flag(self):
        """Test shutdown_flag is a threading.Event."""
        from src.index_core.server import shutdown_flag

        assert isinstance(shutdown_flag, threading.Event)

    def test_backend_instance(self):
        """Test backend_instance initialization."""
        from src.index_core.server import backend_instance

        # Should exist but actual type depends on Backend mock
        assert backend_instance is not None
