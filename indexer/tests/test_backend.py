"""Tests for backend module."""

import unittest
from unittest.mock import MagicMock, Mock, patch

from bitcoin.core import CTransaction

from exceptions import BackendRPCError
from index_core.backend import Backend


class TestBackend(unittest.TestCase):
    """Test Backend class."""

    def setUp(self):
        """Set up test fixtures."""
        # Reset singleton for each test
        Backend._instance = None

    def tearDown(self):
        """Clean up after tests."""
        Backend._instance = None

    def test_backend_singleton(self):
        """Test Backend singleton pattern."""
        # First instance
        backend1 = Backend()
        # Second instance should be the same object
        backend2 = Backend()

        self.assertIs(backend1, backend2)
        self.assertEqual(id(backend1), id(backend2))

    @patch("index_core.backend.config.BACKEND_RAW_TRANSACTIONS_CACHE_SIZE", 100)
    @patch("index_core.backend.config.DESERIALIZED_TX_CACHE_SIZE", 100)
    @patch("index_core.backend.config.DISABLE_RUST_PARSER", True)
    @patch("index_core.backend.RUST_PARSER_AVAILABLE", False)
    def test_backend_initialization(self):
        """Test Backend initialization."""
        with patch("index_core.backend.Backend._create_optimized_session") as mock_session:
            mock_session.return_value = Mock()

            backend = Backend()

            # Check initialization
            self.assertTrue(backend._initialized)
            self.assertIsNotNone(backend.raw_transactions_cache)
            self.assertIsNotNone(backend.deserialized_tx_cache)
            self.assertIsNotNone(backend.blockcount_cache)
            self.assertEqual(backend.blockcount_cache_ttl, 5.0)
            self.assertEqual(backend.last_blockcount_time, 0.0)

    def test_backend_multiple_init_calls(self):
        """Test that Backend only initializes once."""
        with patch("index_core.backend.Backend._create_optimized_session") as mock_session:
            mock_session.return_value = Mock()

            backend = Backend()
            first_cache = backend.raw_transactions_cache

            # Call __init__ again
            backend.__init__()

            # Should still have the same cache object
            self.assertIs(backend.raw_transactions_cache, first_cache)
            # Session creation should only be called once
            mock_session.assert_called_once()

    @patch("index_core.backend.config.BACKEND_RAW_TRANSACTIONS_CACHE_SIZE", 100)
    @patch("index_core.backend.config.DESERIALIZED_TX_CACHE_SIZE", 100)
    def test_invalidate_blockcount_cache(self):
        """Test blockcount cache invalidation."""
        with patch("index_core.backend.Backend._create_optimized_session"):
            backend = Backend()

            # Set a cached value
            backend.blockcount_cache.set("current", 800000)
            backend.last_blockcount_time = 12345

            # Invalidate cache
            backend.invalidate_blockcount_cache()

            # Check cache is cleared
            self.assertIsNone(backend.blockcount_cache.get("current"))
            self.assertEqual(backend.last_blockcount_time, 0)

    @patch("index_core.backend.config.BACKEND_RAW_TRANSACTIONS_CACHE_SIZE", 100)
    @patch("index_core.backend.config.DESERIALIZED_TX_CACHE_SIZE", 100)
    def test_getblockhash(self):
        """Test getblockhash method."""
        with patch("index_core.backend.Backend._create_optimized_session"):
            backend = Backend()

            with patch.object(backend, "rpc") as mock_rpc:
                mock_rpc.return_value = "0000000000000000000123456789abcdef"

                result = backend.getblockhash(12345)

                mock_rpc.assert_called_once_with("getblockhash", [12345])
                self.assertEqual(result, "0000000000000000000123456789abcdef")

    @patch("index_core.backend.config.BACKEND_RAW_TRANSACTIONS_CACHE_SIZE", 100)
    @patch("index_core.backend.config.DESERIALIZED_TX_CACHE_SIZE", 100)
    def test_getblock(self):
        """Test getblock method."""
        with patch("index_core.backend.Backend._create_optimized_session"):
            backend = Backend()

            block_hash = "0000000000000000000123456789abcdef"

            with patch.object(backend, "rpc") as mock_rpc:
                # Test without verbosity
                backend.getblock(block_hash)
                mock_rpc.assert_called_with("getblock", [block_hash, False])

                # Test with verbosity
                backend.getblock(block_hash, verbosity=True)
                mock_rpc.assert_called_with("getblock", [block_hash, True])

    @patch("index_core.backend.config.BACKEND_RAW_TRANSACTIONS_CACHE_SIZE", 100)
    @patch("index_core.backend.config.DESERIALIZED_TX_CACHE_SIZE", 100)
    def test_getblockheader(self):
        """Test getblockheader method."""
        with patch("index_core.backend.Backend._create_optimized_session"):
            backend = Backend()

            block_hash = "0000000000000000000123456789abcdef"
            expected_header = {"height": 800000, "time": 1234567890}

            with patch.object(backend, "rpc") as mock_rpc:
                mock_rpc.return_value = expected_header

                result = backend.getblockheader(block_hash)

                mock_rpc.assert_called_once_with("getblockheader", [block_hash])
                self.assertEqual(result, expected_header)

    @patch("index_core.backend.config.BACKEND_RAW_TRANSACTIONS_CACHE_SIZE", 100)
    @patch("index_core.backend.config.DESERIALIZED_TX_CACHE_SIZE", 100)
    def test_serialize(self):
        """Test serialize method."""
        with patch("index_core.backend.Backend._create_optimized_session"):
            backend = Backend()

            # Create a mock CTransaction
            mock_ctx = Mock(spec=CTransaction)

            with patch("bitcoin.core.CTransaction.serialize") as mock_serialize:
                mock_serialize.return_value = b"serialized_tx_data"

                result = backend.serialize(mock_ctx)

                mock_serialize.assert_called_once_with(mock_ctx)
                self.assertEqual(result, b"serialized_tx_data")

    @patch("index_core.backend.config.BACKEND_RAW_TRANSACTIONS_CACHE_SIZE", 100)
    @patch("index_core.backend.config.DESERIALIZED_TX_CACHE_SIZE", 100)
    def test_rpc_method(self):
        """Test rpc method wrapper."""
        with patch("index_core.backend.Backend._create_optimized_session"):
            backend = Backend()

            method = "getinfo"
            params = ["param1", "param2"]

            with patch.object(backend, "rpc_call") as mock_rpc_call:
                mock_rpc_call.return_value = {"result": "success"}

                result = backend.rpc(method, params)

                # Check that rpc_call was called with correct payload
                expected_payload = {
                    "method": method,
                    "params": params,
                    "jsonrpc": "2.0",
                    "id": 0,
                }
                mock_rpc_call.assert_called_once_with(expected_payload)
                self.assertEqual(result, {"result": "success"})

    @patch("index_core.backend.config.BACKEND_RAW_TRANSACTIONS_CACHE_SIZE", 100)
    @patch("index_core.backend.config.DESERIALIZED_TX_CACHE_SIZE", 100)
    def test_getblockcount_with_cache(self):
        """Test getblockcount with caching."""
        with patch("index_core.backend.Backend._create_optimized_session"):
            backend = Backend()

            # First call - should hit RPC
            with patch.object(backend, "rpc") as mock_rpc:
                mock_rpc.return_value = 800000
                with patch("time.time", return_value=1000):
                    result1 = backend.getblockcount()

                    mock_rpc.assert_called_once_with("getblockcount", [])
                    self.assertEqual(result1, 800000)

            # Second call within TTL - should use cache
            with patch.object(backend, "rpc") as mock_rpc:
                with patch("time.time", return_value=1003):  # 3 seconds later
                    result2 = backend.getblockcount()

                    # RPC should not be called
                    mock_rpc.assert_not_called()
                    self.assertEqual(result2, 800000)

            # Third call after TTL - should hit RPC again
            with patch.object(backend, "rpc") as mock_rpc:
                mock_rpc.return_value = 800001
                with patch("time.time", return_value=1006):  # 6 seconds later
                    result3 = backend.getblockcount()

                    mock_rpc.assert_called_once_with("getblockcount", [])
                    self.assertEqual(result3, 800001)

    @patch("index_core.backend.config.BACKEND_RAW_TRANSACTIONS_CACHE_SIZE", 100)
    @patch("index_core.backend.config.DESERIALIZED_TX_CACHE_SIZE", 100)
    def test_getrawtransaction_single(self):
        """Test getrawtransaction for single transaction."""
        with patch("index_core.backend.Backend._create_optimized_session"):
            backend = Backend()

            tx_hash = "abcdef123456"
            tx_data = {"hex": "0100000001..."}

            with patch.object(backend, "getrawtransaction_batch") as mock_batch:
                mock_batch.return_value = {tx_hash: tx_data}

                result = backend.getrawtransaction(tx_hash, verbose=True)

                mock_batch.assert_called_once_with([tx_hash], verbose=True, skip_missing=False, current_block=None)
                self.assertEqual(result, tx_data)


if __name__ == "__main__":
    unittest.main()
