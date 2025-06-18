"""
Test isolation utilities for ensuring proper cleanup of global state.

These utilities help prevent test isolation issues by providing standardized
cleanup mechanisms for common sources of test pollution.
"""

import logging
import os
import sys
from typing import Any, Dict, List, Optional
from unittest.mock import Mock

import pytest


class EnvironmentIsolation:
    """Context manager for isolating environment variable changes."""

    def __init__(self, **env_vars):
        self.env_vars = env_vars
        self.original_env = {}

    def __enter__(self):
        # Store original values
        for key in self.env_vars:
            self.original_env[key] = os.environ.get(key)

        # Set new values
        for key, value in self.env_vars.items():
            if value is not None:
                os.environ[key] = value
            elif key in os.environ:
                del os.environ[key]

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Restore original values
        for key, original_value in self.original_env.items():
            if original_value is not None:
                os.environ[key] = original_value
            elif key in os.environ:
                del os.environ[key]


class LoggingIsolation:
    """Context manager for isolating logging configuration changes."""

    def __init__(self, logger_name: Optional[str] = None):
        self.logger_name = logger_name
        self.logger = logging.getLogger(logger_name)
        self.original_handlers = None
        self.original_level = None

    def __enter__(self):
        self.original_handlers = self.logger.handlers[:]
        self.original_level = self.logger.level
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Remove any handlers added during the context
        current_handlers = self.logger.handlers[:]
        for handler in current_handlers:
            if handler not in self.original_handlers:
                self.logger.removeHandler(handler)
                try:
                    handler.close()
                except Exception:
                    pass

        # Restore original handlers
        self.logger.handlers[:] = self.original_handlers
        self.logger.setLevel(self.original_level)


class SysModulesIsolation:
    """Context manager for isolating sys.modules changes."""

    def __init__(self, modules_to_mock: List[str]):
        self.modules_to_mock = modules_to_mock
        self.original_modules = {}

    def __enter__(self):
        # Store original modules
        for module_name in self.modules_to_mock:
            self.original_modules[module_name] = sys.modules.get(module_name)
        return self

    def mock_module(self, module_name: str, mock_module: Any = None):
        """Mock a specific module."""
        if mock_module is None:
            mock_module = Mock()
        sys.modules[module_name] = mock_module
        return mock_module

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Restore original modules
        for module_name, original_module in self.original_modules.items():
            if original_module is not None:
                sys.modules[module_name] = original_module
            elif module_name in sys.modules:
                del sys.modules[module_name]


class SysPathIsolation:
    """Context manager for isolating sys.path changes."""

    def __init__(self):
        self.original_path = None

    def __enter__(self):
        self.original_path = sys.path[:]
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.path[:] = self.original_path


@pytest.fixture
def isolated_environment():
    """Fixture that provides environment variable isolation."""

    def _isolate(**env_vars):
        return EnvironmentIsolation(**env_vars)

    return _isolate


@pytest.fixture
def isolated_logging():
    """Fixture that provides logging isolation."""

    def _isolate(logger_name=None):
        return LoggingIsolation(logger_name)

    return _isolate


@pytest.fixture
def isolated_sys_modules():
    """Fixture that provides sys.modules isolation."""

    def _isolate(modules_to_mock):
        return SysModulesIsolation(modules_to_mock)

    return _isolate


@pytest.fixture
def isolated_sys_path():
    """Fixture that provides sys.path isolation."""
    return SysPathIsolation()


class TestIsolationManager:
    """Comprehensive test isolation manager."""

    def __init__(self):
        self.env_isolation = None
        self.logging_isolation = None
        self.modules_isolation = None
        self.path_isolation = None

    def isolate_environment(self, **env_vars):
        """Add environment variable isolation."""
        self.env_isolation = EnvironmentIsolation(**env_vars)
        return self

    def isolate_logging(self, logger_name=None):
        """Add logging isolation."""
        self.logging_isolation = LoggingIsolation(logger_name)
        return self

    def isolate_sys_modules(self, modules_to_mock):
        """Add sys.modules isolation."""
        self.modules_isolation = SysModulesIsolation(modules_to_mock)
        return self

    def isolate_sys_path(self):
        """Add sys.path isolation."""
        self.path_isolation = SysPathIsolation()
        return self

    def __enter__(self):
        if self.env_isolation:
            self.env_isolation.__enter__()
        if self.logging_isolation:
            self.logging_isolation.__enter__()
        if self.modules_isolation:
            self.modules_isolation.__enter__()
        if self.path_isolation:
            self.path_isolation.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Exit in reverse order
        if self.path_isolation:
            self.path_isolation.__exit__(exc_type, exc_val, exc_tb)
        if self.modules_isolation:
            self.modules_isolation.__exit__(exc_type, exc_val, exc_tb)
        if self.logging_isolation:
            self.logging_isolation.__exit__(exc_type, exc_val, exc_tb)
        if self.env_isolation:
            self.env_isolation.__exit__(exc_type, exc_val, exc_tb)


@pytest.fixture
def test_isolation():
    """Fixture that provides comprehensive test isolation."""
    return TestIsolationManager()


# Common isolation patterns for frequently used combinations
@pytest.fixture
def database_test_isolation():
    """Isolation for database-related tests."""
    return (
        TestIsolationManager()
        .isolate_environment(MOCK_DB="1", USE_TEST_DB="1", TESTING="1")
        .isolate_sys_modules(["pymysql", "pymysql.connections", "pymysql.cursors"])
    )


@pytest.fixture
def aws_test_isolation():
    """Isolation for AWS-related tests."""
    return (
        TestIsolationManager()
        .isolate_sys_modules(["boto3", "botocore"])
        .isolate_environment(AWS_ACCESS_KEY_ID="test", AWS_SECRET_ACCESS_KEY="test")
    )


@pytest.fixture
def src20_test_isolation():
    """Isolation for SRC-20 related tests."""
    return TestIsolationManager().isolate_environment(USE_TEST_TX_HEX="1", TESTING="1", MOCK_DB="1").isolate_logging()
