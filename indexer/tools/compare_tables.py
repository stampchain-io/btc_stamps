import os
import sys

import pymysql as mysql
from termcolor import colored


def print_connection_details(prod_host, dev_host, block_index):
    print("\n" + "=" * 50)
    print(colored(" Database Comparison Details ", "white", "on_blue", attrs=["bold"]))
    print("=" * 50)
    print("\n📊 Connection Info:")
    print(f"├─ Production DB: {colored(prod_host, 'cyan')}")
    print(f"└─ Development DB: {colored(dev_host, 'cyan')}")
    print("\n📈 Comparison Range:")
    print(f"└─ Up to block: {colored(str(block_index), 'green', attrs=['bold'])}")
    print("\n" + "=" * 50 + "\n")


def print_block_comparison(prod_block, dev_block):
    print("\n" + "=" * 50)
    print(colored(" Block Hash Mismatch Details ", "white", "on_red", attrs=["bold"]))
    print("=" * 50)

    print("\n🔍 Block Information:")
    print(f"├─ Block Height: {colored(str(prod_block[0]), 'cyan', attrs=['bold'])}")

    print("\n📦 Messages Hash:")
    if prod_block[1] == dev_block[1]:
        print(f"├─ {colored('✓ Matches', 'green', attrs=['bold'])}")
        print(f"└─ Hash: {colored(prod_block[1], 'cyan')}")
    else:
        print(f"├─ {colored('✗ Mismatch', 'red', attrs=['bold'])}")
        print(f"├─ Prod: {colored(prod_block[1], 'yellow')}")
        print(f"└─ Dev:  {colored(dev_block[1], 'yellow')}")

    print("\n🔗 Transaction List Hash:")
    if prod_block[2] == dev_block[2]:
        print(f"├─ {colored('✓ Matches', 'green', attrs=['bold'])}")
        print(f"└─ Hash: {colored(prod_block[2], 'cyan')}")
    else:
        print(f"├─ {colored('✗ Mismatch', 'red', attrs=['bold'])}")
        print(f"├─ Prod: {colored(prod_block[2], 'yellow')}")
        print(f"└─ Dev:  {colored(dev_block[2], 'yellow')}")

    print("\n" + "=" * 50)


def print_comparison_header(table_name):
    print("\n" + "=" * 50)
    print(colored(f" {table_name} Comparison ", "white", "on_blue", attrs=["bold"]))
    print("=" * 50)


def print_summary(table_name, prod_count, dev_count, has_differences):
    print("\nSummary:")
    print(f"├─ Production records: {colored(prod_count, 'cyan')}")
    print(f"└─ Development records: {colored(dev_count, 'cyan')}")

    if not has_differences:
        print(colored("\n✓ Tables match perfectly!", "green", attrs=["bold"]))
    else:
        print(colored("\n✗ Differences found", "red", attrs=["bold"]))


def print_stamp_comparison(prod_record, dev_record):
    """Print detailed comparison of matching tx_hash with different stamps."""
    print(f"\n  • TX: {colored(prod_record[2], 'cyan')}")
    print(f"    ├─ Block: {colored(prod_record[3], 'white')}")
    print(
        f"    ├─ Production: Stamp={colored(prod_record[0], 'yellow')}, "
        f"Ident={colored(prod_record[1], 'yellow')}, "
        f"CPID={colored(prod_record[5], 'yellow')}"
    )
    print(
        f"    └─ Development: Stamp={colored(dev_record[0], 'yellow')}, "
        f"Ident={colored(dev_record[1], 'yellow')}, "
        f"CPID={colored(dev_record[5], 'yellow')}"
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
        print(f"    └─ {colored(f'CPID {cpid} found in {other_db_name} with different tx_hash:', 'yellow')}")
        for tx in related_txs:
            print(f"       • Block: {colored(tx[3], 'cyan')}")
            print(f"         ├─ TX: {tx[2]}")
            print(f"         ├─ Stamp: {tx[0]}")
            print(f"         └─ Ident: {tx[1]}")
    else:
        print(f"    └─ {colored(f'CPID {cpid} not found in {other_db_name}', 'red')}")


def compare_stamptable(prod_cursor, dev_cursor, block_index):
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

    print("\nSummary:")
    print(f"├─ Production records: {colored(len(prod_records), 'cyan')}")
    print(f"└─ Development records: {colored(len(dev_records), 'cyan')}")

    if only_in_prod or only_in_dev or mismatched:
        print(colored("\n✗ Differences found", "red", attrs=["bold"]))

        if mismatched:
            print(colored(f"\n→ Matching TX hash but different stamps ({len(mismatched)} records):", "yellow"))
            for tx in sorted(mismatched, key=lambda x: prod_dict[x][3])[:5]:
                print_stamp_comparison(prod_dict[tx], dev_dict[tx])

        if only_in_prod:
            print(colored(f"\n→ Only in Production ({len(only_in_prod)} records):", "red"))
            for tx in sorted(list(only_in_prod), key=lambda x: prod_dict[x][3])[:5]:
                record = prod_dict[tx]
                print(f"  • Block: {colored(record[3], 'cyan')}")
                print(f"    ├─ TX: {record[2]}")
                print(f"    ├─ Stamp: {record[0]}")
                print(f"    ├─ Ident: {record[1]}")
                print(f"    ├─ CPID: {record[5]}")
                print_cpid_cross_reference(prod_cursor, dev_cursor, record, "prod")

        if only_in_dev:
            print(colored(f"\n→ Only in Development ({len(only_in_dev)} records):", "red"))
            for tx in sorted(list(only_in_dev), key=lambda x: dev_dict[x][3])[:5]:
                record = dev_dict[tx]
                print(f"  • Block: {colored(record[3], 'cyan')}")
                print(f"    ├─ TX: {record[2]}")
                print(f"    ├─ Stamp: {record[0]}")
                print(f"    ├─ Ident: {record[1]}")
                print(f"    ├─ CPID: {record[5]}")
                print_cpid_cross_reference(prod_cursor, dev_cursor, record, "dev")
    else:
        print(colored("\n✓ All stamps match perfectly!", "green", attrs=["bold"]))


def compare_cursed_stamps(prod_cursor, dev_cursor, block_index):
    print_comparison_header("Cursed Stamps (Negative Values)")

    # Fetch all cursed stamp records
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

    # Categorize differences
    only_in_prod = set(prod_dict.keys()) - set(dev_dict.keys())
    only_in_dev = set(dev_dict.keys()) - set(prod_dict.keys())
    common_tx = set(prod_dict.keys()) & set(dev_dict.keys())

    # Find mismatched stamps in common transactions
    mismatched = [tx for tx in common_tx if prod_dict[tx][0] != dev_dict[tx][0] or prod_dict[tx][1] != dev_dict[tx][1]]

    print("\nCursed Stamps Summary:")
    print(f"├─ Production cursed stamps: {colored(len(prod_records), 'cyan')}")
    print(f"└─ Development cursed stamps: {colored(len(dev_records), 'cyan')}")

    if only_in_prod or only_in_dev or mismatched:
        print(colored("\n✗ Differences found in cursed stamps", "red", attrs=["bold"]))

        if mismatched:
            print(colored(f"\n→ Matching TX hash but different cursed values ({len(mismatched)} records):", "yellow"))
            for tx in sorted(mismatched, key=lambda x: prod_dict[x][3])[:5]:
                print_stamp_comparison(prod_dict[tx], dev_dict[tx])

        if only_in_prod:
            print(colored(f"\n→ Cursed only in Production ({len(only_in_prod)} records):", "red"))
            for tx in sorted(list(only_in_prod), key=lambda x: prod_dict[x][3])[:5]:
                record = prod_dict[tx]
                print(f"  • Block: {colored(record[3], 'cyan')}")
                print(f"    ├─ TX: {record[2]}")
                print(f"    ├─ Stamp: {colored(record[0], 'red')}")
                print(f"    ├─ Ident: {record[1]}")
                print(f"    ├─ CPID: {record[5]}")
                print_cpid_cross_reference(prod_cursor, dev_cursor, record, "prod")

        if only_in_dev:
            print(colored(f"\n→ Cursed only in Development ({len(only_in_dev)} records):", "red"))
            for tx in sorted(list(only_in_dev), key=lambda x: dev_dict[x][3])[:5]:
                record = dev_dict[tx]
                print(f"  • Block: {colored(record[3], 'cyan')}")
                print(f"    ├─ TX: {record[2]}")
                print(f"    ├─ Stamp: {colored(record[0], 'red')}")
                print(f"    ├─ Ident: {record[1]}")
                print(f"    ├─ CPID: {record[5]}")
                print_cpid_cross_reference(prod_cursor, dev_cursor, record, "dev")
    else:
        print(colored("\n✓ All cursed stamps match perfectly!", "green", attrs=["bold"]))


def main():
    if os.getcwd().endswith("/indexer"):
        sys.path.append(os.getcwd())
        dotenv_path = os.path.join(os.getcwd(), ".env")
    else:
        sys.path.append(os.path.join(os.getcwd(), "indexer"))
        dotenv_path = os.path.join(os.getcwd(), "indexer/.env")

    from dotenv import load_dotenv

    load_dotenv(dotenv_path=dotenv_path, override=True)

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

    # Get block_index first
    dev_cursor.execute(
        """
        SELECT MAX(block_index)
        FROM blocks
        """
    )
    block_index = dev_cursor.fetchone()[0]

    # Now we can print the connection details with the block_index
    print_connection_details(prod_host, dev_host, block_index)

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
        SELECT block_index, messages_hash, txlist_hash
        FROM blocks
        WHERE block_index < %s
        """,
        (block_index,),
    )
    prod_blocks = prod_cursor.fetchall()

    dev_cursor.execute(
        """
        SELECT block_index, messages_hash, txlist_hash
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
            break

    prod_src20 = set(prod_src20)
    dev_src20 = set(dev_src20)
    not_in_prod_src20 = dev_src20 - prod_src20
    not_in_prod_list_src20 = [item[0] for item in not_in_prod_src20]
    not_in_dev_src20 = prod_src20 - dev_src20
    not_in_dev_list_src20 = [item[0] for item in not_in_dev_src20]

    # print(
    #     f"not in SRC20Valid {prod_host} ",
    #     len(not_in_prod_list_src20),
    #     (not_in_prod_list_src20),
    # )
    # print(
    #     f"not in SRC20Valid {dev_host} ",
    #     len(not_in_prod_list_src20),
    #     (not_in_dev_list_src20),
    # )

    if not_in_prod_list_src20:
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
        # print("not in prod SRC20Valid ------------------  from dev db ", len(results))
        # for result in results:
        #     print(result)

    # convert rows to list
    prod_list = set(prod_list)
    dev_list = set(dev_list)
    not_in_prod = dev_list - prod_list
    not_in_prod_list = [item[0] for item in not_in_prod]
    not_in_dev = prod_list - dev_list
    not_in_dev_list = [item[0] for item in not_in_dev]

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

        # print("\nnot in prod StampTableV4 - results from dev db")
        # for result in results[:5]:
        #     print("result", result)

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
        # print("\nnot in dev StampTableV4 - results from prod db")
        # for result in results[:5]:
        #     print(result)

    # print(f"\nnot in StampTableV4 Prod incl cursed {prod_host} ", len(not_in_prod_list))
    # print("not_in_prod_list", not_in_prod_list)
    # print(f"\nnot in StampTableV4 Dev incl cursed {dev_host} ", len(not_in_dev_list))
    # print(not_in_dev_list)

    # missing_in_prod_list = set(not_in_prod_list) - set(not_in_dev_list)
    # missing_in_StampTableV4_Dev = set(not_in_dev_list) - set(not_in_prod_list)

    # print(f"\nmissing in StampTableV4 Prod incl cursed {prod_host} ", len(missing_in_prod_list))
    # print(missing_in_prod_list)
    # print(f"\nmissing in StampTableV4 Dev incl cursed {dev_host} ", len(missing_in_StampTableV4_Dev))
    # print(missing_in_StampTableV4_Dev)

    # Fetch SRC101Valid data
    prod_cursor.execute(
        """
        SELECT tx_hash, owner, tokenid, tokenid_utf8, block_index, tx_index
        FROM SRC101Valid
        WHERE block_index < %s
        ORDER BY block_index ASC
        """,
        (block_index,),
    )
    prod_src101 = prod_cursor.fetchall()

    dev_cursor.execute(
        """
        SELECT tx_hash, owner, tokenid, tokenid_utf8, block_index, tx_index
        FROM SRC101Valid
        WHERE block_index < %s
        ORDER BY block_index ASC
        """,
        (block_index,),
    )
    dev_src101 = dev_cursor.fetchall()

    # StampTableV4 comparison
    compare_stamptable(prod_cursor, dev_cursor, block_index)
    compare_cursed_stamps(prod_cursor, dev_cursor, block_index)

    # SRC20Valid comparison
    print_comparison_header("SRC20Valid")
    prod_src20 = set(prod_src20)
    dev_src20 = set(dev_src20)
    not_in_prod_src20 = dev_src20 - prod_src20
    not_in_dev_src20 = prod_src20 - dev_src20
    print_summary("SRC20Valid", len(prod_src20), len(dev_src20), bool(not_in_prod_src20 or not_in_dev_src20))

    if not_in_prod_src20 or not_in_dev_src20:
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
                print(f"  • Block: {colored(result[3], 'cyan')}")
                print(f"    └─ TX: {result[0]}")
                print(f"    └─ Tick: {result[1]}")
                print(f"    └─ Amount: {result[2]}")

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
                print(f"  • Block: {colored(result[3], 'cyan')}")
                print(f"    └─ TX: {result[0]}")
                print(f"    └─ Tick: {result[1]}")
                print(f"    └─ Amount: {result[2]}")

    # SRC101Valid comparison - SINGLE INSTANCE
    print_comparison_header("SRC101Valid")
    prod_dict = {(x[0], x[1], x[2], x[4]): x for x in prod_src101}
    dev_dict = {(x[0], x[1], x[2], x[4]): x for x in dev_src101}
    only_in_dev = set(dev_dict.keys()) - set(prod_dict.keys())
    only_in_prod = set(prod_dict.keys()) - set(dev_dict.keys())

    print_summary("SRC101Valid", len(prod_src101), len(dev_src101), bool(only_in_dev or only_in_prod))

    if only_in_dev or only_in_prod:
        if only_in_dev:
            print(colored(f"\n→ Missing from production ({len(only_in_dev)} records):", "yellow"))
            for key in sorted(list(only_in_dev), key=lambda x: x[3])[:5]:
                record = dev_dict[key]
                print(f"  • Block: {colored(record[4], 'cyan')}")
                print(f"    └─ TX: {record[0]}")
                print(f"    └─ Token: {record[2]}")
                print(f"    └─ Owner: {record[1]}")

        if only_in_prod:
            print(colored(f"\n→ Missing from development ({len(only_in_prod)} records):", "yellow"))
            for key in sorted(list(only_in_prod), key=lambda x: x[3])[:5]:
                record = prod_dict[key]
                print(f"  • Block: {colored(record[4], 'cyan')}")
                print(f"    └─ TX: {record[0]}")
                print(f"    └─ Token: {record[2]}")
                print(f"    └─ Owner: {record[1]}")

    if not_in_prod_list_src20 or not_in_dev_list_src20:
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


if __name__ == "__main__":
    main()
