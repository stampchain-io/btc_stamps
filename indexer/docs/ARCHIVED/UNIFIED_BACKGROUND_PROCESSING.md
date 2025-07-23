# Unified Background Processing Strategy

## Current State Analysis

### 1. **SRC-20 Background Validation**
- **Current**: Uses SQLite (`validation_queue.db`) to store blocks that need hash validation
- **Problem**: Not integrated with other background systems
- **Good Design**: Already uses SQLite for temporary data (correct approach)

### 2. **Sales History Processor**
- **Current**: Has two modes - Full Catchup (>200 blocks behind) and Realtime
- **Problem**: Large batch inserts (1000 records) causing lock timeouts
- **Good Design**: Already has rate limiting and mode switching

### 3. **Holder Count Updates**
- **Current**: Trying to update all affected tokens per block
- **Problem**: Large UPDATE queries blocking main processing
- **New Design**: Priority queue system with circuit breaker

## Integration Opportunities

### Shared Infrastructure

```
┌─────────────────────────────────────────────────────────────────┐
│                    Unified Background Processor                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐    │
│  │   Priority    │  │   Circuit    │  │     Rate         │    │
│  │    Queue      │  │   Breaker    │  │    Limiter       │    │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘    │
│         │                  │                    │               │
│  ┌──────▼───────────────────▼──────────────────▼─────────┐    │
│  │              Task Dispatcher & Coordinator              │    │
│  └────────────────────────┬───────────────────────────────┘    │
│                           │                                     │
│  ┌────────────────────────┼───────────────────────────────┐    │
│  │                        │                                │    │
│  │  ┌─────────────┐  ┌───▼──────────┐  ┌───────────────┐│    │
│  │  │   Holder    │  │    Sales     │  │   SRC-20      ││    │
│  │  │   Updater   │  │   History    │  │  Validator    ││    │
│  │  └─────────────┘  └──────────────┘  └───────────────┘│    │
│  │                                                        │    │
│  └────────────────────────────────────────────────────────┘    │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │                    Shared Resources                       │  │
│  │  • SQLite Queue DB (validation_queue.db)                │  │
│  │  • MySQL Connection Pool (shared, managed)               │  │
│  │  • Memory Cache (holder counts, CPID lists)             │  │
│  └─────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Unified Implementation

### 1. **Shared SQLite Queue Database**

```sql
-- Single SQLite database for all background tasks
CREATE TABLE background_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_type TEXT NOT NULL, -- 'holder_update', 'sales_history', 'src20_validation'
    priority INTEGER DEFAULT 5, -- 1=highest, 10=lowest
    payload TEXT NOT NULL, -- JSON encoded task data
    status TEXT DEFAULT 'pending', -- pending, processing, completed, failed
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    retry_count INTEGER DEFAULT 0,
    error_message TEXT
);

CREATE INDEX idx_tasks_status_priority ON background_tasks(status, priority, created_at);
```

### 2. **Unified Task Types**

```python
@dataclass
class BackgroundTask:
    task_type: str
    priority: int
    payload: dict
    
    def to_json(self) -> str:
        return json.dumps({
            'task_type': self.task_type,
            'priority': self.priority,
            'payload': self.payload
        })

# Task examples:
holder_task = BackgroundTask(
    task_type='holder_update',
    priority=3,
    payload={
        'tokens': ['STAMP', 'KEVIN'],
        'block_index': 906472
    }
)

sales_task = BackgroundTask(
    task_type='sales_history',
    priority=5,
    payload={
        'mode': 'catchup',
        'start_block': 906000,
        'end_block': 906472
    }
)

validation_task = BackgroundTask(
    task_type='src20_validation',
    priority=7,
    payload={
        'block_index': 906472,
        'local_hash': 'abc123',
        'valid_src20_str': '...'
    }
)
```

### 3. **Smart Coordination**

```python
class UnifiedBackgroundProcessor:
    def __init__(self):
        self.db_path = "background_tasks.db"
        self.circuit_breaker = CircuitBreaker(threshold=3, reset_time=300)
        self.rate_limiter = RateLimiter(calls_per_second=2.0)
        self.workers = {
            'holder_update': HolderUpdateWorker(),
            'sales_history': SalesHistoryWorker(),
            'src20_validation': ValidationWorker()
        }
        
    def get_next_task(self) -> Optional[BackgroundTask]:
        """Get highest priority task respecting system state."""
        # Check circuit breaker
        if not self.circuit_breaker.can_execute():
            return None
            
        # Check system load
        if self.get_system_load() > 0.8:
            return None
            
        # Get task from SQLite
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT id, task_type, priority, payload
                FROM background_tasks
                WHERE status = 'pending'
                AND retry_count < 3
                ORDER BY priority ASC, created_at ASC
                LIMIT 1
            """)
            row = cursor.fetchone()
            
            if row:
                task_id, task_type, priority, payload = row
                # Mark as processing
                conn.execute("""
                    UPDATE background_tasks
                    SET status = 'processing', started_at = datetime('now')
                    WHERE id = ?
                """, (task_id,))
                conn.commit()
                
                return BackgroundTask(
                    task_type=task_type,
                    priority=priority,
                    payload=json.loads(payload)
                )
        return None
```

## Optimized Configurations

### For Sales History Processing

```python
class OptimizedSalesHistoryWorker:
    def __init__(self):
        self.batch_size = 100  # Reduced from 1000
        self.flush_interval = 5  # Seconds between flushes
        self.max_buffer_size = 500  # Maximum before forced flush
        
    def process_catchup(self, start_block: int, end_block: int):
        """Process sales history in smaller chunks."""
        # Break into smaller block ranges
        chunk_size = 100  # Process 100 blocks at a time
        
        for chunk_start in range(start_block, end_block, chunk_size):
            chunk_end = min(chunk_start + chunk_size, end_block)
            
            # Create sub-task for this chunk
            task = BackgroundTask(
                task_type='sales_history_chunk',
                priority=6,  # Lower priority than holder updates
                payload={
                    'start_block': chunk_start,
                    'end_block': chunk_end
                }
            )
            # Add to queue
            self.queue_task(task)
            
            # Rate limit chunk creation
            time.sleep(0.5)
```

### For Holder Count Updates

```python
class OptimizedHolderCountWorker:
    def __init__(self):
        self.cache = HolderCountCache(ttl=300)
        self.batch_size = 5  # Very small batches
        
    def should_update_token(self, token: str, block_index: int) -> bool:
        """Smart decision on whether to update a token."""
        # Check cache first
        if self.cache.get(token):
            return False
            
        # Check if recently updated
        with self.db.cursor() as cursor:
            cursor.execute("""
                SELECT last_updated 
                FROM src20_market_data 
                WHERE tick = %s
            """, (token,))
            row = cursor.fetchone()
            
            if row and row[0]:
                # Skip if updated in last 5 minutes
                if (datetime.now() - row[0]).seconds < 300:
                    return False
                    
        return True
```

### For SRC-20 Validation

```python
class OptimizedValidationWorker:
    def __init__(self):
        self.api_healthy = True
        self.last_api_check = 0
        
    def should_attempt_validation(self) -> bool:
        """Check if API is healthy before attempting validation."""
        now = time.time()
        
        # Check API health every 60 seconds
        if now - self.last_api_check > 60:
            self.api_healthy = self.check_api_health()
            self.last_api_check = now
            
        return self.api_healthy and not config.FORCE
```

## Integration Benefits

### 1. **Shared Resource Management**
- Single connection pool prevents exhaustion
- Unified rate limiting across all API calls
- Shared circuit breaker prevents cascading failures

### 2. **Smart Priority System**
- Block processing: Priority 1 (highest)
- Recent holder updates: Priority 3
- Sales history realtime: Priority 5
- Sales history catchup: Priority 6
- SRC-20 validation: Priority 7
- Periodic holder refresh: Priority 8

### 3. **Coordinated Processing**
- Holder updates and sales history can share CPID cache
- Validation can pause during heavy load
- Sales catchup can yield to holder updates

### 4. **Unified Monitoring**
```python
def get_system_metrics():
    return {
        'queue_depth': get_queue_depth(),
        'tasks_by_type': get_tasks_by_type(),
        'circuit_breaker_state': circuit_breaker.state,
        'api_health': {
            'counterparty': cp_api_healthy,
            'src20_validator': validator_api_healthy
        },
        'cache_stats': {
            'holder_cache_size': holder_cache.size(),
            'cpid_cache_size': cpid_cache.size(),
            'hit_rate': cache.get_hit_rate()
        }
    }
```

## Migration Path

### Phase 1: Unified Queue (Immediate)
1. Create unified SQLite database
2. Migrate existing queues to new schema
3. Deploy unified task dispatcher

### Phase 2: Optimize Workers (This Week)
1. Implement smart batching for sales history
2. Add caching layer for holder counts
3. Integrate API health checks

### Phase 3: Full Integration (Next Sprint)
1. Shared CPID cache between systems
2. Coordinated rate limiting
3. Advanced priority adjustments

## Configuration

```bash
# Unified background processing
BACKGROUND_QUEUE_DB=/path/to/background_tasks.db
BACKGROUND_MAX_WORKERS=3
BACKGROUND_CIRCUIT_BREAKER_THRESHOLD=3
BACKGROUND_RATE_LIMIT=2.0

# Task-specific settings
HOLDER_UPDATE_BATCH_SIZE=5
HOLDER_UPDATE_CACHE_TTL=300
SALES_HISTORY_BATCH_SIZE=100
SALES_HISTORY_FLUSH_INTERVAL=5
VALIDATION_RETRY_INTERVAL=60

# Priority settings
PRIORITY_HOLDER_RECENT=3
PRIORITY_SALES_REALTIME=5
PRIORITY_SALES_CATCHUP=6
PRIORITY_VALIDATION=7
PRIORITY_HOLDER_REFRESH=8
```

## Benefits of Integration

1. **Resource Efficiency**
   - Single queue reduces overhead
   - Shared caches reduce redundant queries
   - Coordinated rate limiting prevents API bans

2. **Better Performance**
   - Priority system ensures important tasks run first
   - Circuit breaker prevents system overload
   - Smart batching reduces lock contention

3. **Operational Simplicity**
   - Single monitoring dashboard
   - Unified configuration
   - Consistent error handling

4. **Scalability**
   - Easy to add new background tasks
   - Can scale workers independently
   - Queue can be moved to Redis later

## Testing Strategy

1. **Unit Tests**
   - Test each worker independently
   - Verify priority ordering
   - Test circuit breaker behavior

2. **Integration Tests**
   - Run all three systems together
   - Verify no lock timeouts
   - Test graceful degradation

3. **Load Tests**
   - Simulate 10,000 tasks in queue
   - Verify system remains responsive
   - Test with database under load