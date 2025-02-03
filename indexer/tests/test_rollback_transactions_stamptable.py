import pytest


@pytest.fixture
def dummy_db():
    class DummyCursor:
        def __init__(self, executed_queries):
            self.executed_queries = executed_queries

        def execute(self, query, params=None):
            self.executed_queries.append((query, params))
            self.last_query = query
            self.last_params = params
            # Simulate no results
            self.result = []

        def fetchall(self):
            return self.result

        def close(self):
            pass

        def executemany(self, query, param_list):
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


def update_transactions_table(db, block_index, tx_records):
    """
    Stub function to simulate updating the transactions table.
    Returns a list of processed transaction hashes.
    """
    processed = []
    cursor = db.cursor()
    for tx in tx_records:
        processed.append(tx["tx_hash"])
        query = "INSERT INTO transactions (tx_hash, tx_index, block_index) VALUES (%s, %s, %s)"
        cursor.execute(query, (tx["tx_hash"], tx["tx_index"], tx["block_index"]))
    cursor.close()
    return processed


def update_stamptable_v4(db, block_index, stamps):
    """
    Stub function to simulate updating the StampTableV4.
    Returns a list of processed stamps.
    """
    processed = []
    cursor = db.cursor()
    for stamp in stamps:
        processed.append(stamp["stamp"])
        query = "INSERT INTO StampTableV4 (stamp, block_index, creator) VALUES (%s, %s, %s)"
        cursor.execute(query, (stamp["stamp"], stamp["block_index"], stamp.get("creator", "")))
    cursor.close()
    return processed


def test_rollback_transactions(dummy_db):
    # Simulate two transactions
    tx1 = {"tx_hash": "tx1", "tx_index": 1, "block_index": 10}
    tx2 = {"tx_hash": "tx2", "tx_index": 2, "block_index": 11}
    full_list = [tx1, tx2]
    processed_full = update_transactions_table(dummy_db, 11, full_list)

    # Simulate rollback by removing the second transaction
    rollback_list = [tx1]
    processed_rollback = update_transactions_table(dummy_db, 10, rollback_list)

    # Check that rollback results in fewer transactions processed
    assert len(processed_rollback) < len(processed_full), "After rollback, transactions processed should be reduced"


def test_rollback_stamptable(dummy_db):
    # Simulate two stamp records
    stamp1 = {"stamp": 1, "block_index": 10, "creator": "addr1"}
    stamp2 = {"stamp": 2, "block_index": 11, "creator": "addr1"}
    full_list = [stamp1, stamp2]
    processed_full = update_stamptable_v4(dummy_db, 11, full_list)

    # Simulate rollback by removing the second stamp record
    rollback_list = [stamp1]
    processed_rollback = update_stamptable_v4(dummy_db, 10, rollback_list)

    # Check that rollback results in fewer stamps processed
    assert len(processed_rollback) < len(processed_full), "After rollback, stamps processed should be reduced"
