import time
from decimal import Decimal

import pytest

# Import the parse_src20 function from index_core.src20
from index_core.src20 import parse_src20


# Define a dummy cursor and dummy DB to simulate minimal database behavior
class DummyCursor:
    def __init__(self, executed_queries):
        self.executed_queries = executed_queries

    def execute(self, query, params=None):
        self.executed_queries.append((query, params))

    def fetchone(self):
        # Simulate a deploy record being returned for SELECT queries
        # Return a tuple: (lim, max, deci) as expected by get_src20_deploy_in_db
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


@pytest.fixture
def dummy_db():
    return DummyDB()


@pytest.fixture
def deploy_src20_dict():
    # Create a dummy SRC-20 deploy dictionary with required fields
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


def test_parse_src20_deploy(dummy_db, deploy_src20_dict):
    # We'll simulate an empty processed list
    processed_list = []

    # Act: call parse_src20 with our dummy DB and deploy dictionary
    is_valid, updated_dict = parse_src20(dummy_db, deploy_src20_dict, processed_list)

    # Assert: the updated dictionary should have a tick_hash and our dummy db should have recorded an execute call
    assert (
        updated_dict.get("tick_hash") is not None
    ), "tick_hash should be generated for a deploy operation."
    # Check that at least one query was executed (the metadata insertion)
    assert (
        len(dummy_db.queries) > 0
    ), "Expected at least one database query for metadata insertion."
