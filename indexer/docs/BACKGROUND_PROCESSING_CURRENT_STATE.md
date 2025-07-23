# Background Processing - Current State and Optimization

## Overview

This document consolidates the current state of all background processing systems and the pragmatic approach to optimize them using simple coordination.

## Current Systems

### 1. **Async Holder Updater** ✅ (Implemented & Working)
- **Purpose**: Updates holder counts and progress percentages asynchronously
- **Status**: Enabled via `ENABLE_ASYNC_HOLDER_UPDATES=true`
- **Implementation**: Uses a queue to process updates outside main transaction
- **Risk**: Low - already proven to work without lock timeouts

### 2. **SRC-20 Background Validator** ✅ (Implemented & Working)
- **Purpose**: Validates SRC-20 blocks processed with FORCE=true
- **Status**: Enabled via `ENABLE_SRC20_BACKGROUND_VALIDATION=true`
- **Implementation**: SQLite queue, single-threaded, checks API health
- **Risk**: Low - doesn't touch main MySQL tables during validation

### 3. **Sales History Processor** ✅ (Fixed & Enabled)
- **Purpose**: Fetches and stores dispenser sales data
- **Status**: Enabled via `ENABLE_SALES_HISTORY_CATCHUP=true`
- **Implementation**: Chunked commits, reduced batch sizes
- **Risk**: Medium - now manageable with chunking fixes

### 4. **Market Data Scheduler** ⚠️ (Needs Optimization)
- **Purpose**: Updates market data for stamps, SRC-20, and collections
- **Status**: Disabled via `ENABLE_MARKET_DATA_SCHEDULER=false`
- **Risk**: High - processes 10,000 stamps at once, no coordination

## Simple Coordination Approach

Instead of implementing a complex unified system, we'll use the existing `background_coordinator.py` to prevent conflicts:

### Background Coordinator Features
```python
# Simple but effective coordination
- Prevents heavy operations from running simultaneously
- Tracks active tasks with timestamps
- Enforces exclusion rules (e.g., holder updates vs sales history)
- Lightweight with minimal overhead
```

### Integration Pattern
```python
# Wrap any heavy operation with coordinator checks
from index_core.background_coordinator import BackgroundCoordinator

def heavy_operation():
    coordinator = BackgroundCoordinator.get_instance()
    
    if not coordinator.start_task('task_name', is_heavy=True):
        logger.info("Skipping - another heavy task running")
        return
    
    try:
        # Do the work
        perform_operation()
    finally:
        coordinator.end_task('task_name', is_heavy=True)
```

## Optimization Plan for Market Data Scheduler

### Configuration Changes
```bash
# Add to .env
ENABLE_MARKET_DATA_SCHEDULER=false    # Keep disabled until optimized
MARKET_DATA_STAMP_LIMIT=1000          # Reduced from 10000
MARKET_DATA_SRC20_LIMIT=200           # Reduced from 1000
MARKET_DATA_CHUNK_SIZE=100            # Process in chunks
MARKET_DATA_COMMIT_INTERVAL=50        # Commit frequently
MARKET_DATA_MAX_WORKERS=2             # Reduced from 3
```

### Code Changes Needed

1. **Add Coordinator Integration**
```python
# In market_data_jobs.py
def _update_stamp_market_data_job(self):
    coordinator = BackgroundCoordinator.get_instance()
    if not coordinator.start_task('market_data_stamps', is_heavy=True):
        return
    try:
        self._process_stamps_chunked()
    finally:
        coordinator.end_task('market_data_stamps', is_heavy=True)
```

2. **Implement Chunked Processing**
```python
def _process_stamps_chunked(self):
    stamps = self._get_stamps_to_update(limit=self.stamp_limit)
    
    for i in range(0, len(stamps), self.chunk_size):
        chunk = stamps[i:i + self.chunk_size]
        self._process_chunk(chunk)
        
        # Commit every N stamps
        if i % self.commit_interval == 0:
            self.db.commit()
            time.sleep(0.5)  # Brief pause
```

3. **Priority-Based Updates**
```python
# Update HOT stamps more frequently than COLD
def _get_stamps_to_update(self, limit):
    query = """
    SELECT cpid FROM stamp_market_data
    WHERE 
        (activity_level = 'HOT' AND last_updated < DATE_SUB(NOW(), INTERVAL 5 MINUTE))
        OR (activity_level = 'COLD' AND last_updated < DATE_SUB(NOW(), INTERVAL 1 HOUR))
    ORDER BY activity_level, last_updated
    LIMIT %s
    """
```

## Task Exclusion Rules

The coordinator enforces these rules:
1. **Holder updates** and **sales history** cannot run together (both update market data)
2. **Market data updates** are marked as heavy operations
3. Only one heavy operation can run at a time
4. Tasks that started >30 seconds ago are considered stale

## Testing Plan

### Phase 1: Verify Current Systems
- ✅ Async holder updater is working
- ✅ Background validator is working
- ✅ Sales history is working with chunks

### Phase 2: Add Coordinator
1. Integrate coordinator with sales history
2. Integrate coordinator with holder updater
3. Test exclusion rules work correctly

### Phase 3: Optimize Market Data
1. Implement chunking and limits
2. Add coordinator integration
3. Test with small limits first

### Phase 4: Enable Everything
```bash
ENABLE_SRC20_BACKGROUND_VALIDATION=true
ENABLE_SALES_HISTORY_CATCHUP=true
ENABLE_ASYNC_HOLDER_UPDATES=true
ENABLE_MARKET_DATA_SCHEDULER=true  # After optimization
```

## Monitoring

Key metrics to watch:
- Database connections (should stay <35)
- Lock wait timeouts (should be 0)
- Queue depths for each system
- Background task execution times

## Future Enhancements

The complex unified system from UNIFIED_BACKGROUND_PROCESSING.md could be implemented later if needed, but the simple coordinator approach should be sufficient for current needs.