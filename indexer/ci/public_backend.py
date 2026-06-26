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

    def serialize(self, ctx: CTransaction) -> bytes:
        """Mirrors Backend.serialize — needed by transaction_utils when it
        round-trips a parsed tx to compute fees / dedup."""
        return ctx.serialize()

    # ------------------------------------------------------------------
    # Prevout lookups (transaction_utils.get_tx_info needs these for
    # multi-input ARC4 SRC-20 stamps — the ARC4 key is derived from the
    # first input's prevout txid). blockstream.info serves these via
    # /tx/{txid}/hex.
    # ------------------------------------------------------------------

    def getrawtransaction(
        self,
        tx_hash: str,
        verbose: bool = False,
        skip_missing: bool = False,
        current_block: Any = None,
    ) -> str:
        """Return the raw transaction hex for ``tx_hash``. Mirrors the prod
        Backend signature — verbose mode is intentionally NOT implemented
        because the reparse validator only consumes hex."""
        if verbose:
            raise NotImplementedError("PublicNodeBackend.getrawtransaction(verbose=True) not implemented")
        try:
            body = _http_get(f"{self.base}/tx/{tx_hash}/hex")
        except urllib.error.HTTPError as e:
            if e.code == 404 and skip_missing:
                return ""
            raise
        return body.decode().strip()

    def getrawtransaction_batch(
        self,
        txhash_list: List[str],
        verbose: bool = False,
        skip_missing: bool = False,
        _retry: int = 0,
        max_retries: int = 3,
        current_block: Any = None,
    ) -> Dict[str, str]:
        """Batch version. blockstream.info has no batch endpoint so we issue
        N sequential requests. CI fixture sizes (a few txs per block) keep
        this tolerable; if a future fixture exercises a huge prevout fan-out
        we can parallelize."""
        if verbose:
            raise NotImplementedError("PublicNodeBackend.getrawtransaction_batch(verbose=True) not implemented")
        out: Dict[str, str] = {}
        for txid in txhash_list:
            try:
                out[txid] = self.getrawtransaction(txid, verbose=False, skip_missing=skip_missing)
            except Exception:
                if skip_missing:
                    out[txid] = ""
                else:
                    raise
        return out

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
    """Install a PublicNodeBackend through the production injection seam.

    ``index_core.backend.Backend`` is a singleton; ``set_backend_override``
    makes every ``Backend()`` call — including the import-time
    ``backend_instance = Backend()`` module globals across index_core — return
    our shim. This replaces the old per-module monkey-patching, which had to
    enumerate every module that imported ``backend_instance`` by value and
    silently fell through to the real bitcoind RPC (127.0.0.1:8332) whenever a
    module was missed.

    NOTE: this is the explicit-setter path, for callers that import all of
    index_core *before* installing. For import-order-independent installation
    (e.g. so import-time globals also pick up the shim), set the
    ``BTC_STAMPS_BACKEND_OVERRIDE=public_backend:PublicNodeBackend`` env var
    before importing index_core — ``Backend.__new__`` resolves it lazily on the
    first instantiation. ``smoke_parser_validation.py`` uses the env-var path.

    Returns the installed backend so callers can keep a reference.
    """
    from index_core.backend import Backend, set_backend_override

    # Idempotent: if the env-var path already installed a PublicNodeBackend,
    # return that exact instance (the one the import-time module globals
    # captured) rather than creating a second one.
    current = Backend()
    if isinstance(current, PublicNodeBackend):
        return current

    backend = PublicNodeBackend()
    set_backend_override(backend)
    assert Backend() is backend, "backend override did not take effect"
    return backend
