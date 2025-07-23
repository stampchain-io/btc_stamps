import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import config
from index_core.src20 import fetch_api_ledger_data
from index_core.validation_queue import ValidationQueueManager

logger = logging.getLogger(__name__)


class BackgroundValidator:
    """Background service to validate queued blocks when API becomes available."""

    def __init__(self, check_interval: int = 60):
        self.queue_manager = ValidationQueueManager.get_instance()
        self.check_interval = check_interval
        self.is_running = False
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="validator")
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the background validation service."""
        if self.is_running:
            logger.warning("Background validator is already running")
            return

        self.is_running = True
        self._task = asyncio.create_task(self._validation_loop())
        logger.info("Background validator started")

    async def stop(self):
        """Stop the background validation service."""
        self.is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        self.executor.shutdown(wait=True)
        logger.info("Background validator stopped")

    async def _validation_loop(self):
        """Main validation loop that runs in the background."""
        while self.is_running:
            try:
                # Check if we should run validation
                if not self._should_run_validation():
                    await asyncio.sleep(self.check_interval)
                    continue

                # Get pending validations
                pending = self.queue_manager.get_pending_validations(limit=50)

                if not pending:
                    logger.debug("No pending validations in queue")
                    await asyncio.sleep(self.check_interval)
                    continue

                logger.info(f"Processing {len(pending)} pending validations")

                # Process validations in a thread to avoid blocking
                await asyncio.get_event_loop().run_in_executor(self.executor, self._process_validations, pending)

                # Short sleep between batches
                await asyncio.sleep(5)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Error in validation loop: {e}")
                await asyncio.sleep(self.check_interval)

    def _should_run_validation(self) -> bool:
        """Check if we should attempt validation (e.g., not during active indexing)."""
        # Don't run validation if FORCE is currently True (API is down)
        if config.FORCE:
            return False

        # Could add additional checks here, like:
        # - Is the indexer actively processing blocks?
        # - Is system load too high?
        # - Is it within allowed time window?

        return True

    def _process_validations(self, pending_validations):
        """Process a batch of pending validations."""
        successful = 0
        failed = 0

        for block_index, local_hash, valid_src20_str in pending_validations:
            try:
                # Temporarily store current FORCE state
                original_force = config.FORCE
                config.FORCE = False

                # Attempt to fetch API data
                api_hash, api_validation = fetch_api_ledger_data(block_index)

                # Restore FORCE state
                config.FORCE = original_force

                if api_hash is None:
                    # API is still unavailable
                    self.queue_manager.mark_api_error(block_index, "API unavailable during background validation")
                    failed += 1
                    continue

                # Compare hashes
                is_valid = api_hash == local_hash

                # Update validation status
                self.queue_manager.mark_validated(block_index, api_hash, is_valid)

                if is_valid:
                    logger.info(f"✅ Block {block_index} validated successfully")
                    successful += 1
                else:
                    logger.error(f"❌ VALIDATION MISMATCH for block {block_index}! " f"Local: {local_hash}, API: {api_hash}")
                    # Here you could trigger alerts, notifications, etc.

            except Exception as e:
                logger.error(f"Error validating block {block_index}: {e}")
                self.queue_manager.mark_api_error(block_index, str(e))
                failed += 1

        if successful > 0 or failed > 0:
            logger.info(f"Validation batch complete: {successful} successful, {failed} failed")

    def get_status(self) -> dict:
        """Get the current status of the background validator."""
        stats = self.queue_manager.get_validation_stats()
        return {"is_running": self.is_running, "queue_stats": stats, "check_interval": self.check_interval}


# Global instance for easy access
_validator_instance: Optional[BackgroundValidator] = None


def get_background_validator() -> BackgroundValidator:
    """Get or create the global background validator instance."""
    global _validator_instance
    if _validator_instance is None:
        _validator_instance = BackgroundValidator()
    return _validator_instance
