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
        # Handle case where CURRENT_BLOCK_INDEX is None
        block_index = util.CURRENT_BLOCK_INDEX
        if block_index is None:
            logger.warning("Cannot save fallback state: CURRENT_BLOCK_INDEX is None")
            return
        # Convert Dict[int, bool] to Dict[str, Any] for JSON serialization
        state_data = {str(k): v for k, v in failed_blocks.items()}
        queue.save_fallback_state(block_index, state_data)
        logger.info(f"Saved fallback state for block {block_index}")
    except Exception as e:
        logger.error(f"Failed to save fallback state: {e}")
        raise  # Re-raise for caller handling


def load_failed_blocks() -> Dict[int, bool]:
    """Load failed blocks from SQLite, return empty dict if none."""
    queue = ReprocessingQueue.get_instance()
    # Handle case where CURRENT_BLOCK_INDEX is None
    block_index = util.CURRENT_BLOCK_INDEX
    if block_index is None:
        logger.debug("Cannot load fallback state: CURRENT_BLOCK_INDEX is None")
        return {}
    
    state = queue.load_fallback_state(block_index) or {}
    if state:
        logger.debug(f"Loaded fallback state with {len(state)} failed blocks")
        # Convert string keys to integers since JSON storage returns string keys
        return {int(k): bool(v) for k, v in state.items()}
    return {}


def clear_fallback_state(block_index: int) -> None:
    """Clear specific fallback state after successful reparse."""
    queue = ReprocessingQueue.get_instance()
    queue.clear_fallback_state(block_index)
    logger.info(f"Cleared fallback state for block {block_index}")
