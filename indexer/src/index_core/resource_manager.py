"""
Resource management utilities for handling resource cleanup and shutdown procedures.
"""

import logging
import threading

# Import stop_upload_worker
from index_core.async_upload import stop_upload_worker

logger = logging.getLogger(__name__)


def cleanup_resources(executor, zmq_notifier, update_cpids_future, db, cp_pipeline=None, market_data_scheduler_started=False):
    """Helper function to clean up resources safely."""
    logger.info("Starting cleanup...")

    # Set timeouts for each cleanup phase
    PIPELINE_TIMEOUT = 3  # seconds
    UPLOAD_WORKER_TIMEOUT = 5
    ZMQ_TIMEOUT = 2  # seconds
    DB_TIMEOUT = 2  # seconds

    # Helper function to run a task with timeout
    def run_with_timeout(task, timeout, task_name):
        """Run a task with timeout, force continue if it takes too long"""
        logger.info(f"Starting {task_name} cleanup (timeout: {timeout}s)...")

        # Create event for timeout tracking
        completed = threading.Event()

        def target():
            try:
                task()
                completed.set()
            except Exception as e:
                logger.error(f"Error in {task_name} cleanup: {e}")
                completed.set()

        thread = threading.Thread(target=target)
        thread.daemon = True
        thread.start()

        # Wait with timeout
        result = completed.wait(timeout)
        if not result:
            logger.warning(f"{task_name} cleanup timed out after {timeout}s, continuing with next phase")
        return result

    # Stop market data scheduler with timeout
    if market_data_scheduler_started:

        def stop_market_scheduler():
            try:
                from index_core.market_data_jobs import stop_market_data_jobs

                stop_market_data_jobs(timeout=10)
            except Exception as e:
                logger.error(f"Error stopping market data scheduler: {e}")

        run_with_timeout(stop_market_scheduler, 15, "market data scheduler")

    # Stop CP pipeline with timeout
    if cp_pipeline:

        def stop_pipeline():
            try:
                cp_pipeline.stop()
            except Exception as e:
                logger.error(f"Error stopping CP pipeline: {e}")

        run_with_timeout(stop_pipeline, PIPELINE_TIMEOUT, "CP pipeline")

    # Stop Async Upload Worker with timeout (Added)
    def stop_uploader():
        try:
            # This function already handles logging and executor shutdown internally
            stop_upload_worker()
        except Exception as e:
            logger.error(f"Error stopping async upload worker: {e}")

    run_with_timeout(stop_uploader, UPLOAD_WORKER_TIMEOUT, "Async Upload Worker")

    # Cancel any pending CPID updates
    if update_cpids_future and not update_cpids_future.done():
        logger.info("Cancelling pending CPID updates...")
        update_cpids_future.cancel()

    # Clean up ZMQ with timeout
    if zmq_notifier:

        def cleanup_zmq():
            try:
                zmq_notifier.cleanup()
            except Exception as e:
                logger.error(f"Error cleaning up ZMQ: {e}")

        run_with_timeout(cleanup_zmq, ZMQ_TIMEOUT, "ZMQ")

    # Clean up the main thread pool passed to the function (if it exists)
    # Note: The async_upload module has its own executor, stopped by stop_upload_worker
    if executor:
        logger.info("Shutting down main executor...")
        try:
            # Assuming this executor might be different from the upload one
            executor.shutdown(wait=True)  # Use wait=True for the main executor if needed
            logger.info("Main executor shutdown complete")
        except Exception as e:
            logger.error(f"Error shutting down main executor: {e}")

    # Commit any pending transactions and close DB with timeout
    def cleanup_db():
        try:
            logger.info("Finalizing database operations...")
            if db and not getattr(db, "_closed", True):
                try:
                    db.commit()
                    logger.info("Final commit successful")
                except Exception as e:
                    logger.error(f"Error during final commit: {e}")
                    try:
                        db.rollback()
                    except Exception:
                        pass
                finally:
                    try:
                        db.close()
                        logger.info("Database connection closed")
                    except Exception as e:
                        logger.error(f"Error closing database: {e}")
        except Exception as e:
            logger.error(f"Error during database cleanup: {e}")

    run_with_timeout(cleanup_db, DB_TIMEOUT, "database")

    logger.info("Cleanup complete")
    logging.shutdown()
