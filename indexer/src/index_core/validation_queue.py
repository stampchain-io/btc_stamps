import logging
import os
import sqlite3
import threading
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

VALIDATION_QUEUE_TABLE = "src20_validation_queue"
VALIDATION_QUEUE_DB = "validation_queue.db"


class ValidationQueueManager:
    """Manages a queue of blocks that need SRC-20 validation when API becomes available."""

    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self, db_path: Optional[str] = None):
        """Initialize SQLite-based validation queue."""
        if ValidationQueueManager._instance is not None:
            raise Exception("Singleton instance already exists")

        # Use similar pattern to reprocessing queue for SQLite DB path
        if db_path is None:
            # Create validation queue DB in same directory as other SQLite DBs
            base_dir = os.path.dirname(os.path.abspath(__file__))
            db_path = os.path.join(base_dir, "..", "..", VALIDATION_QUEUE_DB)
            db_path = os.path.abspath(db_path)

        self.db_path = db_path
        self.lock = threading.Lock()

        # Initialize SQLite connection with WAL mode for thread safety
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.row_factory = sqlite3.Row  # Enable column access by name

        logger.info(f"Initializing validation queue at: {self.db_path}")
        self._ensure_table_exists()

    def _ensure_table_exists(self):
        """Create the validation queue table if it doesn't exist."""
        with self.lock:
            self.conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {VALIDATION_QUEUE_TABLE} (
                    block_index INTEGER PRIMARY KEY,
                    local_ledger_hash TEXT NOT NULL,
                    valid_src20_str TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    retry_count INTEGER DEFAULT 0,
                    last_retry_at TIMESTAMP DEFAULT NULL,
                    validated_at TIMESTAMP DEFAULT NULL,
                    validation_status TEXT CHECK(validation_status IN ('pending', 'valid', 'mismatch', 'api_error')) DEFAULT 'pending',
                    api_ledger_hash TEXT,
                    error_message TEXT
                )
            """)

            # Create index for efficient queries
            self.conn.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_validation_queue_status
                ON {VALIDATION_QUEUE_TABLE} (validation_status, retry_count)
            """)

            self.conn.commit()
            logger.info(f"Ensured {VALIDATION_QUEUE_TABLE} table exists")

    def add_to_queue(self, block_index: int, local_ledger_hash: str, valid_src20_str: str) -> None:
        """Add a block to the validation queue when processed with FORCE=True."""
        with self.lock:
            try:
                self.conn.execute(
                    f"""
                    INSERT OR REPLACE INTO {VALIDATION_QUEUE_TABLE}
                    (block_index, local_ledger_hash, valid_src20_str, validation_status, created_at)
                    VALUES (?, ?, ?, 'pending', datetime('now'))
                """,
                    (block_index, local_ledger_hash, valid_src20_str),
                )

                self.conn.commit()
                logger.info(f"Added block {block_index} to validation queue")
            except Exception as e:
                logger.error(f"Failed to add block {block_index} to validation queue: {e}")
                raise

    def get_pending_validations(self, limit: int = 100) -> List[Tuple[int, str, str]]:
        """Get blocks pending validation, ordered by block index."""
        with self.lock:
            # Calculate cutoff time for retries
            cutoff_time = (datetime.now() - timedelta(minutes=5)).isoformat()

            cursor = self.conn.execute(
                f"""
                SELECT block_index, local_ledger_hash, valid_src20_str
                FROM {VALIDATION_QUEUE_TABLE}
                WHERE validation_status = 'pending'
                AND (last_retry_at IS NULL OR last_retry_at < ?)
                AND retry_count < 10
                ORDER BY block_index
                LIMIT ?
            """,
                (cutoff_time, limit),
            )

            return [(row[0], row[1], row[2]) for row in cursor.fetchall()]

    def mark_validated(self, block_index: int, api_ledger_hash: str, is_valid: bool) -> None:
        """Mark a block as validated with the result."""
        with self.lock:
            status = "valid" if is_valid else "mismatch"

            self.conn.execute(
                f"""
                UPDATE {VALIDATION_QUEUE_TABLE}
                SET validation_status = ?,
                    api_ledger_hash = ?,
                    validated_at = datetime('now')
                WHERE block_index = ?
            """,
                (status, api_ledger_hash, block_index),
            )

            self.conn.commit()

            if not is_valid:
                logger.error(f"❌ Validation mismatch detected for block {block_index} during retroactive check!")
                # Here we could trigger additional actions like notifications

    def mark_api_error(self, block_index: int, error_message: str) -> None:
        """Mark a validation attempt as failed due to API error."""
        with self.lock:
            self.conn.execute(
                f"""
                UPDATE {VALIDATION_QUEUE_TABLE}
                SET retry_count = retry_count + 1,
                    last_retry_at = datetime('now'),
                    error_message = ?
                WHERE block_index = ?
            """,
                (error_message, block_index),
            )

            self.conn.commit()

    def get_validation_stats(self) -> dict:
        """Get statistics about the validation queue."""
        with self.lock:
            cursor = self.conn.execute(f"""
                SELECT
                    validation_status,
                    COUNT(*) as count,
                    MIN(block_index) as min_block,
                    MAX(block_index) as max_block
                FROM {VALIDATION_QUEUE_TABLE}
                GROUP BY validation_status
            """)

            stats = {}
            for row in cursor.fetchall():
                status, count, min_block, max_block = row
                stats[status] = {"count": count, "min_block": min_block, "max_block": max_block}

            return stats

    def get_mismatches(self) -> List[dict]:
        """Get all blocks with validation mismatches."""
        with self.lock:
            cursor = self.conn.execute(f"""
                SELECT block_index, local_ledger_hash, api_ledger_hash, validated_at
                FROM {VALIDATION_QUEUE_TABLE}
                WHERE validation_status = 'mismatch'
                ORDER BY block_index
            """)

            mismatches = []
            for row in cursor.fetchall():
                mismatches.append({"block_index": row[0], "local_hash": row[1], "api_hash": row[2], "validated_at": row[3]})

            return mismatches

    def cleanup_old_entries(self, days: int = 7) -> int:
        """Clean up old validated entries to prevent DB growth."""
        with self.lock:
            cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

            cursor = self.conn.execute(
                f"""
                DELETE FROM {VALIDATION_QUEUE_TABLE}
                WHERE validation_status IN ('valid', 'api_error')
                AND validated_at < ?
            """,
                (cutoff_date,),
            )

            self.conn.commit()
            deleted = cursor.rowcount

            if deleted > 0:
                logger.info(f"Cleaned up {deleted} old validation entries")

            return deleted
