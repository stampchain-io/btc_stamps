import logging
import time
import uuid
from contextlib import contextmanager
from typing import Any, Dict, Optional

import config

from .database_manager import DatabaseManager

logger = logging.getLogger(__name__)


class MonitoringLogger:
    """Enhanced logging for API calls and processing metrics."""

    def __init__(self):
        self.db_manager = DatabaseManager()

    @contextmanager
    def log_api_call(self, endpoint: str, method: str = "GET"):
        """Context manager to log API calls with timing and success/failure."""
        correlation_id = str(uuid.uuid4())[:8]
        start_time = time.time()
        success = False
        status_code = None
        error_message = None

        logger.info(
            "API_CALL_START",
            extra={"correlation_id": correlation_id, "endpoint": endpoint, "method": method, "timestamp": start_time},
        )

        try:
            yield correlation_id
            success = True
            status_code = 200  # Assume success if no exception
        except Exception as e:
            error_message = str(e)
            status_code = getattr(e, "status_code", 500)
            logger.error(
                "API_CALL_ERROR", extra={"correlation_id": correlation_id, "endpoint": endpoint, "error": error_message}
            )
            raise
        finally:
            response_time_ms = int((time.time() - start_time) * 1000)

            # Log to database for frontend consumption
            self._log_to_database(
                endpoint=endpoint,
                method=method,
                status_code=status_code,
                response_time_ms=response_time_ms,
                success=success,
                error_message=error_message,
            )

            # Structured log for troubleshooting
            logger.info(
                "API_CALL_COMPLETE",
                extra={
                    "correlation_id": correlation_id,
                    "endpoint": endpoint,
                    "method": method,
                    "success": success,
                    "response_time_ms": response_time_ms,
                    "status_code": status_code,
                },
            )

    def _log_to_database(
        self,
        endpoint: str,
        method: str,
        status_code: Optional[int],
        response_time_ms: int,
        success: bool,
        error_message: Optional[str],
    ):
        """Log API call data to database table for frontend queries."""
        db = None
        try:
            db = self.db_manager.connect()
            with db.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO api_call_log
                    (endpoint, method, status_code, response_time_ms, success, error_message)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """,
                    (endpoint, method, status_code, response_time_ms, success, error_message),
                )
                db.commit()
        except Exception as e:
            # Don't let monitoring failures break the main flow
            logger.warning(f"Failed to log API call to database: {e}")
        finally:
            if db is not None:
                db.close()

    def log_processing_metric(self, metric_name: str, value: Any, **context: Any):
        """Log processing metrics with structured format."""
        logger.info(
            "PROCESSING_METRIC", extra={"metric_name": metric_name, "value": value, "timestamp": time.time(), **context}
        )

    def log_queue_status(self, queue_stats: Dict[str, Any]):
        """Log reprocessing queue status for monitoring."""
        logger.info("QUEUE_STATUS", extra={"queue_stats": queue_stats, "timestamp": time.time()})

        # Alert if queue size exceeds threshold
        pending_items = queue_stats.get("pending", 0)
        if pending_items > getattr(config, "QUEUE_ALERT_SIZE", 50):
            logger.warning(
                "QUEUE_ALERT",
                extra={
                    "alert_type": "high_queue_size",
                    "pending_items": pending_items,
                    "threshold": getattr(config, "QUEUE_ALERT_SIZE", 50),
                },
            )


# Global instance for easy import
monitoring_logger = MonitoringLogger()
