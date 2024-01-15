
import os
import pymysql as mysql
from dotenv import load_dotenv
import pymysql as mysql
import os
from decimal import Decimal

load_dotenv()

# Connection parameters
rds_host = os.environ.get('RDS_HOSTNAME')
rds_user = os.environ.get('RDS_USER')
rds_password = os.environ.get('RDS_PASSWORD')
rds_database = os.environ.get('RDS_DATABASE')


print('rdshost:', rds_host)
print('rds_user:', rds_user)


# select all address: tick combinations from balances table
# for each address: tick combination store the address and tick in a var for later processing


# Connect to the database
mysql_conn = mysql.connect(
    host=rds_host,
    user=rds_user,
    password=rds_password,
    database=rds_database
)

# get all unique address: tick combinations from SRC20Valid table
cursor = mysql_conn.cursor()
query = """
SELECT op, creator, destination, tick, amt, block_time, block_index
FROM SRC20Valid
WHERE op = 'TRANSFER' OR op = 'MINT'
"""
cursor.execute(query)
src20_valid_list = cursor.fetchall()
cursor.close()

# drop all rows from the balances table
cursor = mysql_conn.cursor()
query = """
DELETE FROM balances
"""
cursor.execute(query)
mysql_conn.commit()

all_balances = {}
for [op, creator, destination, tick, amt, block_time, block_index] in src20_valid_list:
    destination_id = tick + '_' + destination
    destination_amt = Decimal(0) if destination_id not in all_balances else all_balances[destination_id]['amt']
    destination_amt += amt

    all_balances[destination_id] = {
        'tick': tick,
        'address': destination,
        'amt': destination_amt,
        'last_update': block_index,
        'block_time': block_time
    }

    if op == 'TRANSFER':
        creator_id = tick + '_' + creator
        creator_amt = Decimal(0) if creator_id not in all_balances else all_balances[creator_id]['amt']
        creator_amt -= amt
        all_balances[creator_id] = {
            'tick': tick,
            'address': creator,
            'amt': creator_amt,
            'last_update': block_index,
            'block_time': block_time
        }

print("Inserting {} balances".format(len(all_balances)))

cursor.executemany('''INSERT INTO balances(id, tick, address, amt, last_update, block_time, p)
                    VALUES(%s,%s,%s,%s,%s,%s,%s)''', [(key, value['tick'], value['address'], value['amt'],
                    value['last_update'], value['block_time'], 'SRC-20') for key, value in all_balances.items()])

# close db
mysql_conn.commit()
cursor.close()
mysql_conn.close()
