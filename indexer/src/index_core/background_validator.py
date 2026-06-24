import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from index_core.src20 import LedgerFetchStatus, fetch_api_ledger_data
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
        """Check if we should attempt validation.

        Stampscan availability is now determined per-request via the
        ``LedgerFetchStatus`` returned by ``fetch_api_ledger_data``; the
        legacy ``config.FORCE``-as-API-state signal has been removed.
        Validation is always permitted at the queue level — individual
        fetches deferred when stampscan can't authoritatively answer.
        """
        return True

    def _process_validations(self, pending_validations):
        """Process a batch of pending validations.

        Consumes the new ``LedgerFetchResult`` from ``fetch_api_ledger_data``.
        Only marks a block validated when stampscan returned data for the
        exact requested block (status OK). For deferral statuses (tip-lag /
        not_indexed / API error) the row is left in the queue for the next
        cycle. Mismatches surface via ``ops_alerter`` so they reach SNS /
        log alerting infrastructure.
        """
        successful = 0
        failed = 0

        for block_index, local_hash, valid_src20_str in pending_validations:
            try:
                result = fetch_api_ledger_data(block_index)

                if result.status != LedgerFetchStatus.OK:
                    # Stampscan still can't authoritatively confirm — leave
                    # in queue; mark the latest attempt for observability.
                    self.queue_manager.mark_api_error(
                        block_index,
                        f"deferred during background validation: status={result.status.value}",
                    )
                    failed += 1
                    continue

                is_valid = result.hash == local_hash
                self.queue_manager.mark_validated(block_index, result.hash, is_valid)

                if is_valid:
                    logger.info(f"✅ Block {block_index} validated successfully")
                    successful += 1
                else:
                    logger.error(f"❌ VALIDATION MISMATCH for block {block_index}! Local: {local_hash}, API: {result.hash}")
                    # Surface as a real consensus alert through ops_alerter.
                    try:
                        from index_core.ops_alerter import notify as ops_notify

                        ops_notify(
                            "critical",
                            f"SRC-20 ledger mismatch at block {block_index} (background)",
                            (
                                f"Background validator detected SRC-20 ledger_hash divergence at block {block_index}. "
                                f"Local: {local_hash} Stampscan: {result.hash}. "
                                f"Investigate immediately."
                            ),
                            dedup_key=f"src20-mismatch-bg-{block_index}",
                        )
                    except Exception as alert_err:
                        logger.error(f"ops_alerter notify failed for block {block_index}: {alert_err}")

            except Exception as e:
                logger.error(f"Error validating block {block_index}: {e}")
                self.queue_manager.mark_api_error(block_index, str(e))
                failed += 1

        if successful > 0 or failed > 0:
            logger.info(f"Validation batch complete: {successful} successful, {failed} failed/deferred")

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
