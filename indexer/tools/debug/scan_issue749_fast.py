#!/usr/bin/env python3
"""
Fast scan for issue #749 affected txs, using the native (rayon-parallel) Rust
parser. batch_parse_transactions returns the prefilter-accepted candidates
ALREADY deserialized (EnhancedCTransaction._ctx) plus {should_include,
has_valid_data, keyburn} — so the heavy work (deserialize every tx + filter)
happens in Rust across all cores; Python only classifies the tiny dropped set.

Per block:
  1. getblock v0 (raw hex)               -> cheap fetch
  2. parser.parse_block(raw)             -> all per-tx hexes (native)
  3. parser.batch_parse_transactions(..) -> prefilter-accepted candidates (native)
  4. dropped = accepted candidates NOT present in the `transactions` table
  5. classify each dropped tx (on the Rust-deserialized ._ctx) and bucket by reason:
       multisig_shadowed_by_p2wsh  <- issue #749 (the target)
       multisig_valid_but_dropped  <- valid multisig stamp dropped, no p2wsh (unexpected)
       p2wsh_valid_but_dropped     <- valid OLGA data dropped (unexpected, other bug)
       prefilter_false_positive    <- no valid stamp data either path (legit skip)

Usage:
  poetry run python tools/debug/scan_issue749_fast.py --start 865000 --end 955722
"""
import argparse
import base64
import json
import os
import sys
import time
import urllib.request
from collections import Counter

sys.path.insert(0, "src")
import config  # noqa: E402
import index_core.arc4 as arc4  # noqa: E402
import index_core.script as script  # noqa: E402
import pymysql  # noqa: E402
from index_core.transaction_utils import backend_instance  # noqa: E402

PREFIX = config.PREFIX
OLGA = config.BTC_SRC20_OLGA_BLOCK
PARSER = backend_instance._parser
RPC_URL = os.environ.get("RPC_URL", f"http://{os.environ.get('RPC_IP', '127.0.0.1')}:{os.environ.get('RPC_PORT', '8332')}")
RPC_AUTH = base64.b64encode(f"{os.environ.get('RPC_USER', 'rpc')}:{os.environ.get('RPC_PASSWORD', 'rpc')}".encode()).decode()


def rpc(method, params):
    body = json.dumps({"jsonrpc": "1.0", "id": "s", "method": method, "params": params}).encode()
    req = urllib.request.Request(
        RPC_URL, data=body, headers={"Authorization": "Basic " + RPC_AUTH, "Content-Type": "text/plain"}
    )
    for attempt in range(5):
        try:
            return json.load(urllib.request.urlopen(req, timeout=180))["result"]
        except Exception:
            if attempt == 4:
                raise
            time.sleep(0.5 * (attempt + 1))


def load_indexed_txids():
    conn = pymysql.connect(host=os.environ.get("RDS_HOSTNAME", "127.0.0.1"), port=int(os.environ.get("RDS_PORT", "3306")), user=os.environ.get("RDS_USER", "root"), password=os.environ.get("RDS_PASSWORD", ""), database=os.environ.get("RDS_DATABASE", "btc_stamps"))
    ids = set()
    with conn.cursor() as cur:
        cur.execute("SELECT tx_hash FROM transactions WHERE block_index >= %s", (OLGA,))
        for (h,) in cur.fetchall():
            ids.add(h)
    conn.close()
    return ids


def classify(ctx, block_index):
    """Mirror get_tx_info() decode on a deserialized ctx.
    Returns (reason, multisig_data_or_None)."""
    pubkeys_compiled = []
    keyburn = None
    p2wsh_chunks = []
    for idx, vout in enumerate(ctx.vout):
        try:
            asm = script.get_asm(vout.scriptPubKey)
        except Exception:
            continue
        if not asm:
            continue
        if asm[-1] == "OP_CHECKMULTISIG":
            try:
                pubkeys, _r, kb = script.get_checkmultisig(asm)
            except Exception:
                continue
            if kb is not None:
                keyburn = kb
            pubkeys_compiled += list(pubkeys)
        elif asm[0] == 0 and len(asm[1]) == 32 and idx > 0 and block_index >= OLGA:
            p2wsh_chunks.append(asm[1])

    # multisig path (decode_checkmultisig data extraction)
    ms = None
    if pubkeys_compiled and keyburn == 1:
        chunk = b"".join(pk[1:-1] for pk in pubkeys_compiled)
        chunk = arc4.arc4_decrypt_chunk(chunk, arc4.init_arc4(ctx.vin[0].prevout.hash[::-1]))
        if chunk[2 : 2 + len(PREFIX)] == PREFIX:
            n = int(chunk[:2].hex(), 16)
            if len(chunk) >= 2 + n:
                ms = chunk[2 + len(PREFIX) : 2 + n] or None

    # p2wsh path (get_tx_info SRC-20 branch)
    p2 = None
    has_p2wsh = bool(p2wsh_chunks)
    if has_p2wsh:
        pj = b"".join(p2wsh_chunks).rstrip(b"\x00")
        if pj and len(pj) >= 2 + len(PREFIX):
            n = int.from_bytes(pj[:2], "big")
            if len(pj) >= 2 + n and pj[2 : 2 + n].startswith(PREFIX):
                p2 = pj[2 + len(PREFIX) : 2 + n] or None

    if ms is not None and has_p2wsh and p2 is None:
        return "multisig_shadowed_by_p2wsh", ms
    if ms is not None and not has_p2wsh:
        return "multisig_valid_but_dropped", ms
    if p2 is not None:
        return "p2wsh_valid_but_dropped", p2
    return "prefilter_false_positive", None


def scan_block(height, indexed):
    raw = rpc("getblock", [rpc("getblockhash", [height]), 0])
    _thl, rawtx, *_ = PARSER.parse_block(raw)
    infos = PARSER.batch_parse_transactions(list(rawtx.values()))
    out = []
    for info in infos:
        txid = info._extra_attrs.get("txid")
        if txid in indexed:
            continue  # successfully indexed -> not dropped
        reason, data = classify(info._ctx, height)
        if reason == "prefilter_false_positive":
            continue  # legitimately not a stamp; skip noise
        try:
            payload = data.decode("utf-8", "replace") if data else ""
        except Exception:
            payload = data.hex() if data else ""
        out.append({"txid": txid, "block": height, "reason": reason, "data": payload})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, required=True)
    ap.add_argument("--end", type=int, required=True)
    ap.add_argument("--out", default="/tmp/issue749_affected.json")
    ap.add_argument("--sleep", type=float, default=0.0, help="seconds to sleep between blocks (throttle shared bitcoind)")
    args = ap.parse_args()

    print(f"loading indexed txids (block >= {OLGA}) ...", flush=True)
    indexed = load_indexed_txids()
    print(f"  {len(indexed)} indexed txids loaded", flush=True)

    heights = list(range(args.start, args.end + 1))
    t0 = time.time()
    found = []
    done = 0
    for h in heights:
        try:
            found += scan_block(h, indexed)
        except Exception as e:
            print(f"  block {h} error: {e}", flush=True)
        done += 1
        if args.sleep:
            time.sleep(args.sleep)
        if done % 500 == 0:
            el = time.time() - t0
            rate = done / el
            eta = (len(heights) - done) / rate / 60
            print(
                f"  [{done}/{len(heights)}] {el:.0f}s {rate:.1f} blk/s ETA {eta:.1f}m found={len(found)}",
                flush=True,
            )
            with open(args.out, "w") as f:  # checkpoint
                json.dump(found, f, indent=2)

    el = time.time() - t0
    found.sort(key=lambda a: a["block"])
    with open(args.out, "w") as f:
        json.dump(found, f, indent=2)
    print(f"\nDONE {args.start}-{args.end}: {len(heights)} blocks in {el/60:.1f} min ({len(heights)/el:.1f} blk/s)")
    print(f"total flagged = {len(found)}")
    print("by reason:", dict(Counter(a["reason"] for a in found)))
    print(f"-> {args.out}")
    for a in found[:40]:
        print("  ", a["block"], a["txid"], a["reason"], a["data"][:70])


if __name__ == "__main__":
    main()
