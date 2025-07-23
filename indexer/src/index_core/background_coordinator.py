"""
Simple Background Task Coordinator

Prevents background tasks from overwhelming the database by coordinating
their execution. This is a temporary solution until we implement the
full unified background processor.
"""

import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Dict

logger = logging.getLogger(__name__)


class BackgroundCoordinator:
    """Coordinates background tasks to prevent resource contention."""

    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.active_tasks: Dict[str, datetime] = {}
        self.task_locks: Dict[str, threading.Lock] = {
            "holder_update": threading.Lock(),
            "sales_history": threading.Lock(),
            "src20_validation": threading.Lock(),
        }
        self.global_lock = threading.Lock()
        self.heavy_operation_in_progress = False

    def can_start_task(self, task_name: str, is_heavy: bool = False) -> bool:
        """
        Check if a task can start based on current system state.

        Args:
            task_name: Name of the task ('holder_update', 'sales_history', etc.)
            is_heavy: Whether this is a heavy database operation

        Returns:
            True if the task can proceed, False otherwise
        """
        with self.global_lock:
            # Main block processing ALWAYS has priority - never block it
            if task_name == "block_processing":
                return True

            # Don't start heavy operations if one is already running
            if is_heavy and self.heavy_operation_in_progress:
                logger.debug(f"Cannot start {task_name}: heavy operation in progress")
                return False

            # Check if this specific task is already running
            if task_name in self.active_tasks:
                # Allow if last execution was more than 30 seconds ago
                if datetime.now() - self.active_tasks[task_name] < timedelta(seconds=30):
                    logger.debug(f"Cannot start {task_name}: already running")
                    return False

            # Don't run holder updates and sales history at the same time
            if task_name == "holder_update" and "sales_history" in self.active_tasks:
                if datetime.now() - self.active_tasks["sales_history"] < timedelta(seconds=10):
                    logger.debug("Cannot start holder_update: sales_history is active")
                    return False

            if task_name == "sales_history" and "holder_update" in self.active_tasks:
                if datetime.now() - self.active_tasks["holder_update"] < timedelta(seconds=10):
                    logger.debug("Cannot start sales_history: holder_update is active")
                    return False

            return True

    def start_task(self, task_name: str, is_heavy: bool = False) -> bool:
        """
        Mark a task as started.

        Returns:
            True if task was started, False if it couldn't start
        """
        if not self.can_start_task(task_name, is_heavy):
            return False

        with self.global_lock:
            self.active_tasks[task_name] = datetime.now()
            if is_heavy:
                self.heavy_operation_in_progress = True
            logger.debug(f"Started task: {task_name} (heavy={is_heavy})")
            return True

    def end_task(self, task_name: str, is_heavy: bool = False):
        """Mark a task as completed."""
        with self.global_lock:
            if task_name in self.active_tasks:
                del self.active_tasks[task_name]
            if is_heavy:
                self.heavy_operation_in_progress = False
            logger.debug(f"Ended task: {task_name}")

    def get_active_tasks(self) -> Dict[str, float]:
        """Get currently active tasks and their duration."""
        with self.global_lock:
            now = datetime.now()
            return {task: (now - start_time).total_seconds() for task, start_time in self.active_tasks.items()}

    def _get_active_tasks_unlocked(self) -> Dict[str, float]:
        """Get currently active tasks and their duration without acquiring lock.

        This method assumes the caller already holds the global_lock.
        """
        now = datetime.now()
        return {task: (now - start_time).total_seconds() for task, start_time in self.active_tasks.items()}

    def wait_for_slot(self, task_name: str, timeout: float = 30.0) -> bool:
        """
        Wait for a slot to become available for the task.

        Returns:
            True if slot became available, False if timeout
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            if self.can_start_task(task_name):
                return True
            time.sleep(0.5)

        return False

    def get_stats(self) -> Dict:
        """Get current coordinator statistics."""
        with self.global_lock:
            return {
                "active_tasks": list(self.active_tasks.keys()),
                "active_task_count": len(self.active_tasks),
                "heavy_operation_in_progress": self.heavy_operation_in_progress,
                "task_durations": self._get_active_tasks_unlocked(),
            }


# Convenience decorators for coordinated execution
def coordinated_task(task_name: str, is_heavy: bool = False):
    """Decorator to coordinate task execution."""

    def decorator(func):
        def wrapper(*args, **kwargs):
            coordinator = BackgroundCoordinator.get_instance()

            # Wait for slot
            if not coordinator.wait_for_slot(task_name, timeout=60):
                logger.warning(f"Timeout waiting for slot for {task_name}")
                return None

            # Start task
            if not coordinator.start_task(task_name, is_heavy):
                logger.warning(f"Could not start {task_name}")
                return None

            try:
                # Execute the actual function
                return func(*args, **kwargs)
            finally:
                # Always mark task as ended
                coordinator.end_task(task_name, is_heavy)

        return wrapper

    return decorator


# Example usage in holder updater:
# @coordinated_task('holder_update', is_heavy=True)
# def update_holder_counts(self, block_index: int):
#     # ... actual update logic ...
#     pass
