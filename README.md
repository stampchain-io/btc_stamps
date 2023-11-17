# Bitcoin Stamps Primary Indexer - SRC-20, Glyphs, etc.

- Currently saving ALL BTC transactions for potential other uses,  this may be trimmed by using the config.BLOCKS_TO_KEEP variable
- We are saving all transactions so that multi-sourced data from CP and direct from BTC (SRC-20) can be ordered - maintaining stamp numbering
- In the event of a block reorg the impacted transactions, blocks and entries in StampTable are purged

## Indexer Exection via Docker: 

Revise your variables in docker-compose

`cp docker-compose-sample.yml docker-compose.yml`

Execute the indexer which creates docker instances for the indexer application, MySQL Database, Grafana, and Adminier for MySQL management

`docker-compose up -d`

View app logs here:

`docker-compose logs -f app`


The default configuration is using coindaddy for XCP asset data, this can be configured to use a local CP indexer. 

## Requirements:

 - Account with Quicknode.io (free tier is fine) or a local full BTC Node 
 - MySQL Database or Default MySQL installation from Docker Compose


## Local Execution:

assuming all variables are configured for MySQL and a Bitcoin Node

`python start.py` 