"""
Ledger Hash Comparison Tool

Compares local ledger hashes against the SRC-20 validation API to find
the first block where hashes diverge. Uses binary search for efficiency.

Usage:
    poetry run python tools/ledger_hash_comparison.py
    poetry run python tools/ledger_hash_comparison.py --start 940000
    poetry run python tools/ledger_hash_comparison.py --start 940000 --end 945000
    poetry run python tools/ledger_hash_comparison.py --block 941085
"""

import argparse
import os
import sys
import time
import traceback

import requests
from dotenv import load_dotenv

# Add the parent directory to the Python path
if os.getcwd().endswith("/indexer"):
    sys.path.append(os.getcwd())
    dotenv_path = os.path.join(os.getcwd(), ".env")
else:
    sys.path.append(os.path.join(os.getcwd(), "indexer"))
    dotenv_path = os.path.join(os.getcwd(), "indexer/.env")

import pymysql as mysql

load_dotenv(dotenv_path=dotenv_path, override=True)

SRC20_VALID_TABLE = "SRC20Valid"
API_RATE_LIMIT_DELAY = 0.15  # seconds between API calls


def get_db_connection():
    """Connect to the local database using environment variables."""
    return mysql.connect(
        host=os.environ.get("RDS_HOSTNAME"),
        user=os.environ.get("RDS_USER"),
        password=os.environ.get("RDS_PASSWORD"),
        database=os.environ.get("RDS_DATABASE", "btc_stamps"),
        charset="utf8mb4",
        cursorclass=mysql.cursors.DictCursor,
    )


def fetch_api_hash(block_index):
    """Fetch ledger hash and balance data from the validation API for a given block."""
    secret = os.environ.get("SRC_VALIDATION_SECRET_API2")
    if not secret:
        print("ERROR: SRC_VALIDATION_SECRET_API2 not set in environment")
        sys.exit(1)

    url = (
        f"https://pkizh327c7.execute-api.us-west-2.amazonaws.com/prod/external/balanceHash"
        f"?blockIndex={block_index}&secret={secret}"
    )
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        data = resp.json().get("data", {})
        return data.get("hash", ""), data.get("balance_data", "")
    except requests.RequestException as e:
        print(f"  API error for block {block_index}: {e}")
        return None, None


def get_local_hash(cursor, block_index):
    """Get local ledger hash for a block. Returns empty string for blocks with no SRC-20 activity."""
    cursor.execute("SELECT ledger_hash FROM blocks WHERE block_index = %s", (block_index,))
    row = cursor.fetchone()
    if not row:
        return None
    return row["ledger_hash"] or ""


def get_max_block(cursor):
    """Get the highest block index in the local database."""
    cursor.execute("SELECT MAX(block_index) as max_block FROM blocks")
    return cursor.fetchone()["max_block"]


def get_blocks_with_ledger_hash(cursor, start, end):
    """Get all blocks with non-empty ledger hashes in a range."""
    cursor.execute(
        "SELECT block_index, ledger_hash FROM blocks "
        "WHERE block_index BETWEEN %s AND %s AND ledger_hash != '' AND ledger_hash IS NOT NULL "
        "ORDER BY block_index",
        (start, end),
    )
    return cursor.fetchall()


def binary_search_first_mismatch(cursor, start, end):
    """Use binary search to find the first block with a ledger hash mismatch.

    Only checks blocks that have non-empty local ledger hashes (blocks with SRC-20 activity).
    Returns the block index of the first mismatch, or None if all match.
    """
    blocks = get_blocks_with_ledger_hash(cursor, start, end)
    if not blocks:
        print(f"No blocks with ledger hashes found in range {start}-{end}")
        return None

    print(f"Found {len(blocks)} blocks with ledger hashes in range {start}-{end}")
    print("Binary searching for first mismatch...\n")

    low, high = 0, len(blocks) - 1
    first_mismatch_idx = None

    while low <= high:
        mid = (low + high) // 2
        block = blocks[mid]
        bi = block["block_index"]
        local_hash = block["ledger_hash"]

        api_hash, _ = fetch_api_hash(bi)
        time.sleep(API_RATE_LIMIT_DELAY)

        if api_hash is None:
            print(f"  Block {bi}: API error, skipping")
            low = mid + 1
            continue

        if local_hash == api_hash:
            print(f"  Block {bi}: MATCH")
            low = mid + 1
        else:
            print(f"  Block {bi}: MISMATCH")
            first_mismatch_idx = mid
            high = mid - 1

    if first_mismatch_idx is None:
        return None

    return blocks[first_mismatch_idx]["block_index"]


def find_exact_first_mismatch(cursor, approx_block, lookback=500):
    """Given an approximate mismatch block from binary search, scan linearly
    to find the exact first mismatch block.
    """
    search_start = max(approx_block - lookback, 0)
    blocks = get_blocks_with_ledger_hash(cursor, search_start, approx_block)

    if not blocks:
        return approx_block

    print(f"\nRefining: scanning {len(blocks)} blocks from {search_start} to {approx_block}...")

    last_match = None
    for block in blocks:
        bi = block["block_index"]
        local_hash = block["ledger_hash"]
        api_hash, _ = fetch_api_hash(bi)
        time.sleep(API_RATE_LIMIT_DELAY)

        if api_hash is None:
            continue

        if local_hash == api_hash:
            last_match = bi
        else:
            print(f"\n  First mismatch: block {bi}")
            if last_match:
                print(f"  Last matching block: {last_match}")
            return bi

    return approx_block


def inspect_mismatch_block(cursor, block_index):
    """Show detailed information about a mismatching block."""
    print(f"\n{'='*80}")
    print(f"MISMATCH DETAILS FOR BLOCK {block_index}")
    print(f"{'='*80}")

    # Local hash
    local_hash = get_local_hash(cursor, block_index)
    api_hash, api_balance_data = fetch_api_hash(block_index)

    print(f"\nLocal ledger hash:  {local_hash}")
    print(f"API ledger hash:    {api_hash}")

    # Check previous block
    prev_api_hash, _ = fetch_api_hash(block_index - 1)
    prev_local_hash = get_local_hash(cursor, block_index - 1)
    time.sleep(API_RATE_LIMIT_DELAY)

    print(f"\nPrevious block ({block_index - 1}):")
    print(f"  Local hash: {prev_local_hash}")
    print(f"  API hash:   {prev_api_hash}")
    prev_match = prev_local_hash == prev_api_hash if prev_local_hash and prev_api_hash else "unknown"
    print(f"  Match: {prev_match}")

    # SRC20Valid transactions at this block
    cursor.execute(
        f"SELECT tx_hash, tx_index, op, tick, amt, creator, destination "  # nosec B608
        f"FROM {SRC20_VALID_TABLE} WHERE block_index = %s ORDER BY tx_index",
        (block_index,),
    )
    local_txs = cursor.fetchall()

    print(f"\nLocal SRC20Valid transactions at block {block_index}: {len(local_txs)}")
    for tx in local_txs:
        print(f"  tx={tx['tx_hash']}")
        print(f"    op={tx['op']} tick={tx['tick']} amt={tx['amt']}")
        print(f"    creator={tx['creator']}")
        print(f"    destination={tx['destination']}")

    # API balance data
    if api_balance_data:
        print(f"\nAPI balance_data at block {block_index}:")
        for entry in sorted(api_balance_data.split(";")):
            if entry:
                print(f"  {entry}")

    # Check if API hash is unchanged from previous block (meaning API didn't see any tx)
    if api_hash == prev_api_hash and local_txs:
        print("\n** API hash unchanged from previous block — API does NOT recognize")
        print(f"   the {len(local_txs)} transaction(s) at this block.")
        print("   This is the root cause of the divergence.")

    # Check surrounding blocks for additional context
    print(f"\n{'='*80}")
    print("SURROUNDING BLOCKS")
    print(f"{'='*80}")

    for offset in [-2, -1, 0, 1, 2]:
        bi = block_index + offset
        lh = get_local_hash(cursor, bi)
        ah, _ = fetch_api_hash(bi)
        time.sleep(API_RATE_LIMIT_DELAY)

        cursor.execute(
            f"SELECT COUNT(*) as cnt FROM {SRC20_VALID_TABLE} WHERE block_index = %s",  # nosec B608
            (bi,),
        )
        cnt = cursor.fetchone()["cnt"]

        marker = " <<< MISMATCH ORIGIN" if bi == block_index and lh != ah else ""
        match_str = "MATCH" if lh == ah else ("MISMATCH" if lh and ah else "EMPTY")
        print(f"  Block {bi}: {match_str} | local_txs={cnt} | local_hash={lh or '(empty)'}{marker}")


def scan_for_extra_transactions(cursor, start, end, sample_size=50):
    """Scan for blocks where we have SRC20Valid entries but the API doesn't,
    or vice versa. Uses sampling for efficiency over large ranges.
    """
    print(f"\n{'='*80}")
    print(f"SCANNING FOR DIVERGENT TRANSACTIONS ({start} to {end})")
    print(f"{'='*80}")

    # Get blocks with SRC20Valid entries in range
    cursor.execute(
        "SELECT block_index, COUNT(*) as cnt FROM SRC20Valid "
        "WHERE block_index BETWEEN %s AND %s GROUP BY block_index ORDER BY block_index",
        (start, end),
    )
    our_blocks = cursor.fetchall()
    print(f"Blocks with SRC20Valid entries: {len(our_blocks)}")

    # Sample evenly
    step = max(1, len(our_blocks) // sample_size)
    samples = our_blocks[::step]
    print(f"Checking {len(samples)} sample blocks...\n")

    extra_in_local = []
    for block in samples:
        bi = block["block_index"]
        api_hash, _ = fetch_api_hash(bi)
        prev_api_hash, _ = fetch_api_hash(bi - 1)
        time.sleep(API_RATE_LIMIT_DELAY)

        if api_hash is None or prev_api_hash is None:
            continue

        if api_hash == prev_api_hash:
            cursor.execute(
                f"SELECT op, tick, CAST(amt AS CHAR) as amt, tx_hash "  # nosec B608
                f"FROM {SRC20_VALID_TABLE} WHERE block_index = %s ORDER BY tx_index",
                (bi,),
            )
            txs = cursor.fetchall()
            extra_in_local.append((bi, txs))
            for tx in txs:
                print(f"  EXTRA at block {bi}: {tx['op']} {tx['tick']} amt={tx['amt']} tx={tx['tx_hash']}")

    if not extra_in_local:
        print("  No extra transactions found in sampled blocks.")

    # Also check reverse: blocks where API has changes but we don't
    print("\nChecking for blocks where API has changes we're missing...")
    our_block_set = {b["block_index"] for b in our_blocks}
    missing_count = 0

    for bi in range(start, end, max(1, (end - start) // sample_size)):
        if bi in our_block_set:
            continue
        api_hash, _ = fetch_api_hash(bi)
        prev_api_hash, _ = fetch_api_hash(bi - 1)
        time.sleep(API_RATE_LIMIT_DELAY)

        if api_hash and prev_api_hash and api_hash != prev_api_hash:
            missing_count += 1
            _, bd = fetch_api_hash(bi)
            print(f"  MISSING at block {bi}: API balance_data={bd[:150] if bd else '(empty)'}")

    if missing_count == 0:
        print("  No missing transactions found in sampled blocks.")

    print(f"\nSummary: {len(extra_in_local)} extra local, {missing_count} missing from local (in sample)")
    return extra_in_local


def parse_args():
    parser = argparse.ArgumentParser(description="Compare local ledger hashes against the validation API")
    parser.add_argument("--start", type=int, default=None, help="Start block for search range")
    parser.add_argument("--end", type=int, default=None, help="End block for search range")
    parser.add_argument(
        "--block",
        type=int,
        default=None,
        help="Inspect a single block in detail (skip binary search)",
    )
    parser.add_argument(
        "--scan-extras",
        action="store_true",
        help="After finding mismatch, scan for all extra/missing transactions",
    )
    parser.add_argument(
        "--genesis",
        type=int,
        default=788041,
        help="SRC-20 genesis block (default: 788041)",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    print("Ledger Hash Comparison Tool")
    print("===========================\n")

    try:
        db = get_db_connection()
        cursor = db.cursor()
        max_block = get_max_block(cursor)
        print(f"Local database max block: {max_block}")

        # Single block inspection mode
        if args.block:
            inspect_mismatch_block(cursor, args.block)
            return

        # Determine search range
        start = args.start if args.start else args.genesis
        end = args.end if args.end else max_block
        print(f"Search range: {start} to {end}\n")

        # Binary search for first mismatch
        approx_block = binary_search_first_mismatch(cursor, start, end)

        if approx_block is None:
            print("\nNo mismatches found in the specified range.")
            return

        # Refine to exact first mismatch
        exact_block = find_exact_first_mismatch(cursor, approx_block)

        # Show detailed info
        inspect_mismatch_block(cursor, exact_block)

        # Optionally scan for extra/missing transactions
        if args.scan_extras:
            scan_for_extra_transactions(cursor, exact_block, end)

    except Exception as e:
        print(f"\nError: {e}")
        traceback.print_exc()
    finally:
        if "cursor" in locals():
            cursor.close()
        if "db" in locals():
            db.close()


if __name__ == "__main__":
    main()
