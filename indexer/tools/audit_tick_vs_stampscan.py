#!/usr/bin/env python3
"""Walk every block where a given SRC-20 tick has activity and compare our
indexer's ledger_hash against stampscan for each. Surfaces ALL divergent
blocks for that tick (not just the first chain divergence found by the
bisect tool ``check_stampscan_divergence.py``), and includes the offending
transactions per divergent block so an operator can quickly see "what we
accepted that stampscan rejected" (or vice versa).

Companion to ``tools/check_stampscan_divergence.py`` which probes arbitrary
block ranges. This tool is tick-focused.

Usage:

    # Audit defai end-to-end (every block with defai activity)
    ./tools/audit_tick_vs_stampscan.py defai

    # Audit a subset of blocks for a tick
    START=940000 END=955000 ./tools/audit_tick_vs_stampscan.py defai

    # Stop after finding the first N divergences (default: walk full range)
    MAX_DIVERGENCES=10 ./tools/audit_tick_vs_stampscan.py defai

Required env (auto-loaded from ``/home/ubuntu/btc_stamps/indexer/.env`` if
not exported):

    RDS_HOSTNAME, RDS_USER, RDS_PASSWORD, RDS_DATABASE
    SRC_VALIDATION_SECRET_API2

Exit codes: 0 = all blocks for this tick match, 1 = divergences found, 2 = config error.
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlencode
from urllib.request import urlopen

import pymysql

STAMPSCAN_HASH_URL = "https://pkizh327c7.execute-api.us-west-2.amazonaws.com/prod/external/balanceHash"


def _load_env_file(path: str) -> None:
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


def _blocks_with_tick_activity(db, tick: str, start: Optional[int], end: Optional[int]) -> List[int]:
    """Return sorted list of block_indexes where the given tick had any
    SRC-20 activity (DEPLOY / MINT / TRANSFER) in our SRC20Valid table."""
    sql = "SELECT DISTINCT block_index FROM SRC20Valid WHERE tick = %s"
    params: List = [tick]
    if start is not None:
        sql += " AND block_index >= %s"
        params.append(start)
    if end is not None:
        sql += " AND block_index <= %s"
        params.append(end)
    sql += " ORDER BY block_index"
    with db.cursor() as cur:
        cur.execute(sql, tuple(params))
        return [row["block_index"] for row in cur.fetchall()]


def _local_ledger_hash(db, block_index: int) -> Optional[str]:
    """Return our indexer's ledger_hash for ``block_index``. ``None`` if empty
    (block has no SRC-20 — chain carries prior hash) or block not indexed."""
    with db.cursor() as cur:
        cur.execute("SELECT ledger_hash FROM blocks WHERE block_index = %s", (block_index,))
        row = cur.fetchone()
    if row is None:
        return None
    val = row["ledger_hash"]
    return val if val else None


def _stampscan_hash(block_index: int, secret: str, timeout_sec: int = 15) -> Tuple[Optional[int], Optional[str]]:
    """Return ``(returned_block_index, hash)`` from stampscan's balanceHash
    endpoint. ``(None, None)`` on API failure."""
    url = f"{STAMPSCAN_HASH_URL}?{urlencode({'blockIndex': block_index, 'secret': secret})}"
    try:
        with urlopen(url, timeout=timeout_sec) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        print(f"WARN: stampscan probe for block {block_index} failed: {e}", file=sys.stderr)
        return (None, None)
    if data.get("msg") == "not_indexed":
        return (None, None)
    inner = data.get("data")
    if not isinstance(inner, dict):
        return (None, None)
    try:
        api_bi = int(inner.get("block_index"))
    except (TypeError, ValueError):
        api_bi = None
    return (api_bi, inner.get("hash"))


def _txs_in_block_for_tick(db, block_index: int, tick: str) -> List[Dict]:
    """Return the SRC20Valid rows for the given (block_index, tick), so we can
    surface the offending txs in a divergent block."""
    with db.cursor() as cur:
        cur.execute(
            "SELECT tx_hash, op, amt, creator, destination FROM SRC20Valid "
            "WHERE block_index = %s AND tick = %s ORDER BY tx_index",
            (block_index, tick),
        )
        return cur.fetchall()


def audit_tick(tick: str, start: Optional[int], end: Optional[int], max_divergences: int) -> int:
    secret = _require("SRC_VALIDATION_SECRET_API2")
    db = _open_db()
    try:
        blocks = _blocks_with_tick_activity(db, tick, start, end)
        if not blocks:
            print(f"No SRC-20 activity found for tick={tick!r} in the requested range.")
            return 0
        print(f"Auditing {len(blocks)} block(s) with {tick!r} activity (range {blocks[0]}-{blocks[-1]})...\n")

        divergences: List[Tuple[int, str, str, List[Dict]]] = []
        match_count = 0
        for bi in blocks:
            local = _local_ledger_hash(db, bi)
            api_bi, api_hash = _stampscan_hash(bi, secret)

            if local is None:
                # No SRC-20 activity in OUR DB at this block — shouldn't happen since
                # we just selected blocks with activity, but defend against schema drift.
                continue
            if api_hash is None:
                print(f"block {bi}: ? stampscan probe failed")
                continue
            if api_bi != bi:
                # Stampscan shadow — they returned a prior block. Not a divergence
                # on its own, but worth noting since our tick *did* have activity here.
                print(f"block {bi}: – stampscan shadow→{api_bi} (we have {tick} activity here)")
                continue
            if local == api_hash:
                match_count += 1
                continue

            txs = _txs_in_block_for_tick(db, bi, tick)
            divergences.append((bi, local, api_hash, txs))
            print(f"block {bi}: ✗ DIVERGE  ours={local[:16]}  stampscan={api_hash[:16]}  ({len(txs)} {tick} txs)")
            for tx in txs:
                amt_str = str(tx["amt"]).rstrip("0").rstrip(".") if tx["amt"] is not None else "n/a"
                print(
                    f"  - {tx['tx_hash']}  {tx['op']:8s}  amt={amt_str}  " f"{tx['creator']} → {tx['destination'] or '(self)'}"
                )
            if max_divergences and len(divergences) >= max_divergences:
                print(f"\nReached MAX_DIVERGENCES={max_divergences}; stopping early.")
                break

            time.sleep(0.2)  # be polite to stampscan

        print(f"\nSummary for tick={tick!r}: " f"{match_count} match / {len(divergences)} diverge / {len(blocks)} checked")
        if divergences:
            print(f"First divergent block: {divergences[0][0]}")
            print(f"Divergent blocks: {[d[0] for d in divergences[:20]]}" f"{'...' if len(divergences) > 20 else ''}")
        return 1 if divergences else 0
    finally:
        db.close()


def main() -> int:
    _load_env_file("/home/ubuntu/btc_stamps/indexer/.env")
    if len(sys.argv) < 2:
        print("ERROR: pass the SRC-20 tick as the first arg (e.g. ./audit_tick_vs_stampscan.py defai)", file=sys.stderr)
        return 2
    tick = sys.argv[1]
    start = int(os.environ["START"]) if "START" in os.environ else None
    end = int(os.environ["END"]) if "END" in os.environ else None
    max_div = int(os.environ.get("MAX_DIVERGENCES", "0"))  # 0 = no limit
    return audit_tick(tick, start, end, max_div)


if __name__ == "__main__":
    sys.exit(main())
