import json
import os
import sys
from datetime import datetime

import pymysql as mysql
from termcolor import colored


def print_connection_details(prod_host, dev_host, block_index):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("\n" + "═" * 60)
    print(colored(f"  DATABASE COMPARISON REPORT - {timestamp}  ", "white", "on_blue", attrs=["bold"]))
    print("═" * 60)
    print(f"\n📊 Databases: {colored(prod_host, 'cyan')} → {colored(dev_host, 'cyan')}")
    print(f"📈 Block Range: Up to block {colored(str(block_index), 'green', attrs=['bold'])}")
    print("─" * 60)


def print_block_comparison(prod_block, dev_block):
    print("\n" + "═" * 60)
    print(colored(" ⚠️  BLOCK HASH MISMATCH DETECTED ", "white", "on_red", attrs=["bold"]))
    print("═" * 60)

    print(f"\n Block Height: {colored(str(prod_block[0]), 'cyan', attrs=['bold'])}")

    hashes = [
        ("Messages", prod_block[1], dev_block[1]),
        ("TX List", prod_block[2], dev_block[2]),
        ("Ledger", prod_block[3], dev_block[3]),
    ]

    for name, prod_hash, dev_hash in hashes:
        if prod_hash == dev_hash:
            print(f"  {name}: {colored('✓', 'green')} {prod_hash[:16]}...")
        else:
            print(f"  {name}: {colored('✗', 'red')}")
            print(f"    Prod: {prod_hash[:32]}...")
            print(f"    Dev:  {dev_hash[:32]}...")

    print("═" * 60)


def print_comparison_header(table_name):
    print("\n" + "─" * 60)
    print(colored(f" {table_name} ", "white", attrs=["bold"]) + " " + "─" * (60 - len(table_name) - 3))


def print_summary(table_name, prod_count, dev_count, has_differences):
    status_icon = "✓" if not has_differences else "✗"
    status_color = "green" if not has_differences else "red"
    diff_count = abs(prod_count - dev_count)

    print(f"\n  Records: Prod[{colored(prod_count, 'cyan')}] Dev[{colored(dev_count, 'cyan')}]", end="")
    if diff_count > 0:
        print(f" Δ={colored(diff_count, 'yellow')}", end="")

    status_msg = "MATCH" if not has_differences else "MISMATCH"
    print(f"  [{colored(status_icon + ' ' + status_msg, status_color, attrs=['bold'])}]")


def print_stamp_comparison(prod_record, dev_record):
    """Print detailed comparison of matching tx_hash with different stamps."""
    print(f"\n  TX: {prod_record[2][:8]}... Block[{prod_record[3]}]")
    print(
        f"    Prod: Stamp={colored(prod_record[0], 'yellow')} Ident={colored(prod_record[1], 'yellow')} CPID={colored(prod_record[5], 'yellow')}"
    )
    print(
        f"    Dev:  Stamp={colored(dev_record[0], 'yellow')} Ident={colored(dev_record[1], 'yellow')} CPID={colored(dev_record[5], 'yellow')}"
    )


def lookup_cpid_transactions(cursor, cpid):
    """Look up all transactions associated with a CPID."""
    cursor.execute(
        """
        SELECT stamp, ident, tx_hash, block_index, tx_index, cpid
        FROM StampTableV4
        WHERE cpid = %s
        ORDER BY block_index ASC, tx_index ASC
    """,
        (cpid,),
    )
    return cursor.fetchall()


def print_cpid_cross_reference(prod_cursor, dev_cursor, record, source="dev"):
    """Print cross-reference information for CPID lookups."""
    cpid = record[5]
    other_db_name = "Production" if source == "dev" else "Development"
    cursor = prod_cursor if source == "dev" else dev_cursor

    related_txs = lookup_cpid_transactions(cursor, cpid)

    if related_txs:
        print(f"    {colored(f'CPID {cpid} found in {other_db_name}:', 'yellow')}")
        for tx in related_txs[:2]:  # Show max 2 related txs
            print(f"      Block[{tx[3]}] TX:{tx[2][:8]}... Stamp={tx[0]}")
    else:
        print(f"    {colored(f'CPID {cpid} not found in {other_db_name}', 'red')}")


def compare_stamptable(prod_cursor, dev_cursor, block_index, show_json=False):
    if not show_json:
        print_comparison_header("StampTableV4")

    # Fetch all records with tx_hash as key
    prod_cursor.execute(
        """
        SELECT stamp, ident, tx_hash, block_index, tx_index, cpid
        FROM StampTableV4
        WHERE block_index < %s AND stamp > 0
        ORDER BY block_index ASC, tx_index ASC
    """,
        (block_index,),
    )
    prod_records = prod_cursor.fetchall()

    dev_cursor.execute(
        """
        SELECT stamp, ident, tx_hash, block_index, tx_index, cpid
        FROM StampTableV4
        WHERE block_index < %s AND stamp > 0
        ORDER BY block_index ASC, tx_index ASC
    """,
        (block_index,),
    )
    dev_records = dev_cursor.fetchall()

    # Create dictionaries for easier comparison
    prod_dict = {record[2]: record for record in prod_records}  # tx_hash as key
    dev_dict = {record[2]: record for record in dev_records}

    # Categorize differences
    only_in_prod = set(prod_dict.keys()) - set(dev_dict.keys())
    only_in_dev = set(dev_dict.keys()) - set(prod_dict.keys())
    common_tx = set(prod_dict.keys()) & set(dev_dict.keys())

    # Find mismatched stamps in common transactions
    mismatched = [tx for tx in common_tx if prod_dict[tx][0] != dev_dict[tx][0] or prod_dict[tx][1] != dev_dict[tx][1]]

    if not show_json:
        print("\nSummary:")
        print(f"├─ Production records: {colored(len(prod_records), 'cyan')}")
        print(f"└─ Development records: {colored(len(dev_records), 'cyan')}")

    if only_in_prod or only_in_dev or mismatched:
        print(colored("\n✗ Differences found", "red", attrs=["bold"]))

        # First show items that exist in one side but not the other
        if only_in_prod:
            print(colored(f"\n→ Only in Production ({len(only_in_prod)} records):", "yellow"))
            for tx in sorted(list(only_in_prod), key=lambda x: prod_dict[x][3])[:5]:
                record = prod_dict[tx]
                print(f"  Block[{record[3]}] TX:{record[2][:8]}... Stamp={record[0]} CPID={record[5]}")
                print_cpid_cross_reference(prod_cursor, dev_cursor, record, "prod")

        if only_in_dev:
            print(colored(f"\n→ Only in Development ({len(only_in_dev)} records):", "yellow"))
            for tx in sorted(list(only_in_dev), key=lambda x: dev_dict[x][3])[:5]:
                record = dev_dict[tx]
                print(f"  Block[{record[3]}] TX:{record[2][:8]}... Stamp={record[0]} CPID={record[5]}")
                print_cpid_cross_reference(prod_cursor, dev_cursor, record, "dev")

        if mismatched:
            print(colored(f"\n→ Matching TX hash but different stamps ({len(mismatched)} records):", "yellow"))
            for tx in sorted(mismatched, key=lambda x: prod_dict[x][3])[:5]:
                print_stamp_comparison(prod_dict[tx], dev_dict[tx])

    else:
        print(colored("\n✓ All stamps match perfectly!", "green", attrs=["bold"]))

    return bool(only_in_prod or only_in_dev or mismatched)


def compare_cursed_stamps(prod_cursor, dev_cursor, block_index, show_json=False):
    if not show_json:
        print_comparison_header("Cursed Stamps (Negative Values)")

    # First, get all stamps with their CPIDs from both databases
    prod_cursor.execute(
        """
        SELECT cpid, stamp
        FROM StampTableV4
        WHERE block_index < %s
        """,
        (block_index,),
    )
    prod_cpid_stamps = {(row[0], row[1]) for row in prod_cursor.fetchall()}

    dev_cursor.execute(
        """
        SELECT cpid, stamp
        FROM StampTableV4
        WHERE block_index < %s
        """,
        (block_index,),
    )
    dev_cpid_stamps = {(row[0], row[1]) for row in dev_cursor.fetchall()}

    # Now get cursed stamp records
    prod_cursor.execute(
        """
        SELECT stamp, ident, tx_hash, block_index, tx_index, cpid
        FROM StampTableV4
        WHERE block_index < %s AND stamp < 0
        ORDER BY block_index ASC, tx_index ASC
        """,
        (block_index,),
    )
    prod_records = prod_cursor.fetchall()

    dev_cursor.execute(
        """
        SELECT stamp, ident, tx_hash, block_index, tx_index, cpid
        FROM StampTableV4
        WHERE block_index < %s AND stamp < 0
        ORDER BY block_index ASC, tx_index ASC
        """,
        (block_index,),
    )
    dev_records = dev_cursor.fetchall()

    # Create dictionaries for easier comparison
    prod_dict = {record[2]: record for record in prod_records}  # tx_hash as key
    dev_dict = {record[2]: record for record in dev_records}

    # Find tx_hashes that are unique to each side
    only_in_prod = set(prod_dict.keys()) - set(dev_dict.keys())
    only_in_dev = set(dev_dict.keys()) - set(prod_dict.keys())
    common_tx = set(prod_dict.keys()) & set(dev_dict.keys())

    # Find mismatched stamps in common transactions
    mismatched = [tx for tx in common_tx if prod_dict[tx][0] != dev_dict[tx][0] or prod_dict[tx][1] != dev_dict[tx][1]]

    # Find records with different tx_hash but same CPID and stamp
    diff_tx_same_cpid_prod = []
    for tx in only_in_prod:
        record = prod_dict[tx]
        if (record[5], record[0]) in dev_cpid_stamps:  # Check if CPID and stamp combination exists in dev
            diff_tx_same_cpid_prod.append(tx)

    diff_tx_same_cpid_dev = []
    for tx in only_in_dev:
        record = dev_dict[tx]
        if (record[5], record[0]) in prod_cpid_stamps:  # Check if CPID and stamp combination exists in prod
            diff_tx_same_cpid_dev.append(tx)

    # Find truly unique records (no matching CPID and stamp combination)
    truly_unique_in_prod = [tx for tx in only_in_prod if (prod_dict[tx][5], prod_dict[tx][0]) not in dev_cpid_stamps]
    truly_unique_in_dev = [tx for tx in only_in_dev if (dev_dict[tx][5], dev_dict[tx][0]) not in prod_cpid_stamps]

    print(f"\n  Cursed Records: Prod[{colored(len(prod_records), 'cyan')}] Dev[{colored(len(dev_records), 'cyan')}]")

    if only_in_prod or only_in_dev or mismatched:
        print(colored("\n✗ Differences found in cursed stamps", "red", attrs=["bold"]))

        # Show completely unique records first (no matching CPID and stamp)
        if truly_unique_in_prod:
            print(colored(f"\n→ Unique cursed stamps only in Production ({len(truly_unique_in_prod)} records):", "yellow"))
            for tx in sorted(truly_unique_in_prod, key=lambda x: prod_dict[x][3])[:3]:
                record = prod_dict[tx]
                print(f"  Block[{record[3]}] TX:{record[2][:8]}... Stamp={record[0]} CPID={record[5]}")

        if truly_unique_in_dev:
            print(colored(f"\n→ Unique cursed stamps only in Development ({len(truly_unique_in_dev)} records):", "yellow"))
            for tx in sorted(truly_unique_in_dev, key=lambda x: dev_dict[x][3])[:3]:
                record = dev_dict[tx]
                print(f"  Block[{record[3]}] TX:{record[2][:8]}... Stamp={record[0]} CPID={record[5]}")

        # Show records with different tx_hash but same CPID and stamp
        if diff_tx_same_cpid_prod:
            print(
                colored(
                    f"\n→ Different tx_hash but same CPID and stamp in Production ({len(diff_tx_same_cpid_prod)} records):",
                    "yellow",
                )
            )
            for tx in sorted(diff_tx_same_cpid_prod, key=lambda x: prod_dict[x][3])[:5]:
                record = prod_dict[tx]
                print(f"  • Block: {colored(record[3], 'cyan')}")
                print(f"    ├─ TX: {record[2]}")
                print(f"    ├─ Stamp: {record[0]}")
                print(f"    ├─ Ident: {record[1]}")
                print(f"    ├─ CPID: {record[5]}")
                print_cpid_cross_reference(prod_cursor, dev_cursor, record, "prod")

        if diff_tx_same_cpid_dev:
            print(
                colored(
                    f"\n→ Different tx_hash but same CPID and stamp in Development ({len(diff_tx_same_cpid_dev)} records):",
                    "yellow",
                )
            )
            for tx in sorted(diff_tx_same_cpid_dev, key=lambda x: dev_dict[x][3])[:5]:
                record = dev_dict[tx]
                print(f"  • Block: {colored(record[3], 'cyan')}")
                print(f"    ├─ TX: {record[2]}")
                print(f"    ├─ Stamp: {record[0]}")
                print(f"    ├─ Ident: {record[1]}")
                print(f"    ├─ CPID: {record[5]}")
                print_cpid_cross_reference(prod_cursor, dev_cursor, record, "dev")

        # Show records with matching tx_hash but different values
        if mismatched:
            print(colored(f"\n→ Matching TX hash but different cursed values ({len(mismatched)} records):", "yellow"))
            for tx in sorted(mismatched, key=lambda x: prod_dict[x][3])[:5]:
                print_stamp_comparison(prod_dict[tx], dev_dict[tx])

    else:
        print(colored("\n✓ All cursed stamps match perfectly!", "green", attrs=["bold"]))

    return bool(only_in_prod or only_in_dev or mismatched)


def compare_ownerstable(prod_cursor, dev_cursor, block_index, show_json=False):
    if not show_json:
        print_comparison_header("Owners Table")

    # Fetch all owner records
    prod_cursor.execute(
        """
        SELECT owners.index, deploy_hash, tokenid, owner, prim, address_btc, address_eth, txt_data, expire_timestamp
        FROM owners
        WHERE last_update < %s
        ORDER BY deploy_hash ASC, owners.index ASC
        """,
        (block_index,),
    )
    prod_records = prod_cursor.fetchall()

    dev_cursor.execute(
        """
        SELECT owners.index, deploy_hash, tokenid, owner, prim, address_btc, address_eth, txt_data, expire_timestamp
        FROM owners
        WHERE last_update < %s
        ORDER BY deploy_hash ASC, owners.index ASC
        """,
        (block_index,),
    )
    dev_records = dev_cursor.fetchall()

    # Create dictionaries for easier comparison using deploy_hash and tokenid as composite key
    prod_dict = {(record[1], record[2]): record for record in prod_records}
    dev_dict = {(record[1], record[2]): record for record in dev_records}

    # Categorize differences
    only_in_prod = set(prod_dict.keys()) - set(dev_dict.keys())
    only_in_dev = set(dev_dict.keys()) - set(prod_dict.keys())
    common_tokens = set(prod_dict.keys()) & set(dev_dict.keys())

    # Find mismatched owners in common tokens
    mismatched = [
        token
        for token in common_tokens
        if prod_dict[token][3] != dev_dict[token][3]  # owner
        or prod_dict[token][4] != dev_dict[token][4]  # prim
        or prod_dict[token][5] != dev_dict[token][5]  # address_btc
        or prod_dict[token][6] != dev_dict[token][6]  # address_eth
    ]

    print(
        f"\n  Owner Records (up to block {block_index}): Prod[{colored(len(prod_records), 'cyan')}] Dev[{colored(len(dev_records), 'cyan')}]"
    )

    if len(prod_records) != len(dev_records):
        print(colored("\n⚠️  WARNING: Record count mismatch!", "red", attrs=["bold"]))
        print(colored(f"    Difference: {abs(len(prod_records) - len(dev_records))} records", "red", attrs=["bold"]))

    if only_in_prod or only_in_dev or mismatched:
        print(colored("\n✗ Differences found in owners table", "red", attrs=["bold"]))

        if mismatched:
            print(colored(f"\n→ Ownership mismatches ({len(mismatched)} records):", "yellow"))
            for token in sorted(mismatched)[:3]:
                prod_record = prod_dict[token]
                dev_record = dev_dict[token]
                print(f"\n  Token: {token[0][:8]}.../{token[1]}")
                if prod_record[3] != dev_record[3]:
                    print(f"    Owner: Prod[{prod_record[3][:20]}...] Dev[{dev_record[3][:20]}...]")
                if prod_record[5] != dev_record[5]:
                    print(f"    BTC: Prod[{prod_record[5]}] Dev[{dev_record[5]}]")

        if only_in_prod:
            print(colored(f"\n→ Only in Production ({len(only_in_prod)} records):", "red"))
            for token in sorted(list(only_in_prod))[:5]:
                record = prod_dict[token]
                print(f"\n  • Deploy Hash: {colored(record[1], 'cyan')}")
                print(f"    ├─ Token ID: {record[2]}")
                print(f"    ├─ Owner: {record[3]}")
                print(f"    ├─ Primary: {record[4]}")
                print(f"    ├─ BTC Address: {record[5]}")
                print(f"    └─ ETH Address: {record[6]}")

        if only_in_dev:
            print(colored(f"\n→ Only in Development ({len(only_in_dev)} records):", "red"))
            for token in sorted(list(only_in_dev))[:5]:
                record = dev_dict[token]
                print(f"\n  • Deploy Hash: {colored(record[1], 'cyan')}")
                print(f"    ├─ Token ID: {record[2]}")
                print(f"    ├─ Owner: {record[3]}")
                print(f"    ├─ Primary: {record[4]}")
                print(f"    ├─ BTC Address: {record[5]}")
                print(f"    └─ ETH Address: {record[6]}")
    else:
        print(colored("\n✓ All ownership records match perfectly!", "green", attrs=["bold"]))

    return bool(only_in_prod or only_in_dev or mismatched)


def compare_src101(prod_cursor, dev_cursor, block_index, prod_src101, dev_src101, show_json=False):
    if not show_json:
        print_comparison_header("SRC101Valid")

    # Filter out records with None tx_hash or create dictionaries safely
    prod_dict = {}
    for row in prod_src101:
        if row[0] is not None:  # tx_hash should not be None
            prod_dict[row[0]] = row
    
    dev_dict = {}
    for row in dev_src101:
        if row[0] is not None:  # tx_hash should not be None
            dev_dict[row[0]] = row

    # Find differences
    only_in_prod = set(prod_dict.keys()) - set(dev_dict.keys())
    only_in_dev = set(dev_dict.keys()) - set(prod_dict.keys())
    common_tx = set(prod_dict.keys()) & set(dev_dict.keys())

    # Find mismatched records in common transactions
    mismatched = [
        tx
        for tx in common_tx
        if (
            prod_dict[tx][1] != dev_dict[tx][1]  # owner
            or prod_dict[tx][2] != dev_dict[tx][2]  # tokenid
            or prod_dict[tx][3] != dev_dict[tx][3]  # tokenid_utf8
            or prod_dict[tx][4] != dev_dict[tx][4]  # block_index
        )
    ]

    print_summary("SRC101Valid", len(prod_src101), len(dev_src101), bool(only_in_prod or only_in_dev or mismatched))

    if only_in_prod or only_in_dev or mismatched:
        if only_in_prod:
            print(colored(f"\n→ Only in Production ({len(only_in_prod)} records):", "yellow"))
            # Create a list of records with their block numbers for sorting
            prod_records = [(tx_hash, prod_dict[tx_hash]) for tx_hash in only_in_prod]
            # Sort by block number (index 4 in the record tuple), handle None values
            prod_records.sort(key=lambda x: x[1][4] if x[1][4] is not None else 0)

            for tx_hash, record in prod_records[:5]:
                block_idx = record[4] if record[4] is not None else "NULL"
                owner_display = (record[1][:20] + "...") if record[1] is not None and len(record[1]) > 20 else (record[1] or "NULL")
                tokenid_display = record[2] if record[2] is not None else "NULL"
                print(f"  Block[{block_idx}] TX:{tx_hash[:8]}... Owner={owner_display} TokenID={tokenid_display}")

        if only_in_dev:
            print(colored(f"\n→ Only in Development ({len(only_in_dev)} records):", "yellow"))
            # Create a list of records with their block numbers for sorting
            dev_records = [(tx_hash, dev_dict[tx_hash]) for tx_hash in only_in_dev]
            # Sort by block number (index 4 in the record tuple), handle None values
            dev_records.sort(key=lambda x: x[1][4] if x[1][4] is not None else 0)

            for tx_hash, record in dev_records[:5]:
                block_idx = record[4] if record[4] is not None else "NULL"
                owner_display = (record[1][:20] + "...") if record[1] is not None and len(record[1]) > 20 else (record[1] or "NULL")
                tokenid_display = record[2] if record[2] is not None else "NULL"
                print(f"  Block[{block_idx}] TX:{tx_hash[:8]}... Owner={owner_display} TokenID={tokenid_display}")

        if mismatched:
            print(colored(f"\n→ Mismatched records ({len(mismatched)} records):", "yellow"))
            # Create a list of records with their block numbers for sorting
            mismatched_records = [(tx_hash, prod_dict[tx_hash], dev_dict[tx_hash]) for tx_hash in mismatched]
            # Sort by block number from production record, handle None values
            mismatched_records.sort(key=lambda x: x[1][4] if x[1][4] is not None else 0)

            for tx_hash, prod_record, dev_record in mismatched_records[:5]:
                block_idx = prod_record[4] if prod_record[4] is not None else "NULL"
                print(f"  TX:{tx_hash[:8]}... Block[{block_idx}]")
                if prod_record[1] != dev_record[1]:
                    prod_owner = (prod_record[1][:20] + "...") if prod_record[1] is not None and len(prod_record[1]) > 20 else (prod_record[1] or "NULL")
                    dev_owner = (dev_record[1][:20] + "...") if dev_record[1] is not None and len(dev_record[1]) > 20 else (dev_record[1] or "NULL")
                    print(f"    Owner: Prod[{prod_owner}] Dev[{dev_owner}]")
                if prod_record[2] != dev_record[2]:
                    prod_tokenid = prod_record[2] if prod_record[2] is not None else "NULL"
                    dev_tokenid = dev_record[2] if dev_record[2] is not None else "NULL"
                    print(f"    TokenID: Prod[{prod_tokenid}] Dev[{dev_tokenid}]")

    return bool(only_in_prod or only_in_dev or mismatched)


def print_final_summary(comparison_results, show_json=False):
    """Print a concise final summary of all comparisons."""
    total_issues = sum(1 for r in comparison_results.values() if r["has_issues"])
    total_tables = len(comparison_results)

    # Calculate severity
    total_errors = sum(
        r.get("diff_count", 0) + r.get("mismatch_count", 0) for r in comparison_results.values() if r["has_issues"]
    )

    if show_json:
        # JSON output for CI/testing
        summary = {
            "total_tables": total_tables,
            "tables_with_issues": total_issues,
            "total_errors": total_errors,
            "exit_code": 1 if total_issues > 0 else 0,
            "tables": comparison_results,
        }
        print(json.dumps(summary, indent=2))
        return

    print("\n" + "═" * 60)
    print(colored("  FINAL REPORT  ", "white", "on_blue", attrs=["bold"]))
    print("═" * 60)

    if total_issues == 0:
        print(colored(f"\n ✓ SUCCESS: All {total_tables} tables match perfectly!", "green", attrs=["bold"]))
        print(colored("\n EXIT CODE: 0 (SUCCESS)", "green"))
    else:
        print(
            colored(f"\n ⚠️  ATTENTION: {total_issues} of {total_tables} tables have discrepancies", "yellow", attrs=["bold"])
        )
        print(colored(f"\n TOTAL ERRORS: {total_errors}", "red"))
        print(colored("\n EXIT CODE: 1 (FAILURE)", "red"))

    print("\n" + "─" * 60)
    print(" Table                    Status      Details")
    print("─" * 60)

    for table, result in comparison_results.items():
        icon = "✓" if not result["has_issues"] else "✗"
        color = "green" if not result["has_issues"] else "red"
        status = "PASS" if not result["has_issues"] else "FAIL"

        print(f" {colored(icon, color)} {table:<22} {colored(status, color):<6}", end="")
        if result["has_issues"]:
            issues = []
            if result.get("diff_count", 0) > 0:
                issues.append(f"Δ={result['diff_count']}")
            if result.get("mismatch_count", 0) > 0:
                issues.append(f"Mismatches={result['mismatch_count']}")
            print(f"  {', '.join(issues)}")
        else:
            print()

    print("─" * 60)

    if total_issues > 0:
        print("\n💡 Next Steps:")
        print("  1. Review detailed differences above")
        print("  2. Check for recent indexer changes")
        print("  3. Verify data consistency requirements")

    print("\n" + "═" * 60)


def main():
    # Check for command line arguments
    show_json = "--json" in sys.argv
    show_help = "--help" in sys.argv or "-h" in sys.argv

    if show_help:
        print(
            """
Database Comparison Tool

Usage: python compare_tables.py [options]

Options:
  --json     Output results in JSON format (for CI/testing)
  --help     Show this help message

Exit Codes:
  0 - All tables match perfectly
  1 - One or more tables have discrepancies
  2 - Error during execution
        """
        )
        return 0

    if os.getcwd().endswith("/indexer"):
        sys.path.append(os.getcwd())
        dotenv_path = os.path.join(os.getcwd(), ".env")
    else:
        sys.path.append(os.path.join(os.getcwd(), "indexer"))
        dotenv_path = os.path.join(os.getcwd(), "indexer/.env")

    from dotenv import load_dotenv

    load_dotenv(dotenv_path=dotenv_path, override=True)

    # Track comparison results
    comparison_results = {}
    has_mismatches = False

    prod_host = os.environ.get("ST3_HOSTNAME")
    prod_user = os.environ.get("ST3_USER")
    prod_password = os.environ.get("ST3_PASSWORD")
    prod_database = os.environ.get("PROD_DATABASE")

    dev_host = os.environ.get("RDS_HOSTNAME")
    dev_user = os.environ.get("RDS_USER")
    dev_password = os.environ.get("RDS_PASSWORD")
    dev_database = "btc_stamps"

    prod_conn = mysql.connect(host=prod_host, user=prod_user, password=prod_password, database=prod_database)
    dev_conn = mysql.connect(host=dev_host, user=dev_user, password=dev_password, database=dev_database)

    prod_cursor = prod_conn.cursor()
    dev_cursor = dev_conn.cursor()

    try:
        # Get block_index first
        dev_cursor.execute(
            """
            SELECT MAX(block_index)
            FROM blocks
            """
        )
        block_index = dev_cursor.fetchone()[0]

        # Now we can print the connection details with the block_index
        if not show_json:
            print_connection_details(prod_host, dev_host, block_index)
            # Progress indicator
            print("\n🔄 Running comparisons...")

        # fetch tx_hash, stamp from prod db
        prod_cursor.execute(
            """
            SELECT tx_hash, stamp
            FROM StampTableV4
            WHERE block_index < %s
            """,
            (block_index,),
        )

        prod_list = prod_cursor.fetchall()

        # fetch tx_hash, stamp from dev db
        dev_cursor.execute(
            """
            SELECT tx_hash, stamp
            FROM StampTableV4
            WHERE block_index < %s
            """,
            (block_index,),
        )

        dev_list = dev_cursor.fetchall()

        prod_cursor.execute(
            """
            SELECT tx_hash, amt
            FROM SRC20Valid
            WHERE block_index < %s
            """,
            (block_index,),
        )

        prod_src20 = prod_cursor.fetchall()

        # fetch tx_hash, stamp from dev db
        dev_cursor.execute(
            """
            SELECT tx_hash, amt
            FROM SRC20Valid
            WHERE block_index < %s
            """,
            (block_index,),
        )

        dev_src20 = dev_cursor.fetchall()

        prod_cursor.execute(
            """
            SELECT block_index, messages_hash, txlist_hash, ledger_hash
            FROM blocks
            WHERE block_index < %s
            """,
            (block_index,),
        )
        prod_blocks = prod_cursor.fetchall()

        dev_cursor.execute(
            """
            SELECT block_index, messages_hash, txlist_hash, ledger_hash
            FROM blocks
            WHERE block_index < %s
            """,
            (block_index,),
        )
        dev_blocks = dev_cursor.fetchall()

        prod_blocks = sorted(list(prod_blocks))
        dev_blocks = sorted(list(dev_blocks))

        # Iterate over the two block lists
        for prod_block, dev_block in zip(prod_blocks, dev_blocks):
            if prod_block != dev_block:
                print_block_comparison(prod_block, dev_block)
                has_mismatches = True
                comparison_results["Block Hashes"] = {"has_issues": True, "mismatch_count": 1}
                break
        else:
            comparison_results["Block Hashes"] = {"has_issues": False}

        prod_src20 = set(prod_src20)
        dev_src20 = set(dev_src20)
        not_in_prod_src20 = dev_src20 - prod_src20
        not_in_prod_list_src20 = [item[0] for item in not_in_prod_src20]
        not_in_dev_src20 = prod_src20 - dev_src20
        not_in_dev_list_src20 = [item[0] for item in not_in_dev_src20]

        if not_in_prod_list_src20:
            has_mismatches = True
            # Use the values of tx_hash in not_in_prod_list to do a db lookup on dev db to fetch ident and stamp_url
            dev_cursor.execute(
                """
                SELECT tx_hash, amt, status, creator_bal, destination_bal
                FROM SRC20Valid
                WHERE tx_hash IN %s
                ORDER BY block_index ASC
                """,
                (not_in_prod_list_src20,),
            )

            results = dev_cursor.fetchall()

        # convert rows to list
        prod_list = set(prod_list)
        dev_list = set(dev_list)
        not_in_prod = dev_list - prod_list
        not_in_prod_list = [item[0] for item in not_in_prod]
        not_in_dev = prod_list - dev_list
        not_in_dev_list = [item[0] for item in not_in_dev]

        if not_in_prod_list or not_in_dev_list:
            has_mismatches = True

        if not_in_prod_list:
            # Use the values of tx_hash in not_in_prod_list to do a db lookup on dev db to fetch ident and stamp_url
            dev_cursor.execute(
                """
                SELECT stamp, ident, tx_hash, block_index, tx_index, cpid
                FROM StampTableV4
                WHERE tx_hash IN %s and stamp > 0
                ORDER BY tx_index ASC
                """,
                (not_in_prod_list,),
            )

            results = dev_cursor.fetchall()

        if not_in_dev_list:
            prod_cursor.execute(
                """
                SELECT stamp, ident, tx_hash, block_index, tx_index, cpid
                FROM StampTableV4
                WHERE tx_hash IN %s and stamp > 0
                ORDER BY tx_index ASC
                """,
                (not_in_dev_list,),
            )

            results = prod_cursor.fetchall()

        # Fetch SRC101Valid data
        prod_cursor.execute(
            """
            SELECT tx_hash, owner, tokenid, tokenid_utf8, block_index
            FROM SRC101Valid
            WHERE block_index < %s
            ORDER BY block_index ASC
            """,
            (block_index,),
        )
        prod_src101 = prod_cursor.fetchall()

        dev_cursor.execute(
            """
            SELECT tx_hash, owner, tokenid, tokenid_utf8, block_index
            FROM SRC101Valid
            WHERE block_index < %s
            ORDER BY block_index ASC
            """,
            (block_index,),
        )
        dev_src101 = dev_cursor.fetchall()

        # StampTableV4 comparison
        stamp_has_issues = compare_stamptable(prod_cursor, dev_cursor, block_index, show_json)
        cursed_has_issues = compare_cursed_stamps(prod_cursor, dev_cursor, block_index, show_json)

        # Count differences for StampTableV4
        stamp_diff_count = 0
        if stamp_has_issues:
            # Re-fetch to count differences
            prod_cursor.execute("SELECT COUNT(*) FROM StampTableV4 WHERE block_index < %s AND stamp > 0", (block_index,))
            prod_count = prod_cursor.fetchone()[0]
            dev_cursor.execute("SELECT COUNT(*) FROM StampTableV4 WHERE block_index < %s AND stamp > 0", (block_index,))
            dev_count = dev_cursor.fetchone()[0]
            stamp_diff_count = abs(prod_count - dev_count)

        comparison_results["StampTableV4"] = {"has_issues": stamp_has_issues, "diff_count": stamp_diff_count}
        comparison_results["Cursed Stamps"] = {"has_issues": cursed_has_issues}

        # SRC20Valid comparison
        if not show_json:
            print_comparison_header("SRC20Valid")
        prod_src20 = set(prod_src20)
        dev_src20 = set(dev_src20)
        not_in_prod_src20 = dev_src20 - prod_src20
        not_in_dev_src20 = prod_src20 - dev_src20
        src20_has_issues = bool(not_in_prod_src20 or not_in_dev_src20)
        if not show_json:
            print_summary("SRC20Valid", len(prod_src20), len(dev_src20), src20_has_issues)
        comparison_results["SRC20Valid"] = {
            "has_issues": src20_has_issues,
            "diff_count": abs(len(prod_src20) - len(dev_src20)),
        }

        if src20_has_issues:
            has_mismatches = True
            if not_in_prod_src20:
                dev_cursor.execute(
                    """
                    SELECT tx_hash, tick, amt, block_index
                    FROM SRC20Valid
                    WHERE tx_hash IN %s
                    ORDER BY block_index ASC
                    """,
                    (tuple(x[0] for x in not_in_prod_src20),),
                )
                results = dev_cursor.fetchall()
                print(colored(f"\n→ Missing from production ({len(results)} records):", "yellow"))
                for result in results[:5]:
                    print(f"  Block[{result[3]}] TX:{result[0][:8]}... Tick={result[1]} Amt={result[2]}")

            if not_in_dev_src20:
                prod_cursor.execute(
                    """
                    SELECT tx_hash, tick, amt, block_index
                    FROM SRC20Valid
                    WHERE tx_hash IN %s
                    ORDER BY block_index ASC
                    """,
                    (tuple(x[0] for x in not_in_dev_src20),),
                )
                results = prod_cursor.fetchall()
                print(colored(f"\n→ Missing from development ({len(results)} records):", "yellow"))
                for result in results[:5]:
                    print(f"  Block[{result[3]}] TX:{result[0][:8]}... Tick={result[1]} Amt={result[2]}")

        # SRC101Valid comparison
        src101_has_issues = compare_src101(prod_cursor, dev_cursor, block_index, prod_src101, dev_src101, show_json)
        comparison_results["SRC101Valid"] = {"has_issues": src101_has_issues}
        has_mismatches = src101_has_issues or has_mismatches

        if not_in_prod_list_src20 or not_in_dev_list_src20:
            has_mismatches = True
            print("\n" + "=" * 50)
            print(colored(" SRC20Valid Comparison ", "white", "on_blue", attrs=["bold"]))
            print("=" * 50)

            print("\n📊 Missing Transactions:")
            if len(not_in_prod_list_src20) == 0:
                print(f"├─ Production: {colored('✓ No missing records', 'green', attrs=['bold'])}")
            else:
                print(f"├─ Production: {colored(f'✗ Missing {len(not_in_prod_list_src20)} records', 'red', attrs=['bold'])}")

            if len(not_in_dev_list_src20) == 0:
                print(f"└─ Development: {colored('✓ No missing records', 'green', attrs=['bold'])}")
            else:
                print(f"└─ Development: {colored(f'✗ Missing {len(not_in_dev_list_src20)} records', 'red', attrs=['bold'])}")

        # Owners Table Comparison
        owners_has_issues = compare_ownerstable(prod_cursor, dev_cursor, block_index, show_json)
        comparison_results["Owners Table"] = {"has_issues": owners_has_issues}

    except Exception as e:
        if not show_json:
            print(colored(f"\n❌ ERROR: {str(e)}", "red", attrs=["bold"]))
            print(colored("\nExit Code: 2 (ERROR)", "red"))
        else:
            print(json.dumps({"error": str(e), "exit_code": 2}, indent=2))
        return 2
    finally:
        prod_cursor.close()
        dev_cursor.close()
        prod_conn.close()
        dev_conn.close()

    # Print final summary
    print_final_summary(comparison_results, show_json)

    # Return appropriate exit code based on mismatches
    exit_code = 1 if has_mismatches else 0

    if not show_json:
        print(f"\n📊 Exit Code: {exit_code}")
        if exit_code == 0:
            print("   ✓ All validations passed - safe to proceed")
        else:
            print("   ✗ Validation failures detected - review differences above")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
