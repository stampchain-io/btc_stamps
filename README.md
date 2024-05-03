# Bitcoin Stamps (SRC-20) Indexer / API / Explorer

The Bitcoin Stamps meta-protocol was initially developed using the Counterparty
(XCP) Bitcoin transaction encoding methods as an immutable storage layer for NFT
art (Classic Stamps). It now includes its own separate meta-protocol outside of
XCP called SRC-20 for fungible tokens, which do not conform with the XCP
transaction format and operate as a fully independent meta-protocol. This repo
supports both Classic Stamps, OLGA (P2WSH encoded), SRC-721 Stamps, and SRC-20
tokens, which are all considered part of Bitcoin Stamps. OLGA Stamps using P2WSH
encoding was added as of block height 833000 to support larger transaction
(file) sizes and to provide a lower cost of stamping images immutably on
Bitcoin. Bitcoin Stamps are permanently stored in the UTXO set.

This is the indexer code for [stampchain.io](https://stampchain.io/) which
parses the BTC node for all Stamp transactions, and is the primary API source
for developers building on the Bitcoin Stamps protocol. API endpoint
documentation can be found at:

[stampchain.io/docs](https://stampchain.io/docs)

## Requirements:

- Local full BTC Node or an account with
  [Quicknode.com](https://www.quicknode.com/) (free tier is fine) or similar
  service
- MySQL Database or Default MySQL installation from the Docker installation
- RECOMMENDED: Local Counterparty Node (optional)

For a simple installation of the entire stack Counterparty fednode can be used
to deploy both Counterparty and a full Bitcoin Node. See:
[Setting up a Counterparty Node](https://docs.counterparty.io/docs/basics/getting-started/)

The default configuration is using the public [XCP.dev](https://www.xcp.dev/)
and stampchain Counterparty API's for XCP asset data. To minimize resource
consumption on these free public resources we highly recommend using a local
Counterparty node for long term or production use. These public resources are
intended for dev/test purposes only. Stampchain operates two Counterparty nodes
for redundancy and to ensure the availability of the XCP asset data into the
Stampchain API.

## Installation & Execution with Docker

### Step 1. Create & configure the env files

There are 4 env files that need to be created initially. These files are used to
configure the indexer, grafana, mysql, and the explorer application. The sample
files are provided in the repo and can be copied and modified as needed. The
sample files are:

- `/app/.env.sample` - Explorer application environment variables
- `/docker/.env.grafana.sample` - Grafana environment variables
- `/docker/.env.mysql.sample` - MySQL environment variables
- `indexer/.env.sample` - Indexer environment variables

Copy the sample files to the actual env files:

```shell
cp app/.env.sample app/.env
```

```shell
cp docker/.env.grafana.sample docker/.env.grafana
```

```shell
cp docker/.env.mysql.sample docker/.env.mysql
```

```shell
cp indexer/.env.sample indexer/.env
```

### Step 2 - Run the stack

There are two options for running the stack. Option one is to use docker-compose
commands directly and option two is to use the Makefile with make commands. The
Makefile is a wrapper for docker-compose commands and provides a more simplified
interface for running the stack.

- Option 1. Starting the services with docker-compose commands:

  ```shell
  # Start all the services
  cd docker && docker-compose up -d
  ```

  ```shell
  # View the logs for the indexer application
  cd docker && docker-compose logs -f app
  ```

  ```shell
  # Shutdown all the services
  cd docker && docker-compose down
  ```

- Option 2. Starting the services with the make commands:

  ```shell
  # Start the stack
  make dup
  ```

  ```shell
  # View the logs for the indexer application
  make logs
  ```

  ```shell
  # Shutdown all the services
  make down
  ```

  ```shell
  # Shutdown all the services and clean volumes
  make fdown
  ```

## Local Execution w/o Docker:

Configure all environment variables for MySQL, Bitcoin Node, and Counterparty as
indicated in `.env`

Install Poetry:

```shell
curl -sSL https://install.python-poetry.org | python3 -
```

Install Dependencies

```shell
cd indexer
poetry install --no-dev
```

Execute Indexer:

```shell
poetry run indexer
```
