import os
import sys
import types
from typing import Any

import pytest


# Fake cursor and connection for testing
class FakeCursor:
    def __init__(self):
        self.queries = []
        self.fetched = []
        self.one = None
        self.description = None

    def execute(self, query, params=None):
        self.queries.append((query, params))

    def executemany(self, query, params_list):
        self.queries.append((query, params_list))

    def fetchone(self):
        return self.one

    def fetchall(self):
        return self.fetched

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        pass


class FakeConnection:
    def __init__(self):
        self.open = True
        self._cursor = FakeCursor()
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self, dictionary=False):
        return self._cursor

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def ping(self, reconnect=False):
        pass

    def close(self):
        self.closed = True


# Stub pymysql modules before importing code
_pymysql_mod: Any = types.ModuleType("pymysql")


def fake_connect(**kwargs):
    return FakeConnection()


_pymysql_mod.connect = fake_connect
_pymysql_mod.__path__ = []
sys.modules["pymysql"] = _pymysql_mod
_pconn_mod: Any = types.ModuleType("pymysql.connections")
_pconn_mod.Connection = FakeConnection
sys.modules["pymysql.connections"] = _pconn_mod
_pcurs_mod: Any = types.ModuleType("pymysql.cursors")
_pcurs_mod.Cursor = FakeCursor
_pcurs_mod.DictCursor = FakeCursor
sys.modules["pymysql.cursors"] = _pcurs_mod

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))
from index_core.reparse.db_manager import ReparseDBManager


def test_initialize_creates_temp_tables():
    mgr = ReparseDBManager()
    conn = mgr.connection
    assert isinstance(conn, FakeConnection)
    # Check that temp tables were created
    queries = conn._cursor.queries
    assert any("CREATE TEMPORARY TABLE _reparse_blocks" in q[0] for q in queries)


def test_execute_and_fetch_one_and_all():
    mgr = ReparseDBManager()
    conn = mgr.connection
    # Prepare description and fetched
    conn._cursor.description = [("col", None)]
    conn._cursor.fetched = [("val1",), ("val2",)]
    result, cols = mgr.execute("SELECT col", None)
    assert result == [("val1",), ("val2",)]
    assert cols == ["col"]
    # Test fetchone
    conn._cursor.one = {"a": 1}
    assert mgr.fetchone("SELECT a") == {"a": 1}
    # Test fetchall
    conn._cursor.fetched = [{"b": 2}]
    assert mgr.fetchall("SELECT b") == [{"b": 2}]


def test_table_exists_false_and_true():
    mgr = ReparseDBManager()
    conn = mgr.connection
    # Stub count = 0
    conn._cursor.one = (0,)
    assert mgr.table_exists("tbl") is False
    # Stub count = 1
    conn._cursor.one = (1,)
    assert mgr.table_exists("tbl") is True
