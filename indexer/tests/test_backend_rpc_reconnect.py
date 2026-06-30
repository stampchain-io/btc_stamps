"""Regression test for issue #812: stale bitcoind RPC connections after a backend restart.

Root cause guarded here: after a ``bitcoind`` restart the keep-alive connection
pool on the live indexer's ``requests.Session`` can hand back a half-open
(CLOSE-WAIT) socket; a subsequent RPC call then blocks/hangs and the indexer
wedges near tip until a manual restart.

The fix (``Backend._reset_session``) drops the stale pool and reconnects on a
fresh session inside the existing ``rpc_call`` retry loop, and every call applies
a bounded ``(connect, read)`` timeout so a wedged socket raises instead of
hanging forever. These tests assert that:

  * a ``ConnectionError`` / ``Timeout`` raised once is retried on a brand-new
    session (the stale session is closed) and ultimately succeeds, and
  * the bounded timeout is passed to every ``session.post`` call.

This is a connection-resilience guard only: RPC results / request payloads /
parse path are unchanged (Consensus-None).
"""

import unittest
from unittest.mock import Mock, patch

from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import Timeout

from index_core.backend import Backend


def _ok_response(result):
    resp = Mock()
    resp.status_code = 200
    resp.json.return_value = {"result": result, "error": None}
    return resp


@patch("index_core.backend.config.RPC_URL", "http://user:pass@127.0.0.1:8332")
@patch("index_core.backend.config.QUICKNODE_ENDPOINT", None)
@patch("index_core.backend.config.QUICKNODE_API_KEY", None)
class TestBackendRpcReconnect(unittest.TestCase):
    """rpc_call must self-heal after a stale/dropped bitcoind connection."""

    def setUp(self):
        Backend._instance = None
        Backend._override = None

    def tearDown(self):
        Backend._instance = None
        Backend._override = None

    def test_reconnects_on_connection_error_then_succeeds(self):
        """A ConnectionError once -> stale pool dropped, retried on a fresh session, succeeds."""
        stale_session = Mock(name="stale_session")
        stale_session.post.side_effect = RequestsConnectionError("Connection reset by peer")
        fresh_session = Mock(name="fresh_session")
        fresh_session.post.return_value = _ok_response(840000)

        # The session factory yields the initial (stale) pool, then the
        # reconnect pool. Keep it patched for the whole call so the reconnect
        # inside rpc_call gets the mock and never dials a real socket.
        with patch(
            "index_core.backend.Backend._create_optimized_session",
            side_effect=[stale_session, fresh_session],
        ), patch("index_core.backend.time.sleep"):
            backend = Backend()
            result = backend.rpc("getblockcount", [])

        self.assertEqual(result, 840000)
        # The stale pool was closed (sockets reaped) ...
        stale_session.close.assert_called_once()
        # ... and the retry went out on the brand-new session.
        fresh_session.post.assert_called_once()
        # The live session is now the fresh one.
        self.assertIs(backend._session, fresh_session)

    def test_reconnects_on_socket_timeout_then_succeeds(self):
        """A read Timeout (wedged socket) is also healed via reconnect + retry."""
        stale_session = Mock(name="stale_session")
        stale_session.post.side_effect = Timeout("read timed out")
        fresh_session = Mock(name="fresh_session")
        fresh_session.post.return_value = _ok_response("deadbeef")

        with patch(
            "index_core.backend.Backend._create_optimized_session",
            side_effect=[stale_session, fresh_session],
        ), patch("index_core.backend.time.sleep"):
            backend = Backend()
            result = backend.rpc("getblockhash", [840000])

        self.assertEqual(result, "deadbeef")
        stale_session.close.assert_called_once()
        fresh_session.post.assert_called_once()

    def test_bounded_timeout_applied_to_every_call(self):
        """Every RPC post must carry a bounded (connect, read) timeout."""
        session = Mock(name="session")
        session.post.return_value = _ok_response(1)

        with patch(
            "index_core.backend.Backend._create_optimized_session",
            side_effect=[session],
        ), patch("index_core.backend.time.sleep"):
            backend = Backend()
            backend.rpc("getblockcount", [])

        _, kwargs = session.post.call_args
        self.assertEqual(kwargs["timeout"], (5, 30))  # safe defaults
        # Both bounds are finite/positive so a wedged socket cannot hang forever.
        connect_timeout, read_timeout = kwargs["timeout"]
        self.assertGreater(connect_timeout, 0)
        self.assertGreater(read_timeout, 0)

    def test_rpc_timeout_env_override(self):
        """RPC_TIMEOUT / RPC_CONNECT_TIMEOUT env vars override the defaults."""
        with patch.dict("os.environ", {"RPC_CONNECT_TIMEOUT": "3", "RPC_TIMEOUT": "45"}):
            self.assertEqual(Backend._get_rpc_timeout(), (3.0, 45.0))


if __name__ == "__main__":  # pragma: no cover - manual run convenience
    unittest.main()
