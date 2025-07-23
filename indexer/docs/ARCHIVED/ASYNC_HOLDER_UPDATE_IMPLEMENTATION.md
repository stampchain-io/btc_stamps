# Async Holder Update Implementation Plan

## Overview

This document outlines the implementation plan for a performant async holder count update system that won't interfere with main block processing.

## Architecture Overview

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ Block Processor │────▶│ Update Scheduler │────▶│ Priority Queue  │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                           │
                        ┌──────────────────┐               │
                        │ Circuit Breaker  │◀──────────────┤
                        └──────────────────┘               │
                                                           ▼
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Cache Layer   │◀────│  Update Worker   │◀────│ Task Processor  │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                │
                                ▼
                        ┌──────────────────┐
                        │    Database      │
                        └──────────────────┘
```

## Key Components

### 1. **Update Scheduler** (`schedule_holder_updates`)
- Tracks tokens affected by operations in each block
- Creates update tasks with appropriate priority levels
- Ensures no duplicate tasks for the same tokens

### 2. **Priority Queue System**
- **HIGH**: Tokens with recent transactions (process immediately)
- **MEDIUM**: Periodic refresh updates (process within 5 minutes)
- **LOW**: Initial population/catchup (process when queue is idle)

### 3. **Circuit Breaker**
- Prevents cascading failures when database is under load
- Opens after 3 consecutive failures
- Resets after 5 minutes of cool-down

### 4. **Cache Layer**
- In-memory cache with 5-minute TTL
- Reduces database reads for frequently accessed tokens
- Serves API requests during update operations

### 5. **Optimized Query Strategy**
- Use `READ UNCOMMITTED` for SELECT queries to avoid locks
- Process updates in batches of 5 tokens
- Individual UPDATE statements per token (not bulk updates)
- 10-second query timeout to prevent long-running queries

## Implementation Steps

### Phase 1: Core Infrastructure (Immediate)

1. **Add Database Index**
   ```sql
   CREATE INDEX idx_balances_tick_amt ON balances(tick, amt);
   CREATE INDEX idx_src20_market_data_tick_updated ON src20_market_data(tick, last_updated);
   ```

2. **Deploy Optimized Holder Updater**
   - Replace `async_holder_updater.py` with `optimized_holder_updater.py`
   - Update imports in `blocks.py` and `server.py`

3. **Configure Environment Variables**
   ```bash
   HOLDER_UPDATE_BATCH_SIZE=5
   HOLDER_UPDATE_QUERY_TIMEOUT=10
   HOLDER_UPDATE_CACHE_TTL=300
   HOLDER_UPDATE_MAX_QUEUE_SIZE=1000
   ```

### Phase 2: Integration (This Week)

1. **Update Block Processor**
   ```python
   # In blocks.py finalize_block():
   if block_index % 10 == 0:  # Every 10 blocks
       holder_updater.schedule_update(
           block_index, 
           UpdatePriority.HIGH
       )
   ```

2. **Add Monitoring Endpoints**
   - Queue size monitoring
   - Circuit breaker status
   - Cache hit rate
   - Average update latency

3. **Implement Gradual Catchup**
   ```python
   # Separate background job for initial population
   def catchup_holder_counts():
       tokens_without_data = get_tokens_missing_holder_data()
       for batch in chunks(tokens_without_data, 50):
           schedule_update(batch, UpdatePriority.LOW)
           time.sleep(1)  # Rate limit
   ```

### Phase 3: Advanced Optimizations (Next Sprint)

1. **Read Replica Support**
   - Route holder count SELECTs to read replicas
   - Keep writes on primary database

2. **Materialized View Alternative**
   ```sql
   CREATE TABLE token_holder_summary (
       tick VARCHAR(20) PRIMARY KEY,
       holder_count INT,
       total_minted BIGINT,
       progress_percentage DECIMAL(5,2),
       last_block_updated INT,
       updated_at TIMESTAMP
   );
   ```

3. **Event-Driven Updates**
   - Trigger updates only on balance-changing operations
   - Use database triggers or application-level events

## Configuration Recommendations

### For Testing
```bash
ENABLE_ASYNC_HOLDER_UPDATES=true
HOLDER_UPDATE_BATCH_SIZE=2
HOLDER_UPDATE_PRIORITY_HIGH_ONLY=true
HOLDER_UPDATE_DRY_RUN=true
```

### For Production (After Testing)
```bash
ENABLE_ASYNC_HOLDER_UPDATES=true
HOLDER_UPDATE_BATCH_SIZE=5
HOLDER_UPDATE_QUERY_TIMEOUT=10
HOLDER_UPDATE_CIRCUIT_BREAKER_THRESHOLD=3
HOLDER_UPDATE_MAX_QUEUE_SIZE=1000
```

## Performance Targets

| Metric | Current | Target |
|--------|---------|--------|
| Single token update | 5-15s | <100ms |
| Batch update (5 tokens) | 30-60s | <500ms |
| Queue processing rate | N/A | 60 tokens/minute |
| Block processing impact | Blocking | <50ms delay |
| API response during updates | Timeout | <100ms (from cache) |

## Monitoring and Alerts

1. **Key Metrics**
   - Queue depth > 500: Warning
   - Queue depth > 800: Critical
   - Circuit breaker open: Alert
   - Update latency > 5s: Warning
   - Cache hit rate < 50%: Info

2. **Dashboards**
   - Real-time queue depth
   - Update latency percentiles
   - Tokens updated per minute
   - Circuit breaker state history

## Rollback Plan

1. Set `ENABLE_ASYNC_HOLDER_UPDATES=false`
2. Restart indexer
3. Run manual holder count update if needed
4. Monitor for lock timeouts

## Testing Strategy

1. **Unit Tests**
   - Circuit breaker behavior
   - Priority queue ordering
   - Cache expiration

2. **Integration Tests**
   - Concurrent updates
   - Lock timeout handling
   - Graceful shutdown

3. **Load Tests**
   - 1000 tokens in queue
   - Sustained update rate
   - Database under load

## Success Criteria

- [ ] No lock wait timeouts during normal operation
- [ ] Block processing continues uninterrupted
- [ ] 95% of updates complete within 1 second
- [ ] API responses served from cache during updates
- [ ] Graceful degradation under heavy load