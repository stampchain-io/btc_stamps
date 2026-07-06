# New tests for in-memory stamp numbering and cache behavior
from types import SimpleNamespace

import pytest

import index_core.caching as reparse_caching
from index_core.memory_manager import memory_manager as mm
from index_core.reparse.validator import InMemoryBlockProcessor


@pytest.fixture(autouse=True)
def clear_stamp_cache():
    """Clear caches before and after each test"""
    reparse_caching.clear_all_caches()
    yield
    reparse_caching.clear_all_caches()


def make_fake_result(tx_hash: str, block_index: int, block_time: int, cpid=None):
    # data must be non-empty dict to be processed
    return SimpleNamespace(data={"cpid": cpid}, tx_hash=tx_hash, block_index=block_index, block_time=block_time)


def test_stamp_counter_initial_and_single_increment():
    proc = InMemoryBlockProcessor()
    fake = make_fake_result("tx1", 1, 100)
    proc.process_transaction_results([fake])

    # With no prior stamps seeded, the first stamp number is 0 — matching
    # production's get_next_stamp_number default_value. The "counter" cache holds
    # the LAST-USED number, so after one stamp it is 0.
    counter = reparse_caching.cache_manager.get_cache_value("stamp", "counter")
    assert counter == 0

    # valid_stamps_in_block should include stamp 0, keyed by the production
    # ValidStamp field name (stamp_number); the non-production "stamp" alias is
    # intentionally NOT present so str(dict) is byte-identical to production.
    assert len(proc.valid_stamps_in_block) == 1
    record = proc.valid_stamps_in_block[0]
    assert record["stamp_number"] == 0
    assert "stamp" not in record
    assert record["tx_hash"] == "tx1"


def test_stamp_counter_multiple_increments():
    proc = InMemoryBlockProcessor()
    f1 = make_fake_result("tx1", 1, 100)
    f2 = make_fake_result("tx2", 2, 200)
    f3 = make_fake_result("tx3", 3, 300)
    proc.process_transaction_results([f1])
    proc.process_transaction_results([f2, f3])

    # Counter (last-used) should be 2 after three stamps numbered 0, 1, 2
    counter = reparse_caching.cache_manager.get_cache_value("stamp", "counter")
    assert counter == 2

    # Check stamps assigned in order
    stamps = [rec["stamp_number"] for rec in proc.valid_stamps_in_block]
    assert stamps == [0, 1, 2]


def test_cache_cleared_under_memory_pressure(monkeypatch):
    proc = InMemoryBlockProcessor()
    fake = make_fake_result("tx1", 1, 100)
    proc.process_transaction_results([fake])
    # Ensure counter set (last-used == 0 after the first stamp)
    assert reparse_caching.cache_manager.get_cache_value("stamp", "counter") == 0

    # Simulate memory pressure: monkey-patch memory_manager to clear all caches
    monkeypatch.setattr(mm, "clear_caches_if_needed", lambda: reparse_caching.cache_manager.clear_all())
    reparse_caching.cache_manager.check_memory_pressure()

    # After clearing, stamp counter should be None
    assert reparse_caching.cache_manager.get_cache_value("stamp", "counter") is None
