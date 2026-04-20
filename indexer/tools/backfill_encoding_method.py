#!/usr/bin/env python
"""
Backfill encoding_method column in StampTableV4.

This script populates the encoding_method column for existing stamps using a
three-phase approach:

Phase 1: Unambiguous SQL updates based on block ranges and keyburn values.
Phase 2: Rust re-parse for ambiguous stamps (block_index >= 865000, keyburn=1).
Phase 3: Verification queries.

Usage:
    cd indexer && poetry run python tools/backfill_encoding_method.py [--phase N] [--batch-size N] [--dry-run]

The script can safely run alongside the live indexer (read-only RPC + single-column UPDATEs).
"""

import argparse
import logging
import os
import sys
import time

from dotenv import load_dotenv

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def get_db_connection():
    """Create a database connection using environment variables."""
    import pymysql

    return pymysql.connect(
        host=os.environ.get("MYSQL_HOST", "localhost"),
        port=int(os.environ.get("MYSQL_PORT", 3306)),
        user=os.environ.get("MYSQL_USER", "root"),
        password=os.environ.get("MYSQL_PASSWORD", ""),
        database=os.environ.get("MYSQL_DATABASE", "btc_stamps"),
        charset="utf8mb4",
        autocommit=False,
    )


def phase1_sql_updates(db, dry_run=False):
    """Phase 1: Unambiguous SQL updates based on block ranges."""
    cursor = db.cursor()

    updates = [
        (
            "Pre-833000: all MULTISIG",
            "UPDATE StampTableV4 SET encoding_method = 'MULTISIG' WHERE block_index < 833000 AND encoding_method IS NULL",
        ),
        (
            "keyburn=NULL after 833000: CP-originated OLGA (P2WSH)",
            "UPDATE StampTableV4 SET encoding_method = 'OLGA' WHERE keyburn IS NULL AND block_index >= 833000 AND encoding_method IS NULL",
        ),
        (
            "833000-865000, keyburn=1: all MULTISIG (OLGA didn't exist yet)",
            "UPDATE StampTableV4 SET encoding_method = 'MULTISIG' WHERE block_index >= 833000 AND block_index < 865000 AND keyburn = 1 AND encoding_method IS NULL",
        ),
    ]

    for description, sql in updates:
        logger.info(f"Phase 1: {description}")
        if dry_run:
            # Count affected rows
            count_sql = sql.replace(
                "UPDATE StampTableV4 SET encoding_method = 'MULTISIG'", "SELECT COUNT(*) FROM StampTableV4"
            )
            count_sql = count_sql.replace(
                "UPDATE StampTableV4 SET encoding_method = 'OLGA'", "SELECT COUNT(*) FROM StampTableV4"
            )
            cursor.execute(count_sql)
            count = cursor.fetchone()[0]
            logger.info(f"  [DRY RUN] Would update {count} rows")
        else:
            cursor.execute(sql)
            logger.info(f"  Updated {cursor.rowcount} rows")
            db.commit()

    cursor.close()


def phase2_rust_reparse(db, batch_size=1000, dry_run=False):
    """Phase 2: Re-parse ambiguous stamps with the Rust parser.

    For stamps where block_index >= 865000 AND keyburn = 1 AND encoding_method IS NULL,
    fetch the raw tx hex and check for OP_CHECKMULTISIG via the Rust parser.
    """
    try:
        from btc_stamps_parser import FastTransactionParser
    except ImportError:
        logger.error("Rust parser (btc_stamps_parser) not available. Cannot run Phase 2.")
        logger.error("Build it with: cd indexer && poetry run task build")
        return

    from index_core.backend import Backend

    backend = Backend()
    parser = FastTransactionParser()

    cursor = db.cursor()

    # Count total stamps to process
    cursor.execute("SELECT COUNT(*) FROM StampTableV4 WHERE block_index >= 865000 AND keyburn = 1 AND encoding_method IS NULL")
    total = cursor.fetchone()[0]
    logger.info(f"Phase 2: {total} stamps to re-parse")

    if total == 0:
        cursor.close()
        return

    processed = 0
    multisig_count = 0
    olga_count = 0

    while True:
        cursor.execute(
            "SELECT stamp, tx_hash FROM StampTableV4 "
            "WHERE block_index >= 865000 AND keyburn = 1 AND encoding_method IS NULL "
            "ORDER BY stamp LIMIT %s",
            (batch_size,),
        )
        rows = cursor.fetchall()
        if not rows:
            break

        tx_hashes = [row[1] for row in rows]
        stamp_ids = {row[1]: row[0] for row in rows}

        # Batch fetch raw transactions
        try:
            raw_txs = backend.getrawtransaction_batch(tx_hashes, verbose=False)
        except Exception as e:
            logger.error(f"Error fetching batch of {len(tx_hashes)} transactions: {e}")
            # Fall back to one-by-one
            raw_txs = {}
            for tx_hash in tx_hashes:
                try:
                    raw_txs[tx_hash] = backend.getrawtransaction(tx_hash, verbose=False)
                except Exception:
                    logger.warning(f"Failed to fetch tx {tx_hash}, skipping")

        multisig_stamps = []
        olga_stamps = []

        for tx_hash in tx_hashes:
            tx_hex = raw_txs.get(tx_hash)
            if tx_hex is None:
                logger.warning(f"No raw tx data for {tx_hash} (stamp {stamp_ids[tx_hash]}), skipping")
                continue

            try:
                tx_info = parser.deserialize_transaction(tx_hex)
                has_multisig = any(output.has_op_checkmultisig for output in tx_info.outputs)

                if has_multisig:
                    multisig_stamps.append(stamp_ids[tx_hash])
                    multisig_count += 1
                else:
                    olga_stamps.append(stamp_ids[tx_hash])
                    olga_count += 1
            except Exception as e:
                logger.warning(f"Error parsing tx {tx_hash}: {e}, skipping")

        # Batch update
        if not dry_run:
            if multisig_stamps:
                placeholders = ",".join(["%s"] * len(multisig_stamps))
                cursor.execute(
                    f"UPDATE StampTableV4 SET encoding_method = 'MULTISIG' WHERE stamp IN ({placeholders})",
                    multisig_stamps,
                )
            if olga_stamps:
                placeholders = ",".join(["%s"] * len(olga_stamps))
                cursor.execute(
                    f"UPDATE StampTableV4 SET encoding_method = 'OLGA' WHERE stamp IN ({placeholders})",
                    olga_stamps,
                )
            db.commit()

        processed += len(rows)
        logger.info(f"  Progress: {processed}/{total} stamps " f"(MULTISIG: {multisig_count}, OLGA: {olga_count})")

    cursor.close()
    logger.info(f"Phase 2 complete: {multisig_count} MULTISIG, {olga_count} OLGA")


def phase3_verification(db):
    """Phase 3: Verify the backfill results."""
    cursor = db.cursor()

    # Check for remaining NULLs
    cursor.execute("SELECT COUNT(*) FROM StampTableV4 WHERE encoding_method IS NULL")
    null_count = cursor.fetchone()[0]
    logger.info(f"Verification: {null_count} stamps with NULL encoding_method")

    # Distribution check
    cursor.execute("SELECT encoding_method, COUNT(*) FROM StampTableV4 GROUP BY encoding_method ORDER BY encoding_method")
    rows = cursor.fetchall()
    logger.info("Distribution:")
    for method, count in rows:
        logger.info(f"  {method or 'NULL'}: {count}")

    cursor.close()

    if null_count > 0:
        logger.warning("Some stamps still have NULL encoding_method!")
    else:
        logger.info("All stamps have encoding_method set.")


def main():
    parser = argparse.ArgumentParser(description="Backfill encoding_method in StampTableV4")
    parser.add_argument("--phase", type=int, choices=[1, 2, 3], help="Run only a specific phase (default: all)")
    parser.add_argument("--batch-size", type=int, default=1000, help="Batch size for Phase 2 (default: 1000)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    args = parser.parse_args()

    db = get_db_connection()

    try:
        if args.phase is None or args.phase == 1:
            logger.info("=== Phase 1: SQL-based updates ===")
            start = time.time()
            phase1_sql_updates(db, dry_run=args.dry_run)
            logger.info(f"Phase 1 completed in {time.time() - start:.1f}s")

        if args.phase is None or args.phase == 2:
            logger.info("=== Phase 2: Rust re-parse ===")
            start = time.time()
            phase2_rust_reparse(db, batch_size=args.batch_size, dry_run=args.dry_run)
            logger.info(f"Phase 2 completed in {time.time() - start:.1f}s")

        if args.phase is None or args.phase == 3:
            logger.info("=== Phase 3: Verification ===")
            phase3_verification(db)

    finally:
        db.close()

    logger.info("Backfill complete.")


if __name__ == "__main__":
    main()
