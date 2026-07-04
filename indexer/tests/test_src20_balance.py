import os
import sys
import unittest
from decimal import Decimal

import pytest

# Add the parent directory to sys.path to allow relative imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Import the Src20Processor from the index_core module
from index_core.src20 import Src20Processor
from tests.test_helpers import mock_database, setup_test_env


def test_normalize_valid_amount():
    # Arrange: create a dummy SRC20 dictionary with a valid amount for mint operation
    src20_dict = {"amt": "100.50", "dec": 2, "tick": "abc"}
    processed_list = []

    # Create a Src20Processor instance with dummy db (None) and no lock
    processor = Src20Processor(None, src20_dict, processed_list)

    # Act: call normalize_and_validate_amt
    result = processor.normalize_and_validate_amt()

    # Assert: the returned value should match the expected Decimal('100.50')
    # Note: Depending on Decimal normalization, the exact representation might differ,
    # so we compare numerical equality.
    assert result == Decimal("100.50"), f"Expected 100.50 but got {result}"


def test_normalize_invalid_amount():
    # Arrange: create a SRC20 dictionary with an amount that exceeds allowed decimal places
    src20_dict = {"amt": "100.501", "dec": 2, "tick": "abc"}
    processed_list = []

    # Create a Src20Processor instance
    processor = Src20Processor(None, src20_dict, processed_list)

    # Act and Assert: calling normalize_and_validate_amt should raise a ValueError
    with pytest.raises(ValueError, match="Decimal places exceeds the limit"):
        processor.normalize_and_validate_amt()


class TestSrc20Balance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Set up the test environment
        setup_test_env()

    def setUp(self):
        # Create a mock database for this test
        self.db_mock = mock_database()
        # Enter the context manager
        self.mock_conn = self.db_mock.__enter__()

    def tearDown(self):
        # Exit the context manager
        self.db_mock.__exit__(None, None, None)

    def test_db_mocking_works(self):
        """Simple test to verify the database mocking is working properly."""
        # We can access the mocked database connection
        self.assertIsNotNone(self.mock_conn)

        # Make sure it has a cursor method
        self.assertTrue(hasattr(self.mock_conn, "cursor"))

        # And we can call the cursor method
        cursor = self.mock_conn.cursor()
        self.assertIsNotNone(cursor)
