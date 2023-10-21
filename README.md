# btc_stamps

Bitcoin Stamps SRC-20 Primary Indexer


- This current version is saving BTC transactions to both a local server.db file (equivalent to counterparty.db) and a mysql database
- More work needs to be done to remove the dependence on the local sqlite db. This was for verification to make sure commits were happening to both DB's in the same manner to handle block reorgs
- It is currently saving ALL BTC transactions for potential other uses, however this may be trimmed to only stamp/src-20 related transactions
- We are saving all transactions so that multi-sourced data from CP and direct from BTC can be ordered - maintaining stamp numbering
- In the event of a block reorg execution is stopped. this needs to be updated to delete from the stamptablev4, blocks, and transactions table for the block >= the reorg
- Currently the SRC-20 transactions directly on BTC are getting saved into the transactions table, and then parsed through other functions which number the stamps, and pull CP transactions
- This is not intended to parse CP transactions, however this is possible with some work.

This is executed via the start.py

These environment variables must be set for the sql server connection

```
rds_host = os.environ.get('RDS_HOSTNAME')
rds_user = os.environ.get('RDS_USER')
rds_password = os.environ.get('RDS_PASSWORD')
rds_database = os.environ.get('RDS_DATABASE')
```

The table creation into MySQL has not been tested so the table schema may need to be created manually. 
