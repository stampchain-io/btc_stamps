# Bitcoin Stamps Indexer - Docker Image

[![Docker Build](https://github.com/stampchain-io/btc_stamps/actions/workflows/docker-auto-publish.yml/badge.svg)](https://github.com/stampchain-io/btc_stamps/actions/workflows/docker-auto-publish.yml)

Official Docker image for the Bitcoin Stamps Indexer - the reference implementation for parsing and indexing Bitcoin Stamps meta-protocols on the Bitcoin blockchain.

## Available Tags

- `latest` - Built automatically from the `main` branch
- `dev` - Built automatically from the `dev` branch
- `<sha>` - Built from specific commits (first 7 characters of commit hash)
- `vX.Y.Z` - Stable release versions

## Quick Start

The snippet below is a minimal, self-contained example for running the
published image directly. If you have cloned the repository, prefer the
canonical root Compose files (`docker-compose.yml` + `docker-compose.override.yml`,
with `docker-compose.prod.yml` / `docker-compose.local.yml` overlays) and the
`make` targets instead of maintaining a separate per-indexer compose.

```yml
services:
  db:
    image: mysql:8.4.0
    # ... database configuration ...
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost", "-u", "root", "-p${MYSQL_ROOT_PASSWORD}"]
      interval: 5s
      timeout: 5s
      retries: 5
      start_period: 15s

  indexer:
    image: btcstamps/indexer:latest
    command: poetry run indexer
    volumes:
      - ./files:/usr/src/app/files
    depends_on:
      db:
        condition: service_healthy
    environment:
      - DOCKER_CONTAINER=1
      - RDS_HOSTNAME=db
      - RDS_PORT=3306
      - RDS_DATABASE=btc_stamps
      - RDS_USER=btc_stamps
      - RDS_PASSWORD=your_password
      - BITCOIND_USER=bitcoinrpc
      - BITCOIND_PASSWORD=your_password
      - BITCOIND_HOST=your_bitcoin_node
      - BITCOIND_PORT=8332
```

## System Requirements

- Python 3.10–3.12 (3.12 recommended). **Python 3.13 is not yet consensus-compatible — do not run the indexer on 3.13** (tracked in #871).
- MySQL 8.4.0+
- Bitcoin Core node with RPC access

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `RDS_HOSTNAME` | MySQL host | `localhost` |
| `RDS_PORT` | MySQL port | `3306` |
| `RDS_DATABASE` | MySQL database name | `btc_stamps` |
| `RDS_USER` | MySQL username | `btc_stamps` |
| `RDS_PASSWORD` | MySQL password | - |
| `BITCOIND_USER` | Bitcoin Core RPC username | `bitcoinrpc` |
| `BITCOIND_PASSWORD` | Bitcoin Core RPC password | - |
| `BITCOIND_HOST` | Bitcoin Core host | `localhost` |
| `BITCOIND_PORT` | Bitcoin Core RPC port | `8332` |
| `DOCKER_CONTAINER` | Set to 1 when running in container | `1` |
| `STORE_FILES` | Whether to store files | `1` |
| `DEBUG` | Enable debug mode | `0` |

## Testing Docker Builds

To validate Docker builds before deployment:

```bash
# Run a quick Docker build test without starting services
./run-container.sh --test

# Test with specific configuration
./run-container.sh --build --with-db  # Test with local MySQL
./run-container.sh --image dev --prod  # Test with dev image and stdout logs
```

The `--test` option is ideal for CI pipelines and pre-commit validation.

## More Information

- **Protocol documentation:** [bitcoinstamps.xyz](https://bitcoinstamps.xyz) — the core Bitcoin Stamps protocol site
- **Source & issues:** [GitHub repository](https://github.com/stampchain-io/btc_stamps)
- **Explorer & API:** [stampchain.io](https://stampchain.io/) · [API docs](https://stampchain.io/docs)