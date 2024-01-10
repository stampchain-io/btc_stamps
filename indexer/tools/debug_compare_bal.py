import os
import pymysql as mysql
from dotenv import load_dotenv
import pymysql as mysql
import os
import codecs
import re

''' temporary queries to validate against Steves balances table '''

# parent_dir = os.path.dirname(os.getcwd())
# dotenv_path = os.path.join(parent_dir, '.env')
load_dotenv()

# Connection parameters
rds_host = os.environ.get('RDS_HOSTNAME')
rds_user = os.environ.get('RDS_USER')
rds_password = os.environ.get('RDS_PASSWORD')
rds_database = os.environ.get('RDS_DATABASE')


print('rdshost:', rds_host)
print('rds_user:', rds_user)


# Connect to the database
mysql_conn = mysql.connect(
    host=rds_host,
    user=rds_user,
    password=rds_password,
    database=rds_database
)

def convert_to_utf(row):
    def convert(match):
        return f"\\U{ord(match.group(0)):08X}"
    
    converted_row = []
    for item in row:
        if isinstance(item, str):
            converted_item = re.sub(r'[^\x00-\x7F]', convert, item)
            converted_row.append(converted_item)
        else:
            converted_row.append(item)
    return tuple(converted_row)


# Compare id, last_update, and amt fields
cursor = mysql_conn.cursor()

# Query to get highest last_update value from balances
query = """
SELECT last_update
FROM balances
ORDER BY last_update DESC
"""
cursor.execute(query)
highest_block = cursor.fetchone()[0]
print("BALANCES: Highest block in table:", highest_block)
# highest_block = 822825

# Query to get the highest block_index value from SRC_STEVE
query = """
select block_index
from SRC_STEVE
order by block_index desc
"""
cursor.execute(query)
highest_block = cursor.fetchone()[0]
print("STEVE: Highest block in table:", highest_block)

# Query to get all rows in SRC_STEVE <= highest_block
query = """
SELECT COUNT(*)
FROM SRC_STEVE
WHERE block_index <= %s
"""
cursor.execute(query, (highest_block,))
result = cursor.fetchone()[0]
print(f"Count of all rows in SRC_STEVE <= block {highest_block}:", result)

# Query to count all rows in balances <= highest_block
query = """
SELECT COUNT(*)
FROM balances
WHERE last_update <= %s
"""
cursor.execute(query, (highest_block,))
result = cursor.fetchone()[0]
print(f"Count of all rows in balances <= block {highest_block}:", result)


# Query to output all rows that are in SRC_STEVE but NOT in balances where block_index is less than or equal to highest_block
query = """
SELECT id, block_index, amt
FROM SRC_STEVE
"""
cursor.execute(query)
src_steve_rows = cursor.fetchall()

converted_rows = [convert_to_utf(row) for row in src_steve_rows]

# Query to get all rows from balances / these already use unicode strings
query = """
SELECT id, last_update, amt
FROM balances
"""
cursor.execute(query)
balances_rows = cursor.fetchall()

# Convert rows to sets of tuples for faster lookup
src_steve_set = set(converted_rows)
balances_set = set(balances_rows)

# Find rows that are in SRC_STEVE but not in balances
difference = src_steve_set - balances_set

# Convert the result back to a list of tuples
difference_rows = list(difference)

# Count the number of rows in SRC_STEVE but not in balances
src_steve_not_in_balances_count = len(difference_rows)

# Count the number of rows in balances but not in SRC_STEVE
balances_not_in_src_steve_count = len(balances_rows) - len(difference_rows)


print(f"SRC_STEVE rows not in balances: {src_steve_not_in_balances_count}")
print(f"balances rows not in SRC_STEVE: {balances_not_in_src_steve_count}")


# find all matching rows between src_steve_set and balances_set
matching_rows = src_steve_set & balances_set
matching_rows_count = len(matching_rows)
print(f"Matching rows between SRC_STEVE and balances: {matching_rows_count}")
