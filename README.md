<div align="center">
  <img src="docs/assets/stampchain-hero.jpg" alt="Bitcoin Stamps" width="100%">

  # Bitcoin Stamps

  ### The official indexer for the Bitcoin Stamps meta-protocol: immutable digital assets stored directly in Bitcoin's UTXO set

  **SRC-20 / SRC-721 / OLGA / SRC-721r / SRC-101**

  [![Code Quality & Unit Tests](https://img.shields.io/github/actions/workflow/status/stampchain-io/btc_stamps/python-check.yml?label=Code%20Quality&job=code-quality&branch=main)](https://github.com/stampchain-io/btc_stamps/actions/workflows/python-check.yml) [![Rust Checks](https://img.shields.io/github/actions/workflow/status/stampchain-io/btc_stamps/python-check.yml?label=Rust%20Checks&job=rust&branch=main)](https://github.com/stampchain-io/btc_stamps/actions/workflows/python-check.yml) [![Integration Tests](https://img.shields.io/github/actions/workflow/status/stampchain-io/btc_stamps/python-check.yml?label=Integration&job=integration&branch=main)](https://github.com/stampchain-io/btc_stamps/actions/workflows/python-check.yml) [![Coverage Analysis](https://img.shields.io/github/actions/workflow/status/stampchain-io/btc_stamps/coverage.yml?label=Coverage&branch=main)](https://github.com/stampchain-io/btc_stamps/actions/workflows/coverage.yml) [![codecov](https://codecov.io/gh/stampchain-io/btc_stamps/graph/badge.svg?token=OB2OS37L5H)](https://codecov.io/gh/stampchain-io/btc_stamps)
 [![Docker Build](https://img.shields.io/github/actions/workflow/status/stampchain-io/btc_stamps/docker-auto-publish.yml?label=Docker%20Build&branch=main)](https://github.com/stampchain-io/btc_stamps/actions/workflows/docker-auto-publish.yml)

  [![Last Commit](https://img.shields.io/github/last-commit/stampchain-io/btc_stamps)](https://github.com/stampchain-io/btc_stamps) [![Python Versions](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)](https://www.python.org/) [![License](https://img.shields.io/github/license/stampchain-io/btc_stamps)](LICENSE) [![Stars](https://img.shields.io/github/stars/stampchain-io/btc_stamps?style=social)](https://github.com/stampchain-io/btc_stamps/stargazers) [![Forks](https://img.shields.io/github/forks/stampchain-io/btc_stamps?style=social)](https://github.com/stampchain-io/btc_stamps/network/members) [![Issues](https://img.shields.io/github/issues/stampchain-io/btc_stamps)](https://github.com/stampchain-io/btc_stamps/issues) [![Pull Requests](https://img.shields.io/github/issues-pr/stampchain-io/btc_stamps)](https://github.com/stampchain-io/btc_stamps/pulls)
</div>

## 📋 Overview

`btc_stamps` is the official indexer for Bitcoin Stamps, a meta-protocol built on Bitcoin
and dedicated to immutability and permanent data storage on the Bitcoin blockchain.
This protocol is experimental and provided without warranty (see [LICENSE](LICENSE)).

The project evolved from a meta-protocol design created by Mikeinspace
([Bitcoin Stamps Github](https://github.com/mikeinspace/stamps)) in February 2023
([initial commit](https://github.com/mikeinspace/stamps/commit/a04461c541cd3eb3c0fcc59eff0f16c24911c014)).
Reinamora137 developed this implementation, which has since become the foundation for the
entire Bitcoin Stamps ecosystem.

> **Core principle**: Unlike Ordinals, Bitcoin Stamps operate directly on the UTXO set to ensure true immutability.
> This fundamental design choice makes it impossible to accidentally spend or "inscribe" a Stamp.

## 🔶 Features: The Bitcoin Stamps Protocol Suite

The Bitcoin Stamps meta-protocol offers a suite of sub-protocols built on Bitcoin, all
designed with immutability at their core:

| Protocol | Purpose | Activation |
|----------|---------|------------|
| 🏛️ **Classic Stamps** | Immutable digital collectibles via Counterparty standards | Block 779,652 |
| 💰 **SRC-20** | Fair-launch fungible tokens, standard BTC miner fees only | Block 788,041 |
| 🖼️ **SRC-721** | Layered NFTs composed from multiple Stamps via JSON manifests | Block 792,370 |
| ⚡ **OLGA** | P2WSH encoding: smaller transactions, 60-70% lower costs | Blocks 833,000 / 865,000 / 940,000 |
| 🔄 **SRC-721r** | Recursive Stamps with JavaScript, virtually unlimited file sizes | Active |
| 🌐 **SRC-101** | Bitcoin-native domain name system | Block 870,652 |

### 🏛️ Classic Stamps
Immutable digital collectibles with built-in token functionality via Counterparty standards.
While originally intended for 1:1 editions, creators can issue up to 4,294,967,295 editions per Stamp.
Initially implemented using OP_MULTISIG transactions with Base64 encoded images, Classic Stamps
now also support the OLGA P2WSH transaction format for up to 65kb per transaction. This design
directly addresses the accidental spending vulnerability and prunability issues found in Ordinals.

**History**: The first Official Bitcoin Stamp (Stamp 0) was created by Mikeinspace in Block 779,652.

### 💰 SRC-20 Stamps
A fair, accessible fungible token protocol where users only pay standard BTC miner fees.
Inspired by BRC-20 but enhanced with the immutability guarantees of Stamps.

**History**: The first SRC-20 Token, "KEVIN," was deployed by Reinamora in Block 788,041
(on Counterparty). SRC-20 moved to direct Bitcoin transactions at Block 793,068 and adopted
the OLGA / P2WSH encoding at Block 865,000.

### 🖼️ SRC-721 Stamps
An advanced NFT format that uses JSON manifests to construct complex, layered images from data
distributed across multiple Stamps. This approach enables high-resolution artworks while
maintaining compatibility with Counterparty's token layer.

**History**: First implemented in Block 792,370.

### ⚡ OLGA Stamps
A technical breakthrough that eliminates Base64 encoding overhead, reducing transaction size
by 50% and lowering costs by 60-70% compared to the original OP_MULTISIG format. OLGA
maintains full functionality while being significantly more efficient.

**History**: OLGA activated per-protocol: Classic Stamps at Block 833,000, SRC-20 at Block
865,000, and SRC-101 at Block 940,000. It is now the standard for new Classic Stamps.

### 🔄 SRC-721r Stamps
The next evolution of SRC-721, enabling complex recursive images created using JavaScript and
other libraries stored directly on Stamps. By recursively combining multiple Stamps, creators
can build experiences with virtually unlimited file sizes.

### 🌐 SRC-101 Stamps
A domain name system native to Bitcoin Stamps, developed by [bitname.pro](https://bitname.pro/).

## 🚀 Quick Start (Docker)

### Requirements

- 🔗 Local full BTC Node or an account with [Quicknode.com](https://www.quicknode.com/) (free tier is sufficient)
- 🗄️ MySQL Database or default MySQL installation from the provided Docker setup
- 🐍 Python 3.10-3.12 (3.12 recommended). Do not use Python 3.13: it diverges from consensus (tracked in [#871](https://github.com/stampchain-io/btc_stamps/issues/871))
- 💡 RECOMMENDED: Local Counterparty Node (optional but recommended for production)

For a simple Docker-based installation of the Bitcoin Node and Counterparty stack, see:
[Setting up a Counterparty Node](https://docs.counterparty.io/docs/basics/getting-started/)

The default configuration uses the public [Counterparty.io API](https://api.counterparty.io/)
and Stampchain.io Counterparty APIs for XCP asset data. For production use, we strongly
recommend running a local Counterparty node to reduce dependency on public resources.

If you don't have Docker installed, follow the official guide:
[Install Docker Engine](https://docs.docker.com/engine/install/).

### Clone the repo

`main` is the trunk and default branch, so a fresh clone already checks it out:

```shell
git clone https://github.com/stampchain-io/btc_stamps.git
cd btc_stamps
```

For a verified, reproducible deployment, check out a signed release tag (e.g.
`git switch --detach 1.9.1`) and verify its Docker image per
[Signed Releases](#-signed-releases).

### Step 1: Create & configure the env file

The docker stack reads a single env file (`.env.local` by default). Create it
from the template and fill in your Bitcoin node + database details:

```shell
cp .env.example .env.local
# edit .env.local: set RDS_USER / RDS_PASSWORD / RDS_DATABASE and node RPC creds
```

### Step 2: Run the stack

The compose setup uses one canonical base (`docker-compose.yml`) plus overrides:

- **Development (default):** `docker-compose.override.yml` is applied
  automatically and brings up the indexer (on host networking) + a local MySQL
  with persistent `db_data`.
- **Production:** `docker-compose.prod.yml` is selected explicitly and targets a
  managed MySQL (RDS/Aurora) with no local database. (Production currently runs
  natively via systemd; the docker-prod path is not yet deployed.)

```shell
# Development: indexer + local MySQL
docker compose up -d

# View indexer logs
docker compose logs -f indexer

# Stop the stack
docker compose down

# Production overlay (managed RDS/Aurora; not yet deployed)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

The same flows are available via `make` (`make dev`, `make logs`,
`make down`, `make prod`); run `make help` for the full list.

### Development Container Management

The indexer includes a flexible container management system for development and testing:

```shell
cd indexer

# Run local development build (outputs to log files)
./run-container.sh --build

# Run specific Docker Hub version with local MySQL
./run-container.sh --image 1.9.1  # or --image edge (latest main build)

# Run with logs to stdout (ideal for testing)
./run-container.sh --image edge --prod

# Run detached in background
./run-container.sh --image edge --detach

# Show all options
./run-container.sh --help
```

**Environment modes:**

- `--dev` (default): Saves logs to local files, ideal for long-running development
- `--prod`: Directs logs to stdout/stderr, better for testing and debugging

**Database connection:**
All modes use the MySQL connection details from your `.env.local` file, so you can test any
Docker Hub version against your local database.

> For backward compatibility, the legacy `local-dev.sh` script is still available and delegates to the new unified runner.

### Quick Testing with Docker Hub Images

For rapid testing without building locally:

1. **Set up environment file:**
```shell
cd indexer
cp .env.sample .env.local
# Edit .env.local with your MySQL and BTC node details
```

2. **Run the latest pre-release (edge) build:**
```shell
./run-container.sh --image edge --prod
```

This will:

- Pull the latest edge image from Docker Hub (newest main build)
- Connect to your local MySQL database (specified in .env.local)
- Output logs to stdout for easy debugging
- Use your local Bitcoin node configuration

### Testing Docker Builds

Before deploying or committing changes to Docker configuration, validate your builds:

```shell
# Run a quick build test without starting services
cd indexer
./run-container.sh --test
```

This will build a test image, verify it can run properly, clean up after testing, and exit
with status code 0 on success or 1 on failure. The `--test` option is ideal for CI pipelines
and pre-commit validation.

### Troubleshooting Container Issues

If you encounter problems with container execution:

1. **Verify database connection:**
   The container connects to the MySQL server based on your .env.local file. Make sure your database is accessible at the address specified by `RDS_HOSTNAME`.

2. **Test with production mode:**
   ```shell
   ./run-container.sh --image edge --prod
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
   ./run-container.sh --image edge --bridge
   ```

## 💻 Local Execution without Docker

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
poetry run task bandit    # Run security checks with bandit
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

## 📡 ZMQ Configuration

The indexer can use ZeroMQ (ZMQ) notifications from Bitcoin Core to receive immediate
notification of new blocks. This is more efficient than polling for new blocks.

When a new block is received via ZMQ, the indexer delays processing it to allow Counterparty
to catch up. Configure the delay with the `ZMQ_NOTIFICATION_DELAY` environment variable
(default: 5 seconds):

```bash
# Example: Set ZMQ notification delay to 10 seconds
export ZMQ_NOTIFICATION_DELAY=10.0
```

This delay helps prevent 404 errors when fetching new blocks from the Counterparty API,
as it gives Counterparty time to process the new block before the indexer tries to fetch it.

## 📋 Stamps Improvement Proposals (SIPs)

Protocol evolution is governed through community-driven SIPs. See [SIP-0000](https://github.com/stampchain-io/btc_stamps/issues/686) for the full process.

| SIP | Title | Status |
|-----|-------|--------|
| [0001](https://github.com/stampchain-io/btc_stamps/issues/685) | SRC-20 Conditional Transfers (Hashlock/Timelock) | Draft |
| [0002](https://github.com/stampchain-io/btc_stamps/issues/484) | SRC-20 UTXO Binding & Transfer Format v2.0 | Superseded (by 0001) |
| [0003](https://github.com/stampchain-io/btc_stamps/issues/485) | SRC-20 Cross-Chain Bridge Specification | Draft |
| [0004](https://github.com/stampchain-io/btc_stamps/issues/687) | Shielded SRC-20 (Privacy Extension, Phased) | Draft |
| [0005](https://github.com/stampchain-io/btc_stamps/issues/688) | Binary Transfer Format for SRC-20 | Draft |
| [0006](https://github.com/stampchain-io/btc_stamps/issues/689) | Native SRC-20 AMM (Automated Market Maker) | Draft |
| [0007](https://github.com/stampchain-io/btc_stamps/issues/735) | Probabilistic Atomic Swaps for SRC-20 | Draft |
| [0008](https://github.com/stampchain-io/btc_stamps/issues/692) | Dual Transaction Parsing | Draft |
| [0009](https://github.com/stampchain-io/btc_stamps/issues/725) | On-Demand SRC-20 SVG Generation | Draft |
| [0010](https://github.com/stampchain-io/btc_stamps/issues/726) | Decentralised Stamp Relay Network | Draft |
| [0011](https://github.com/stampchain-io/btc_stamps/issues/736) | Batch Operations & State Channels for SRC-20 | Draft |
| [0110](https://github.com/stampchain-io/btc_stamps/issues/878) | Ordinals Provenance Preservation ("Stamp an Inscription") | Draft |

> **SIP-0110** is intentionally numbered to mirror **BIP-110**: where BIP-110 would restrict witness-data inscriptions, SIP-0110 lets Ordinals holders preserve their content on the UTXO set. The 0012-0109 range remains open for normal sequential assignment (see [SIP-0000](https://github.com/stampchain-io/btc_stamps/issues/686)).

Full roadmap and gating criteria: [bitcoinstamps.xyz/en/protocols/sips](https://bitcoinstamps.xyz/en/protocols/sips) | Whitepaper details: [docs/whitepaper/improvement-proposals.md](docs/whitepaper/improvement-proposals.md)

## 📚 Documentation & Links

- 📄 Full protocol documentation at [bitcoinstamps.xyz](https://bitcoinstamps.xyz), the core Bitcoin Stamps protocol site
- 🌐 Explore stamps, tokens, and transactions at [stampchain.io](https://stampchain.io/)
- 📖 Developer API docs at [stampchain.io/docs](https://stampchain.io/docs)
- 📑 [Technical Whitepaper](docs/whitepaper/index.md) for protocol architecture and specifications
- 🗺️ [SIP Roadmap & Registry](https://bitcoinstamps.xyz/en/protocols/sips) for protocol improvement proposals
- 💬 Join the community in the [Bitcoin Stamps Telegram chat](https://t.me/BitcoinStamps)

## 🤝 Contributing

The Bitcoin Stamps protocol is open source and community-driven. If you have ideas,
improvements, or bug fixes, please submit a pull request or open an issue.

This repository follows a **trunk model**: **branch off `main` and open PRs against `main`**
(the single primary branch). Every PR is reviewed by two code owners. Releases are cut by
maintainers via the automated **Cut Release** workflow. See
[`CONTRIBUTING.md`](CONTRIBUTING.md) for the full workflow and
[`docs/dev/versioning.md`](docs/dev/versioning.md) for versioning and the release process.

## 🔏 Signed Releases

Release images published to Docker Hub (`btcstamps/indexer`) are **signed keyless with
[Sigstore/cosign](https://www.sigstore.dev/)** (GitHub Actions OIDC, no private keys) and
carry an SPDX SBOM attestation. Each
[GitHub Release](https://github.com/stampchain-io/btc_stamps/releases) records the exact
`btcstamps/indexer@sha256:…` digest and the `cosign verify` command. To verify provenance
before running an image (substitute the release version and digest):

```bash
cosign verify \
  --certificate-identity-regexp '^https://github.com/stampchain-io/btc_stamps/.github/workflows/docker-auto-publish.yml@refs/tags/X.Y.Z$' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  btcstamps/indexer@sha256:<digest>
```

## 💎 Donate

Bitcoin Stamps is community-funded and currently maintained by Reinamora137. Donations
directly support maintenance, development, and hosting costs for the stampchain.io
infrastructure.

**Bitcoin Stamps Dev Fund**: `bc1qe5sz3mt4a3e57n8e39pprval4qe0xdrkzew203`

SRC-20 (KEVIN) tokens or BTC donations are greatly appreciated and serve as the primary
funding source for this experimental project.

## 📄 License

This project is experimental and provided without warranty. See [LICENSE](LICENSE) for full details.
