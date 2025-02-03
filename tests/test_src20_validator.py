import pytest
from decimal import Decimal

from index_core.src20 import Src20Validator


def test_process_values_valid():
    # Arrange: Create a valid SRC-20 dictionary
    input_dict = {
        "tick": "ABC",
        "max": "100.00",
        "lim": "50.00",
        "dec": "2",
        "p": "src-20",
        "op": "MINT",
    }
    validator = Src20Validator(input_dict.copy())

    # Act: Process values
    output_dict = validator.process_values()

    # Assert: Check tick normalization and numeric conversion
    assert output_dict.get("tick") == "abc", "Tick should be converted to lowercase."
    assert isinstance(
        output_dict.get("max"), Decimal
    ), "max should be converted to Decimal."
    assert isinstance(
        output_dict.get("lim"), Decimal
    ), "lim should be converted to Decimal."
    assert output_dict.get("dec") == 2, "dec should be converted to int 2."
    assert "tick_hash" in output_dict, "tick_hash should be added to the output dict."
    assert validator.is_valid, "Validator should mark input as valid."


def test_process_values_invalid_numeric():
    # Arrange: Create a SRC-20 dictionary with invalid numeric values
    input_dict = {
        "tick": "ABC",
        "max": "one hundred",
        "lim": "fifty",
        "dec": "2",
        "p": "src-20",
        "op": "MINT",
    }
    validator = Src20Validator(input_dict.copy())

    # Act: Process values
    output_dict = validator.process_values()

    # Assert: Check that invalid numeric fields are set to None and errors are recorded
    assert output_dict.get("max") is None, "Invalid max value should be set to None."
    assert output_dict.get("lim") is None, "Invalid lim value should be set to None."
    error_messages = validator.errors
    assert any(
        "INVALID NUM" in msg for msg in error_messages
    ), "Validator errors should mention invalid numeric values."
