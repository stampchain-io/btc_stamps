"""
Fallback state management for persistence across restarts.

This module handles saving and loading fallback mode state to ensure
proper rollback detection even after indexer restarts or crashes.
"""

import json
import logging
import os
import time
from typing import Dict, Optional, Set

import config

logger = logging.getLogger(__name__)


class FallbackStateManager:
    """Manages fallback mode state persistence."""

    def __init__(self, state_file: Optional[str] = None):
        """
        Initialize the fallback state manager.

        Args:
            state_file: Optional custom path for state file
        """
        if state_file is None:
            # Default to storing in a temporary directory or project-specific location
            state_dir = getattr(config, "FALLBACK_STATE_DIR", "/tmp")
            if not os.path.exists(state_dir):
                try:
                    os.makedirs(state_dir, exist_ok=True)
                except OSError:
                    state_dir = "/tmp"

            self.state_file = os.path.join(state_dir, "btc_stamps_fallback_state.json")
        else:
            self.state_file = state_file

        self.state = self._load_state()

    def _load_state(self) -> Dict:
        """Load fallback state from disk."""
        if not os.path.exists(self.state_file):
            return {
                "fallback_active": False,
                "fallback_started_at": None,
                "failed_cp_blocks": [],
                "last_updated": None,
                "version": "1.0",
            }

        try:
            with open(self.state_file, "r") as f:
                state = json.load(f)

            # Convert failed_cp_blocks back to set for faster operations
            if "failed_cp_blocks" in state and isinstance(state["failed_cp_blocks"], list):
                state["failed_cp_blocks"] = set(state["failed_cp_blocks"])

            return state
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Could not load fallback state from {self.state_file}: {e}")
            return {
                "fallback_active": False,
                "fallback_started_at": None,
                "failed_cp_blocks": set(),
                "last_updated": None,
                "version": "1.0",
            }

    def _save_state(self):
        """Save current fallback state to disk."""
        try:
            # Convert set to list for JSON serialization
            state_to_save = self.state.copy()
            if "failed_cp_blocks" in state_to_save and isinstance(state_to_save["failed_cp_blocks"], set):
                state_to_save["failed_cp_blocks"] = list(state_to_save["failed_cp_blocks"])

            state_to_save["last_updated"] = time.time()

            with open(self.state_file, "w") as f:
                json.dump(state_to_save, f, indent=2)

        except IOError as e:
            logger.error(f"Could not save fallback state to {self.state_file}: {e}")

    def start_fallback_mode(self, start_block: int):
        """Mark the start of fallback mode."""
        self.state["fallback_active"] = True
        self.state["fallback_started_at"] = start_block
        if "failed_cp_blocks" not in self.state:
            self.state["failed_cp_blocks"] = set()

        logger.info(f"Fallback mode started at block {start_block}")
        self._save_state()

    def add_failed_block(self, block_index: int):
        """Add a block that failed CP processing."""
        if "failed_cp_blocks" not in self.state:
            self.state["failed_cp_blocks"] = set()

        self.state["failed_cp_blocks"].add(block_index)
        self._save_state()

    def end_fallback_mode(self):
        """Mark the end of fallback mode (cleanup state)."""
        self.state["fallback_active"] = False
        self.state["fallback_started_at"] = None
        self.state["failed_cp_blocks"] = set()

        logger.info("Fallback mode ended, state cleared")
        self._save_state()

    def is_fallback_active(self) -> bool:
        """Check if fallback mode is currently active."""
        return self.state.get("fallback_active", False)

    def get_fallback_start_block(self) -> Optional[int]:
        """Get the block where fallback mode started."""
        return self.state.get("fallback_started_at")

    def get_failed_blocks(self) -> Set[int]:
        """Get the set of blocks that failed CP processing."""
        failed_blocks = self.state.get("failed_cp_blocks", set())
        if isinstance(failed_blocks, list):
            failed_blocks = set(failed_blocks)
        return failed_blocks

    def get_fallback_info(self) -> Dict:
        """Get comprehensive fallback information."""
        failed_blocks = self.get_failed_blocks()
        return {
            "fallback_active": self.is_fallback_active(),
            "fallback_started_at": self.get_fallback_start_block(),
            "failed_cp_blocks_count": len(failed_blocks),
            "failed_cp_blocks_sample": list(failed_blocks)[:10] if failed_blocks else [],
            "last_updated": self.state.get("last_updated"),
            "needs_rollback": self.is_fallback_active() and len(failed_blocks) > 0,
        }

    def cleanup_state_file(self):
        """Remove the state file (for testing or complete cleanup)."""
        try:
            if os.path.exists(self.state_file):
                os.remove(self.state_file)
                logger.info(f"Removed fallback state file: {self.state_file}")
        except IOError as e:
            logger.warning(f"Could not remove state file {self.state_file}: {e}")


# Global state manager instance
_state_manager = None


def get_fallback_state_manager() -> FallbackStateManager:
    """Get the global fallback state manager instance."""
    global _state_manager
    if _state_manager is None:
        _state_manager = FallbackStateManager()
    return _state_manager
