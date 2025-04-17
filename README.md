<div align="center">
  <img src="https://ipfs.io/ipfs/QmYnuPtWj6NyW1Rrrp5dU489rwPCAfH9Atxuq1Ap7v5cNU" alt="Bitcoin Stamps" width="210">
  
  # Bitcoin Stamps
  
  ### SRC-20 / SRC-721 / OLGA / SRC-721r / SRC-101
  
  -  [![🧪 Code Quality & Unit Tests](https://github.com/stampchain-io/btc_stamps/actions/workflows/python-check.yml/badge.svg?branch=dev&job=code-quality)](https://github.com/stampchain-io/btc_stamps/actions/workflows/python-check.yml) [![🔧 Rust Checks](https://github.com/stampchain-io/btc_stamps/actions/workflows/python-check.yml/badge.svg?branch=dev&job=rust)](https://github.com/stampchain-io/btc_stamps/actions/workflows/python-check.yml) [![🌐 Integration Tests](https://github.com/stampchain-io/btc_stamps/actions/workflows/python-check.yml/badge.svg?branch=dev&job=integration)](https://github.com/stampchain-io/btc_stamps/actions/workflows/python-check.yml) [![🐋 Docker Build](https://github.com/stampchain-io/btc_stamps/actions/workflows/docker-auto-publish.yml/badge.svg?branch=dev)](https://github.com/stampchain-io/btc_stamps/actions/workflows/docker-auto-publish.yml)

  -  [![Last Commit](https://img.shields.io/github/last-commit/stampchain-io/btc_stamps)](https://github.com/stampchain-io/btc_stamps) [![Python Versions](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)](https://www.python.org/) [![License](https://img.shields.io/github/license/stampchain-io/btc_stamps)](LICENSE) [![Stars](https://img.shields.io/github/stars/stampchain-io/btc_stamps?style=social)](https://github.com/stampchain-io/btc_stamps/stargazers) [![Forks](https://img.shields.io/github/forks/stampchain-io/btc_stamps?style=social)](https://github.com/stampchain-io/btc_stamps/network/members) [![Issues](https://img.shields.io/github/issues/stampchain-io/btc_stamps)](https://github.com/stampchain-io/btc_stamps/issues) [![Pull Requests](https://img.shields.io/github/issues-pr/stampchain-io/btc_stamps)](https://github.com/stampchain-io/btc_stamps/pulls)
</div>

## 📋 Overview

`btc_stamps` is the official indexer for Bitcoin Stamps, a cutting-edge meta-protocol 
built on Bitcoin dedicated to immutability and permanent data storage on the Bitcoin blockchain. 
This protocol is experimental and provided without warranty. For full details, please refer 
to the [LICENSE](LICENSE) file.

This project evolved from a meta-protocol design created by Mikeinspace
([Bitcoin Stamps Github](https://github.com/mikeinspace/stamps)) in February 2023.
Reinamora137 developed this implementation, which has since become the foundation for the
entire Bitcoin Stamps ecosystem. You can view the [initial commit here](https://github.com/mikeinspace/stamps/commit/a04461c541cd3eb3c0fcc59eff0f16c24911c014).

- 💬 Join the community in the [Bitcoin Stamps Telegram chat](https://t.me/BitcoinStamps)
- 🌐 Explore the protocol at [stampchain.io](https://stampchain.io/)
- 📚 Find developer API docs at [stampchain.io/docs](https://stampchain.io/docs)

## 🔶 Bitcoin Stamps - Immutable Digital Assets on Bitcoin

The Bitcoin Stamps meta-protocol offers a comprehensive suite of sub-protocols built on Bitcoin,
all designed with immutability at their core. Each protocol serves a unique purpose while
maintaining the security and permanence of the Bitcoin network:

### 🏛️ CLASSIC STAMPS
Immutable digital collectibles with built-in token functionality via Counterparty standards.
While originally intended for 1:1 editions, creators can issue up to 4,294,967,295 editions per Stamp.

Initially implemented using OP_MULTISIG transactions with Base64 encoded images, Classic Stamps
now also support the OLGA P2WSH transaction format for up to 65kb per transaction. This design
directly addresses the accidental spending vulnerability and prunability issues found in Ordinals.

**History**: The first Official Bitcoin Stamp (Stamp 0) was created by Mikeinspace in
Block 779652.

### 💰 SRC-20 STAMPS
A fair, accessible fungible token protocol where users only pay standard BTC
miner fees. Inspired by BRC-20 but enhanced with the immutability guarantees of Stamps.

**History**: The first SRC-20 Token, "KEVIN," was deployed by Reinamora in Block 788041.

### 🖼️ SRC-721 STAMPS
An advanced NFT format that uses JSON manifests to construct complex, layered images from data
distributed across multiple Stamps. This ingenious approach enables high-resolution artworks
while maintaining compatibility with Counterparty's token layer.

**History**: First implemented in Block 792370.

### ⚡ OLGA STAMPS
A technical breakthrough that eliminates Base64 encoding overhead, reducing
transaction size by 50% and lowering costs by 60-70% compared to the original OP_MULTISIG format.
OLGA maintains full functionality while being significantly more efficient.

**History**: First deployed in Block 833000 and now the standard for new Classic Stamps.

### 🔄 SRC-721r STAMPS
The next evolution of SRC-721, enabling complex recursive images created using
JavaScript and other libraries stored directly on Stamps. By recursively combining multiple Stamps,
creators can build experiences with virtually unlimited file sizes.

### 🌐 SRC-101 STAMPS
A domain name system native to Bitcoin Stamps, developed by [bitname.pro](https://bitname.pro/)

> **Core principle**: Unlike Ordinals, Bitcoin Stamps operate directly on the UTXO set to ensure true immutability.
> This fundamental design choice makes it impossible to accidentally spend or "inscribe" a Stamp.

## 🤝 Contributions

The Bitcoin Stamps protocol is open source and community-driven. 
If you have ideas, improvements, or bug fixes, please submit
a pull request or open an issue.

## 💎 Donate

Bitcoin Stamps is community-funded and currently maintained by Reinamora137.

Donations directly support maintenance, development, and hosting costs 
for the stampchain.io infrastructure. 

**Bitcoin Stamps Dev Fund**: `bc1qe5sz3mt4a3e57n8e39pprval4qe0xdrkzew203`

SRC-20 (KEVIN) tokens or BTC donations are greatly appreciated and serve
as the primary funding source for this experimental project.

## 🚀 Installation

### Requirements:

- 🔗 Local full BTC Node or an account with [Quicknode.com](https://www.quicknode.com/) (free tier is sufficient)
- 🗄️ MySQL Database or default MySQL installation from the provided Docker setup
- 🐍 Python 3.10 or higher
- 💡 RECOMMENDED: Local Counterparty Node (optional but recommended for production)

For a simple Docker-based installation of the Bitcoin Node and Counterparty stack, see:
[Setting up a Counterparty Node](https://docs.counterparty.io/docs/basics/getting-started/)

The default configuration uses the public [Counterparty.io API](https://api.counterparty.io/)
and Stampchain.io Counterparty APIs for XCP asset data. For production use, we strongly recommend 
running a local Counterparty node to reduce dependency on public resources.

### 🐳 Installation & Execution with Docker

If you don't have Docker installed, follow the official Docker installation guide:
[Install Docker Engine](https://docs.docker.com/engine/install/) for your platform.

#### Clone the repo and switch to the main production branch

```shell
git clone https://github.com/stampchain-io/btc_stamps.git
git switch main
```

#### Step 1: Create & configure the env files

Create these three environment files from the provided templates:

- `/app/.env.sample` - Explorer application environment variables [if submodule installed]
- `/docker/.env.mysql.sample` - MySQL environment variables
- `indexer/.env.sample` - Indexer environment variables

Copy the sample files:

```shell
cp app/.env.sample app/.env
cp docker/.env.mysql.sample docker/.env.mysql
cp indexer/.env.sample indexer/.env
```

#### Step 2: Run the stack

Choose one of these methods to run the services:

##### Option 1: Using docker-compose commands

```shell
# Start all services
cd docker && docker-compose up -d

# View indexer logs
docker-compose logs -f indexer

# Shutdown services
docker-compose down
```

##### Option 2: Using make commands

```shell
# Start the stack
make dup

# View logs
make logs

# Shutdown services
make down

# Shutdown and clean volumes
make fdown
```

#### Development Container Management

The indexer includes a flexible container management system for development and testing:

```shell
cd indexer

# Run local development build (outputs to log files)
./run-container.sh --build

# Run specific Docker Hub version with local MySQL
./run-container.sh --image 1.8.26  # or --image dev

# Run with logs to stdout (ideal for testing)
./run-container.sh --image dev --prod

# Run detached in background
./run-container.sh --image dev --detach

# Show all options
./run-container.sh --help
```

**Environment modes:**
- `--dev` (default): Saves logs to local files, ideal for long-running development
- `--prod`: Directs logs to stdout/stderr, better for testing and debugging

**Database connection:**
All modes use the MySQL connection details from your `.env.local` file, so you can test any Docker Hub version against your local database.

> For backward compatibility, the legacy `local-dev.sh` script is still available and delegates to the new unified runner.

#### Quick Testing with Docker Hub Images

For rapid testing without building locally:

1. **Set up environment file:**
```shell
cd indexer
cp .env.sample .env.local
# Edit .env.local with your MySQL and BTC node details
```

2. **Run the latest development version:**
```shell
./run-container.sh --image dev --prod
```

This will:
- Pull the latest dev image from Docker Hub
- Connect to your local MySQL database (specified in .env.local)
- Output logs to stdout for easy debugging
- Use your local Bitcoin node configuration

#### Testing Docker Builds

Before deploying or committing changes to Docker configuration, validate your builds:

```shell
# Run a quick build test without starting services
cd indexer
./run-container.sh --test
```

This will:
- Build a test image
- Verify it can run properly
- Clean up after testing
- Exit with status code 0 on success or 1 on failure

The `--test` option is ideal for CI pipelines and pre-commit validation.

#### Troubleshooting Container Issues

If you encounter problems with container execution:

1. **Verify database connection:**
   The container connects to the MySQL server based on your .env.local file. Make sure your database is accessible at the address specified by `RDS_HOSTNAME`.

2. **Test with production mode:**
   ```shell
   ./run-container.sh --image dev --prod
   ```
   This outputs logs directly to the console, making it easier to identify errors.

3. **Clean up Docker resources:**
   ```shell
   ./run-container.sh --cleanup
   ```
   This removes all containers, volumes, and images related to the project.

4. **Check container logs:**
   ```shell
   docker logs indexer-local-indexer-1
   ```

5. **Verify network mode:**
   If using host mode (default), ensure your local services are available on localhost.
   If your services are on different hosts, try bridge mode:
   ```shell
   ./run-container.sh --image dev --bridge
   ```

### 💻 Local Execution without Docker

Configure environment variables for MySQL, Bitcoin Node, and Counterparty in the `.env` file.

Before installing Python dependencies, install system requirements:

```shell
sudo apt-get update
sudo apt-get install libgmp-dev
```

Install Poetry:

```shell
curl -sSL https://install.python-poetry.org | python3 - --version 2.1.1
```

Install dependencies and build the Rust parser:

```shell
cd indexer
poetry install --only main

# Build the high-performance Rust parser
poetry run task build
```

Run the indexer:

```shell
poetry run indexer
```

## 🧪 Development Workflow

For development, follow these steps:

1. **Install Development Dependencies**:
```shell
poetry install  # Installs all dependencies including dev tools
```

2. **Run Code Quality Checks**:
```shell
# Run all checks (code quality, Rust parser, integration tests)
poetry run run_checks

# Or run specific checks:
poetry run check-code     # Run only code quality checks
poetry run check-rust     # Run only Rust checks
poetry run check-integration  # Run only integration tests
poetry run bandit         # Run security checks with bandit
```

3. **Build Rust Parser During Development**:
```shell
# Using taskipy
poetry run task build-dev  # Development build with debug symbols

# Or directly
cd src/rust_parser
./build.sh  # Builds and verifies the Rust parser
```


## ⚡ Performance Optimization

The indexer features a high-performance Rust-based transaction parser that dramatically improves processing speed:

- 🚀 20-50x faster transaction parsing than pure Python implementation
- 🧠 Efficient memory management
- 🔒 Thread-safe operation with built-in caching
- ⚙️ Parallel batch processing capabilities

The Rust parser is automatically built during installation. To rebuild:

```shell
cd indexer
poetry run task build
```

For development builds with debug symbols:

```shell
cd indexer/src/rust_parser
cargo build
```
## ZMQ Configuration

The indexer can use ZeroMQ (ZMQ) notifications from Bitcoin Core to receive immediate notification of new blocks. This is more efficient than polling for new blocks.

### ZMQ Notification Delay

When a new block is received via ZMQ, the indexer will delay processing it to allow Counterparty to catch up. This delay can be configured with the `ZMQ_NOTIFICATION_DELAY` environment variable (default: 5 seconds).

```bash
# Example: Set ZMQ notification delay to 10 seconds
export ZMQ_NOTIFICATION_DELAY=10.0
```

This delay helps prevent 404 errors when fetching new blocks from the Counterparty API, as it gives Counterparty time to process the new block before the indexer tries to fetch it.


