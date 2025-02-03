import time
import pytest
from decimal import Decimal

from index_core.src20 import update_src20_balances


@pytest.fixture
def dummy_db():
    class DummyCursor:
        def __init__(self, executed_queries):
            self.executed_queries = executed_queries

        def execute(self, query, params=None):
            self.executed_queries.append((query, params))
            self.last_query = query
            self.last_params = params
            # Simulate query execution with no results
            self.result = []

        def fetchall(self):
            # Return the simulated results
            return self.result

        def close(self):
            # No-op for dummy cursor
            pass

        def executemany(self, query, param_list):
            # Simulate successful executemany call
            self.last_executemany = (query, param_list)
            return None

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
def block_transactions():
    # Create two valid mint transactions for tick 'abc'
    tx1 = {
        "valid": 1,
        "op": "MINT",
        "tick": "abc",
        "tick_hash": "dummy_tick_hash",
        "amt": "100.00",
        "dec": "2",
        "tx_hash": "hash1",
        "tx_index": 1,
        "creator": "addr1",
        "destination": "addr1",
        "block_index": 10,
        "block_time": int(time.time()),
    }
    tx2 = {
        "valid": 1,
        "op": "MINT",
        "tick": "abc",
        "tick_hash": "dummy_tick_hash",
        "amt": "50.00",
        "dec": "2",
        "tx_hash": "hash2",
        "tx_index": 2,
        "creator": "addr1",
        "destination": "addr1",
        "block_index": 11,
        "block_time": int(time.time()),
    }
    return [tx1, tx2]


def test_block_rollback(dummy_db, block_transactions):
    # Process all transactions (simulate block index 11)
    balances_before = update_src20_balances(
        dummy_db, 11, int(time.time()), block_transactions
    )
    total_before = sum(
        item.get("credit", Decimal("0")) - item.get("debit", Decimal("0"))
        for item in balances_before
        if item.get("tick") == "abc"
    )

    # Simulate a rollback: remove the second transaction and process only up to block index 10
    balances_after = update_src20_balances(
        dummy_db, 10, int(time.time()), block_transactions[:-1]
    )
    total_after = sum(
        item.get("credit", Decimal("0")) - item.get("debit", Decimal("0"))
        for item in balances_after
        if item.get("tick") == "abc"
    )

    # Assert that after rollback, the total minted balance is lower
    assert (
        total_after < total_before
    ), "After rollback, total balance should be reduced."
