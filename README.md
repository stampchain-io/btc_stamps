![Bitcoin Stamps](https://ipfs.io/ipfs/QmYnuPtWj6NyW1Rrrp5dU489rwPCAfH9Atxuq1Ap7v5cNU)

# Bitcoin Stamps 

## SRC-20 / SRC-721 / OLGA / SRC-721r / SRC-101

[![Python Checks](https://github.com/stampchain-io/btc_stamps/actions/workflows/python-check.yml/badge.svg)](https://github.com/stampchain-io/btc_stamps/actions/workflows/python-check.yml)
![last commit](https://img.shields.io/github/last-commit/stampchain-io/btc_stamps)


`btc_stamps` is the indexer, API, and explorer for Bitcoin Stamps. Which is an
experimental meta-protocol built on Bitcoin with no warranty.

This code was conceived based on the meta-protocol design created by Mikeinspace
([Bitcoin Stamps Github](https://github.com/mikeinspace/stamps)) in Feb 2023 by
Reinamora137. This code has served as the basis for all things Stamps since inception.
 See also [Bitcoin Stamps Initial Commit](https://github.com/mikeinspace/stamps/commit/a04461c541cd3eb3c0fcc59eff0f16c24911c014)

Much of the history of Bitcoin Stamps can be seen in this chat: [Bitcoin Stamps Telegram](https://t.me/BitcoinStamps)

This code also serves as the indexer and API for [stampchain.io](https://stampchain.io/),
which is the primary API source for developers building on the Bitcoin Stamps protocol. 

API endpoint documentation can be found at:

[stampchain.io/docs](https://stampchain.io/docs)

# Bitcoin Stamps - Immutable Digital Assets on Bitcoin

Bitcoin Stamps encompass a collection of sub-protocols built on Bitcoin, all
embodying the ethos of immutability. Here's an overview of the various stamp
types and their historical significance:

## CLASSIC STAMPS
NFT tokens where each Stamp can utilize a built-in token layer via standards
developed on Counterparty in 2014. Originally, Stamps were encouraged to be 1:1,
but creators can issue up to 4,294,967,295 individual tokens per Stamp.
Initially using only OP_MULTISIG transactions and a Base64 encoded image, they
now also include the OLGA P2WSH transaction format. Stamps were purpose built
to address the issues of accidental spending and prunability of Ordinals data.

**History**: The first Official Bitcoin Stamp was created by Mikeinspace in
Block 779652 (Stamp 0).

## SRC-20 STAMPS
A fungible token layer built around a fair mint system where users only pay BTC
miner fees. Modeled after BRC-20, but with the immutability of Stamps.

**History**: The first official SRC-20 Token (KEVIN) was deployed by Reinamora
in Block 788041.

## SRC-721 STAMPS
An NFT format utilizing a small JSON file to construct layered images from data
stored across multiple Stamps. This enables complex, high-resolution Stamps
while still leveraging the token layer employed via Counterparty.

**History**: The first SRC-721 Stamp was created in Block 792370.

## OLGA STAMPS
A new transaction format that eliminates the need for Base64 encoding, reducing
the transaction footprint by 50%. This optimized format reduces the  costs of 
the initial OP_MULTISIG format by approximately 60-70%, while maintaining all
original functionality. Almost all Classic Stamps after block 833000 are OLGA.

**History**: The first OLGA Stamp was created in Block 833000.

## SRC-721r STAMPS
The evolution of SRC-721, allowing for complex recursive images created from
JavaScript and other libraries stored on Stamps.

## SRC-101 STAMPS
A domain name system built on Bitcoin Stamps. Currently in development.

Since SATs don't exist, we Stamp on the UTXO set to ensure immutability. It is
impossible to inscribe a Stamp.

# Contributions

The Bitcoin Stamps protocol is open source and is being actively developed. 
If you have any ideas, improvements, or bug fixes, please feel free to submit
a pull request or open an issue.


# Donate

Bitcoin Stamps is open-source and community funded. The current maintainer
and original creator of the protocol is Reinamora137.

Bitcoin received will go towards maintenance, development and, hosting costs 
for stampchain.io. 

Bitcoin Stamps Dev Fund: bc1qe5sz3mt4a3e57n8e39pprval4qe0xdrkzew203

SRC-20 (KEVIN) tokens or BTC donations are extremely appreciated and serve
as the primary source of funding for this experimental project.


# Bitcoin Stamps Installation

## Requirements:

- Local full BTC Node or an account with [Quicknode.com](https://www.quicknode.com/)
  (free tier is fine) or similar service
- MySQL Database or Default MySQL installation from the provided Docker installation
- RECOMMENDED: Local Counterparty Node (optional)

For a simple Docker based installation of the Bitcoin Node and Counterparty stack see:

[Setting up a Counterparty Node](https://docs.counterparty.io/docs/basics/getting-started/)

The default configuration uses the public [Counterparty.io API](https://api.counterparty.io/)
and Stampchain.io Counterparty APIs for XCP asset data. To minimize resource
consumption on these free public resources, we highly recommend using a local
Counterparty node for long-term or production use. These public resources are
intended for dev/test purposes only. Stampchain operates two Counterparty nodes
for redundancy and to ensure the availability of the XCP asset data in the
Stampchain API.

## Installation & Execution with Docker

### Clone the repo

`git clone https://github.com/stampchain-io/btc_stamps.git`

If you wish to use the frontend app and API integrated into the docker config, you may use:

`git submodule update --init app`

### Step 1. Create & configure the env files

There are 3 env files that need to be created initially. These files are used to
configure the indexer, MySQL, and the explorer application. The sample files are
provided in the repo and can be copied and modified as needed. The sample files
are:

- `/app/.env.sample` - Explorer application environment variables [if submodule installed]
- `/docker/.env.mysql.sample` - MySQL environment variables
- `indexer/.env.sample` - Indexer environment variables

Copy the sample files to the actual env files:


```shell
cp app/.env.sample app/.env
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
  cd docker && docker-compose logs -f indexer
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
poetry install --only main
```

Execute Indexer:

```shell
poetry run indexer
```
