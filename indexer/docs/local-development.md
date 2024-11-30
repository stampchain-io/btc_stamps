# Local Development Setup

This document describes how to set up and run the BTC Stamps Indexer in a local development environment using Docker.

## Quick Start

```bash
# Start with default configuration (host networking)
./local-dev.sh

# Start with local MySQL database
./local-dev.sh --with-db
```

## Environment Configuration

### Default Environment Variables (.env.local)

The script automatically creates a `.env.local` file with these defaults if it doesn't exist:

```bash
RDS_DATABASE=btc_stamps
RDS_USER=btc_stamps
RDS_PASSWORD=password
DOCKER_CONTAINER=1
```

### Additional Environment Variables

The following environment variables can be configured in your `.env.local`:

| Variable | Description | Default |
|----------|-------------|---------|
| `RDS_HOSTNAME` | MySQL host address | `localhost` |
| `RDS_DATABASE` | Database name | `btc_stamps` |
| `RDS_USER` | Database user | `btc_stamps` |
| `RDS_PASSWORD` | Database password | `password` |
| `QUICKNODE_URL` | QuickNode API URL | - |
| `RPC_TOKEN` | RPC authentication token | - |
| `RPC_IP` | RPC server IP | - |
| `RPC_USER` | RPC username | `rpc` |
| `RPC_PASSWORD` | RPC password | `rpc` |
| `BACKEND_POLL_INTERVAL` | Poll interval in seconds | `0.5` |
| `DEBUG` | Enable debug mode | `1` |

## Docker Services

### Indexer Service

The main application service with the following configuration:

- Image: `btc_stamps/indexer:local-dev`
- Network Mode: Configurable (host/bridge)
- Volumes:
  - `./logs:/app/logs` - Application logs
  - `../files:/usr/src/app/files` - Data files

### MySQL Service (Optional)

NOTE: A SQL server connection on the local or remote suck as AWS RDS is REQUIRED. This container is optional.
Local MySQL database service:

- Image: `mysql:8.4.0`
- Port: `3306`
- Volumes:
  - `./db_data:/var/lib/mysql` - Persistent data
  - `./table_schema.sql:/docker-entrypoint-initdb.d/table_schema.sql` - Schema initialization

## Command Line Options

The `local-dev.sh` script supports several options:

| Option | Description |
|--------|-------------|
| `--with-db` | Start with local MySQL container |
| `--bridge` | Use bridge networking instead of host networking |
| `--detach` | Run containers in the background |
| `--build` | Force rebuild of Docker images |
| `--test` | Run tests only |
| `--cleanup` | Clean up local development environment |
| `-h, --help` | Show help message |

### Examples

```bash
# Start with local database in detached mode
./local-dev.sh --with-db --detach

# Force rebuild and use bridge networking
./local-dev.sh --build --bridge

# Clean up local environment
./local-dev.sh --cleanup
```

## Networking

The application supports two networking modes:

1. **Host Network** (Default)
   - Direct access to host network interfaces
   - Better performance for local development
   - Use `localhost` to access services

2. **Bridge Network**
   - Isolated container network
   - More similar to production environment
   - Use container names as hostnames

To switch to bridge networking:

```bash
./local-dev.sh --bridge
```

## Logs

- Docker container logs are directed to stdout/stderr
- Local development logs are stored in `./logs/indexer.log`
- Debug mode can be enabled via the `DEBUG=1` environment variable

## Development Workflow

1. Start the environment:
   ```bash
   ./local-dev.sh --with-db
   ```

2. Monitor logs:
   ```bash
   docker compose -f docker-compose.local.yml logs -f
   ```

3. Clean up when done:
   ```bash
   ./local-dev.sh --cleanup
   ```

## Troubleshooting

1. **Database Connection Issues**
   - Verify MySQL is running: `docker compose -f docker-compose.local.yml ps`
   - Check credentials in `.env.local`
   - Ensure correct networking mode is selected

2. **Permission Issues**
   - Ensure `logs` directory is writable
   - Check file ownership in mounted volumes

3. **Network Issues**
   - Try switching between host and bridge networking
   - Verify port conflicts on host machine