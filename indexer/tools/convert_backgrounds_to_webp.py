#!/usr/bin/env python3
"""Convert static SRC-20 background images in bootstrap/srcbackground.csv to WebP.

The ``srcbackground`` table (and the checked-in ``bootstrap/srcbackground.csv`` that
seeds it) stores each token's background as a base64 ``data:`` payload of the form
``image/<fmt>;base64,<data>``. Static JPEG/PNG images dominate storage and compress
~60-90% as WebP; animated GIFs are left untouched so their animation is preserved.

This operates on the CSV (the source of truth that bootstraps every DB) rather than a
live DB, so it never interferes with a running indexer. Re-import / re-bootstrap applies
the result to a database; ``tools/update_bg.py`` then refreshes the stored SVGs.

Properties:
  * static only -- ``image/jpeg``, ``image/jpg``, ``image/png`` are converted; every
    other type (notably ``image/gif`` and already-``image/webp``) is passed through
    byte-for-byte.
  * never-regress -- a row is only rewritten when the WebP payload is strictly smaller
    than the original; otherwise the original is kept. No background can grow.
  * idempotent -- re-running on converted output is a no-op.

Usage:
    poetry run python tools/convert_backgrounds_to_webp.py            # in place
    poetry run python tools/convert_backgrounds_to_webp.py --in X --out Y --quality 80
"""

import argparse
import base64
import csv
import io
import os
import sys

from PIL import Image

# srcbackground.csv has no header; column order matches the table definition.
BASE64_COL = 2  # tick, tick_hash, base64, font_size, text_color, unicode, p

STATIC_MIMES = {"image/jpeg", "image/jpg", "image/png"}
DEFAULT_CSV = os.path.join(os.path.dirname(__file__), "..", "bootstrap", "srcbackground.csv")

# base64 payloads (esp. GIFs) far exceed csv's default 128 KB field cap.
csv.field_size_limit(sys.maxsize)


def split_data_uri(value):
    """Return (mime, b64data) for ``image/x;base64,DATA`` or (None, None) if not matched."""
    marker = ";base64,"
    idx = value.find(marker)
    if idx == -1:
        return None, None
    return value[:idx], value[idx + len(marker) :]


def to_webp(raw, quality):
    """Encode raw image bytes to WebP, preserving alpha. Returns WebP bytes."""
    im = Image.open(io.BytesIO(raw))
    if im.mode in ("P", "LA"):
        im = im.convert("RGBA" if "transparency" in im.info or im.mode == "LA" else "RGB")
    elif im.mode == "CMYK":
        im = im.convert("RGB")
    buf = io.BytesIO()
    im.save(buf, "WEBP", quality=quality, method=6)
    return buf.getvalue()


def convert_row(value, quality, stats):
    """Return possibly-rewritten base64 column value; mutate stats counters."""
    mime, data = split_data_uri(value)
    if mime is None:
        stats["unparsed"] += 1
        return value
    fmt = mime.split("/")[-1]
    cur_len = len(value)
    if mime not in STATIC_MIMES:
        stats["skipped_" + fmt] = stats.get("skipped_" + fmt, 0) + 1
        stats["bytes_before"] += cur_len
        stats["bytes_after"] += cur_len
        return value
    try:
        raw = base64.b64decode(data)
        webp = to_webp(raw, quality)
    except Exception as exc:  # noqa: BLE001 - report and keep original
        stats["failed"] += 1
        print(f"  ! convert failed ({mime}): {exc}; keeping original", file=sys.stderr)
        stats["bytes_before"] += cur_len
        stats["bytes_after"] += cur_len
        return value
    new_value = "image/webp;base64," + base64.b64encode(webp).decode("ascii")
    stats["bytes_before"] += cur_len
    if len(new_value) < cur_len:
        stats["converted_" + fmt] = stats.get("converted_" + fmt, 0) + 1
        stats["bytes_after"] += len(new_value)
        return new_value
    stats["kept_no_gain"] += 1
    stats["bytes_after"] += cur_len
    return value


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="in_path", default=DEFAULT_CSV, help="input CSV (default: bootstrap/srcbackground.csv)")
    ap.add_argument("--out", dest="out_path", default=None, help="output CSV (default: overwrite input)")
    ap.add_argument("--quality", type=int, default=80, help="WebP quality (default: 80)")
    args = ap.parse_args()
    out_path = args.out_path or args.in_path

    stats = {"rows": 0, "bytes_before": 0, "bytes_after": 0, "kept_no_gain": 0, "failed": 0, "unparsed": 0}
    rows = []
    with open(args.in_path, newline="") as f:
        for row in csv.reader(f):
            if len(row) > BASE64_COL:
                row[BASE64_COL] = convert_row(row[BASE64_COL], args.quality, stats)
            rows.append(row)
            stats["rows"] += 1

    tmp = out_path + ".tmp"
    with open(tmp, "w", newline="") as f:
        csv.writer(f).writerows(rows)
    os.replace(tmp, out_path)

    before, after = stats["bytes_before"], stats["bytes_after"]
    print(f"rows={stats['rows']} quality=q{args.quality}")
    for k in sorted(stats):
        if k.startswith(("converted_", "skipped_")):
            print(f"  {k}: {stats[k]}")
    print(f"  kept_no_gain={stats['kept_no_gain']} failed={stats['failed']} unparsed={stats['unparsed']}")
    pct = 100 * (before - after) / before if before else 0
    print(f"base64 bytes: {before/1024:.0f} KB -> {after/1024:.0f} KB ({pct:.1f}% smaller)")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
