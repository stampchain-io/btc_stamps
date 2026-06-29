#!/usr/bin/env python3
"""Regenerate stored SRC-20 stamp SVGs for given ticks and re-upload them to S3.

Use this after changing a token's background in ``srcbackground`` (e.g. the WebP
re-encode in tools/convert_backgrounds_to_webp.py) to refresh the already-rendered
``{tx_hash}.svg`` files on S3 **without** a full chain reindex. For each matching
``SRC20Valid`` row it rebuilds the SVG from the current background, uploads it
(overwriting the same S3 key), and updates ``StampTableV4.file_hash`` /
``file_size_bytes``.

Connection uses the standard ``RDS_*`` env vars, so run this on the host whose env
points at the target database (the prod deployment's env points ``RDS_*`` at Aurora).
S3 upload only happens when ``STORE_FILES`` + ``AWS_S3_*`` are configured (see config.py);
with storage disabled it updates the DB only -- so a dev run never touches S3.

CDN note: stamp objects are served by Cloudflare as ``immutable, max-age=31536000``.
Overwriting S3 alone leaves clients on the stale cached copy, so this writes a purge
manifest (one stamp URL per regenerated file) for a follow-up Cloudflare cache purge.

Usage:
    poetry run python tools/update_bg.py KEVIN STAMP            # specific ticks
    poetry run python tools/update_bg.py --all-webp            # every tick now WebP-backed
    poetry run python tools/update_bg.py --all-webp --dry-run  # report only, no upload/DB write
"""

import argparse
import os
import sys

import pymysql as mysql
from dotenv import load_dotenv

_INDEXER_DIR = os.getcwd() if os.getcwd().endswith("/indexer") else os.path.join(os.getcwd(), "indexer")
sys.path.append(_INDEXER_DIR)
# config in this stack reads .env.local; fall back to .env. Neither overrides a real env var.
for _name in (".env.local", ".env"):
    load_dotenv(dotenv_path=os.path.join(_INDEXER_DIR, _name))

import config  # noqa: E402
from index_core.async_upload import stop_upload_worker, wait_for_uploads  # noqa: E402
from index_core.aws import get_s3_objects  # noqa: E402
from index_core.src20 import build_src20_svg_string  # noqa: E402
from index_core.stamp import store_files  # noqa: E402

STAMP_MIMETYPE = "image/svg+xml"


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument(
        "ticks",
        nargs="*",
        help="tick values to regenerate (use double backslash for unicode, e.g. bear\\\\u0001f43b)",
    )
    p.add_argument(
        "--all-webp",
        action="store_true",
        help="regenerate every tick whose srcbackground is now image/webp (the converted set)",
    )
    p.add_argument("--dry-run", action="store_true", help="report counts/sizes only; no S3 upload, no DB write")
    p.add_argument(
        "--no-s3-dedup",
        action="store_true",
        help="skip enumerating existing S3 objects; treat every file as new (overwrite). "
        "Use when every targeted file changed (e.g. --all-webp) to avoid a full-bucket list.",
    )
    p.add_argument(
        "--shard",
        default=None,
        help="process only shard i of M of the resolved ticks (e.g. 3/8). Lets several "
        "processes run disjoint subsets in parallel against a robust DB.",
    )
    p.add_argument(
        "--manifest",
        default="update_bg_purge_urls.txt",
        help="file to write regenerated stamp URLs for the Cloudflare purge step",
    )
    return p.parse_args()


def connect():
    return mysql.connect(
        host=os.environ.get("RDS_HOSTNAME"),
        user=os.environ.get("RDS_USER"),
        password=os.environ.get("RDS_PASSWORD"),
        port=int(os.environ.get("RDS_PORT", 3306)),
        database=os.environ.get("RDS_DATABASE"),
    )


def resolve_ticks(cursor, args):
    if args.all_webp:
        # ORDER BY so every shard sees the same ordering and the i::M slices partition cleanly.
        cursor.execute("SELECT tick FROM srcbackground WHERE base64 LIKE 'image/webp%' AND p = 'SRC-20' ORDER BY tick")
        ticks = [r[0] for r in cursor.fetchall()]
    else:
        ticks = list(args.ticks)
    # de-dup (preserve order) so shards are strictly disjoint -- avoids two shards racing the same S3 keys.
    ticks = list(dict.fromkeys(ticks))
    if args.shard:
        i, m = (int(x) for x in args.shard.split("/"))
        ticks = ticks[i::m]
        print(f"shard {i}/{m}: {len(ticks)} tick(s)")
    return ticks


def main():
    args = parse_args()
    db = connect()
    cursor = db.cursor()
    print(f"connected to {os.environ.get('RDS_HOSTNAME')} / {os.environ.get('RDS_DATABASE')}  dry_run={args.dry_run}")

    s3_enabled = bool(config.AWS_S3_ENABLED)
    if not args.dry_run and not s3_enabled:
        print("WARNING: S3 storage is disabled (STORE_FILES/AWS_S3_* unset) -- will update DB only, no upload.")
    if not args.dry_run and s3_enabled:
        if args.no_s3_dedup:
            config.S3_OBJECTS = {}  # every upload treated as new -> overwrite; no bucket enumeration
        else:
            config.S3_OBJECTS = get_s3_objects(db, config.AWS_S3_BUCKETNAME, config.AWS_S3_CLIENT)

    ticks = resolve_ticks(cursor, args)
    if not ticks:
        print("no ticks to process (pass ticks or --all-webp)")
        return
    print(f"processing {len(ticks)} tick(s)")

    # Flush async uploads per tick: the unbounded upload queue would otherwise buffer the
    # whole run (~1.2M SVGs) in memory. Per-tick commit also checkpoints progress.
    flush_async = (not args.dry_run) and s3_enabled and config.USE_ASYNC_UPLOADS
    regenerated = 0
    manifest_count = 0
    manifest_f = open(args.manifest, "w")
    try:
        for i, tick in enumerate(ticks, 1):
            cursor.execute(
                "SELECT tx_hash, p, op, tick, amt, lim, max FROM SRC20Valid WHERE tick = %s",
                (tick,),
            )
            rows = cursor.fetchall()
            for tx_hash, p, op, row_tick, amt, lim, mx in rows:
                svg = build_src20_svg_string(
                    db,
                    {
                        "p": p.upper(),
                        "op": op.upper(),
                        "tick": row_tick.upper(),
                        "amt": int(amt) if amt else amt,
                        "lim": lim,
                        "max": mx,
                    },
                )
                if isinstance(svg, str):
                    svg = svg.encode("utf-8")
                filename = f"{tx_hash}.svg"
                manifest_f.write(f"https://{config.DOMAINNAME}/stamps/{filename}\n")
                manifest_count += 1
                if not args.dry_run:
                    file_obj_md5, _ = store_files(db, filename, svg, STAMP_MIMETYPE)
                    cursor.execute(
                        "UPDATE StampTableV4 SET file_hash = %s, file_size_bytes = %s WHERE tx_hash = %s",
                        (file_obj_md5, len(svg), tx_hash),
                    )
                regenerated += 1
            if not args.dry_run:
                db.commit()
                if flush_async:
                    wait_for_uploads()  # drain this tick's uploads before the next -> bounded memory
            print(f"  [{i}/{len(ticks)}] {tick}: {len(rows)} stamp(s)  (total {regenerated})")
    finally:
        manifest_f.close()
        if flush_async:
            stop_upload_worker()
        db.close()
    action = "would regenerate" if args.dry_run else "regenerated"
    print(f"{action} {regenerated} SVG(s); wrote {manifest_count} URLs to {args.manifest}")
    if not args.dry_run and s3_enabled:
        print("NEXT: purge these URLs (or the /stamps/ path) from Cloudflare so clients drop the immutable cache.")


if __name__ == "__main__":
    main()
