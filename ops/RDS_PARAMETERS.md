# RDS Parameter Parity

Production RDS (`stamps-mysql-8-4` parameter group) and local Docker MySQL
must share the same MySQL tuning so that dev/CI behavior matches prod and
operations like `OPTIMIZE TABLE` don't hit a quiet behavioral gap.

## Parameters

| Parameter | Value | Notes |
| --- | --- | --- |
| `innodb_buffer_pool_size` | `3G` | Set in Docker compose; on RDS this is sized by instance class. |
| `tmp_table_size` | `268435456` (256 MB) | Covers observed temp-table spikes from `OPTIMIZE TABLE stamp_holder_cache`. |
| `max_heap_table_size` | `268435456` (256 MB) | Must equal `tmp_table_size` — MySQL caps in-memory temp tables to the smaller of the two. |

## Where they are configured

- **Production (RDS)**: parameter group `stamps-mysql-8-4`. Both parameters
  are dynamic; `ApplyMethod=immediate` works, no reboot required.
- **Local / dev**: passed as MySQL command-line flags in:
  - `docker-compose.local.yml`
  - `indexer/docker-compose.local.yml`
  - `docker/docker-compose.yml`

## Operational alarms

The `stampminter` SNS topic
(`arn:aws:sns:us-east-1:947253282047:stampminter`) receives SMS + email for
existing RDS alarms. New alarms added in this PR:

- `stamps-4-storage-low` — `FreeStorageSpace` < 10 GB
- `stamps-4-database-connections-very-high` — `DatabaseConnections` > 500

These complement the existing `stamps-4-database-connections-high` (>400)
alarm to give earlier warning of pool-exhaustion incidents.

## Maintenance follow-up

After parameter group update, run `OPTIMIZE TABLE stamp_holder_cache`
during a maintenance window to reclaim ~3.4 GB of unused space.
