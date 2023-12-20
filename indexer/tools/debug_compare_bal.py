import os
import pymysql as mysql
from dotenv import load_dotenv
import pymysql as mysql
import os

parent_dir = os.path.dirname(os.getcwd())
dotenv_path = os.path.join(parent_dir, '.env')
load_dotenv(dotenv_path)

# Connection parameters
rds_host = os.environ.get('RDS_HOSTNAME')
rds_user = os.environ.get('RDS_USER')
rds_password = os.environ.get('RDS_PASSWORD')
rds_database = os.environ.get('RDS_DATABASE')


print('rdshost:', rds_host)
print('drs_user:', rds_user)


# Connect to the database
mysql_conn = mysql.connect(
    host=rds_host,
    user=rds_user,
    password=rds_password,
    database=rds_database
)

# Compare id, last_update, and amt fields
cursor = mysql_conn.cursor()

# Query to get balances for the highest block_index value
query = """
SELECT last_update
FROM balances
ORDER BY last_update DESC
LIMIT 1
"""

cursor.execute(query)
highest_block = cursor.fetchone()[0]

# Query to compare id field
query = """
SELECT SRC_STEVE.id, SRC_STEVE.block_index, SRC_STEVE.amt, balances.last_update, balances.amt
FROM SRC_STEVE
JOIN balances ON SRC_STEVE.id = balances.id
WHERE balances.last_update <= %s
"""

cursor.execute(query, (highest_block,))
result = cursor.fetchall()

print("Highest Block Compared:", highest_block)

# get count of total # of rows from SRC_STEVE.balances and balances
query = """
SELECT COUNT(*)
FROM SRC_STEVE
"""

cursor.execute(query)
src_steve_count = cursor.fetchone()[0]

print("SRC_STEVE Row count:", src_steve_count)


# Compare last_update and amt fields
output = []

for row in result:
    id_value = row[0]
    src_steve_block_index = row[1]
    src_steve_amt = row[2]
    balances_last_update = row[3]
    balances_amt = row[4]

    if src_steve_block_index == balances_last_update and src_steve_amt != balances_amt:
        output.append(f"ERROR: Mismatch for id {id_value}. {src_steve_block_index} / {src_steve_block_index}. SRC_STEVE amt: {src_steve_amt}. Balances amt: {balances_amt}")
    elif src_steve_block_index == balances_last_update and src_steve_amt == balances_amt:
        output.append(f"MATCH: id {id_value}, balance {balances_amt}")
    elif src_steve_block_index < balances_last_update:
        if balances_amt != src_steve_amt:
            output.append(f"WARN: id {id_value}, balance {balances_amt} / {src_steve_amt} BLOCKS NOT Matching YET S: {src_steve_block_index} / Balances {balances_last_update}")
    elif src_steve_block_index != balances_last_update:
        output.append(f"INFO: block index not matching {id_value}. Steve update: {src_steve_block_index}. Balances update: {balances_last_update}")
    else:
        output.append(f"ERROR: Unknown error for id {id_value}. Last update: {src_steve_block_index}. SRC_STEVE amt: {src_steve_amt}. Balances amt: {balances_amt}")

# Sort the output list
output.sort()
match_count = 0
error_count = 0
warn_count = 0
info_count = 0

for message in output:
    if message.startswith("MATCH"):
        match_count += 1
    elif message.startswith("ERROR"):
        error_count += 1
    elif message.startswith("WARN"):
        warn_count += 1
    elif message.startswith("INFO"):
        info_count += 1

print("Match count:", match_count)
print("Error count:", error_count)
print("Warn count:", warn_count)
print("Info count:", info_count)

# Output the sorted messages
for message in output:
    print(message)

print("selecting missing balances")

query = """
SELECT SRC_STEVE.id, SRC_STEVE.block_index, SRC_STEVE.amt
FROM SRC_STEVE
LEFT JOIN balances ON SRC_STEVE.id = balances.id
WHERE balances.id IS NULL AND SRC_STEVE.block_index < %s
"""

cursor.execute(query, (highest_block,))
result = cursor.fetchall()

# Output the result
for row in result:
    id_value = row[0]
    src_steve_block_index = row[1]
    src_steve_amt = row[2]
    output.append(f"MISSING: id {id_value}, block index {src_steve_block_index}, amt {src_steve_amt}")

cursor.close()
mysql_conn.close()
