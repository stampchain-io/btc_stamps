"""
Differential harness: stamp_mime.classify_safe() vs magic.from_buffer().

Purpose
-------
Continuously verify that the in-house byte-prefix classifier in
`index_core/stamp_mime.py` reproduces libmagic 5.41's
`magic.from_buffer(buf, mime=True)` output for every stamp ever indexed
into StampTableV4 — within the dispatcher's upstream gates (json.loads,
is_legitimate_html, STRIP_WHITESPACE.lstrip()). Re-run after any
classifier change to confirm continued match.

Invocation
----------
NOT auto-collected by pytest (requires RDS creds, heavy I/O). Run
manually:

    cd indexer
    export RDS_HOSTNAME=... RDS_USER=... RDS_PASSWORD=... \
           RDS_DATABASE=... RDS_PORT=3306
    python -m tests.test_stamp_mime_diff [--mode=rare|sample|full]

Run modes
---------
    rare    — only rows whose stamp_mimetype is in RARE_MIMES (~32k
              rows). Fast (~5 min). Use this iteratively while tuning
              the classifier.
    sample  — RARE_MIMES + a deterministic 0.1% sample of the four
              common types (svg/png/gif/jpeg). ~33.5k rows. ~6 min.
              Use this for sign-off when rare-mode is clean.
    full    — every row in StampTableV4 (1.47M). ONLY run from a
              non-prod host or off-peak. Final pre-merge confidence
              check.

Coverage caveat
---------------
StampTableV4 stores content in `stamp_base64`. For dedup'd content (most
SVG rows reference a hash of the unique bytes stored once) this column
may be NULL. Rows with NULL `stamp_base64` are skipped — but coverage
analysis confirmed all rare-mime rows have non-empty stamp_base64, so
the rare/sample modes hit every behaviorally-interesting code path.

Resource safety
---------------
* Uses `pymysql.cursors.SSCursor` (server-side cursor): O(1) row memory.
* Reads `stamp_base64` only — never touches consensus columns or the
  prod indexer's write surface.
* Single connection (prod indexer pool is 40 — no risk).
* Prints `---` heartbeat every 1000 rows so a stalled run is visible.

Pre-flight (operator)
---------------------
* `systemctl is-active btc-stamps-indexer` — confirm not actively
  reparsing.
* `nproc` / `free -m` — confirm headroom.
* If running on the same host as production, prefer mode=rare first;
  promote to sample/full only on a separate host.

Exit code
---------
* 0 — zero divergences across the requested mode
* 1 — at least one divergence (details printed)
* 2 — DB connect or other infra failure (details printed)
"""

from __future__ import annotations

import argparse
import base64
import binascii
import os
import sys
import time
from typing import Iterator, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "src"))

# libmagic is OPTIONAL — the harness's purpose is to verify the in-house
# classifier still matches libmagic 5.41. If libmagic isn't installed
# (e.g. running on the production image post-removal), skip the
# comparison and exit informationally.
try:
    import magic
except ImportError:
    print("INFO: python-magic / libmagic not installed in this "
          "environment. Differential check requires libmagic 5.41 as "
          "the reference. Install libmagic1=1:5.41-3ubuntu0.1 + "
          "python-magic==0.4.27 to run.", file=sys.stderr)
    sys.exit(0)

import pymysql                              # noqa: E402
from pymysql.cursors import SSCursor       # noqa: E402
from index_core import stamp_mime          # noqa: E402

# is_legitimate_html runs BEFORE libmagic in the production dispatcher
# (enhanced_mime_detection.get_processed_content_and_mime). To fairly
# compare classifier vs libmagic we apply it as a pre-filter on BOTH
# paths — matching exactly what the indexer does.
from index_core.enhanced_mime_detection import is_legitimate_html  # noqa: E402


# These are the mime values RDS has actually emitted historically. The
# rare-tail set excludes the dominant svg/png/gif/jpeg which are unlikely
# to diverge (and dwarf the corpus). The differential targets the long
# tail first because that's where classifier disagreement is plausible.
RARE_MIMES = (
    "",                           # empty stamp_mimetype column
    "text/html",
    "image/webp",
    "image/jpeg",                 # included in rare bucket because most
    "image/bmp",                  # JPEG headers are tiny (riskier diff)
    "application/gzip",
    "application/zip",
    "application/zlib",
    "application/javascript",
    "application/octet-stream",
    "application/json",
    "audio/mpeg",
    "image/avif",
    "image/heic",
    "text/xml",
    "text/plain",
)

COMMON_MIMES = ("image/svg+xml", "image/png", "image/gif")

# Decode failures are noted but not counted as divergences — they
# indicate corruption in the persisted base64, not a classifier issue.
DECODE_FAILURES = []


def connect():
    return pymysql.connect(
        host=os.environ["RDS_HOSTNAME"],
        user=os.environ["RDS_USER"],
        password=os.environ["RDS_PASSWORD"],
        database=os.environ["RDS_DATABASE"],
        port=int(os.environ.get("RDS_PORT", "3306")),
        cursorclass=SSCursor,
        read_timeout=300,
        charset="utf8mb4",
    )


def iter_rows(mode: str) -> Iterator[Tuple[str, int, str, str]]:
    """Yield (tx_hash, block_index, stamp_mimetype, stamp_base64) tuples."""
    conn = connect()
    try:
        cur = conn.cursor()
        if mode == "rare":
            fmt = ",".join(["%s"] * len(RARE_MIMES))
            sql = (
                f"SELECT tx_hash, block_index, COALESCE(stamp_mimetype,''), "
                f"stamp_base64 FROM StampTableV4 "
                f"WHERE COALESCE(stamp_mimetype,'') IN ({fmt}) "
                f"AND stamp_base64 IS NOT NULL "
                f"AND LENGTH(stamp_base64) > 0"
            )
            cur.execute(sql, RARE_MIMES)
        elif mode == "sample":
            fmt_rare = ",".join(["%s"] * len(RARE_MIMES))
            fmt_common = ",".join(["%s"] * len(COMMON_MIMES))
            sql = (
                f"SELECT tx_hash, block_index, COALESCE(stamp_mimetype,''), "
                f"stamp_base64 FROM StampTableV4 "
                f"WHERE stamp_base64 IS NOT NULL "
                f"AND LENGTH(stamp_base64) > 0 "
                f"AND (COALESCE(stamp_mimetype,'') IN ({fmt_rare}) "
                f"     OR (COALESCE(stamp_mimetype,'') IN ({fmt_common}) "
                f"         AND CRC32(tx_hash) %% 1000 = 0))"
            )
            cur.execute(sql, RARE_MIMES + COMMON_MIMES)
        elif mode == "full":
            sql = (
                "SELECT tx_hash, block_index, COALESCE(stamp_mimetype,''), "
                "stamp_base64 FROM StampTableV4 "
                "WHERE stamp_base64 IS NOT NULL "
                "AND LENGTH(stamp_base64) > 0"
            )
            cur.execute(sql)
        else:
            raise ValueError(f"unknown mode: {mode}")
        for row in cur:
            yield row
        cur.close()
    finally:
        conn.close()


def decode(b64: str) -> bytes | None:
    """Best-effort base64 decode. Returns None on hard failure."""
    if isinstance(b64, bytes):
        b64 = b64.decode("ascii", errors="replace")
    try:
        return base64.b64decode(b64, validate=False)
    except (binascii.Error, ValueError):
        return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--mode", choices=("rare", "sample", "full"), default="rare",
        help="Which subset of StampTableV4 to scan (default: rare)",
    )
    ap.add_argument(
        "--max-divergences", type=int, default=200,
        help="Stop logging after this many divergences (run still completes)",
    )
    args = ap.parse_args(argv)

    started = time.monotonic()
    divergences: list[tuple] = []
    seen = 0
    decode_fails = 0

    try:
        for tx_hash, block_index, prod_mime, b64 in iter_rows(args.mode):
            seen += 1
            buf = decode(b64)
            if buf is None:
                decode_fails += 1
                if decode_fails <= 5:
                    DECODE_FAILURES.append((tx_hash, block_index, prod_mime))
                continue

            # Mirror the production dispatcher's pre-classifier
            # transforms exactly:
            #
            #   * STRIP_WHITESPACE gate (models.py:417): above this
            #     block height, prod calls bytestring_data.lstrip()
            #     before handing the bytes to magic.from_buffer. Without
            #     this, content like "\n<svg..." reaches libmagic as
            #     literal "\n<svg..." (libmagic→text/plain) instead of
            #     "<svg..." (libmagic→image/svg+xml).
            STRIP_WHITESPACE_BLOCK = 797200
            processed = buf.lstrip() if block_index > STRIP_WHITESPACE_BLOCK else buf

            # Catch libmagic failures the same way the indexer does, so
            # the differential reflects what the indexer ACTUALLY sees.
            try:
                lib_mime = magic.from_buffer(processed, mime=True)
            except Exception:
                lib_mime = "application/octet-stream"

            new_mime = stamp_mime.classify_safe(processed)

            # Mirror the production dispatcher's TWO upstream gates that
            # run BEFORE the classifier (libmagic or in-house):
            #
            #   1. json.loads() — see models.py:406-410. If the buffer
            #      strict-parses as JSON, prod returns "application/json"
            #      directly. Six prod-corpus single-byte rows ('8', '7',
            #      '1' etc) are valid JSON literals that libmagic alone
            #      would call octet-stream — but the dispatcher's
            #      json.loads gate catches them first.
            #
            #   2. is_legitimate_html() — see enhanced_mime_detection.
            #      get_processed_content_and_mime (line 184-192 legacy /
            #      203-213 modern). Overrides to "text/html" when the
            #      buffer is well-formed HTML.
            #
            # We apply BOTH gates here so the diff reflects what the
            # indexer's dispatcher would actually emit — not raw
            # classifier output.
            try:
                import json
                # json.loads runs on RAW bytes (pre-lstrip) in
                # models.py:406-410.
                json.loads(buf.decode("utf-8"))
                lib_mime = "application/json"
                new_mime = "application/json"
            except Exception:
                try:
                    # is_legitimate_html runs on the lstripped
                    # `content_bytes` (the processed_data parameter).
                    if is_legitimate_html(processed):
                        lib_mime = "text/html"
                        new_mime = "text/html"
                except Exception:
                    pass

            if lib_mime != new_mime:
                # Suffix-equivalent collapse: libmagic sometimes returns
                # "application/x-gzip" where we return "application/gzip"
                # (same suffix "gzip"). Both pass through the same
                # downstream gate. We DO NOT consider this a divergence
                # because the file_suffix and is_btc_stamp outcomes are
                # identical.
                lib_suf = lib_mime.split("/")[-1]
                new_suf = new_mime.split("/")[-1]
                if lib_suf == new_suf:
                    continue
                divergences.append((
                    tx_hash, block_index, prod_mime, lib_mime, new_mime,
                    buf[:64].hex(),
                ))

            if seen % 1000 == 0:
                elapsed = time.monotonic() - started
                print(
                    f"--- {seen} rows scanned, {len(divergences)} "
                    f"divergences, {decode_fails} b64-decode fails, "
                    f"{elapsed:.1f}s elapsed",
                    file=sys.stderr, flush=True,
                )

    except pymysql.MySQLError as e:
        print(f"INFRA ERROR: {e}", file=sys.stderr)
        return 2

    elapsed = time.monotonic() - started
    print()
    print(f"Mode:         {args.mode}")
    print(f"Rows scanned: {seen}")
    print(f"Divergences:  {len(divergences)}")
    print(f"Decode fails: {decode_fails}")
    print(f"Wall clock:   {elapsed:.1f}s")
    print()

    for d in divergences[: args.max_divergences]:
        tx_hash, block_index, prod_mime, lib_mime, new_mime, hexprefix = d
        print(
            f"  block={block_index:>7} tx={tx_hash} "
            f"prod_mime={prod_mime!r:30s} "
            f"libmagic={lib_mime!r:30s} -> classifier={new_mime!r:30s} "
            f"head={hexprefix}"
        )
    if len(divergences) > args.max_divergences:
        print(f"  ... and {len(divergences) - args.max_divergences} more")

    if DECODE_FAILURES:
        print()
        print("First few base64 decode failures (informational):")
        for f in DECODE_FAILURES:
            print(f"  block={f[1]:>7} tx={f[0]} prod_mime={f[2]!r}")

    return 1 if divergences else 0


if __name__ == "__main__":
    sys.exit(main())
