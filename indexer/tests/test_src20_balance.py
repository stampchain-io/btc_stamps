import unittest
from decimal import Decimal

import pytest

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
        setup_test_env()
        cls._db_patcher = mock_database()
        cls._db_mock = cls._db_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._db_patcher.stop()
