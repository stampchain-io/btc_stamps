import time
import pytest
from decimal import Decimal

# Import the Python SRC-20 parser
from index_core.src20 import parse_src20

# Attempt to import the Rust parser; skip tests if not available
pytest.importorskip("btc_stamps_parser")
from btc_stamps_parser import parse_rust_src20


@pytest.fixture
def dummy_db():
    """A dummy DB fixture that simulates minimal database behavior."""

    class DummyCursor:
        def __init__(self, executed_queries):
            self.executed_queries = executed_queries

        def execute(self, query, params=None):
            self.executed_queries.append((query, params))

        def fetchone(self):
            return ("50", "100", "2")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    class DummyDB:
        def __init__(self):
            self.queries = []

        def cursor(self):
            return DummyCursor(self.queries)

        def commit(self):
            pass

    return DummyDB()


@pytest.fixture
def deploy_src20_dict():
    """Fixture for a dummy SRC-20 deploy dictionary."""
    return {
        "op": "DEPLOY",
        "tick": "ABC",
        "max": "100",
        "lim": "50",
        "dec": "2",
        "tx_hash": "dummyhash",
        "tx_index": 1,
        "creator": "address1",
        "destination": "address2",
        "block_index": 10,
        "block_time": int(time.time()),
    }


def test_parser_comparison_deploy(dummy_db, deploy_src20_dict):
    """Compare outputs of the Python and Rust parsers for a deploy operation."""
    processed_list_py = []
    is_valid_py, result_py = parse_src20(dummy_db, deploy_src20_dict, processed_list_py)

    processed_list_rust = []
    is_valid_rust, result_rust = parse_rust_src20(
        dummy_db, deploy_src20_dict, processed_list_rust
    )

    # Compare key fields: validation flag, tick (normalized), tick_hash, and op
    assert (
        is_valid_py == is_valid_rust
    ), "Validation flags should match between Python and Rust parser detections."
    assert result_py.get("tick") == result_rust.get(
        "tick"
    ), "Tick values should match (both normalized)."
    assert result_py.get("tick_hash") == result_rust.get(
        "tick_hash"
    ), "Tick hashes should match between parsers."
    assert result_py.get("op") == result_rust.get(
        "op"
    ), "Operation types should be identical."

    # Optionally, compare numeric fields if present
    if result_py.get("max") and result_rust.get("max"):
        assert Decimal(result_py.get("max")) == Decimal(
            result_rust.get("max")
        ), "Max values should be equivalent."

    # Record that both parsed outputs contain expected keys
    expected_keys = ["op", "tick", "tick_hash"]
    for key in expected_keys:
        assert key in result_py, f"Key '{key}' should be in Python parser result."
        assert key in result_rust, f"Key '{key}' should be in Rust parser result."
