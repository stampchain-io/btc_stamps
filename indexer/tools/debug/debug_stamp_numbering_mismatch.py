#!/usr/bin/env python3
"""
Debug script to analyze stamp numbering mismatch at block 825002.
This script compares stamp assignments and identifies the exact point of divergence.
"""

import logging
import sys
from decimal import Decimal
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

import config
from index_core.database_manager import DatabaseManager
from index_core.caching import cache_manager

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def analyze_stamp_sequence_around_block(db, target_block: int, window: int = 10):
    """Analyze stamp sequence around a specific block."""
    logger.info(f"Analyzing stamp sequence around block {target_block} (window: ±{window})")

    cursor = db.cursor()

    # Get stamps around the target block
    cursor.execute(
        """
        SELECT block_index, tx_index, tx_hash, stamp, cpid, is_btc_stamp, is_cursed
        FROM stamps 
        WHERE block_index BETWEEN %s AND %s
        ORDER BY block_index, tx_index
    """,
        (target_block - window, target_block + window),
    )

    stamps = cursor.fetchall()

    print(f"\nStamp sequence around block {target_block}:")
    print("Block    | TxIdx | Stamp   | Type    | CPID      | TxHash")
    print("-" * 75)

    prev_stamp = None
    gaps_found = []

    for stamp_data in stamps:
        block_idx, tx_idx, tx_hash, stamp_num, cpid, is_btc, is_cursed = stamp_data

        stamp_type = "STAMP" if is_btc else ("CURSED" if is_cursed else "OTHER")
        cpid_short = cpid[:8] if cpid else "None"
        tx_hash_short = tx_hash[:8] if tx_hash else "None"

        print(f"{block_idx:8} | {tx_idx:5} | {stamp_num:7} | {stamp_type:7} | {cpid_short:9} | {tx_hash_short}")

        # Check for gaps in stamp numbers (only for positive stamps)
        if stamp_num > 0 and prev_stamp is not None and prev_stamp > 0:
            expected_next = prev_stamp + 1
            if stamp_num != expected_next:
                gap_size = stamp_num - expected_next
                gaps_found.append(
                    {
                        "prev_stamp": prev_stamp,
                        "current_stamp": stamp_num,
                        "gap_size": gap_size,
                        "block": block_idx,
                        "tx_hash": tx_hash,
                    }
                )
                print(f"         >>> GAP DETECTED: Expected {expected_next}, got {stamp_num} (gap: {gap_size})")

        if stamp_num > 0:  # Only track positive stamps for sequence
            prev_stamp = stamp_num

    if gaps_found:
        print(f"\nFound {len(gaps_found)} gaps in stamp sequence:")
        for gap in gaps_found:
            print(f"  Gap at block {gap['block']}: {gap['prev_stamp']} -> {gap['current_stamp']} (size: {gap['gap_size']})")
    else:
        print("\nNo gaps found in stamp sequence.")

    cursor.close()
    return stamps, gaps_found


def analyze_stamp_count_vs_max_stamp(db):
    """Analyze the relationship between stamp count and max stamp number."""
    logger.info("Analyzing stamp count vs max stamp number")

    cursor = db.cursor()

    # Get total stamp count and max stamp number
    cursor.execute("SELECT COUNT(*) FROM stamps WHERE stamp > 0")
    total_stamps = cursor.fetchone()[0]

    cursor.execute("SELECT MAX(stamp) FROM stamps WHERE stamp > 0")
    max_stamp = cursor.fetchone()[0]

    # Calculate expected vs actual
    expected_max = total_stamps
    difference = max_stamp - expected_max if max_stamp else 0

    print(f"\nStamp Count Analysis:")
    print(f"Total stamps in database: {total_stamps}")
    print(f"Maximum stamp number: {max_stamp}")
    print(f"Expected max stamp: {expected_max}")
    print(f"Difference: {difference}")

    if difference != 0:
        print(f"⚠️  MISMATCH: {difference} stamp numbers are unaccounted for")

        # Find missing stamp numbers
        cursor.execute(
            """
            WITH RECURSIVE stamp_sequence(n) AS (
                SELECT 1
                UNION ALL
                SELECT n + 1 FROM stamp_sequence WHERE n < %s
            )
            SELECT s.n as missing_stamp
            FROM stamp_sequence s
            LEFT JOIN stamps st ON s.n = st.stamp
            WHERE st.stamp IS NULL
            ORDER BY s.n
            LIMIT 20
        """,
            (max_stamp,),
        )

        missing_stamps = cursor.fetchall()
        if missing_stamps:
            print(f"First 20 missing stamp numbers: {[row[0] for row in missing_stamps]}")
    else:
        print("✅ Stamp count matches maximum stamp number")

    cursor.close()
    return total_stamps, max_stamp, difference


def find_duplicate_stamps(db):
    """Find any duplicate stamp numbers."""
    logger.info("Checking for duplicate stamp numbers")

    cursor = db.cursor()
    cursor.execute("""
        SELECT stamp, COUNT(*) as count
        FROM stamps 
        WHERE stamp > 0
        GROUP BY stamp 
        HAVING COUNT(*) > 1
        ORDER BY stamp
    """)

    duplicates = cursor.fetchall()

    if duplicates:
        print(f"\n⚠️  Found {len(duplicates)} duplicate stamp numbers:")
        for stamp_num, count in duplicates:
            print(f"  Stamp {stamp_num}: {count} occurrences")

            # Get details of duplicate stamps
            cursor.execute(
                """
                SELECT block_index, tx_hash, cpid
                FROM stamps 
                WHERE stamp = %s
                ORDER BY block_index
            """,
                (stamp_num,),
            )

            details = cursor.fetchall()
            for detail in details:
                print(f"    Block {detail[0]}: {detail[1][:12]}... CPID: {detail[2]}")
    else:
        print("\n✅ No duplicate stamp numbers found")

    cursor.close()
    return duplicates


def check_cache_state():
    """Check current cache state for stamp counters."""
    logger.info("Checking cache state")

    stamp_counter = cache_manager.get_cache_value("stamp", "stamp")
    cursed_counter = cache_manager.get_cache_value("stamp", "cursed")

    print(f"\nCache State:")
    print(f"Stamp counter: {stamp_counter}")
    print(f"Cursed counter: {cursed_counter}")

    return stamp_counter, cursed_counter


def analyze_specific_transaction(db, tx_hash: str):
    """Analyze a specific transaction mentioned in the issue."""
    logger.info(f"Analyzing transaction: {tx_hash}")

    cursor = db.cursor()
    cursor.execute(
        """
        SELECT block_index, tx_index, stamp, cpid, is_btc_stamp, is_cursed
        FROM stamps 
        WHERE tx_hash = %s
    """,
        (tx_hash,),
    )

    result = cursor.fetchone()

    if result:
        block_idx, tx_idx, stamp_num, cpid, is_btc, is_cursed = result
        print(f"\nTransaction Analysis for {tx_hash[:12]}...:")
        print(f"  Block: {block_idx}")
        print(f"  TX Index: {tx_idx}")
        print(f"  Stamp Number: {stamp_num}")
        print(f"  CPID: {cpid}")
        print(f"  Is BTC Stamp: {is_btc}")
        print(f"  Is Cursed: {is_cursed}")

        # Find stamps around this one
        cursor.execute(
            """
            SELECT tx_hash, stamp, cpid
            FROM stamps 
            WHERE stamp BETWEEN %s AND %s AND stamp > 0
            ORDER BY stamp
        """,
            (stamp_num - 5, stamp_num + 5),
        )

        nearby_stamps = cursor.fetchall()
        print(f"\nStamps around {stamp_num}:")
        for nearby in nearby_stamps:
            marker = " <-- TARGET" if nearby[0] == tx_hash else ""
            print(f"  {nearby[1]:7}: {nearby[0][:12]}... CPID: {nearby[2]}{marker}")
    else:
        print(f"\n❌ Transaction {tx_hash} not found in stamps table")

    cursor.close()
    return result


def main():
    """Main analysis function."""
    print("Bitcoin Stamps Indexer - Stamp Numbering Mismatch Analysis")
    print("=" * 65)

    try:
        # Connect to database
        db_manager = DatabaseManager()
        db = db_manager.connect()

        # Check cache state
        check_cache_state()

        # Analyze stamp count vs max stamp
        total_stamps, max_stamp, difference = analyze_stamp_count_vs_max_stamp(db)

        # Check for duplicates
        duplicates = find_duplicate_stamps(db)

        # Analyze sequence around target block 825002
        stamps, gaps = analyze_stamp_sequence_around_block(db, 825002, 15)

        # Focus on the specific transaction mentioned in the issue
        # Transaction that should be 249841 in prod but is 249846 in dev
        target_tx = "95dca4dc27e50e7b26174a0ded7af3b26527def625670d058ae09200eeb3d735"
        tx_result = analyze_specific_transaction(db, target_tx)

        # Summary
        print(f"\n" + "=" * 65)
        print("ANALYSIS SUMMARY")
        print(f"=" * 65)
        print(f"Total stamps: {total_stamps}")
        print(f"Max stamp number: {max_stamp}")
        print(f"Numbering difference: {difference}")
        print(f"Duplicate stamps found: {len(duplicates) if duplicates else 0}")
        print(f"Sequence gaps found: {len(gaps)}")

        if difference == 5:
            print(f"\n🎯 The 5-stamp offset matches the reported issue!")
            print("This suggests 5 stamp numbers were assigned but stamps not created,")
            print("or 5 stamps were created but numbers skipped.")

        if gaps:
            print(f"\n⚠️  Gaps in stamp sequence suggest cache clearing issues")
            print("or database transaction rollbacks that didn't preserve counters.")

    except Exception as e:
        logger.error(f"Error during analysis: {e}")
        raise
    finally:
        if "db" in locals():
            db.close()


if __name__ == "__main__":
    main()
