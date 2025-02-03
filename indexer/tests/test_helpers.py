import os
from unittest.mock import patch


def setup_test_env():
    """Set up test environment variables and mocks"""
    os.environ["USE_TEST_TX_HEX"] = "1"
    os.environ["TESTING"] = "1"
    os.environ["USE_TEST_DB"] = "1"
    os.environ["MOCK_DB"] = "1"


def mock_database():
    """Create a database mock patcher"""
    return patch("index_core.database_manager.DatabaseManager")
