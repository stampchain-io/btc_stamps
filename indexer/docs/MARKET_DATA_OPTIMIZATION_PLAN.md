# Market Data Scheduler Optimization Plan

## Implementation Status

✅ **Phase 1 Complete**: Background coordinator integrated with all heavy operations
✅ **Phase 2 Complete**: Environment variables added for all configuration
🔄 **Phase 3 In Progress**: Ready for testing with optimized settings

## Current State Analysis

### Problems Identified:
1. **No Coordination**: Market data, sales history, and holder updates can run simultaneously
2. **Large Batch Sizes**: Processing 10,000 stamps / 1,000 tokens at once
3. **Long Transactions**: No intermediate commits during processing
4. **Resource Contention**: Multiple systems updating same tables
5. **Memory Issues**: Loading thousands of records into memory

### Systems That Need Coordination:
1. **Market Data Scheduler** (stamps, SRC-20, collections)
2. **Sales History Processor** (dispenser sales)
3. **Async Holder Updater** (holder counts, progress)
4. **Background Validator** (SRC-20 validation)

## Optimization Strategy

### Phase 1: Integrate Background Coordinator
1. **Wrap all background tasks** with coordinator checks
2. **Define task priorities** and exclusion rules
3. **Implement proper error handling** and task cleanup

### Phase 2: Optimize Market Data Jobs
1. **Reduce batch sizes** for memory efficiency
2. **Add chunked processing** with intermediate commits
3. **Implement progressive delays** based on system load
4. **Add circuit breakers** for API failures

### Phase 3: Smart Scheduling
1. **Stagger job execution** to avoid overlaps
2. **Prioritize based on data freshness** needs
3. **Skip unnecessary updates** for inactive assets

## Implementation Plan

### 1. Background Coordinator Integration

```python
# Add to market_data_jobs.py
from index_core.background_coordinator import BackgroundCoordinator

def _update_stamp_market_data_job(self):
    coordinator = BackgroundCoordinator.get_instance()
    
    # Check if we can start
    if not coordinator.start_task('market_data_stamps', is_heavy=True):
        logger.info("Skipping stamp market data update - another heavy task is running")
        return
    
    try:
        # Existing logic with optimizations
        self._update_stamp_market_data_optimized()
    finally:
        coordinator.end_task('market_data_stamps', is_heavy=True)
```

### 2. Chunked Processing Implementation

```python
def _update_stamp_market_data_optimized(self):
    # Configuration
    CHUNK_SIZE = 100  # Process 100 stamps at a time
    COMMIT_INTERVAL = 50  # Commit every 50 stamps
    
    # Get stamps needing updates
    stamps = self._get_stamps_needing_update(limit=1000)  # Reduced from 10000
    
    # Process in chunks
    for i in range(0, len(stamps), CHUNK_SIZE):
        chunk = stamps[i:i + CHUNK_SIZE]
        
        # Check if we should continue
        if self._should_pause_processing():
            logger.info("Pausing market data update due to system load")
            break
            
        # Process chunk
        self._process_stamp_chunk(chunk, commit_interval=COMMIT_INTERVAL)
        
        # Small delay between chunks
        time.sleep(0.5)
```

### 3. Load-Based Pausing

```python
def _should_pause_processing(self):
    """Check if we should pause based on system load"""
    # Check database connection pool
    if self.db_manager.get_active_connections() > 30:
        return True
        
    # Check if main indexer is behind
    if self._is_indexer_behind():
        return True
        
    # Check memory usage
    if self._get_memory_usage() > 70:
        return True
        
    return False
```

### 4. Priority-Based Updates

```python
def _get_stamps_needing_update(self, limit=1000):
    """Get stamps prioritized by activity and staleness"""
    query = """
    SELECT cpid, last_updated 
    FROM stamp_market_data
    WHERE 
        -- Prioritize active stamps
        (activity_level IN ('HOT', 'ACTIVE') 
         AND last_updated < DATE_SUB(NOW(), INTERVAL 5 MINUTE))
        OR
        -- Update warm stamps less frequently
        (activity_level = 'WARM' 
         AND last_updated < DATE_SUB(NOW(), INTERVAL 15 MINUTE))
        OR
        -- Update cold stamps rarely
        (activity_level = 'COLD' 
         AND last_updated < DATE_SUB(NOW(), INTERVAL 1 HOUR))
    ORDER BY 
        CASE activity_level
            WHEN 'HOT' THEN 1
            WHEN 'ACTIVE' THEN 2
            WHEN 'WARM' THEN 3
            WHEN 'COLD' THEN 4
        END,
        last_updated ASC
    LIMIT %s
    """
```

## Configuration Changes

### Environment Variables (Implemented):
```bash
# Market Data Scheduler Configuration
ENABLE_MARKET_DATA_SCHEDULER=true           # Enable/disable the scheduler

# Update intervals (seconds)
MARKET_DATA_STAMP_UPDATE_INTERVAL=900       # 15 minutes
MARKET_DATA_SRC20_UPDATE_INTERVAL=300       # 5 minutes  
MARKET_DATA_COLLECTION_UPDATE_INTERVAL=1800 # 30 minutes
MARKET_DATA_HOLDER_UPDATE_INTERVAL=300      # 5 minutes

# Batch sizes (items per batch)
MARKET_DATA_STAMP_BATCH_SIZE=50            # Reduced from 100
MARKET_DATA_SRC20_BATCH_SIZE=25            # Reduced from 50

# Selection limits (items per cycle)
MARKET_DATA_STAMP_SELECTION_LIMIT=500      # Reduced from 10000
MARKET_DATA_SRC20_SELECTION_LIMIT=150      # Reduced from 1000

# Database commit frequency
MARKET_DATA_COMMIT_CHUNK_SIZE=10           # Commit every 10 updates

# Performance tuning
MARKET_DATA_MAX_WORKERS=3                  # Thread pool size
MARKET_DATA_RATE_LIMIT=1.5                 # Requests per second
```

### Timing Adjustments:
```python
# Stagger job execution to avoid overlaps
STAMP_UPDATE_INTERVAL = 900          # 15 minutes (keep)
SRC20_UPDATE_INTERVAL = 450          # 7.5 minutes (offset from stamps)
COLLECTION_UPDATE_INTERVAL = 1800    # 30 minutes (keep)
```

## Testing Plan

### Phase 1: Isolated Testing
1. Test background coordinator with mock tasks
2. Verify task exclusion rules work correctly
3. Test error handling and cleanup

### Phase 2: Integration Testing
1. Enable one job at a time with small limits
2. Monitor database locks and connections
3. Check memory usage patterns

### Phase 3: Load Testing
1. Gradually increase limits
2. Run all jobs concurrently
3. Monitor for lock timeouts

## Monitoring

### Key Metrics:
1. **Database Connections**: Should stay below 35
2. **Lock Wait Time**: Should be <1 second average
3. **Memory Usage**: Should stay below 80%
4. **API Rate Limits**: Should not exceed 1.5 req/sec
5. **Update Latency**: HOT stamps <10 min, COLD stamps <2 hours

### Alert Thresholds:
- Database connections > 35: Pause heavy tasks
- Lock timeouts > 5 in 1 minute: Stop all updates
- Memory > 80%: Trigger garbage collection
- API errors > 10 consecutive: Circuit breaker

## Rollback Plan

If issues occur:
1. Set `ENABLE_MARKET_DATA_SCHEDULER=false`
2. Clear any stuck locks: `SHOW PROCESSLIST` and kill long queries
3. Reset coordinator state
4. Review logs for root cause

## Success Criteria

1. **No lock timeouts** during normal operation
2. **HOT stamps updated** within 10 minutes
3. **Database connections** stay below 35
4. **Memory usage** stable below 70%
5. **All systems coexist** without conflicts