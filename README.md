# Bitcoin Stamps Primary Indexer - SRC-20, SRC-721, Glyphs, etc.

The Bitcoin Stamps protocol was initially developed on top of Bitcoin via Counterparty (XCP) as an immutable storage layer for NFT art. It now includes its own separate protocol (SRC-20) which does not utillize XCP and creates transactions directly onto Bitcoin (BTC) without the XCP transaction layer. This indexer supports both XCP and direct to BTC transactions which are both considered part of Bitcoin Stamps. Bitcoin Stamps are permanently stored in the Bitcoin UTXO set and cannot be pruned from the blockchain.

This is the public indexing code for stampchain.io which is the primary API source for developers building on the Bitcoin Stamps protocol.

## Requirements:

 - Local full BTC Node or an account with Quicknode.io (free tier is fine) or similar service  
 - MySQL Database or Default MySQL installation from the Docker installation
 - HIGHLY RECOMMENDED: Local Counterparty Node (optional) 

We recommend using Counterparty fednode to deploy both Counterparty and a full Bitcoin Node via `fednode install base master` see: [Setting up a Counterparty Node](https://github.com/CounterpartyXCP/Documentation/blob/master/Installation/federated_node.md)

The default configuration is using the public Coindaddy API for XCP asset data. To minimize resource consumption on this free public resource we highly recommend using a local Counterparty node for long term use. Bitcoin Stamps and Stampchain is not directly associated with this service and cannot guarantee its availability or long term accessibility. It is intended for dev/test purposes only. Stampchain operates two Counterparty nodes for redundancy and to ensure the availability of the XCP asset data into the Stampchain API.

## Indexer Exection via Docker: 

Revise your variables in docker-compose

`cp docker-compose-sample.yml docker-compose.yml`

Execute the indexer which creates docker instances for the indexer application, MySQL Database, Grafana for visualization, and Adminer for MySQL management

`docker-compose up -d`

View indexer application logs:

`docker-compose logs -f app`


## Local Execution w/o Docker:

Configure all environment variables for MySQL, Bitcoin Node, and Counterparty as indicated in `config.py`

`python start.py` 