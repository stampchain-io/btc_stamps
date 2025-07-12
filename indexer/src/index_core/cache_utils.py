import hashlib
import json
import logging
import threading
import time
from functools import wraps
from typing import Any, Dict, Optional

try:
    import redis

    redis_available = True
except ImportError:
    redis_available = False

import config

logger = logging.getLogger(__name__)


class CacheManager:
    """Manages caching with Redis primary and in-memory fallback."""

    def __init__(self):
        self.redis_client = None
        self.memory_cache = {}
        self.memory_cache_lock = threading.Lock()
        self.max_memory_items = 1000  # Limit in-memory cache size

        # Try to connect to Redis if available
        if redis_available and hasattr(config, "REDIS_HOST"):
            try:
                self.redis_client = redis.Redis(
                    host=getattr(config, "REDIS_HOST", "localhost"),
                    port=getattr(config, "REDIS_PORT", 6379),
                    db=getattr(config, "REDIS_DB", 0),
                    decode_responses=True,
                    socket_timeout=5,
                    socket_connect_timeout=5,
                )
                # Test connection
                self.redis_client.ping()  # type: ignore
                logger.info("Connected to Redis cache")
            except Exception as e:
                logger.warning(f"Redis connection failed, using in-memory cache: {e}")
                self.redis_client = None
        else:
            logger.info("Redis not available, using in-memory cache")

    def _generate_key(self, prefix: str, *args: Any, **kwargs: Any) -> str:
        """Generate cache key from prefix and arguments."""
        key_data = f"{prefix}:{args}:{sorted(kwargs.items())}"
        return hashlib.sha256(key_data.encode()).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        """Get item from cache."""
        try:
            if self.redis_client:
                value = self.redis_client.get(key)
                if value and isinstance(value, str):
                    return json.loads(value)
            else:
                with self.memory_cache_lock:
                    if key in self.memory_cache:
                        item = self.memory_cache[key]
                        if item["expires_at"] > time.time():
                            return item["data"]
                        else:
                            del self.memory_cache[key]
        except Exception as e:
            logger.debug(f"Cache get error for key {key}: {e}")

        return None

    def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        """Set item in cache with TTL."""
        try:
            if self.redis_client:
                return self.redis_client.setex(key, ttl, json.dumps(value))
            else:
                with self.memory_cache_lock:
                    # Cleanup old items if cache is full
                    if len(self.memory_cache) >= self.max_memory_items:
                        current_time = time.time()
                        expired_keys = [k for k, v in self.memory_cache.items() if v["expires_at"] <= current_time]
                        for k in expired_keys:
                            del self.memory_cache[k]

                        # If still full, remove oldest items
                        if len(self.memory_cache) >= self.max_memory_items:
                            items_to_remove = len(self.memory_cache) - self.max_memory_items + 100
                            oldest_keys = sorted(self.memory_cache.keys(), key=lambda k: self.memory_cache[k]["created_at"])[
                                :items_to_remove
                            ]
                            for k in oldest_keys:
                                del self.memory_cache[k]

                    self.memory_cache[key] = {"data": value, "created_at": time.time(), "expires_at": time.time() + ttl}
                return True
        except Exception as e:
            logger.debug(f"Cache set error for key {key}: {e}")
            return False

    def delete(self, key: str) -> bool:
        """Delete item from cache."""
        try:
            if self.redis_client:
                return bool(self.redis_client.delete(key))
            else:
                with self.memory_cache_lock:
                    if key in self.memory_cache:
                        del self.memory_cache[key]
                        return True
        except Exception as e:
            logger.debug(f"Cache delete error for key {key}: {e}")

        return False

    def clear(self) -> bool:
        """Clear all cache items."""
        try:
            if self.redis_client:
                return bool(self.redis_client.flushdb())
            else:
                with self.memory_cache_lock:
                    self.memory_cache.clear()
                return True
        except Exception as e:
            logger.debug(f"Cache clear error: {e}")
            return False


# Global cache instance
cache_manager = CacheManager()


def cached_api_call(prefix: str, ttl: int = 300):
    """Decorator for caching API calls."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any):
            # Generate cache key
            cache_key = cache_manager._generate_key(prefix, *args, **kwargs)

            # Try to get from cache first
            cached_result = cache_manager.get(cache_key)
            if cached_result is not None:
                logger.debug(f"Cache hit for {func.__name__}")
                return cached_result

            # Call function and cache result
            result = func(*args, **kwargs)
            if result is not None:
                cache_manager.set(cache_key, result, ttl)
                logger.debug(f"Cached result for {func.__name__}")

            return result

        return wrapper

    return decorator


def get_cache_stats() -> Dict[str, Any]:
    """Get cache statistics."""
    stats = {"type": "redis" if cache_manager.redis_client else "memory", "connected": False, "memory_items": 0}

    try:
        if cache_manager.redis_client:
            stats["connected"] = True
            info = cache_manager.redis_client.info()
            stats["redis_memory"] = info.get("used_memory_human", "unknown")
            stats["redis_keys"] = cache_manager.redis_client.dbsize()
        else:
            with cache_manager.memory_cache_lock:
                stats["memory_items"] = len(cache_manager.memory_cache)
    except Exception as e:
        logger.debug(f"Error getting cache stats: {e}")

    return stats


def invalidate_block_cache(block_index: int):
    """Invalidate cache entries for a specific block."""
    patterns = [f"block_transactions_{block_index}", f"block_hash_{block_index}", f"block_events_{block_index}"]

    for pattern in patterns:
        cache_manager.delete(pattern)

    logger.debug(f"Invalidated cache for block {block_index}")
