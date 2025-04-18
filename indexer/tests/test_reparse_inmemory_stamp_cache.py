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

    # Counter should start at 1
    counter = reparse_caching.cache_manager.get_cache_value("stamp", "counter")
    assert counter == 1

    # valid_stamps_in_block should include stamp 1
    assert len(proc.valid_stamps_in_block) == 1
    record = proc.valid_stamps_in_block[0]
    assert record["stamp"] == 1
    assert record["tx_hash"] == "tx1"


def test_stamp_counter_multiple_increments():
    proc = InMemoryBlockProcessor()
    f1 = make_fake_result("tx1", 1, 100)
    f2 = make_fake_result("tx2", 2, 200)
    f3 = make_fake_result("tx3", 3, 300)
    proc.process_transaction_results([f1])
    proc.process_transaction_results([f2, f3])

    # Counter should be 3 after three stamps
    counter = reparse_caching.cache_manager.get_cache_value("stamp", "counter")
    assert counter == 3

    # Check stamps assigned in order
    stamps = [rec["stamp"] for rec in proc.valid_stamps_in_block]
    assert stamps == [1, 2, 3]


def test_cache_cleared_under_memory_pressure(monkeypatch):
    proc = InMemoryBlockProcessor()
    fake = make_fake_result("tx1", 1, 100)
    proc.process_transaction_results([fake])
    # Ensure counter set
    assert reparse_caching.cache_manager.get_cache_value("stamp", "counter") == 1

    # Simulate memory pressure: monkey-patch memory_manager to clear all caches
    monkeypatch.setattr(mm, "clear_caches_if_needed", lambda: reparse_caching.cache_manager.clear_all())
    reparse_caching.cache_manager.check_memory_pressure()

    # After clearing, stamp counter should be None
    assert reparse_caching.cache_manager.get_cache_value("stamp", "counter") is None
