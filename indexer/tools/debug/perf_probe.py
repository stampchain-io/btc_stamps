#!/usr/bin/env python3
"""
Read-only indexing performance probe (stampsdev).

Measures, per sampled block, where per-block time goes and whether
PREWARM_DESERIALIZE_CACHE actually helps:

  A) Per-phase timing (real functions, read-only):
       fetch (getblockhash + getblock v0) | parse_block | filter (batch_parse)
       | per-candidate decode (get_tx_info incl. prev_tx fetch)
  B) PREWARM off vs on, modeled on the real main-loop sequence:
       OFF: parse_block + filter_batch_parse + per-candidate deserialize(MISS)
       ON : parse_block + prewarm_batch_parse + filter_batch_parse + deserialize(HIT)

Also captures swap activity (/proc/vmstat) over the run and DB read/write
latency (non-destructive: a TEMPORARY table) to gauge memory-pressure impact.

Usage: poetry run python tools/debug/perf_probe.py [block ...]
"""

import os
import sys
import time

sys.path.insert(0, "src")
import config  # noqa: E402
import index_core.util as util  # noqa: E402
import pymysql  # noqa: E402
from index_core.block_validation import filter_block_transactions  # noqa: E402
from index_core.transaction_utils import backend_instance as B  # noqa: E402
from index_core.transaction_utils import get_tx_info  # noqa: E402

PARSER = B._parser


def vmstat_swap():
    d = {}
    with open("/proc/vmstat") as f:
        for line in f:
            k, v = line.split()
            if k in ("pswpin", "pswpout"):
                d[k] = int(v)
    return d


def t(fn):
    s = time.perf_counter()
    r = fn()
    return (time.perf_counter() - s) * 1000.0, r


def probe_block(height):
    bh = B.getblockhash(height)
    util.CURRENT_BLOCK_INDEX = height

    ms_fetch, raw = t(lambda: B.rpc("getblock", [bh, 0]))
    ms_parse, parsed = t(lambda: PARSER.parse_block(raw))
    thl, rawtx = parsed[0], parsed[1]
    hexes = list(rawtx.values())

    block_data = {"tx": [{"txid": h, "hex": rawtx[h]} for h in thl]}
    ms_filter, filt = t(lambda: filter_block_transactions(block_data, stamp_issuances=None))
    cand_hexes = list(filt[1].values())

    # per-candidate decode (the real consensus path, incl. prev_tx RPC fetch)
    s = time.perf_counter()
    decoded = 0
    for hx in cand_hexes:
        try:
            info = get_tx_info(hx, block_index=height, db=None, stamp_issuance=None)
            if info and info.data:
                decoded += 1
        except Exception:
            pass
    ms_decode = (time.perf_counter() - s) * 1000.0

    # ---- B: prewarm OFF vs ON, modeled on the real loop ----
    # OFF: parse_block + filter_batch + per-candidate deserialize(miss)
    B.deserialized_tx_cache.clear()
    off_parse, _ = t(lambda: PARSER.parse_block(raw))
    off_filter, _ = t(lambda: PARSER.batch_parse_transactions(hexes))
    s = time.perf_counter()
    for hx in cand_hexes:
        B.deserialize(hx)
    off_deser = (time.perf_counter() - s) * 1000.0
    off_total = off_parse + off_filter + off_deser

    # ON: parse_block + prewarm_batch + filter_batch + per-candidate deserialize(hit)
    B.deserialized_tx_cache.clear()
    on_parse, _ = t(lambda: PARSER.parse_block(raw))
    on_prewarm, _ = t(lambda: B._prewarm_deserialize_cache(rawtx))
    on_filter, _ = t(lambda: PARSER.batch_parse_transactions(hexes))
    s = time.perf_counter()
    for hx in cand_hexes:
        B.deserialize(hx)
    on_deser = (time.perf_counter() - s) * 1000.0
    on_total = on_parse + on_prewarm + on_filter + on_deser

    return {
        "block": height,
        "ntx": len(thl),
        "ncand": len(cand_hexes),
        "ndecoded": decoded,
        "fetch": ms_fetch,
        "parse_block": ms_parse,
        "filter": ms_filter,
        "decode_all_cand": ms_decode,
        "off_total": off_total,
        "off_deser": off_deser,
        "on_total": on_total,
        "on_prewarm": on_prewarm,
        "on_deser": on_deser,
        "prewarm_delta": on_total - off_total,  # >0 => prewarm is SLOWER
    }


def db_latency():
    conn = pymysql.connect(
        host=os.environ.get("RDS_HOSTNAME", "127.0.0.1"),
        port=int(os.environ.get("RDS_PORT", "3306")),
        user=os.environ.get("RDS_USER", "root"),
        password=os.environ.get("RDS_PASSWORD", ""),
        database=os.environ.get("RDS_DATABASE", "btc_stamps"),
    )
    out = {}
    with conn.cursor() as cur:
        s = time.perf_counter()
        cur.execute("SELECT COUNT(*) FROM SRC20Valid WHERE tick=%s", ("IRONB",))
        cur.fetchall()
        out["select_indexed_ms"] = (time.perf_counter() - s) * 1000.0

        s = time.perf_counter()
        cur.execute("SELECT COUNT(*) FROM transactions WHERE block_index BETWEEN %s AND %s", (900000, 900500))
        cur.fetchall()
        out["select_range_ms"] = (time.perf_counter() - s) * 1000.0

        cur.execute("CREATE TEMPORARY TABLE _perf_probe (id INT, h CHAR(64), d VARCHAR(255))")
        rows = [(i, "%064x" % i, "stamp:{...payload...}") for i in range(2000)]
        s = time.perf_counter()
        cur.executemany("INSERT INTO _perf_probe VALUES (%s,%s,%s)", rows)
        conn.commit()
        out["insert_2000_ms"] = (time.perf_counter() - s) * 1000.0
        cur.execute("DROP TEMPORARY TABLE _perf_probe")
    conn.close()
    return out


def main():
    blocks = [int(b) for b in sys.argv[1:]] or [867000, 920000, 951939, 955000]
    print(f"PREWARM_DESERIALIZE_CACHE config = {config.PREWARM_DESERIALIZE_CACHE}")
    sw0 = vmstat_swap()
    print(
        f"\n{'block':>8} {'ntx':>5} {'cand':>4} {'fetch':>7} {'parse':>7} {'filter':>7} {'decode':>8} "
        f"{'OFFtot':>7} {'ONtot':>7} {'prewarmΔ':>9}"
    )
    rows = []
    for b in blocks:
        try:
            r = probe_block(b)
            rows.append(r)
            print(
                f"{r['block']:>8} {r['ntx']:>5} {r['ncand']:>4} {r['fetch']:>7.0f} {r['parse_block']:>7.0f} "
                f"{r['filter']:>7.0f} {r['decode_all_cand']:>8.0f} {r['off_total']:>7.0f} {r['on_total']:>7.0f} "
                f"{r['prewarm_delta']:>+9.0f}"
            )
        except Exception as e:
            print(f"{b:>8} ERROR {e}")
    sw1 = vmstat_swap()

    print("\n--- swap during run (pages; 1 page = 4KB) ---")
    print(f"  pswpin  +{sw1['pswpin']-sw0['pswpin']}   pswpout +{sw1['pswpout']-sw0['pswpout']}")

    print("\n--- DB latency (current memory pressure) ---")
    for k, v in db_latency().items():
        print(f"  {k}: {v:.0f} ms")

    if rows:
        n = len(rows)
        print("\n--- averages ---")
        for k in ("fetch", "parse_block", "filter", "decode_all_cand", "off_total", "on_total", "prewarm_delta"):
            print(f"  {k}: {sum(r[k] for r in rows)/n:.0f} ms")
        print("\nNOTE: prewarmΔ > 0 means PREWARM=true is SLOWER for that block.")


if __name__ == "__main__":
    main()
