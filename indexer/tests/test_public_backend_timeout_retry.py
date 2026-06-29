"""Focused regression test for ci/public_backend._http_get socket-timeout retry.

Root cause guarded here: on py>=3.10 a socket read timeout raises a bare
``TimeoutError`` (== ``socket.timeout``), which is NEITHER ``urllib.error.HTTPError``
nor ``urllib.error.URLError``. Before the fix it escaped the retry loop and failed
the whole reparse job (the recurring flaky "Reparse Consensus Validation" timeout).
The fix retries it with the existing capped exponential backoff; this test asserts
``_http_get`` retries past a transient ``TimeoutError`` and ultimately succeeds.

The ci/ module is CI infrastructure (not a package on the import path), so we load
it by file path rather than importing it as a normal module.
"""

import importlib.util
import os
import socket
from pathlib import Path
from unittest import mock

_MODULE_PATH = Path(__file__).resolve().parent.parent / "ci" / "public_backend.py"


def _load_public_backend():
    spec = importlib.util.spec_from_file_location("ci_public_backend", _MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_http_get_retries_socket_timeout_then_succeeds():
    pb = _load_public_backend()

    class _FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b"block-bytes"

    # First call: socket read timeout (bare TimeoutError on py>=3.10). Second
    # call: a valid response. The retry branch must absorb the timeout so the
    # second attempt runs and returns the bytes.
    calls = {"n": 0}

    def _fake_urlopen(req, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TimeoutError("timed out")
        return _FakeResp()

    # socket.timeout is an alias of TimeoutError on py>=3.10 — assert the
    # premise so the test stays honest about what it is guarding.
    assert socket.timeout is TimeoutError or issubclass(socket.timeout, OSError)

    with mock.patch.object(pb.urllib.request, "urlopen", _fake_urlopen), mock.patch.object(
        pb.time, "sleep", lambda *_a, **_k: None
    ):
        result = pb._http_get("https://example.invalid/block/abc/raw")

    assert result == b"block-bytes"
    assert calls["n"] == 2, "expected exactly one retry after the transient timeout"


def test_http_get_raises_after_exhausting_retries_on_timeout():
    pb = _load_public_backend()

    def _always_timeout(req, timeout=None):
        raise socket.timeout("timed out")

    with mock.patch.object(pb.urllib.request, "urlopen", _always_timeout), mock.patch.object(
        pb.time, "sleep", lambda *_a, **_k: None
    ):
        try:
            pb._http_get("https://example.invalid/block/abc/raw", retries=3)
        except RuntimeError as e:
            assert "failed after 3 attempts" in str(e)
        else:  # pragma: no cover - guard
            raise AssertionError("expected RuntimeError after exhausting retries")


if __name__ == "__main__":  # pragma: no cover - manual run convenience
    os.environ.setdefault("CI_BLOCKSTREAM_MIN_INTERVAL", "0")
    test_http_get_retries_socket_timeout_then_succeeds()
    test_http_get_raises_after_exhausting_retries_on_timeout()
    print("ok")
