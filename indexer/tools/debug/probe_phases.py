#!/usr/bin/env python3
"""
Fill the write/hash gap left by perf_probe.py (read-only / non-mutating).

Measures, per sampled block, the per-block costs perf_probe.py did NOT cover:
  - hashing CPU: building the three consensus-hash content strings
    (txlist / ledger / messages) + a sha256 over each. The messages_hash
    content is str(txhash_list) over EVERY tx in the block, so this scales
    with block size. Proxy for create_check_hashes()'s CPU (excludes its DB writes).
  - DB write: insert N rows into a TEMPORARY table mirroring the real
    `transactions` schema (12 cols) -> realistic per-block insert latency.

NOTE: CP issuance fetch (per-block Counterparty RPC) is intentionally NOT
measured here — that path is owned by the #754/#756 work.

Usage: poetry run python tools/debug/probe_phases.py [block ...]
"""
import hashlib
import os
import sys
import time

sys.path.insert(0, "src")
import pymysql  # noqa: E402
from index_core.transaction_utils import backend_instance as B  # noqa: E402

PARSER = B._parser


def hashing_cost(txhash_list):
    s = time.perf_counter()
    # mirror create_check_hashes content building; stamps/src20 are small per block,
    # the messages_hash over the full txhash_list is the size-scaling part.
    for content in (str([]), str([]), str(txhash_list)):
        hashlib.sha256(content.encode()).hexdigest()
    return (time.perf_counter() - s) * 1000.0


def db_insert_cost(nrows):
    conn = pymysql.connect(host=os.environ.get("RDS_HOSTNAME", "127.0.0.1"), port=int(os.environ.get("RDS_PORT", "3306")), user=os.environ.get("RDS_USER", "root"), password=os.environ.get("RDS_PASSWORD", ""), database=os.environ.get("RDS_DATABASE", "btc_stamps"))
    with conn.cursor() as cur:
        cur.execute(
            """CREATE TEMPORARY TABLE _pp_tx (
                 tx_index BIGINT, tx_hash CHAR(64), block_index INT, block_hash CHAR(64),
                 block_time DATETIME, source VARCHAR(64), destination TEXT, btc_amount BIGINT,
                 fee BIGINT, fee_rate_sat_vb DOUBLE, data BLOB, keyburn TINYINT)"""
        )
        rows = [
            (i, "%064x" % i, 900000, "%064x" % 0, "2024-01-01 00:00:00",
             "bc1qexamplesource", "bc1qexampledest", 0, 1430, 5.0,
             b'{"p":"src-20","op":"transfer","tick":"TEST","amt":"1000"}', 1)
            for i in range(nrows)
        ]
        s = time.perf_counter()
        cur.executemany(
            "INSERT INTO _pp_tx VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", rows
        )
        conn.commit()
        ms = (time.perf_counter() - s) * 1000.0
        cur.execute("DROP TEMPORARY TABLE _pp_tx")
    conn.close()
    return ms


def main():
    blocks = [int(b) for b in sys.argv[1:]] or [867000, 920000, 951939, 955000]
    print(f"{'block':>8} {'ntx':>6} {'hash_ms':>8} {'insert/blk_ms':>14}")
    for h in blocks:
        raw = B.rpc("getblock", [B.getblockhash(h), 0])
        thl, rawtx, *_ = PARSER.parse_block(raw)
        hm = hashing_cost(thl)
        # the indexer only inserts stamp txs (data != None); ~candidate count per block.
        infos = PARSER.batch_parse_transactions(list(rawtx.values()))
        ncand = len(infos)
        im = db_insert_cost(max(ncand, 1))
        print(f"{h:>8} {len(thl):>6} {hm:>8.1f} {im:>14.1f}  (stamp_rows={ncand})")

    print("\n--- DB insert scaling (rows -> ms, temp table) ---")
    for n in (10, 100, 1000, 5000):
        print(f"  {n:>5} rows: {db_insert_cost(n):.0f} ms")


if __name__ == "__main__":
    main()
