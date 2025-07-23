"""
Utility functions and decorators for background task coordination.
Makes it easy to integrate the BackgroundCoordinator with existing code.
"""

import functools
import logging
from typing import Callable

from index_core.background_coordinator import BackgroundCoordinator

logger = logging.getLogger(__name__)


def coordinated_task(task_name: str, is_heavy: bool = False):
    """
    Decorator to wrap a function with background coordinator checks.

    Usage:
        @coordinated_task('market_data_stamps', is_heavy=True)
        def update_stamp_market_data():
            # Heavy database operations
            pass

    Args:
        task_name: Unique name for this task
        is_heavy: Whether this is a heavy operation that should block others
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            coordinator = BackgroundCoordinator.get_instance()

            # Try to start the task
            if not coordinator.start_task(task_name, is_heavy=is_heavy):
                logger.info(f"Skipping {task_name} - " f"{'heavy operation' if is_heavy else 'task'} already running")
                return None

            try:
                # Execute the actual function
                logger.debug(f"Starting coordinated task: {task_name}")
                result = func(*args, **kwargs)
                logger.debug(f"Completed coordinated task: {task_name}")
                return result

            except Exception as e:
                logger.error(f"Error in coordinated task {task_name}: {e}")
                raise

            finally:
                # Always mark task as ended
                coordinator.end_task(task_name, is_heavy=is_heavy)

        return wrapper

    return decorator


def can_run_task(task_name: str, is_heavy: bool = False) -> bool:
    """
    Check if a task can run without actually starting it.

    Useful for conditional logic before setting up resources.

    Args:
        task_name: Name of the task to check
        is_heavy: Whether this would be a heavy operation

    Returns:
        True if the task could run, False otherwise
    """
    coordinator = BackgroundCoordinator.get_instance()
    return coordinator.can_start_task(task_name, is_heavy)


class CoordinatedContext:
    """
    Context manager for coordinated tasks.

    Usage:
        with CoordinatedContext('sales_history', is_heavy=True) as ctx:
            if ctx.can_proceed:
                # Do heavy work
                pass
    """

    def __init__(self, task_name: str, is_heavy: bool = False):
        self.task_name = task_name
        self.is_heavy = is_heavy
        self.coordinator = BackgroundCoordinator.get_instance()
        self.can_proceed = False

    def __enter__(self):
        self.can_proceed = self.coordinator.start_task(self.task_name, self.is_heavy)
        if not self.can_proceed:
            logger.info(
                f"Cannot start {self.task_name} - " f"{'heavy operation' if self.is_heavy else 'task'} already running"
            )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.can_proceed:
            self.coordinator.end_task(self.task_name, self.is_heavy)
        return False  # Don't suppress exceptions


# Convenience functions for common task names
def with_market_data_coordination(func: Callable) -> Callable:
    """Decorator specifically for market data operations."""
    return coordinated_task("market_data", is_heavy=True)(func)


def with_sales_history_coordination(func: Callable) -> Callable:
    """Decorator specifically for sales history operations."""
    return coordinated_task("sales_history", is_heavy=True)(func)


def with_holder_update_coordination(func: Callable) -> Callable:
    """Decorator specifically for holder update operations."""
    return coordinated_task("holder_update", is_heavy=True)(func)
