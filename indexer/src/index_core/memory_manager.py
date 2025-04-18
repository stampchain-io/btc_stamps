"""Memory management utilities."""

import logging
import os
import time
from typing import TYPE_CHECKING, Any, Dict, Optional

import psutil

from index_core.cache_types import LRUCache

logger = logging.getLogger(__name__)


class MemoryManager:
    """Manages memory usage and cache clearing."""

    def __init__(self, memory_threshold: float = 0.85):
        """Initialize the memory manager.

        Args:
            memory_threshold: The memory usage threshold (0.0 to 1.0) that triggers cache clearing
        """
        self.memory_threshold = memory_threshold
        self._registered_caches: Dict[str, LRUCache[Any]] = {}
        self._process = psutil.Process(os.getpid())
        self._last_check = 0.0
        self._check_interval = 5.0  # Check memory every 5 seconds at most
        self._last_log = 0.0
        self._log_interval = 60.0  # Log memory usage every 60 seconds

    def register_cache(self, name: str, cache: LRUCache[Any]) -> None:
        """Register a cache for memory management."""
        self._registered_caches[name] = cache
        logger.debug(f"Registered cache: {name} (max_size={cache.max_size})")

    def unregister_cache(self, name: str) -> None:
        """Unregister a cache from memory management."""
        if name in self._registered_caches:
            del self._registered_caches[name]
            logger.info(f"Unregistered cache: {name}")
        else:
            logger.warning(f"Attempted to unregister non-existent cache: {name}")

    def get_memory_usage(self) -> float:
        """Get current memory usage as a percentage."""
        return self._process.memory_percent() / 100.0

    def should_check_memory(self) -> bool:
        """Determine if enough time has passed for another memory check."""
        current_time = time.time()
        if current_time - self._last_check >= self._check_interval:
            self._last_check = current_time
            return True
        return False

    def log_memory_usage(self, current_block: Optional[int] = None) -> None:
        """Log memory usage if enough time has passed since last log.

        Args:
            current_block: Optional block number for context in log message
        """
        current_time = time.time()
        if current_time - self._last_log >= self._log_interval:
            memory_usage = self.get_memory_usage()
            block_info = f" at block {current_block}" if current_block is not None else ""
            logger.info(f"Memory usage{block_info}: {memory_usage:.1%}, Cache sizes: {self.get_cache_stats()}")
            self._last_log = current_time

    def clear_caches_if_needed(self) -> None:
        """Clear all registered caches if memory usage is above threshold."""
        if not self.should_check_memory():
            return

        memory_usage = self.get_memory_usage()
        if memory_usage > self.memory_threshold:
            logger.warning(
                f"Memory usage ({memory_usage:.1%}) above threshold ({self.memory_threshold:.1%}), clearing caches. "
                f"Cache sizes: {self.get_cache_stats()}"
            )
            self.clear_all()
            new_usage = self.get_memory_usage()
            logger.info(f"Memory usage after clearing caches: {new_usage:.1%}")

    def clear_all(self) -> None:
        """Clear all registered caches."""
        for name, cache in self._registered_caches.items():
            logger.info(f"Clearing cache: {name} (size={len(cache)})")
            cache.clear()

    def get_cache_stats(self) -> Dict[str, int]:
        """Get statistics about registered caches."""
        return {name: len(cache) for name, cache in self._registered_caches.items()}


# Global memory manager instance
if TYPE_CHECKING:
    memory_manager: MemoryManager
else:
    try:
        memory_manager = MemoryManager()
    except Exception:
        # Stub in environments without psutil.Process
        memory_manager = None  # type: ignore
