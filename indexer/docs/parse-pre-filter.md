# Parser and Threading Optimization Plan

## Performance Analysis

### Profiling Data (block range 876383-876403)
- Total time: 49.347s/20 blocks (~2.47s per block)
- Total function calls: 3,984,899 (3,982,229 primitive calls)
- Target: ~1.48s per block (40% reduction)

### Major Bottlenecks (by cumulative time)

1. Threading/Lock Operations (58% of total time)
```
ncalls  tottime  cumtime  filename:lineno(function)
 1438    0.003   28.806  threading.py:589(wait)
 2701    0.008   28.805  threading.py:288(wait)
10994   28.793   28.793  {method 'acquire' of '_thread.lock' objects}
 3541    0.011   28.775  concurrent/futures/_base.py:201(as_completed)
```

2. Network/RPC Operations (48% of total time)
```
ncalls  tottime  cumtime  filename:lineno(function)
    1    0.004   23.697  xcprequest.py:45(fetch_cp_concurrent)
   20    0.018    9.409  backend.py:361(get_tx_list)
 8752    0.008    8.065  socket.py:691(readinto)
```

3. Transaction Parsing (16% of total time)
```
ncalls  tottime  cumtime  filename:lineno(function)
   20    0.291    7.946  parser.py:132(parse_block)
   20    7.653    7.653  {method 'parse_block' of 'FastTransactionParser' objects}
   46    1.839    1.839  {method 'batch_parse_transactions' of 'FastTransactionParser' objects}
```

4. Database Operations (12% of total time)
```
ncalls  tottime  cumtime  filename:lineno(function)
 8266    0.023    6.125  pymysql/connections.py:735(_read_packet)
 2178    0.003    6.121  pymysql/cursors.py:133(execute)
 2178    0.004    6.055  pymysql/cursors.py:319(_query)
```

### Memory Usage Patterns
- Peak memory usage: 85-90% during large block processing
- Cache pressure points:
  - Script cache: ~35,889 entries per block
  - Transaction cache: ~2,178 entries per block
  - Database connection pool: ~8,266 operations

## Implementation Priorities

1. Threading/Lock Optimization (58% of time)
2. Pre-filtering Optimization (16% of time)
3. Memory Management Improvements

## Implementation Plan

### Phase 1: Threading Optimization (Week 1)

1. Replace Global Locks with Fine-grained Locking:
```python
class ThreadSafeCache:
    def __init__(self):
        self._cache = {}
        self._locks = {}  # Per-key locks
        self._global_lock = threading.RLock()  # Only for _locks dict
        
    def get(self, key):
        # Fast path - no lock
        try:
            return self._cache[key]
        except KeyError:
            pass
            
        # Get or create lock for this key
        with self._global_lock:
            lock = self._locks.setdefault(key, threading.Lock())
            
        with lock:
            return self._cache.get(key)
            
    def set(self, key, value):
        with self._global_lock:
            lock = self._locks.setdefault(key, threading.Lock())
            
        with lock:
            self._cache[key] = value
```

2. Optimize Thread Pool Usage:
```python
class OptimizedThreadPool:
    def __init__(self):
        self.executor = ThreadPoolExecutor(
            max_workers=4,  # Based on profiling
            thread_name_prefix='parser'
        )
        self._active_tasks = 0
        self._task_lock = threading.Lock()
        
    def submit_task(self, fn, *args):
        with self._task_lock:
            if self._active_tasks >= 3:  # Leave room for main thread
                self._wait_for_tasks()
            self._active_tasks += 1
            
        future = self.executor.submit(fn, *args)
        future.add_done_callback(self._task_completed)
        return future
        
    def _task_completed(self, future):
        with self._task_lock:
            self._active_tasks -= 1
```

3. Implement Lock-Free Data Structures:
```rust
use crossbeam_channel::{bounded, Sender, Receiver};

pub struct LockFreeParser {
    tx_queue: (Sender<Transaction>, Receiver<Transaction>),
    result_queue: (Sender<ParseResult>, Receiver<ParseResult>),
    
    pub fn new() -> Self {
        let (tx_send, tx_recv) = bounded(1000);
        let (res_send, res_recv) = bounded(1000);
        Self {
            tx_queue: (tx_send, tx_recv),
            result_queue: (res_send, res_recv)
        }
    }
    
    pub fn process_transactions(&self, txs: Vec<Transaction>) {
        // Process in parallel without locks
        txs.into_par_iter()
           .for_each(|tx| {
                self.tx_queue.0.send(tx).unwrap();
           });
    }
}
```

### Phase 2: Pre-filtering Optimization (Week 2)

1. Implement Rust Pre-filter:
```rust
impl FastTransactionParser {
    pub fn pre_filter_block(&self, block: &Block) -> PreFilterResult {
        // Use parallel iterator for filtering
        let filtered: Vec<_> = block.txdata
            .par_iter()
            .filter_map(|tx| {
                if self.quick_filter_tx(tx) {
                    Some(tx.clone())
                } else {
                    None
                }
            })
            .collect();
            
        PreFilterResult {
            transactions: filtered,
            metrics: self.collect_metrics()
        }
    }
    
    #[inline]
    fn quick_filter_tx(&self, tx: &Transaction) -> bool {
        tx.output.iter().any(|out| {
            let script = out.script_pubkey.as_bytes();
            matches!(script, 
                [0x00, rest @ ..] if rest.len() == 32 ||  // P2WSH
                bytes if bytes.last() == Some(&0xAE) ||    // Multisig
                [0x6a, ..]                                // OP_RETURN
            )
        })
    }
}
```

2. Optimize Python Integration:
```python
class Parser:
    def __init__(self):
        self.thread_pool = OptimizedThreadPool()
        self.parser = LockFreeParser()
        
    def parse_block(self, block_data: bytes) -> List[Transaction]:
        # Pre-filter in Rust
        filtered = self.parser.pre_filter_block(block_data)
        
        # Process in batches using thread pool
        results = []
        for batch in filtered.chunks(self.batch_size):
            future = self.thread_pool.submit_task(
                self.parser.process_batch, batch
            )
            results.extend(future.result())
            
        return results
```

### Phase 3: Integration and Testing (Week 3)

1. Metrics Collection:
```python
class ParserMetrics:
    def __init__(self):
        self.lock_contention = Counter()
        self.processing_times = []
        self.thread_usage = []
        
    def record_lock_wait(self, lock_id: str, wait_time: float):
        self.lock_contention[lock_id] += wait_time
        
    def record_processing(self, batch_size: int, time_taken: float):
        self.processing_times.append((batch_size, time_taken))
```

2. Validation Tests:
```python
def test_threading_optimization():
    test_blocks = load_test_blocks()
    metrics = ParserMetrics()
    
    for block in test_blocks:
        with ThreadProfiler() as profiler:
            result = parser.parse_block(block)
            
        metrics.record_lock_wait(
            profiler.lock_contentions,
            profiler.wait_times
        )
    
    assert max(metrics.lock_contention.values()) < 0.1  # < 10% wait time
```

## Implementation Schedule

### Week 1: Threading Optimization
- Day 1-2: Implement ThreadSafeCache
- Day 3-4: Implement OptimizedThreadPool
- Day 5: Implement LockFreeParser base structure

### Week 2: Pre-filtering Implementation
- Day 1-2: Implement Rust pre-filter
- Day 3-4: Implement Python integration
- Day 5: Add metrics collection

### Week 3: Testing and Integration
- Day 1-2: Implement validation tests
- Day 3: Performance testing
- Day 4-5: Optimization and bug fixes

## Success Metrics

1. Threading Improvements:
   - Reduce lock wait time from 28.8s to <14s per 20 blocks
   - Reduce lock contention count by 50%
   - Maintain thread pool utilization >80%

2. Pre-filter Effectiveness:
   - Filter out >60% of non-stamp transactions before processing
   - Reduce parse_block time from 7.9s to <4s per 20 blocks
   - Keep memory usage under 85%

## Validation Strategy

1. Automated Tests:
   - Threading tests with high concurrency
   - Pre-filter accuracy tests
   - Memory leak detection
   - Performance regression tests

2. Monitoring:
   - Lock contention metrics
   - Thread pool utilization
   - Memory usage patterns
   - Processing time per block



## Implementation Details



## Detailed Week 1 Implementation Plan: Threading Optimization

### Day 1: ThreadSafeCache Implementation

1. Create New Cache Module (cache_manager.py):
```python
from typing import Generic, TypeVar, Dict, Optional
from threading import RLock, Lock
from collections import OrderedDict
import time

KT = TypeVar('KT')  # Key type
VT = TypeVar('VT')  # Value type

class CacheMetrics:
    def __init__(self):
        self.hits = 0
        self.misses = 0
        self.lock_contentions = 0
        self.lock_wait_time = 0.0
        self._lock = RLock()

    def record_hit(self): 
        with self._lock:
            self.hits += 1

    def record_miss(self):
        with self._lock:
            self.misses += 1

class ThreadSafeCache(Generic[KT, VT]):
    def __init__(self, maxsize: int = 10000, ttl: float = 300):
        self._cache: Dict[KT, VT] = OrderedDict()
        self._locks: Dict[KT, Lock] = {}
        self._global_lock = RLock()
        self._metrics = CacheMetrics()
        self._maxsize = maxsize
        self._ttl = ttl
        self._timestamps: Dict[KT, float] = {}

    def _get_lock(self, key: KT) -> Lock:
        """Get or create lock for key with minimal contention."""
        try:
            return self._locks[key]
        except KeyError:
            with self._global_lock:
                # Double-check pattern
                if key not in self._locks:
                    self._locks[key] = Lock()
                return self._locks[key]

    def get(self, key: KT) -> Optional[VT]:
        # Fast path - no lock
        try:
            value = self._cache[key]
            timestamp = self._timestamps[key]
            if time.time() - timestamp <= self._ttl:
                self._metrics.record_hit()
                return value
        except KeyError:
            pass

        # Slow path - with lock
        lock = self._get_lock(key)
        start_time = time.time()
        with lock:
            wait_time = time.time() - start_time
            self._metrics.lock_wait_time += wait_time
            if wait_time > 0.001:  # 1ms threshold
                self._metrics.lock_contentions += 1

            try:
                value = self._cache[key]
                timestamp = self._timestamps[key]
                if time.time() - timestamp <= self._ttl:
                    self._metrics.record_hit()
                    return value
            except KeyError:
                self._metrics.record_miss()
                return None

    def set(self, key: KT, value: VT) -> None:
        lock = self._get_lock(key)
        with lock:
            # Evict oldest if at capacity
            if len(self._cache) >= self._maxsize:
                with self._global_lock:
                    while len(self._cache) >= self._maxsize:
                        try:
                            oldest_key, _ = next(iter(self._cache.items()))
                            del self._cache[oldest_key]
                            del self._timestamps[oldest_key]
                            del self._locks[oldest_key]
                        except (StopIteration, KeyError):
                            break

            self._cache[key] = value
            self._timestamps[key] = time.time()

    def get_metrics(self) -> Dict[str, float]:
        """Get cache performance metrics."""
        total = self._metrics.hits + self._metrics.misses
        hit_rate = self._metrics.hits / total if total > 0 else 0
        return {
            'hit_rate': hit_rate,
            'lock_contentions': self._metrics.lock_contentions,
            'avg_wait_time': self._metrics.lock_wait_time / total if total > 0 else 0,
            'size': len(self._cache),
            'lock_count': len(self._locks)
        }
```

### Day 2: Cache Integration

1. Update Parser to Use New Cache (parser.py):
```python
class Parser:
    def __init__(self):
        self._script_cache = ThreadSafeCache[str, bytes](
            maxsize=40000,  # Based on profiling (~35,889 entries/block)
            ttl=300  # 5 minutes TTL
        )
        self._tx_cache = ThreadSafeCache[str, Transaction](
            maxsize=3000,  # Based on profiling (~2,178 entries/block)
            ttl=60  # 1 minute TTL for transactions
        )
        self._metrics_logger = MetricsLogger()

    def _log_cache_metrics(self):
        script_metrics = self._script_cache.get_metrics()
        tx_metrics = self._tx_cache.get_metrics()
        self._metrics_logger.log_cache_stats({
            'script_cache': script_metrics,
            'tx_cache': tx_metrics
        })
```

### Day 3-4: OptimizedThreadPool Implementation

1. Create Thread Pool Manager (thread_pool.py):
```python
from concurrent.futures import ThreadPoolExecutor, Future
from threading import Lock, Event
from typing import Callable, Any, List, Optional
import queue
import time

class ThreadPoolMetrics:
    def __init__(self):
        self.task_times: List[float] = []
        self.queue_times: List[float] = []
        self.active_threads = 0
        self._lock = Lock()

    def record_task(self, queue_time: float, execution_time: float):
        with self._lock:
            self.task_times.append(execution_time)
            self.queue_times.append(queue_time)

class OptimizedThreadPool:
    def __init__(self, 
                 max_workers: int = 4,
                 max_queue_size: int = 1000,
                 name: str = 'parser'):
        self.executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix=name
        )
        self._active_tasks = 0
        self._task_lock = Lock()
        self._queue = queue.Queue(maxsize=max_queue_size)
        self._shutdown = Event()
        self._metrics = ThreadPoolMetrics()
        
        # Start worker threads
        self._workers = [
            threading.Thread(target=self._worker_loop)
            for _ in range(max_workers)
        ]
        for w in self._workers:
            w.daemon = True
            w.start()

    def _worker_loop(self):
        """Main worker thread loop."""
        while not self._shutdown.is_set():
            try:
                task = self._queue.get(timeout=1.0)
                if task is None:
                    break

                fn, args, future, queue_time = task
                try:
                    with self._task_lock:
                        self._metrics.active_threads += 1
                    
                    start_time = time.time()
                    result = fn(*args)
                    execution_time = time.time() - start_time
                    
                    self._metrics.record_task(
                        time.time() - queue_time,
                        execution_time
                    )
                    future.set_result(result)
                except Exception as e:
                    future.set_exception(e)
                finally:
                    with self._task_lock:
                        self._metrics.active_threads -= 1
                    self._queue.task_done()
            except queue.Empty:
                continue

    def submit_task(self, fn: Callable, *args) -> Future:
        """Submit task to thread pool with improved queuing."""
        if self._shutdown.is_set():
            raise RuntimeError("ThreadPool is shutting down")

        future = Future()
        queue_time = time.time()
        
        try:
            self._queue.put(
                (fn, args, future, queue_time),
                timeout=1.0
            )
        except queue.Full:
            # Handle queue overflow
            self._handle_queue_full()
            self._queue.put(
                (fn, args, future, queue_time),
                timeout=1.0
            )
            
        return future

    def _handle_queue_full(self):
        """Handle queue overflow condition."""
        logger.warning("Thread pool queue full, waiting for capacity")
        while self._queue.full() and not self._shutdown.is_set():
            # Process one item from queue directly
            try:
                task = self._queue.get_nowait()
                if task:
                    fn, args, future, queue_time = task
                    try:
                        result = fn(*args)
                        future.set_result(result)
                    except Exception as e:
                        future.set_exception(e)
                    finally:
                        self._queue.task_done()
            except queue.Empty:
                break
            time.sleep(0.001)  # Short sleep to prevent CPU spin

    def shutdown(self, wait: bool = True):
        """Shutdown thread pool gracefully."""
        self._shutdown.set()
        # Signal workers to exit
        for _ in self._workers:
            self._queue.put(None)
        
        if wait:
            for worker in self._workers:
                worker.join()
            
        self.executor.shutdown(wait=wait)
```

### Day 5: Lock-Free Parser Base Structure

1. Update Rust Parser Implementation (lib.rs):
```rust
use crossbeam_channel::{bounded, Sender, Receiver};
use parking_lot::RwLock;
use std::sync::Arc;

pub struct LockFreeParser {
    tx_queue: (Sender<Transaction>, Receiver<Transaction>),
    result_queue: (Sender<ParseResult>, Receiver<ParseResult>),
    cache: Arc<RwLock<LruCache<String, Vec<u8>>>>,
    
    pub fn new(cache_size: usize) -> Self {
        let (tx_send, tx_recv) = bounded(1000);
        let (res_send, res_recv) = bounded(1000);
        
        Self {
            tx_queue: (tx_send, tx_recv),
            result_queue: (res_send, res_recv),
            cache: Arc::new(RwLock::new(LruCache::new(cache_size)))
        }
    }
    
    pub fn process_transactions(&self, txs: Vec<Transaction>) -> PyResult<Vec<ParseResult>> {
        let results = txs.into_par_iter()
            .map(|tx| {
                // Try cache first
                if let Some(result) = self.check_cache(&tx) {
                    return result;
                }
                
                // Process and cache result
                let result = self.process_single_tx(tx);
                self.cache_result(&tx, &result);
                result
            })
            .collect();
            
        Ok(results)
    }
}
```

### Testing Plan for Week 1

1. Cache Tests:
```python
def test_thread_safe_cache():
    cache = ThreadSafeCache[str, str](maxsize=100)
    
    def worker(items):
        for k, v in items:
            cache.set(k, v)
            assert cache.get(k) == v
            
    # Spawn multiple threads
    threads = []
    for i in range(4):
        items = [(f"key{j}", f"val{j}") for j in range(i*25, (i+1)*25)]
        t = threading.Thread(target=worker, args=(items,))
        threads.append(t)
        
    for t in threads:
        t.start()
    for t in threads:
        t.join()
        
    metrics = cache.get_metrics()
    assert metrics['lock_contentions'] < 50  # Acceptable contention
    assert metrics['hit_rate'] > 0.9  # Good hit rate
```

2. Thread Pool Tests:
```python
def test_thread_pool_performance():
    pool = OptimizedThreadPool(max_workers=4)
    
    def cpu_task(n):
        return sum(i * i for i in range(n))
        
    futures = []
    start = time.time()
    
    for i in range(100):
        future = pool.submit_task(cpu_task, 10000)
        futures.append(future)
        
    results = [f.result() for f in futures]
    duration = time.time() - start
    
    metrics = pool._metrics
    assert metrics.active_threads <= 4  # Never exceed max workers
    assert max(metrics.queue_times) < 1.0  # Queue time under 1s
```

### Monitoring Integration

1. Add Prometheus Metrics:
```python
from prometheus_client import Counter, Histogram, Gauge

LOCK_CONTENTION_COUNTER = Counter(
    'parser_lock_contentions_total',
    'Total number of lock contentions'
)

LOCK_WAIT_TIME = Histogram(
    'parser_lock_wait_seconds',
    'Lock wait time in seconds',
    buckets=[.0001, .001, .01, .1, 1]
)

ACTIVE_THREADS = Gauge(
    'parser_active_threads',
    'Number of active parser threads'
)
```

