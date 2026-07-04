#!/usr/bin/env python3
"""Diagnose SRC-20 ledger_hash divergence between our indexer (prod RDS) and
the canonical stampscan API. Probes a configurable block range, reports the
first divergent block, and prints a per-block breakdown.

Block_index-shadow responses (stampscan returning the prior SRC-20-touching
block when the requested block has no SRC-20 activity) are correctly
classified as ``shadow``, not ``diverge``.

Usage:

    # Bisect a wide range, sampling every 1000 blocks
    PROBE=1000 START=900000 END=955000 ./tools/check_stampscan_divergence.py

    # Walk every block (slow, for narrowing once the range is small)
    PROBE=1 START=953595 END=953620 ./tools/check_stampscan_divergence.py

    # Specific blocks
    ./tools/check_stampscan_divergence.py 953597 953598 953599

Required env (read from /home/ubuntu/btc_stamps/indexer/.env by default if
the explicit env vars aren't set):

    RDS_HOSTNAME, RDS_USER, RDS_PASSWORD, RDS_DATABASE   # the indexer DB
    SRC_VALIDATION_SECRET_API2                            # stampscan API secret

Output: one line per block to stdout; exit code 0 if no divergences found,
1 if any divergences, 2 on configuration error. Suitable as a CI gate or
ad-hoc operator probe.
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Iterable, List, Optional, Tuple
from urllib.parse import urlencode
from urllib.request import urlopen

import pymysql

STAMPSCAN_URL = "https://pkizh327c7.execute-api.us-west-2.amazonaws.com/prod/external/balanceHash"


def _load_env_file(path: str) -> None:
    """Lightweight .env loader — sets vars not already in os.environ."""
    try:
        with open(path) as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val
    except FileNotFoundError:
        pass


def _require(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        print(f"ERROR: required env var {name} is not set", file=sys.stderr)
        sys.exit(2)
    return val


def _open_db():
    return pymysql.connect(
        host=_require("RDS_HOSTNAME"),
        user=_require("RDS_USER"),
        password=_require("RDS_PASSWORD"),
        database=os.environ.get("RDS_DATABASE", "btc_stamps"),
        cursorclass=pymysql.cursors.DictCursor,
    )


def _fetch_local_hash(db, block_index: int) -> Optional[str]:
    """Return our indexer's ledger_hash for ``block_index``. ``None`` means the
    row exists but ledger_hash is empty (no SRC-20 activity in this block — by
    design the chain carries the prior SRC-20 block's hash forward). Raises
    ``KeyError`` if the block isn't indexed yet."""
    with db.cursor() as cur:
        cur.execute("SELECT ledger_hash FROM blocks WHERE block_index = %s", (block_index,))
        row = cur.fetchone()
    if row is None:
        raise KeyError(block_index)
    val = row["ledger_hash"]
    return val if val else None


def _fetch_stampscan(block_index: int, secret: str, timeout_sec: int = 15) -> Tuple[Optional[int], Optional[str]]:
    """Return ``(returned_block_index, hash)`` from the stampscan API. ``(None, None)``
    on API failure or missing payload. The returned block_index may be < requested
    when stampscan shadows to the previous SRC-20-touching block."""
    url = f"{STAMPSCAN_URL}?{urlencode({'blockIndex': block_index, 'secret': secret})}"
    try:
        with urlopen(url, timeout=timeout_sec) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        print(f"WARN: stampscan probe for block {block_index} failed: {e}", file=sys.stderr)
        return (None, None)
    if data.get("msg") == "not_indexed":
        return (None, "not_indexed")
    inner = data.get("data")
    if not isinstance(inner, dict):
        return (None, None)
    try:
        api_bi = int(inner.get("block_index"))
    except (TypeError, ValueError):
        api_bi = None
    api_hash = inner.get("hash")
    return (api_bi, api_hash)


def _classify(local: Optional[str], api_bi: Optional[int], api_hash: Optional[str], requested: int) -> str:
    """Return one of: ``match``, ``diverge``, ``shadow``, ``local_empty``,
    ``not_indexed``, ``api_error``."""
    if api_hash is None and api_bi is None:
        return "api_error"
    if api_hash == "not_indexed":
        return "not_indexed"
    if local is None:
        # Our side has no SRC-20 in this block — the chain forwards prior hash.
        # Whatever stampscan returns is informational; not a divergence.
        return "local_empty"
    if api_bi != requested:
        return "shadow"
    if local == api_hash:
        return "match"
    return "diverge"


def probe(block_indexes: Iterable[int], secret: str, per_probe_sleep: float = 0.2) -> Tuple[int, List[int]]:
    """Iterate ``block_indexes`` in order, printing one line per block to stdout.
    Returns ``(divergence_count, list_of_divergent_block_indexes)``."""
    db = _open_db()
    try:
        diverged: List[int] = []
        for bi in block_indexes:
            try:
                local = _fetch_local_hash(db, bi)
            except KeyError:
                print(f"block {bi}: indexer has not yet indexed this block — skipping")
                continue
            api_bi, api_hash = _fetch_stampscan(bi, secret)
            kind = _classify(local, api_bi, api_hash, bi)
            if kind == "match":
                print(f"block {bi}: ✓ MATCH  ledger={local[:16]}")
            elif kind == "diverge":
                diverged.append(bi)
                print(f"block {bi}: ✗ DIVERGE  prod={local[:16]}  stampscan={api_hash[:16]}")
            elif kind == "shadow":
                print(f"block {bi}: – shadow  stampscan→{api_bi} (no SRC-20 at {bi})")
            elif kind == "local_empty":
                print(f"block {bi}: – local_empty  (no SRC-20 here — chain forwards prior hash)")
            elif kind == "not_indexed":
                print(f"block {bi}: ? not_indexed by stampscan yet")
            else:
                print(f"block {bi}: ? api_error (probe failed)")
            if per_probe_sleep:
                time.sleep(per_probe_sleep)
        return (len(diverged), diverged)
    finally:
        db.close()


def _parse_block_range(argv: List[str]) -> List[int]:
    """Build the block-index list from either positional args (specific blocks)
    or START/END/PROBE env vars (range)."""
    if argv:
        return [int(x) for x in argv]
    try:
        start = int(_require("START"))
        end = int(_require("END"))
    except Exception:
        print("ERROR: pass specific blocks as args, or set START/END env vars", file=sys.stderr)
        sys.exit(2)
    step = max(1, int(os.environ.get("PROBE", "1")))
    return list(range(start, end + 1, step))


def main() -> int:
    # Fall back to prod's .env so an operator running this from anywhere on the
    # host (without exporting creds) gets reasonable defaults.
    _load_env_file("/home/ubuntu/btc_stamps/indexer/.env")
    secret = _require("SRC_VALIDATION_SECRET_API2")
    blocks = _parse_block_range(sys.argv[1:])
    print(f"Probing {len(blocks)} block(s) against stampscan...\n")
    div_count, divergent = probe(blocks, secret)
    print(f"\nResult: {div_count} divergence(s) of {len(blocks)} probed")
    if divergent:
        print(f"First divergent block: {divergent[0]}")
        if len(divergent) > 1:
            print(f"Divergent blocks: {divergent[:20]}{'...' if len(divergent) > 20 else ''}")
        return 1
    print("All probed blocks agree with stampscan ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
