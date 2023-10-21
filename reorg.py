import sqlite3
from bitcoinrpc.authproxy import AuthServiceProxy, JSONRPCException
import os

# Setup Bitcoin Core RPC connection
rpc_user = os.environ.get("rpc_user", 'rpc')
rpc_password = os.environ.get("rpc_password", 'rpc')
global_rpc_ip = os.environ.get("rpc_ip", '127.0.0.1')
rpc_ip = os.environ.get("rpc_ip", '127.0.0.1')
rpc_port = os.environ.get("rpc_port",'8332')

rpc_connection = AuthServiceProxy(f"http://{rpc_user}:{rpc_password}@{rpc_ip}:{rpc_port}")

# Setup SQLite database
conn = sqlite3.connect('blockchain.db')
c = conn.cursor()

# Create blocks table if it doesn't exist
c.execute('''CREATE TABLE IF NOT EXISTS blocks(
                      block_index INTEGER UNIQUE,
                      block_hash TEXT UNIQUE,
                      block_time INTEGER,
                      previous_block_hash TEXT UNIQUE,
                      difficulty INTEGER,
                      PRIMARY KEY (block_index, block_hash))
                   ''')
conn.commit()

# Get the current block height from Bitcoin Core
current_height = rpc_connection.getblockcount()
print(current_height)

if current_height > 0:
    # populate db with any missing records
    for height in range(779652, current_height + 1):
        # print("Checking block {} for reorgs".format(height))
        # Check if the block is already in the database
        c.execute('SELECT * FROM blocks WHERE block_index = ?', (height,))
        result = c.fetchone()

        if result is None:
            print("Adding block {} to the database".format(height))
            # If the block isn't in the database, add it
            block_hash = rpc_connection.getblockhash(height)
            block = rpc_connection.getblock(block_hash)
            c.execute('''
                INSERT INTO blocks (block_index, block_hash, block_time, previous_block_hash)
                VALUES (?, ?, ?, ?)
            ''', (height, block_hash, block['time'], block['previousblockhash']))
            conn.commit()

    # Check the last 10 blocks for reorgs
for height in range(current_height, current_height - 10, -1):
    # Get the block hash from Bitcoin Core
    block_hash = rpc_connection.getblockhash(height)

    # Get the block details from Bitcoin Core
    block = rpc_connection.getblock(block_hash)
    # print("checking for reorg at height {}".format(block))
    # Check if the block is already in the database

    c.execute('SELECT block_hash, block_index, block_time, previous_block_hash FROM blocks WHERE block_index = ?', (height,))
    result = c.fetchone()

    if result is None:
        # If the block isn't in the database, add it
        c.execute('''
            INSERT INTO blocks (block_index, block_hash, block_time, previous_block_hash)
            VALUES (?, ?, ?, ?)
        ''', (height, block_hash,  block['time'], block['previousblockhash']))
        conn.commit()
    else:
        # If the block is already in the database, check for a reorg
        db_block_hash, _, db_block_time, db_previous_block_hash = result

        if db_block_hash != block_hash or db_previous_block_hash != block['previousblockhash']:
            # Move the print statement here
            print("Reorg detected at height {}".format(height))
            # Here you would add code to handle the reorg...