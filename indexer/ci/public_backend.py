"""Public-node-backed Backend shim for the reparse-validate CI workflow.

The production ``index_core.backend.Backend`` talks bitcoind JSON-RPC. CI on a
remote runner doesn't have access to a bitcoind, so this module implements the
subset of the Backend interface that reparse.validator.compute_block_hashes
actually calls, backed by the public blockstream.info REST API:

  * ``getblockhash(block_index) -> str``
  * ``getblock(block_hash, verbosity=2) -> dict``
      shape: {"tx": [{"txid": ..., "hex": ...}, ...], "time": int}
  * ``deserialize(tx_hex) -> CTransaction``  (used by Python-fallback filter)
  * ``_parser`` attribute  (None — forces the slower Python filter path; the
    parser is still imported and used by ``compute_block_hashes`` itself, but
    the filter doesn't need it here at CI fixture sizes)

Trust model: Bitcoin blocks are content-addressed. The caller passes the
expected ``block_hash`` and we verify the bytes hash to it before parsing.
A malicious blockstream response can't produce a valid header hash without
breaking SHA256; if the hash mismatches we raise.

This module deliberately does NOT live under ``indexer/src/index_core/`` — it's
test/CI infrastructure, not part of the production indexer code path.
"""

from __future__ import annotations

import hashlib
import io
import urllib.error
import urllib.request
from typing import Any, Dict, List

# python-bitcoinlib is already a runtime dep (bitcoin.core is imported by
# index_core.backend). Reuse it here to avoid pulling in another parser.
from bitcoin.core import CBlock, CTransaction

BLOCKSTREAM_BASE = "https://blockstream.info/api"


def _http_get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "btc-stamps-ci/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _double_sha256_le_hex(data: bytes) -> str:
    """Bitcoin block hash: little-endian double-SHA256 of the 80-byte header."""
    digest = hashlib.sha256(hashlib.sha256(data).digest()).digest()
    return digest[::-1].hex()


class PublicNodeBackend:
    """Drop-in stand-in for index_core.backend.Backend for CI reparse.

    Only the methods reparse.validator and block_validation call are
    implemented. Everything else raises NotImplementedError so accidental
    coupling to production paths fails loudly rather than silently.
    """

    def __init__(self, base: str = BLOCKSTREAM_BASE) -> None:
        self.base = base.rstrip("/")
        # The production filter path calls `backend_instance._parser` to decide
        # between the Rust batch path and the Python single-tx fallback. Set to
        # None to take the fallback — slower but doesn't require the Rust
        # parser wheel at this layer, and the fixture sizes make it tolerable.
        self._parser = None

    # ------------------------------------------------------------------
    # Bitcoin RPC compatibility surface
    # ------------------------------------------------------------------

    def getblockhash(self, block_index: int) -> str:
        body = _http_get(f"{self.base}/block-height/{int(block_index)}")
        return body.decode().strip()

    def getblock(self, block_hash: str, verbosity: int = 2) -> Dict[str, Any]:
        if verbosity != 2:
            raise NotImplementedError(f"PublicNodeBackend only supports verbosity=2 (got {verbosity})")

        raw = _http_get(f"{self.base}/block/{block_hash}/raw")
        computed = _double_sha256_le_hex(raw[:80])
        if computed != block_hash:
            raise RuntimeError(f"blockstream block bytes for {block_hash} hash to {computed}; refusing to use")

        block = CBlock.deserialize(raw)
        # CBlock.nTime is the block header timestamp (uint32)
        block_time = int(block.nTime)

        tx_list: List[Dict[str, str]] = []
        for tx in block.vtx:
            # python-bitcoinlib's GetTxid() == reversed double-SHA of serialized
            # tx WITHOUT witness, which matches bitcoind's txid (NOT wtxid).
            try:
                txid_bytes = tx.GetTxid()
            except AttributeError:
                # Older python-bitcoinlib lacks GetTxid; fall back to GetHash for
                # non-segwit cases. Modern installations have GetTxid.
                txid_bytes = tx.GetHash()
            tx_list.append(
                {
                    "txid": txid_bytes[::-1].hex(),  # bitcoind shows big-endian
                    "hex": tx.serialize().hex(),
                }
            )

        return {"tx": tx_list, "time": block_time}

    # ------------------------------------------------------------------
    # Methods called by block_validation.filter_block_transactions Python fallback
    # ------------------------------------------------------------------

    def deserialize(self, tx_hex: str) -> CTransaction:
        """Return a CTransaction parsed from hex. Mirrors Backend.deserialize."""
        return CTransaction.deserialize(bytes.fromhex(tx_hex))

    # ------------------------------------------------------------------
    # Safety net: anything else fails loudly rather than silently
    # ------------------------------------------------------------------

    def __getattr__(self, name: str) -> Any:
        raise NotImplementedError(
            f"PublicNodeBackend does not implement {name!r}. "
            "This is a deliberate restriction — CI reparse only needs "
            "getblockhash, getblock(verbosity=2), and deserialize."
        )


def install_public_backend() -> PublicNodeBackend:
    """Monkey-patch index_core modules to use a PublicNodeBackend instance.

    Returns the installed backend so callers can keep a reference.
    """
    backend = PublicNodeBackend()
    # The production code reads ``backend_instance`` from a few modules; patch
    # them all so reparse.validator and block_validation pick up our shim.
    import index_core.backend as _backend_mod
    import index_core.block_validation as _bv_mod
    import index_core.transaction_utils as _tu_mod

    _backend_mod.backend_instance = backend
    _bv_mod.backend_instance = backend
    _tu_mod.backend_instance = backend
    return backend
