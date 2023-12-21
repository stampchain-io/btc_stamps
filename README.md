# Bitcoin Stamps (SRC-20) Indexer / API / Explorer 

The Bitcoin Stamps protocol was initially developed using Counterparty (XCP) on Bitcoin as an immutable storage layer for NFT art (Classic Stamps). It now includes its own separate protocol outside of XCP called SRC-20 which creates transactions directly onto Bitcoin without the XCP transaction layer. This repo supports both Classic Stamps and direct to BTC SRC-20 tokens which are both considered part of Bitcoin Stamps. Bitcoin Stamps are permanently stored in the Bitcoin UTXO set and cannot be pruned from the blockchain. This permanence comes at a price through Bitcoin transaction fees that don't benefit from the witness data discount. The Bitcoin Stamps protocol is intended for use cases where permanence is required and the cost of the transaction is of little concern.

This is the public indexer code for stampchain.io which parses the BTC node for all Stamp transactions, and is the primary API source for developers building on the Bitcoin Stamps protocol.

## Requirements:

 - Local full BTC Node or an account with Quicknode.io (free tier is fine) or similar service  
 - MySQL Database or Default MySQL installation from the Docker installation
 - RECOMMENDED: Local Counterparty Node (optional) 

For a simple installation of the entire stack Counterparty fednode can be used to deploy both Counterparty and a full Bitcoin Node. See: [Setting up a Counterparty Node](https://github.com/CounterpartyXCP/Documentation/blob/master/Installation/federated_node.md)

The default configuration is using the public XCP.dev and stampchain Counterparty API's for XCP asset data. To minimize resource consumption on these free public resources we highly recommend using a local Counterparty node for long term or production use. These public resources are intended for dev/test purposes only. Stampchain operates two Counterparty nodes for redundancy and to ensure the availability of the XCP asset data into the Stampchain API.

## Indexer Exection via Docker: 

- Option 1:

Revise your variables in docker-compose

`cp docker/docker-compose-sample.yml docker/docker-compose.yml`

Execute the indexer which creates docker instances for the indexer application, MySQL Database, Grafana for visualization, and Adminer for MySQL management

`cd docker && docker-compose up -d`

View indexer application logs:

`cd docker && docker-compose logs -f app`


- Option 2:

You can use the Makefile to start all the services:

`make dup`

View indexer application logs:

`make logs`

Shutdown all the services:

`make down`

shutdown all the services and clean volumes:

`make fdown`


## Local Execution w/o Docker:

Configure all environment variables for MySQL, Bitcoin Node, and Counterparty as indicated in `config.py`

`python start.py` 