# btc_stamps

Bitcoin Stamps Primary Indexer - SRC-20, Glyphs, etc.


- This current version is saving BTC transactions to both a local server.db file (equivalent to counterparty.db) and a MySQL database
- More work needs to be done to remove the dependence on the local sqlite db. This was for verification to make sure commits were happening to both DB's in the same manner to handle block reorgs
- It is currently saving ALL BTC transactions for potential other uses, however this may be trimmed to only stamp/src-20 related transactions
- We are saving all transactions so that multi-sourced data from CP and direct from BTC (SRC-20) can be ordered - maintaining stamp numbering
- In the event of a block reorg execution is stopped. this needs to be updated to delete from the stamptablev4, blocks, and transactions table for the block >= the reorg
- Currently the SRC-20 transactions directly on BTC are saved to the transactions table, and then parsed through other functions which number the stamps, and merge with CP transactions in StampTableV4
- This is not intended to parse CP transactions, however this is possible with some work.

This is executed via the start.py

These env vars must be set for the MySQL server connection - currently in blocks.py (TODO: move to config.py)

```
rds_host = os.environ.get('RDS_HOSTNAME')
rds_user = os.environ.get('RDS_USER')
rds_password = os.environ.get('RDS_PASSWORD')
rds_database = os.environ.get('RDS_DATABASE')
```

These env vars located in config.py must be set for the BTC node connection, this could be a service like quicknode. The transactions helpers  which CP can use to parse the BTC node database files directly has been removed/disabled so the API connection is required. 

```
RPC_USER = os.environ.get("RPC_USER", 'rpc')
RPC_PASSWORD = os.environ.get("RPC_PASSWORD", 'rpc')
RPC_IP = os.environ.get("RPC_IP", '127.0.0.1')
RPC_PORT = os.environ.get("RPC_PORT",'8332')
RPC_URL = f"http://{RPC_USER}:{RPC_PASSWORD}@{RPC_IP}:{RPC_PORT}"
RPC_CONNECTION = AuthServiceProxy(RPC_URL)
```

The MySQL table schema can be imported from table_schema.sql The table creation functions within the parser have not been fully tested. 


