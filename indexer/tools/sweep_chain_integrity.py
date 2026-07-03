#!/usr/bin/env python3
"""Read-only chain-integrity sweep for btc_stamps issue #780.

Compares the prod RDS ``blocks.block_hash`` for every ``block_index`` in the
table against the canonical bitcoind chain (``getblockhash(N)``) and reports any
row whose stored hash does not match the canonical hash at that height (i.e. a
block that was recorded on a since-orphaned fork / stale tip).

READ-ONLY by design. This tool performs ONLY:
  * ``SELECT block_index, block_hash FROM blocks`` (server-side streaming cursor)
  * bitcoind JSON-RPC ``getblockhash(N)`` (and ``getblockheader`` for context on
    mismatches)
It NEVER writes to RDS, NEVER writes to bitcoind, and does not touch any running
indexer/reparse process. It is intentionally NOT wired into CI; run it manually.

Credentials are read from an indexer ``.env`` file (default:
``/home/ubuntu/btc_stamps/indexer/.env``) or from the process environment.

Usage:
    python indexer/tools/sweep_chain_integrity.py \
        [--env-path PATH] [--batch 1000] [--parallel 6] \
        [--first N] [--last N] [--check-only] \
        [--log /tmp/sweep_chain_integrity.log] \
        [--report /tmp/sweep_chain_integrity.report.json]

    --check-only   Only run the connectivity sanity check (RDS range + a single
                   getblockcount/getblockhash) and exit. Does not sweep.
"""

import argparse
import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pymysql
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

DEFAULT_ENV_PATH = "/home/ubuntu/btc_stamps/indexer/.env"
DEFAULT_LOG_PATH = "/tmp/sweep_chain_integrity.log"
DEFAULT_REPORT_PATH = "/tmp/sweep_chain_integrity.report.json"

log = logging.getLogger("sweep")


def setup_logging(log_path):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(log_path), logging.StreamHandler(sys.stdout)],
    )


def load_env(path):
    """Merge values from a .env file with the process environment.

    Process environment takes precedence so the tool can run without the file.
    """
    env = {}
    if path and os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip().strip('"').strip("'")
    # Process environment overrides file values when present.
    for k in (
        "RPC_IP",
        "RPC_PORT",
        "RPC_USER",
        "RPC_PASSWORD",
        "RDS_HOSTNAME",
        "RDS_USER",
        "RDS_PASSWORD",
        "RDS_DATABASE",
        "RDS_PORT",
    ):
        if os.environ.get(k):
            env[k] = os.environ[k]
    return env


def make_rpc_session(user, password, pool=32):
    s = requests.Session()
    s.auth = (user, password)
    retries = Retry(
        total=5,
        backoff_factor=0.3,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=frozenset(["POST"]),
    )
    adapter = HTTPAdapter(pool_connections=pool, pool_maxsize=pool, max_retries=retries)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    s.headers.update({"content-type": "application/json"})
    return s


def rpc_batch_getblockhash(session, url, heights, timeout=60, max_attempts=5):
    """Single JSON-RPC batch call for many heights -> dict[height]=hash.

    Retries the whole batch with exponential backoff so a transient bitcoind
    hiccup (it is shared with a running indexer + reparse) does not abort the
    sweep. Read-only: getblockhash returns a hash by height, no block download.
    """
    payload = [{"jsonrpc": "1.0", "id": h, "method": "getblockhash", "params": [h]} for h in heights]
    data = json.dumps(payload)
    last_err = None
    for attempt in range(1, max_attempts + 1):
        try:
            r = session.post(url, data=data, timeout=timeout)
            r.raise_for_status()
            out = {}
            for item in r.json():
                h = item["id"]
                if item.get("error"):
                    raise RuntimeError(f"RPC error for height {h}: {item['error']}")
                out[h] = item["result"]
            return out
        except Exception as e:  # noqa: BLE001 - be considerate, back off and retry
            last_err = e
            wait = min(30, 0.5 * (2 ** (attempt - 1)))
            log.warning(
                "getblockhash batch (%s heights, first=%s) attempt %s/%s failed: %s; " "backing off %.1fs",
                len(heights),
                heights[0] if heights else "-",
                attempt,
                max_attempts,
                e,
                wait,
            )
            time.sleep(wait)
    raise RuntimeError(f"getblockhash batch failed after {max_attempts} attempts: {last_err}")


def rpc_single(session, url, method, params, timeout=30):
    payload = {"jsonrpc": "1.0", "id": "x", "method": method, "params": params}
    r = session.post(url, data=json.dumps(payload), timeout=timeout)
    r.raise_for_status()
    j = r.json()
    if j.get("error"):
        raise RuntimeError(f"{method} error: {j['error']}")
    return j["result"]


def connect_rds(env):
    return pymysql.connect(
        host=env["RDS_HOSTNAME"],
        user=env["RDS_USER"],
        password=env["RDS_PASSWORD"],
        database=env["RDS_DATABASE"],
        port=int(env.get("RDS_PORT", 3306)),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.SSDictCursor,
        autocommit=True,
        read_timeout=300,
        connect_timeout=30,
    )


def write_report(report_path, report):
    tmp = report_path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(report, f, indent=2)
    os.replace(tmp, report_path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--env-path", default=DEFAULT_ENV_PATH)
    ap.add_argument("--batch", type=int, default=1000, help="rows per getblockhash batch call")
    ap.add_argument("--parallel", type=int, default=6, help="concurrent in-flight RPC batches (keep 4-8; bitcoind is shared)")
    ap.add_argument("--first", type=int, default=None, help="lowest block_index to check (default: MIN in table)")
    ap.add_argument("--last", type=int, default=None, help="highest block_index to check (default: MAX in table)")
    ap.add_argument("--check-only", action="store_true", help="run connectivity sanity check and exit")
    ap.add_argument("--log", default=DEFAULT_LOG_PATH)
    ap.add_argument("--report", default=DEFAULT_REPORT_PATH)
    args = ap.parse_args()

    args.parallel = max(1, min(args.parallel, 8))
    setup_logging(args.log)

    env = load_env(args.env_path)
    rpc_url = f"http://{env['RPC_IP']}:{env['RPC_PORT']}/"
    rpc = make_rpc_session(env["RPC_USER"], env["RPC_PASSWORD"], pool=32)

    log.info("Connecting to RDS %s ...", env["RDS_HOSTNAME"])
    conn = connect_rds(env)

    # --- connectivity / sanity check (read-only) ---
    where = []
    params = []
    if args.first is not None:
        where.append("block_index >= %s")
        params.append(args.first)
    if args.last is not None:
        where.append("block_index <= %s")
        params.append(args.last)
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""

    with conn.cursor() as cur:
        cur.execute(
            "SELECT MIN(block_index) AS lo, MAX(block_index) AS hi, COUNT(*) AS cnt " "FROM blocks" + where_sql,
            params,
        )
        info = cur.fetchone()
    if not info or info["cnt"] == 0:
        log.error("No rows in blocks for the requested range; nothing to do.")
        return 1
    lo, hi, cnt = info["lo"], info["hi"], info["cnt"]
    log.info("blocks range to sweep: %s..%s (%s rows)", lo, hi, cnt)

    tip_count = rpc_single(rpc, rpc_url, "getblockcount", [])
    tip_hash = rpc_batch_getblockhash(rpc, rpc_url, [hi])[hi]
    log.info("bitcoind reachable: getblockcount=%s; getblockhash(%s)=%s", tip_count, hi, tip_hash)
    if hi > tip_count:
        log.warning(
            "prod max block_index %s is ABOVE bitcoind tip %s; heights above tip cannot be checked",
            hi,
            tip_count,
        )

    if args.check_only:
        log.info("--check-only: connectivity OK, exiting without sweep.")
        return 0

    # --- full sweep (read-only) ---
    BATCH = args.batch
    PARALLEL = args.parallel
    mismatches = []
    total = 0
    t0 = time.time()

    cur = conn.cursor()
    cur.execute(
        "SELECT block_index, block_hash FROM blocks" + where_sql + " ORDER BY block_index",
        params,
    )

    def fetch_canon_batch(heights):
        return rpc_batch_getblockhash(rpc, rpc_url, heights, timeout=90)

    in_flight = {}

    def submit(ex, rows):
        heights = [r["block_index"] for r in rows]
        in_flight[ex.submit(fetch_canon_batch, heights)] = rows

    def drain_one():
        nonlocal total
        done = next(as_completed(in_flight))
        rows = in_flight.pop(done)
        canon = done.result()
        for r in rows:
            idx = r["block_index"]
            prod = r["block_hash"]
            c = canon.get(idx)
            if c is None:
                # Height not in canonical chain (above tip) — record as mismatch.
                mismatches.append((idx, prod, None))
                log.warning("MISSING canonical hash for block_index=%s (above tip?)", idx)
            elif prod != c:
                mismatches.append((idx, prod, c))
                log.warning("MISMATCH block_index=%s prod=%s canon=%s", idx, prod, c)
            total += 1
            if total % 10000 == 0:
                elapsed = time.time() - t0
                rate = total / elapsed if elapsed else 0
                log.info(
                    "progress: %s/%s blocks checked (%.0f/s), %s mismatches so far",
                    total,
                    cnt,
                    rate,
                    len(mismatches),
                )
                write_report(
                    args.report,
                    {
                        "status": "in_progress",
                        "range": [lo, hi],
                        "total_rows_in_range": cnt,
                        "blocks_checked": total,
                        "mismatches_found": len(mismatches),
                        "mismatches": [{"block_index": m[0], "prod_hash": m[1], "canonical_hash": m[2]} for m in mismatches],
                    },
                )

    pending_rows = []
    with ThreadPoolExecutor(max_workers=PARALLEL) as ex:
        while True:
            row = cur.fetchone()
            if row is None:
                if pending_rows:
                    submit(ex, pending_rows)
                    pending_rows = []
                break
            pending_rows.append(row)
            if len(pending_rows) >= BATCH:
                submit(ex, pending_rows)
                pending_rows = []
                while len(in_flight) >= PARALLEL:
                    drain_one()
        while in_flight:
            drain_one()

    cur.close()

    elapsed = time.time() - t0
    log.info("=== SWEEP COMPLETE ===")
    log.info("Total blocks checked: %s", total)
    log.info("Mismatches: %s", len(mismatches))
    log.info("Elapsed: %.1fs", elapsed)

    detail = []
    for idx, prod, canon in mismatches:
        t_canon = None
        if canon:
            try:
                hdr = rpc_single(rpc, rpc_url, "getblockheader", [canon, True])
                t_canon = hdr.get("time")
            except Exception as e:  # noqa: BLE001
                t_canon = f"<err: {e}>"
        log.warning(
            "MISMATCH detail: idx=%s prod=%s canon=%s canon_time=%s",
            idx,
            prod,
            canon,
            t_canon,
        )
        detail.append(
            {
                "block_index": idx,
                "prod_hash": prod,
                "canonical_hash": canon,
                "canonical_time": t_canon,
            }
        )

    report = {
        "status": "complete",
        "range": [lo, hi],
        "total_rows_in_range": cnt,
        "blocks_checked": total,
        "mismatches_found": len(mismatches),
        "mismatches": detail,
        "elapsed_seconds": round(elapsed, 1),
    }
    write_report(args.report, report)
    log.info("Report written to %s", args.report)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
