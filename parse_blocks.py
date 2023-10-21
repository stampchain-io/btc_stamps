import sqlite3
# import os
# from bitcoinrpc.authproxy import AuthServiceProxy, JSONRPCException
import json
import time
# Import the parse_trx module

from parse_stamp import stamp_tx_parse
from config import getrawtransaction, decimal_default
from config import get_db_connection, bitcoin_getblock

# Get a connection to the database
conn = get_db_connection()


def parse_block(block_hash):
    block_data = bitcoin_getblock(block_hash)
    block_height = block_data['height']
    txs = block_data['tx']
    print("block_data: ", block_data)
    parsed_txs = []
    for tx in txs:
        # print(tx)
        print("parsing tx")
        parsed_tx = stamp_tx_parse(tx, block_height) # if we were succesful parsing for stamp: we will save to trx table.
        if parsed_tx:
            print("appending parsed_tx to parsed_txs")
            parsed_txs.append(parsed_tx)
    return parsed_txs


# Create a cursor object
c = conn.cursor()

# Create transactions table if it doesn't exist
c.execute('''CREATE TABLE IF NOT EXISTS transactions(
                      tx_index INTEGER PRIMARY KEY,
                      tx_hash TEXT UNIQUE,
                      block_index INTEGER,
                      block_hash TEXT,
                      block_time INTEGER,
                      source TEXT,
                      destination TEXT,
                      btc_amount INTEGER,
                      fee INTEGER,
                      hex_data BLOB)
                   ''')
conn.commit()

# Create srcx table if it doesn't exist
c.execute('''CREATE TABLE IF NOT EXISTS srcx(
                      tx_index INTEGER PRIMARY KEY,
                      block_index INTEGER,
                      tx_hash TEXT UNIQUE,
                      source TEXT,
                      destination TEXT,
                      amt DECIMAL,
                      dec INTEGER DEFAULT 18,
                      lim DECIMAL,
                      max DECIMAL,
                      op TEXT,
                      p TEXT,
                      tick TEXT,
                      status TEXT)
                   ''')
conn.commit()


# Get the latest block index in the transactions table
c.execute('SELECT MAX(block_index) FROM transactions')
print("getting latest block start index")
result = c.fetchone()
if result[0] is None:
    latest_block_index = 793486
else:
    latest_block_index = result[0]

# Query the blocks table for new blocks
c.execute('SELECT * FROM blocks WHERE block_index > ?', (latest_block_index,))
blocks = c.fetchall()
print("Found {} new blocks".format(len(blocks)))

# Parse the transactions containing stamp: in each new block and insert them into the transactions table
# this will reparse blocks each time if no stamps were found previously
for block in blocks:
    print("Processing block {}".format(block[0]))
    parsed_txs = parse_block(block[1]) # check all trx in block for stamp: and parse
    print("parsed_txs: ", parsed_txs)
    for parsed_tx in parsed_txs:
        txid = parsed_tx['txid']

        # use the input_txid vout value and lookup the input_txid{vout} from the node and extract the address from that lookup
        input_txid = parsed_tx['vin'][0]['txid']
        input_tx = getrawtransaction(input_txid, verbose=True) # get the input_tx info - this is the only location to determine source
        print("input_tx: ", input_tx)
        input_index = parsed_tx['vin'][0]['vout']
        print("input_index: ", input_index)
        source = input_tx['vout'][input_index]['scriptPubKey']['address']
        print("input_address: ", source)
        time.sleep(2)
        # byte count inside the utxo 
        print(json.dumps(parsed_tx, indent=4, default=decimal_default))
        # if this fails then this is not a transfer transaction
        try:
            destination = parsed_tx['vout'][0]['scriptPubKey']['address']
        except:
            raise Exception("This is not a valid stamp - probably a CP transaction")

        fee = parsed_tx.get('fee', 0)
        hex_data = parsed_tx['hex']  # in the parse_block we get the utxo hex data in a list... save that instead? 
        btc_amount = parsed_tx.get('value', 0)
        block_index = block[0]
        block_hash = block[1]
        block_time = block[2]
        
        # if tx_dict['src_dict'] is not None we will import the dictionary into the srcx table with all appropraite values from the dictionary
        if parsed_tx['src_dict'] is not None:
            if tick_value is not None:
                tick_value = tick_value.upper()
            c.execute('INSERT OR IGNORE INTO srcx ( block_index, tx_hash, source, destination, dec, lim, max, amt, op, p, tick, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                        (int(block_index), txid, source, destination,
                        int(parsed_tx['src_dict'].get('dec')) if parsed_tx['src_dict'].get('dec') is not None else 0,
                        float(parsed_tx['src_dict'].get('lim')) if parsed_tx['src_dict'].get('lim') is not None else 0.00,
                        float(parsed_tx['src_dict'].get('max')) if parsed_tx['src_dict'].get('max') is not None else 0.00,
                        float(parsed_tx['src_dict'].get('amt', 0.00)),
                        str(parsed_tx['src_dict'].get('op', None)),
                        str(parsed_tx['src_dict'].get('p', None)),
                        tick_value))
            conn.commit()
        # Insert the found stamp transactions into the transactions table

        # Insert the found stamp transactions into the transactions table
        c.execute('INSERT OR IGNORE INTO transactions (tx_hash, block_index, block_hash, block_time, source, destination, btc_amount, fee, hex_data) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)', (txid, block_index, block_hash, block_time, source, destination, btc_amount, fee, hex_data))
        conn.commit()


