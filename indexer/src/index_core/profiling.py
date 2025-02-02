"""
Profiling utilities for the indexer.
Handles cProfile-based profiling of block processing and other operations.
"""

import cProfile
import logging
import os
import pstats
from datetime import datetime
from functools import wraps
from pstats import SortKey

import config
import index_core.util as util

logger = logging.getLogger(__name__)


class Profiler:
    def __init__(self):
        self.profiling_enabled = config.DEBUG_PROFILING
        logger.info(f"Profiling initialized. DEBUG_PROFILING={self.profiling_enabled}")

        # Initialize basic attributes
        self.profile_dir = None
        self.profiler = None
        self.blocks_profiled = 0
        self.blocks_seen = 0
        self.profiling_active = False
        self.first_block_skipped = False
        self.start_block = None
        self.timestamp = None
        self.stats_file = None
        self.profile_data_file = None

        # Only set up profiling if enabled
        if self.profiling_enabled:
            self._setup_profiling()

    def _setup_profiling(self):
        """Set up profiling directory and initialize profiler if profiling is enabled."""
        try:
            # Get absolute path to the project root
            current_file_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_file_dir)))
            self.profile_dir = os.path.join(project_root, "indexer", "profiling")

            logger.info(f"Creating profiling directory at: {self.profile_dir}")
            os.makedirs(self.profile_dir, exist_ok=True)

            # Test directory is writable
            test_file = os.path.join(self.profile_dir, ".test")
            try:
                with open(test_file, "w") as f:
                    f.write("test")
                os.remove(test_file)
                logger.info("Successfully verified profiling directory is writable")
            except Exception as e:
                logger.error(f"Profiling directory is not writable: {e}")
                raise
        except Exception as e:
            logger.error(f"Failed to create profiling directory: {e}")
            raise

        # Initialize profiler
        self.profiler = cProfile.Profile()
        # Generate timestamp for unique filenames
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    def start_block_profiling(self):
        """Start profiling for a block if conditions are met."""
        if not self.profiling_enabled:
            logger.debug("Profiling not enabled, skipping")
            return

        # Increment blocks seen counter
        self.blocks_seen += 1
        logger.info(
            f"Profiling: Blocks seen: {self.blocks_seen}, Blocks profiled: {self.blocks_profiled}, Active: {self.profiling_active}"
        )

        # Skip first block
        if not self.first_block_skipped:
            self.first_block_skipped = True
            logger.info("Skipping profiling for first block to avoid startup overhead")
            return

        # Check if we've already profiled 20 blocks
        if self.blocks_profiled >= 20:
            logger.info(f"Already profiled {self.blocks_profiled} blocks, no more profiling needed")
            if self.profiling_active:
                logger.info("Reached 20 blocks, saving profile data")
                self._save_profile_data()
            return

        # Start profiling if not already active
        if not self.profiling_active:
            self.profiling_active = True  # Set this BEFORE enabling profiler
            self.start_block = util.CURRENT_BLOCK_INDEX

            # Set filenames now that we know the start block
            self.stats_file = os.path.join(self.profile_dir, f"profile_stats_block_{self.start_block}_{self.timestamp}.txt")
            self.profile_data_file = os.path.join(
                self.profile_dir, f"profile_data_block_{self.start_block}_{self.timestamp}.prof"
            )
            logger.info(f"Profile output files will be:\n- Stats: {self.stats_file}\n- Data: {self.profile_data_file}")

            self.profiler.enable()
            logger.info(f"Starting profiling at block {self.start_block}")
            logger.info(f"Starting profiling for block {self.blocks_profiled + 1}/20")
        else:
            # Re-enable profiler for next block if it was temporarily disabled
            self.profiler.enable()
            logger.info(f"Continuing profiling for block {self.blocks_profiled + 1}/20")

    def end_block_profiling(self):
        """End profiling for a block and save results if complete."""
        if not self.profiling_enabled:
            logger.debug("Profiling not enabled in end_block_profiling")
            return

        if not self.profiling_active:
            logger.debug("Profiling not active in end_block_profiling")
            return

        # Temporarily disable profiler
        self.profiler.disable()

        # Increment block count after successful processing
        self.blocks_profiled += 1
        logger.info(f"Completed profiling block {self.blocks_profiled}/20 (at block {util.CURRENT_BLOCK_INDEX})")

        # Check if we've hit 20 blocks
        if self.blocks_profiled >= 20:
            logger.info("Completed profiling 20 blocks, saving profile data")
            self._save_profile_data()
        else:
            # Re-enable profiler for next block
            self.profiler.enable()
            logger.info(f"Re-enabled profiling for next block. {self.blocks_profiled}/20 blocks profiled")

    def _save_profile_data(self):
        """Save profiling data and disable profiler."""
        if not self.profiling_active:
            logger.debug("Profiling not active in save_profile_data")
            return

        logger.info("Saving profiling data...")
        self.profiler.disable()

        try:
            # Save the raw profiling data for visualization
            self.profiler.dump_stats(self.profile_data_file)
            logger.info(f"Saved raw profiling data to: {self.profile_data_file}")

            # Create stats object and sort by cumulative time
            stats = pstats.Stats(self.profiler)
            stats.sort_stats(SortKey.CUMULATIVE)

            # Save detailed stats to text file
            with open(self.stats_file, "w") as f:
                # Add profiling context header
                f.write("Profiling Summary\n")
                f.write("================\n")
                f.write(f"Start Block: {self.start_block}\n")
                f.write(f"End Block: {util.CURRENT_BLOCK_INDEX}\n")
                f.write(f"Blocks Profiled: {self.blocks_profiled}\n")
                f.write(f"Total Blocks Seen: {self.blocks_seen}\n\n")
                f.write("Detailed Statistics\n")
                f.write("===================\n")

                stats.stream = f
                stats.print_stats()
                # Add callers and callees information
                f.write("\n\nCALLERS:\n")
                stats.print_callers()
                f.write("\n\nCALLEES:\n")
                stats.print_callees()

            logger.info(
                f"Profiling completed for {self.blocks_profiled} blocks (from {self.start_block} to {util.CURRENT_BLOCK_INDEX})"
            )
            logger.info(f"Stats saved to: {self.stats_file}")
            logger.info(f"To visualize the profile data, run: snakeviz {self.profile_data_file}")
        except Exception as e:
            logger.error(f"Error saving profiling data: {e}")
            raise

        self.profiling_active = False  # Set this AFTER saving data


def profile_function(func):
    """Decorator to profile a specific function."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        if not config.DEBUG_PROFILING:
            return func(*args, **kwargs)

        # Initialize profiler if needed
        if not hasattr(profile_function, "profiler"):
            profile_function.profiler = cProfile.Profile()

        profiler = profile_function.profiler
        try:
            profiler.enable()
            result = func(*args, **kwargs)
            profiler.disable()
            return result
        except Exception as e:
            profiler.disable()
            raise e

    return wrapper


def get_function_stats():
    """Get the current profiling statistics for function profiling."""
    if hasattr(profile_function, "profiler"):
        stats = pstats.Stats(profile_function.profiler)
        stats.sort_stats(SortKey.TIME)
        return stats
    return None
