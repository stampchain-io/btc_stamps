import os

# Reprocessing Queue Configs (for handling CP API lags at tip)
REPROCESS_DB_PATH = os.environ.get("REPROCESS_DB_PATH", "reprocess_queue.db")  # Path to SQLite DB file
REPROCESS_MAX_ATTEMPTS = int(os.environ.get("REPROCESS_MAX_ATTEMPTS", 5))  # Max retries before permanent failure
REPROCESS_CLEANUP_AGE = int(os.environ.get("REPROCESS_CLEANUP_AGE", 86400))  # Age in seconds to cleanup old entries (24h)
REPROCESS_BATCH_SIZE = int(os.environ.get("REPROCESS_BATCH_SIZE", 10))  # Max items to dequeue per cycle
REPROCESS_POLL_INTERVAL = int(os.environ.get("REPROCESS_POLL_INTERVAL", 30))  # Seconds between queue checks

"""
Config Rationale:
- MAX_ATTEMPTS: Prevents infinite loops on persistent failures (from analysis: CP can lag indefinitely).
- CLEANUP_AGE: Keeps DB lean; delete after 24h (customizable).
- BATCH_SIZE: Balances throughput without overwhelming CP API.
- POLL_INTERVAL: Frequent enough for real-time but not CPU-intensive.
"""

# Monitoring & Alerting Configs (for 9.4)
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")  # DEBUG for verbose
QUEUE_ALERT_SIZE = int(os.environ.get("QUEUE_ALERT_SIZE", 50))  # Alert if queue > this
API_FAILURE_ALERT = int(os.environ.get("API_FAILURE_ALERT", 5))  # Consecutive failures
METRICS_INTERVAL = int(os.environ.get("METRICS_INTERVAL", 60))  # Seconds between metric logs
ALERT_EMAIL = os.environ.get("ALERT_EMAIL", "")  # Optional for email alerts

"""
Rationale:
- LOG_LEVEL: Controls verbosity; DEBUG for dev troubleshooting.
- ALERT_*: Thresholds for proactive notifications (e.g., via email or log).
- METRICS_INTERVAL: Balances monitoring without log spam.
"""

# Real-time Processing Optimization Configs (for 9.5)
PARALLEL_MAX_WORKERS = int(os.environ.get("PARALLEL_MAX_WORKERS", 10))  # Max concurrent workers
PARALLEL_BATCH_SIZE = int(os.environ.get("PARALLEL_BATCH_SIZE", 20))  # Items per batch
PARALLEL_TIMEOUT = int(os.environ.get("PARALLEL_TIMEOUT", 30))  # Timeout per batch in seconds

# Caching Configuration
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")  # Redis server host
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))  # Redis server port
REDIS_DB = int(os.environ.get("REDIS_DB", 0))  # Redis database number
CACHE_BLOCK_HASH_TTL = int(os.environ.get("CACHE_BLOCK_HASH_TTL", 3600))  # Block hash cache TTL (1 hour)
CACHE_API_RESPONSE_TTL = int(os.environ.get("CACHE_API_RESPONSE_TTL", 300))  # API response cache TTL (5 min)

# Graceful Degradation
GRACEFUL_DEGRADATION = os.environ.get("GRACEFUL_DEGRADATION", "true").lower() == "true"  # Enable degraded mode

# Rate Limiting Optimizations
DYNAMIC_RATE_LIMITING = os.environ.get("DYNAMIC_RATE_LIMITING", "true").lower() == "true"  # Adaptive rate limits
RATE_LIMIT_BURST_SIZE = int(os.environ.get("RATE_LIMIT_BURST_SIZE", 5))  # Burst allowance
RATE_LIMIT_RECOVERY_TIME = int(os.environ.get("RATE_LIMIT_RECOVERY_TIME", 60))  # Recovery period

"""
Optimization Config Rationale:
- PARALLEL_*: Controls concurrent processing to balance speed vs resource usage.
- REDIS_*: Optional caching layer for reducing redundant API calls.
- FALLBACK_*: Enables graceful degradation when primary sources fail.
- RATE_LIMIT_*: Adaptive rate limiting to handle API constraints dynamically.

These settings work together to optimize real-time processing while maintaining reliability.
"""
