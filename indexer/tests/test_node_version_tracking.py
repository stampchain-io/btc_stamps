"""
Tests for node version tracking
================================

Tests for upsert_node_version(), get_current_versions(), version parsing,
and persist_all_versions() orchestration.
"""

import json
import unittest
from unittest.mock import MagicMock, patch

import pytest


class TestUpsertNodeVersion(unittest.TestCase):
    """Test upsert_node_version() insert, skip, and version change behavior."""

    def _make_mock_db(self, fetchone_return=None):
        db = MagicMock()
        cursor = MagicMock()
        db.cursor.return_value = cursor
        cursor.fetchone.return_value = fetchone_return
        return db, cursor

    def test_new_insert(self):
        """First insert for a component should INSERT with is_current=TRUE."""
        from index_core.database import upsert_node_version

        db, cursor = self._make_mock_db(fetchone_return=None)

        result = upsert_node_version(
            db,
            component_name="bitcoin_core",
            version_string="28.0.0",
            version_major=28,
            version_minor=0,
            version_revision=0,
        )

        assert result is True
        # Should not UPDATE (no existing row)
        calls = cursor.execute.call_args_list
        assert len(calls) == 2  # SELECT + INSERT
        assert "INSERT" in calls[1][0][0]
        db.commit.assert_called_once()

    def test_no_change_skip(self):
        """Same version_string should return False and not write."""
        from index_core.database import upsert_node_version

        db, cursor = self._make_mock_db(fetchone_return=(42, "28.0.0"))

        result = upsert_node_version(
            db,
            component_name="bitcoin_core",
            version_string="28.0.0",
        )

        assert result is False
        # Only the SELECT, no INSERT or UPDATE
        calls = cursor.execute.call_args_list
        assert len(calls) == 1
        db.commit.assert_not_called()

    def test_version_change_with_history(self):
        """Different version should supersede the old row and insert new."""
        from index_core.database import upsert_node_version

        db, cursor = self._make_mock_db(fetchone_return=(42, "27.0.0"))

        result = upsert_node_version(
            db,
            component_name="bitcoin_core",
            version_string="28.0.0",
            version_major=28,
            version_minor=0,
            version_revision=0,
        )

        assert result is True
        calls = cursor.execute.call_args_list
        assert len(calls) == 3  # SELECT + UPDATE old + INSERT new
        # UPDATE should set is_current=NULL and superseded_at
        update_sql = calls[1][0][0]
        assert "is_current = NULL" in update_sql
        assert "superseded_at" in update_sql
        # INSERT should have is_current=TRUE
        insert_sql = calls[2][0][0]
        assert "INSERT" in insert_sql
        db.commit.assert_called_once()

    def test_extra_info_serialized_as_json(self):
        """extra_info dict should be serialized to JSON string."""
        from index_core.database import upsert_node_version

        db, cursor = self._make_mock_db(fetchone_return=None)

        extra = {"subversion": "/Satoshi:28.0.0/", "connections": 10}
        upsert_node_version(
            db,
            component_name="bitcoin_core",
            version_string="28.0.0",
            extra_info=extra,
        )

        insert_call = cursor.execute.call_args_list[1]
        params = insert_call[0][1]
        # extra_info_json should be at index 6
        assert json.loads(params[6]) == extra

    def test_rollback_on_error(self):
        """DB errors during insert should trigger rollback."""
        from index_core.database import upsert_node_version

        db, cursor = self._make_mock_db(fetchone_return=None)
        # Make the INSERT fail
        cursor.execute.side_effect = [None, Exception("DB error")]

        with pytest.raises(Exception, match="DB error"):
            upsert_node_version(
                db,
                component_name="bitcoin_core",
                version_string="28.0.0",
            )

        db.rollback.assert_called_once()


class TestGetCurrentVersions(unittest.TestCase):
    """Test get_current_versions() returns correctly formatted data."""

    def test_returns_formatted_rows(self):
        from index_core.database import get_current_versions

        db = MagicMock()
        cursor = MagicMock()
        db.cursor.return_value = cursor
        cursor.description = [
            ("component_name",),
            ("version_string",),
            ("version_major",),
            ("version_minor",),
            ("version_revision",),
            ("version_suffix",),
            ("extra_info",),
            ("detected_at",),
        ]
        cursor.fetchall.return_value = [
            ("bitcoin_core", "28.0.0", 28, 0, 0, None, '{"connections": 10}', "2025-01-01"),
            ("stamps_indexer", "1.8.26+canary.252", 1, 8, 26, "canary.252", None, "2025-01-01"),
        ]

        results = get_current_versions(db)

        assert len(results) == 2
        assert results[0]["component_name"] == "bitcoin_core"
        assert results[0]["extra_info"] == {"connections": 10}
        assert results[1]["extra_info"] is None


class TestBitcoinCoreVersionParsing(unittest.TestCase):
    """Test Bitcoin Core version integer parsing (e.g. 280000 -> 28.0.0)."""

    def test_standard_version(self):
        """280000 should parse to 28.0.0."""
        version_int = 280000
        major = version_int // 10000
        minor = (version_int % 10000) // 100
        revision = version_int % 100
        assert (major, minor, revision) == (28, 0, 0)

    def test_version_with_minor_and_revision(self):
        """250201 should parse to 25.2.1."""
        version_int = 250201
        major = version_int // 10000
        minor = (version_int % 10000) // 100
        revision = version_int % 100
        assert (major, minor, revision) == (25, 2, 1)

    def test_version_270100(self):
        """270100 should parse to 27.1.0."""
        version_int = 270100
        major = version_int // 10000
        minor = (version_int % 10000) // 100
        revision = version_int % 100
        assert (major, minor, revision) == (27, 1, 0)


class TestIndexerVersionParsing(unittest.TestCase):
    """Test indexer semver+suffix parsing."""

    def test_version_with_suffix(self):
        import re

        version_string = "1.8.26+canary.252"
        match = re.match(r"(\d+)\.(\d+)\.(\d+)(?:\+(.+))?", version_string)
        assert match is not None
        assert (int(match.group(1)), int(match.group(2)), int(match.group(3))) == (1, 8, 26)
        assert match.group(4) == "canary.252"

    def test_version_without_suffix(self):
        import re

        version_string = "2.0.0"
        match = re.match(r"(\d+)\.(\d+)\.(\d+)(?:\+(.+))?", version_string)
        assert match is not None
        assert (int(match.group(1)), int(match.group(2)), int(match.group(3))) == (2, 0, 0)
        assert match.group(4) is None


class TestPersistAllVersions(unittest.TestCase):
    """Test persist_all_versions() orchestration."""

    @patch("index_core.node_health.persist_indexer_version")
    @patch("index_core.node_health.persist_bitcoin_core_version")
    @patch("index_core.node_health.persist_counterparty_versions")
    def test_calls_all_persist_functions(self, mock_cp, mock_btc, mock_idx):
        from index_core.node_health import persist_all_versions

        persist_all_versions()

        mock_btc.assert_called_once()
        mock_cp.assert_called_once()
        mock_idx.assert_called_once()

    @patch("index_core.node_health.persist_indexer_version")
    @patch("index_core.node_health.persist_bitcoin_core_version")
    @patch("index_core.node_health.persist_counterparty_versions")
    def test_one_failure_doesnt_block_others(self, mock_cp, mock_btc, mock_idx):
        """If bitcoin_core persistence fails, counterparty and indexer should still run."""
        from index_core.node_health import persist_all_versions

        mock_btc.side_effect = Exception("RPC down")

        persist_all_versions()

        mock_btc.assert_called_once()
        mock_cp.assert_called_once()
        mock_idx.assert_called_once()


class TestPersistBitcoinCoreVersion(unittest.TestCase):
    """Test persist_bitcoin_core_version() with mocked RPC."""

    @patch("index_core.database_manager.DatabaseManager")
    @patch("index_core.backend.Backend")
    def test_persist_bitcoin_core_version(self, mock_backend_cls, mock_db_mgr_cls):
        from index_core.node_health import persist_bitcoin_core_version

        mock_backend = MagicMock()
        mock_backend.getnetworkinfo.return_value = {
            "version": 280000,
            "subversion": "/Satoshi:28.0.0/",
            "protocolversion": 70016,
            "connections": 10,
        }
        mock_backend_cls.return_value = mock_backend

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None  # No existing row
        mock_db_mgr_cls.return_value.connect.return_value = mock_db

        persist_bitcoin_core_version()

        # Verify INSERT was called with correct version
        insert_call = mock_cursor.execute.call_args_list[1]
        params = insert_call[0][1]
        assert params[0] == "bitcoin_core"
        assert params[1] == "28.0.0"
        assert params[2] == 28  # major
        assert params[3] == 0  # minor
        assert params[4] == 0  # revision
        mock_db.close.assert_called_once()

    @patch("index_core.backend.Backend")
    def test_skips_when_rpc_fails(self, mock_backend_cls):
        from index_core.node_health import persist_bitcoin_core_version

        mock_backend = MagicMock()
        mock_backend.getnetworkinfo.return_value = None
        mock_backend_cls.return_value = mock_backend

        # Should not raise
        persist_bitcoin_core_version()


class TestPersistIndexerVersion(unittest.TestCase):
    """Test persist_indexer_version() with mocked config."""

    @patch("index_core.database_manager.DatabaseManager")
    @patch("index_core.node_health.config")
    def test_persist_indexer_version(self, mock_config, mock_db_mgr_cls):
        from index_core.node_health import persist_indexer_version

        mock_config.VERSION_STRING = "1.8.26+canary.252"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None
        mock_db_mgr_cls.return_value.connect.return_value = mock_db

        persist_indexer_version()

        insert_call = mock_cursor.execute.call_args_list[1]
        params = insert_call[0][1]
        assert params[0] == "stamps_indexer"
        assert params[1] == "1.8.26+canary.252"
        assert params[2] == 1  # major
        assert params[3] == 8  # minor
        assert params[4] == 26  # revision
        assert params[5] == "canary.252"  # suffix
        mock_db.close.assert_called_once()


class TestPersistCounterpartyVersions(unittest.TestCase):
    """Test persist_counterparty_versions() with mocked fetch."""

    @patch("index_core.database_manager.DatabaseManager")
    @patch("index_core.fetch_utils.fetch_node_version_v2")
    @patch("index_core.node_health.config")
    def test_persist_counterparty_versions(self, mock_config, mock_fetch, mock_db_mgr_cls):
        from index_core.node_health import persist_counterparty_versions

        mock_config.NODES = [
            {"name": "local", "url": "http://localhost:4000/v2"},
        ]

        mock_fetch.return_value = (
            "11.0.3",
            {
                "version_major": 11,
                "version_minor": 0,
                "version_revision": 3,
                "last_block": 850000,
                "last_message_index": 12345,
                "network": "mainnet",
                "server_ready": True,
            },
        )

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None
        mock_db_mgr_cls.return_value.connect.return_value = mock_db

        persist_counterparty_versions()

        insert_call = mock_cursor.execute.call_args_list[1]
        params = insert_call[0][1]
        assert params[0] == "counterparty:local"
        assert params[1] == "11.0.3"
        mock_db.close.assert_called_once()

    @patch("index_core.database_manager.DatabaseManager")
    @patch("index_core.fetch_utils.fetch_node_version_v2")
    @patch("index_core.node_health.config")
    def test_skips_node_when_fetch_fails(self, mock_config, mock_fetch, mock_db_mgr_cls):
        from index_core.node_health import persist_counterparty_versions

        mock_config.NODES = [
            {"name": "local", "url": "http://localhost:4000/v2"},
        ]
        mock_fetch.return_value = (None, None)

        mock_db = MagicMock()
        mock_db_mgr_cls.return_value.connect.return_value = mock_db

        persist_counterparty_versions()

        # No cursor operations beyond the connection
        mock_db.cursor.assert_not_called()
        mock_db.close.assert_called_once()
