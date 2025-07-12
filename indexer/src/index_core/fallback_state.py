"""
Fallback state management for persistence across restarts.

This module handles saving and loading fallback mode state to ensure
proper rollback detection even after indexer restarts or crashes.
"""

import logging
from typing import Dict

from . import util  # For CURRENT_BLOCK_INDEX
from .reprocessing_queue import ReprocessingQueue

logger = logging.getLogger(__name__)


def save_failed_blocks(failed_blocks: Dict[int, bool]) -> None:
    """Save failed blocks state using SQLite queue."""
    try:
        queue = ReprocessingQueue.get_instance()
        queue.save_fallback_state(util.CURRENT_BLOCK_INDEX, failed_blocks)
        logger.info(f"Saved fallback state for block {util.CURRENT_BLOCK_INDEX}")
    except Exception as e:
        logger.error(f"Failed to save fallback state: {e}")
        raise  # Re-raise for caller handling


def load_failed_blocks() -> Dict[int, bool]:
    """Load failed blocks from SQLite, return empty dict if none."""
    queue = ReprocessingQueue.get_instance()
    state = queue.load_fallback_state(util.CURRENT_BLOCK_INDEX) or {}
    if state:
        logger.debug(f"Loaded fallback state with {len(state)} failed blocks")
    return state


def clear_fallback_state(block_index: int) -> None:
    """Clear specific fallback state after successful reparse."""
    queue = ReprocessingQueue.get_instance()
    queue.clear_fallback_state(block_index)
    logger.info(f"Cleared fallback state for block {block_index}")
