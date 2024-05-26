import os
import sys

import pymysql as mysql

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

print("production", prod_host, "dev", dev_host)
prod_conn = mysql.connect(host=prod_host, user=prod_user, password=prod_password, database=prod_database)

dev_conn = mysql.connect(host=dev_host, user=dev_user, password=dev_password, database=dev_database)

prod_cursor = prod_conn.cursor()
dev_cursor = dev_conn.cursor()

dev_cursor.execute(
    """
                   SELECT MAX(block_index)
                     FROM blocks
                    """
)
block_index = dev_cursor.fetchone()[0]

print("block_index", block_index)

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
        print(f"First BLOCK HASH mismatch found:\nProd block: {prod_block}\nDev block: {dev_block}")
        break

prod_src20 = set(prod_src20)
dev_src20 = set(dev_src20)
not_in_prod_src20 = dev_src20 - prod_src20
not_in_prod_list_src20 = [item[0] for item in not_in_prod_src20]
not_in_dev_src20 = prod_src20 - dev_src20
not_in_dev_list_src20 = [item[0] for item in not_in_dev_src20]

print(
    f"not in SRC20Valid {prod_host} ",
    len(not_in_prod_list_src20),
    (not_in_prod_list_src20),
)
print(
    f"not in SRC20Valid {dev_host} ",
    len(not_in_prod_list_src20),
    (not_in_dev_list_src20),
)

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
    print("not in prod SRC20Valid ------------------  from dev db ", len(results))
    for result in results:
        print(result)

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
                    ORDER BY block_index ASC
                    """,
        (not_in_prod_list,),
    )

    results = dev_cursor.fetchall()

    print("\nnot in prod StampTableV4 - results from dev db ")
    for result in results[:5]:
        print("result", result)

if not_in_dev_list:
    prod_cursor.execute(
        """
                    SELECT stamp, ident, tx_hash, block_index, tx_index, cpid
                    FROM StampTableV4
                    WHERE tx_hash IN %s and stamp > 0
                    ORDER BY block_index ASC
                    """,
        (not_in_dev_list,),
    )

    results = prod_cursor.fetchall()
    print(" \nnot in dev StampTableV4 - results from prod db")
    for result in results[:5]:
        print(result)

print(f"\nnot in StampTableV4 Prod incl cursed {prod_host} ", len(not_in_prod_list))
# print("not_in_prod_list", not_in_prod_list)
print(f"\nnot in StampTableV4 Dev incl cursed {dev_host} ", len(not_in_dev_list))
# print(not_in_dev_list)
