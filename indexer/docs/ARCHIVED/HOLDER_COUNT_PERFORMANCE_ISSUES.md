# Bitcoin Stamps Indexer - Holder Count Performance Issues

## Executive Summary

The indexer is experiencing severe performance issues due to holder count and progress percentage update queries causing database lock timeouts. These queries are blocking the main block processing, preventing the indexer from catching up to the chain tip.

## Critical Issues Identified

### 0. CRITICAL BUG FOUND: Synchronous Holder Updates Still Running
- **Problem**: Despite disabling async holder updates, the main block processing was still calling `holder_updater.update_holder_counts()` synchronously in `finalize_block()`
- **Impact**: This was the root cause of continued lock wait timeouts even after disabling all background jobs
- **Fix Applied**: Commented out the synchronous holder update code in `blocks.py` lines 1250-1269

## Critical Issues Identified

### 1. Long-Running Holder Count UPDATE Queries
- **Problem**: Holder count UPDATE queries are taking 5-15+ minutes to complete
- **Impact**: Blocking all other database operations, causing cascading lock wait timeouts
- **Root Cause**: The queries are joining the entire `balances` table with `SRC20Valid` and updating `src20_market_data` for large sets of tokens at once

Example problematic query:
```sql
UPDATE src20_market_data smd
JOIN (
    SELECT
        b.tick,
        COUNT(DISTINCT b.address) as holder_count,
        COALESCE(SUM(b.amt), 0) as total_minted,
        ROUND(COALESCE(SUM(b.amt), 0) / NULLIF(d.max, 0) * 100, 2) as progress_percentage
    FROM balances b
    LEFT JOIN SRC20Valid d ON d.tick = b.tick AND d.op = 'DEPLOY'
    WHERE b.tick IN (/* many tokens */)
    AND b.amt > 0
    GROUP BY b.tick, d.max
) counts ON smd.tick = counts.tick
SET
    smd.holder_count = counts.holder_count,
    smd.total_minted = counts.total_minted,
    smd.progress_percentage = COALESCE(counts.progress_percentage, 0),
    smd.last_updated = NOW()
```

### 2. Multiple Competing Update Processes
- **Holder Count Catchup Job**: Tries to update ALL tokens with missing data in force mode
- **Async Holder Updater**: Updates tokens affected by each block
- **Market Data Jobs**: Also trying to update market data
- **Sales History Processor**: Processing large batches of dispenses

All are competing for locks on the same tables.

### 3. Sales History Processor Overload
- Fetching 10,000 dispenses at a time
- Processing 1,435 stamp dispenses in large batches
- Buffer flushes taking 40+ seconds, blocking other operations

### 4. Inefficient Query Patterns
- No proper indexing strategy for holder count calculations
- Full table scans on `balances` table (258,000+ rows)
- No query optimization for batch updates

## Temporary Mitigations Applied

1. **Disabled Market Data Scheduler**: `ENABLE_MARKET_DATA_SCHEDULER=false`
2. **Disabled Sales History Catchup**: `ENABLE_SALES_HISTORY_CATCHUP=false`
3. **Disabled SRC20 Background Validation**: `ENABLE_SRC20_BACKGROUND_VALIDATION=false`
4. **Disabled Async Holder Updates**: `ENABLE_ASYNC_HOLDER_UPDATES=false`
5. **Reduced Sales History Buffer Size**: From 1,000 to 100 records
6. **Added Lock Prevention**: Threading lock to prevent concurrent holder updates

## Recommended Solutions

### Immediate Actions (Priority 1)
1. **Kill All Long-Running Queries**
   ```sql
   -- Find stuck queries
   SELECT ID, TIME, LEFT(INFO, 200) AS QUERY 
   FROM INFORMATION_SCHEMA.PROCESSLIST 
   WHERE DB='btc_stamps' AND TIME > 60;
   
   -- Kill them
   KILL <query_id>;
   ```

2. **Run Indexer in Minimal Mode**
   - Focus only on block processing
   - Disable all background jobs
   - Let it catch up to chain tip first

### Short-Term Fixes (Priority 2)
1. **Optimize Holder Count Query**
   - Add composite index: `CREATE INDEX idx_balances_tick_amt ON balances(tick, amt);`
   - Process tokens in smaller batches (5-10 at a time)
   - Use READ UNCOMMITTED isolation level for holder count reads

2. **Implement Incremental Updates**
   - Only update tokens that had transactions in the current block
   - Cache holder counts in memory/Redis
   - Update database periodically, not on every block

3. **Separate Read/Write Concerns**
   - Use read replicas for holder count calculations
   - Write updates in batches during low-activity periods

### Long-Term Solutions (Priority 3)
1. **Redesign Holder Count Architecture**
   - Maintain a separate `token_holder_counts` table
   - Update incrementally on balance changes
   - Use database triggers or event sourcing

2. **Implement Proper Queue Management**
   - Use a proper job queue (Redis/RabbitMQ) instead of in-memory
   - Prioritize block processing over market data updates
   - Implement circuit breakers for long-running queries

3. **Database Optimization**
   - Partition `balances` table by token tick
   - Use materialized views for holder counts
   - Implement proper connection pooling with query timeouts

## Performance Benchmarks

Current problematic performance:
- Holder count update for all tokens: 10-15 minutes
- Sales history buffer flush (1,435 records): 40+ seconds
- Block processing when blocked: Lock wait timeout after 50 seconds

Target performance:
- Holder count update per token: <100ms
- Sales history buffer flush (100 records): <1 second
- Block processing: <2 seconds per block

## Configuration Recommendations

For production catch-up mode:
```bash
ENABLE_MARKET_DATA_SCHEDULER=false
ENABLE_SALES_HISTORY_CATCHUP=false
ENABLE_SRC20_BACKGROUND_VALIDATION=false
ENABLE_ASYNC_HOLDER_UPDATES=false
DB_POOL_TIMEOUT=30  # Reduce from 120
```

For normal operation (after optimization):
```bash
ENABLE_MARKET_DATA_SCHEDULER=true
ENABLE_SALES_HISTORY_CATCHUP=true
ENABLE_SRC20_BACKGROUND_VALIDATION=true
ENABLE_ASYNC_HOLDER_UPDATES=true
HOLDER_UPDATE_BATCH_SIZE=5
HOLDER_UPDATE_INTERVAL=300  # 5 minutes
```

## Monitoring and Alerting

Add monitoring for:
1. Query execution time > 30 seconds
2. Lock wait timeouts
3. Database connection pool exhaustion
4. Block processing lag > 100 blocks

## Next Steps

1. **Immediate**: Keep all background jobs disabled until caught up
2. **This Week**: Implement query optimizations and smaller batch sizes
3. **Next Sprint**: Redesign holder count architecture for scalability
4. **Future**: Consider moving to a more scalable database solution for analytics queries