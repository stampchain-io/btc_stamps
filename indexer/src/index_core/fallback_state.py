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
    """Save failed blocks state using normalized SQLite structure."""
    try:
        queue = ReprocessingQueue.get_instance()
        # Handle case where CURRENT_BLOCK_INDEX is None
        block_index = util.CURRENT_BLOCK_INDEX
        if block_index is None:
            logger.warning("Cannot save fallback state: CURRENT_BLOCK_INDEX is None")
            return

        # No more JSON conversion - direct integer keys
        queue.save_fallback_state(block_index, failed_blocks)
        logger.info(f"Saved fallback state for block {block_index}")
    except Exception as e:
        logger.error(f"Failed to save fallback state: {e}")
        raise  # Re-raise for caller handling


def load_failed_blocks() -> Dict[int, bool]:
    """Load failed blocks from normalized SQLite structure."""
    queue = ReprocessingQueue.get_instance()
    # Handle case where CURRENT_BLOCK_INDEX is None
    block_index = util.CURRENT_BLOCK_INDEX
    if block_index is None:
        logger.debug("Cannot load fallback state: CURRENT_BLOCK_INDEX is None")
        return {}

    # Load from normalized structure - returns Dict[int, bool] directly
    state = queue.load_fallback_state(block_index)
    if state:
        logger.debug(f"Loaded fallback state with {len(state)} failed blocks")
        # Ensure all keys are integers (defensive programming)
        return {int(k): bool(v) for k, v in state.items()}
    return {}


def clear_fallback_state(block_index: int) -> None:
    """Clear specific fallback state after successful reparse."""
    queue = ReprocessingQueue.get_instance()
    queue.clear_fallback_state(block_index)
    logger.info(f"Cleared fallback state for block {block_index}")
