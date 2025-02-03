import pytest
from decimal import Decimal

from index_core.src20 import Src20Processor
from index_core.caching import cache_manager


def test_update_valid_transfer():
    # Arrange: Create a dummy SRC20 dictionary to simulate a TRANSFER operation
    src20_dict = {"amt": "100.00", "dec": 2, "tick": "abc", "op": "TRANSFER"}
    processed_list = []
    processor = Src20Processor(None, src20_dict, processed_list)

    # Act: Call update_valid_src20_list with running balances
    processor.update_valid_src20_list(
        running_user_balance_creator="200",
        running_user_balance_destination="50",
        operation="TRANSFER",
    )

    # Assert: Validate that the balances are updated correctly
    assert processor.src20_dict.get("total_balance_creator") == Decimal(
        "100.00"
    ), f"Expected creator balance of 100.00, got {processor.src20_dict.get('total_balance_creator')}"
    assert processor.src20_dict.get("total_balance_destination") == Decimal(
        "150.00"
    ), f"Expected destination balance of 150.00, got {processor.src20_dict.get('total_balance_destination')}"


def test_update_valid_mint():
    # Arrange: Use a test tick and reset total minted in cache
    tick = "def"
    cache_manager.set_cache_value("total_minted", tick, Decimal("0"))
    src20_dict = {"amt": "50.00", "dec": 2, "tick": tick, "op": "MINT"}
    processed_list = []
    processor = Src20Processor(None, src20_dict, processed_list)

    # Act: Call update_valid_src20_list for a MINT operation with running user balance
    processor.update_valid_src20_list(
        running_user_balance_creator="150", operation="MINT", total_minted="0"
    )

    # Assert: Validate that the total minted and destination balance are updated as expected
    assert processor.src20_dict.get("total_minted") == Decimal(
        "50.00"
    ), f"Expected total minted of 50.00, got {processor.src20_dict.get('total_minted')}"
    assert processor.src20_dict.get("total_balance_destination") == Decimal(
        "200.00"
    ), f"Expected destination balance of 200.00, got {processor.src20_dict.get('total_balance_destination')}"

    # Also assert the cache is updated for the given tick
    cached_total = cache_manager.get_cache_value("total_minted", tick)
    assert cached_total == Decimal(
        "50.00"
    ), f"Expected cached total minted to be 50.00, got {cached_total}"
