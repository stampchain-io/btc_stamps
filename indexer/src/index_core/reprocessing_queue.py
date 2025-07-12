import json
import logging
import random
import sqlite3
import threading
import time
from typing import Dict, List, Optional, Tuple

import config  # Assuming configs like REPROCESS_DB_PATH, REPROCESS_MAX_ATTEMPTS=5, REPROCESS_CLEANUP_AGE=86400 (24h)

logger = logging.getLogger(__name__)


def exponential_backoff(attempt: int, max_delay: int = 60) -> float:
    """Calculate exponential backoff delay with random jitter."""
    base_delay = min(2**attempt, max_delay)
    return base_delay + random.uniform(0, 0.1 * base_delay)  # Add 10% jitter


class ReprocessingQueue:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self, db_path: str = getattr(config, "REPROCESS_DB_PATH", "reprocess_queue.db")):
        """Initialize SQLite-based queue with WAL mode for thread-safety."""
        if ReprocessingQueue._instance is not None:
            raise Exception("Singleton instance already exists")
        self.db_path = db_path
        self.lock = threading.Lock()
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")  # Enable Write-Ahead Logging for concurrency
        self._create_table()
        self._init_fallback_table()
        self.migrate_old_json()

    def _create_table(self) -> None:
        """Create queue table if not exists."""
        with self.lock:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reprocess_queue (
                    tx_hash TEXT PRIMARY KEY,
                    attempts INTEGER DEFAULT 0,
                    next_retry_time REAL,  -- Unix timestamp
                    status TEXT DEFAULT 'pending',  -- pending, processing, failed, done
                    added_at REAL DEFAULT (unixepoch()),  -- Creation timestamp
                    last_attempt_at REAL  -- Last retry timestamp
                )
            """
            )
            self.conn.commit()

    def enqueue(self, tx_hash: str) -> None:
        """Add tx to queue with initial values."""
        with self.lock:
            try:
                self.conn.execute(
                    """
                    INSERT OR REPLACE INTO reprocess_queue
                    (tx_hash, attempts, next_retry_time, status, added_at, last_attempt_at)
                    VALUES (?, 0, ?, 'pending', unixepoch(), NULL)
                """,
                    (tx_hash, time.time() + exponential_backoff(0)),
                )
                self.conn.commit()
                logger.info(f"Enqueued tx {tx_hash} for reprocessing")
            except sqlite3.Error as e:
                logger.error(f"Failed to enqueue {tx_hash}: {e}")
                raise

    def dequeue(self, limit: int = 10) -> List[Tuple[str, int]]:
        """Get ready items (next_retry_time <= now, status=pending/failed), ordered by next_retry_time."""
        with self.lock:
            cur = self.conn.cursor()
            cur.execute(
                """
                SELECT tx_hash, attempts FROM reprocess_queue
                WHERE next_retry_time <= unixepoch() AND status IN ('pending', 'failed')
                ORDER BY next_retry_time ASC
                LIMIT ?
            """,
                (limit,),
            )
            items = cur.fetchall()
            # Mark as processing
            for tx_hash, _ in items:
                cur.execute('UPDATE reprocess_queue SET status = "processing" WHERE tx_hash = ?', (tx_hash,))
            self.conn.commit()
            return items

    def update_status(self, tx_hash: str, success: bool, error_msg: Optional[str] = None) -> None:
        """Update after processing: if success, mark done; else increment attempts and set next retry."""
        with self.lock:
            cur = self.conn.cursor()
            cur.execute("SELECT attempts FROM reprocess_queue WHERE tx_hash = ?", (tx_hash,))
            row = cur.fetchone()
            if not row:
                return
            attempts = row[0] + 1
            if success:
                cur.execute(
                    'UPDATE reprocess_queue SET status = "done", last_attempt_at = unixepoch() WHERE tx_hash = ?', (tx_hash,)
                )
                logger.info(f"Successfully reprocessed {tx_hash}")
            elif attempts >= getattr(config, "REPROCESS_MAX_ATTEMPTS", 5):
                cur.execute(
                    'UPDATE reprocess_queue SET attempts = ?, status = "failed", last_attempt_at = unixepoch() WHERE tx_hash = ?',
                    (attempts, tx_hash),
                )
                logger.error(f"Max attempts reached for {tx_hash}. Error: {error_msg}")
            else:
                delay = exponential_backoff(attempts)
                next_time = time.time() + delay
                cur.execute(
                    """
                    UPDATE reprocess_queue SET
                    attempts = ?,
                    next_retry_time = ?,
                    status = "failed",
                    last_attempt_at = unixepoch()
                    WHERE tx_hash = ?
                """,
                    (attempts, next_time, tx_hash),
                )
                logger.warning(f"Retry {attempts} for {tx_hash} in {delay}s. Error: {error_msg}")
            self.conn.commit()

    def cleanup(self) -> int:
        """Remove old done/failed items older than REPROCESS_CLEANUP_AGE seconds."""
        with self.lock:
            threshold: float = time.time() - getattr(config, "REPROCESS_CLEANUP_AGE", 86400)
            cur = self.conn.cursor()
            cur.execute('DELETE FROM reprocess_queue WHERE added_at < ? AND status IN ("done", "failed")', (threshold,))
            deleted = cur.rowcount
            self.conn.commit()
            if deleted > 0:
                logger.info(f"Cleaned up {deleted} old queue items")
            return deleted

    def get_status(self) -> dict[str, int]:
        """Get queue stats for monitoring."""
        with self.lock:
            cur = self.conn.cursor()
            cur.execute("SELECT status, COUNT(*) FROM reprocess_queue GROUP BY status")
            stats: dict[str, int] = dict(cur.fetchall())
            cur.execute(
                "SELECT COUNT(*) FROM reprocess_queue WHERE attempts >= ?", (getattr(config, "REPROCESS_MAX_ATTEMPTS", 5),)
            )
            stats["maxed_attempts"] = cur.fetchone()[0]
            return stats

    def close(self) -> None:
        """Close DB connection."""
        self.conn.close()

    def _init_fallback_table(self):
        """Initialize fallback states table if not exists."""
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS fallback_states (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    block_index INTEGER UNIQUE,
                    state_data TEXT NOT NULL,  -- JSON blob of failed_cp_blocks dict
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )
            self.conn.commit()
            cursor.close()

    def migrate_old_json(self, json_path: str = "fallback_state.json"):
        """Migrate existing JSON fallback to DB if file exists."""
        import json
        import os

        with self.lock:
            if os.path.exists(json_path):
                try:
                    with open(json_path, "r") as f:
                        state_data = json.load(f)
                    if state_data:
                        self.save_fallback_state(list(state_data.keys())[0] if state_data else 0, state_data)
                        os.rename(json_path, f"{json_path}.migrated")  # Backup old file
                        logger.info(f"Migrated fallback state from {json_path} to DB")
                except Exception as e:
                    logger.warning(f"Failed to migrate old JSON: {e}")

    def save_fallback_state(self, block_index: int, state_data: Dict) -> None:
        """Save failed_cp_blocks state as JSON blob."""
        state_json = json.dumps(state_data)
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO fallback_states
                (block_index, state_data, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            """,
                (block_index, state_json),
            )
            self.conn.commit()
            cursor.close()

    def load_fallback_state(self, block_index: int) -> Optional[Dict]:
        """Load failed_cp_blocks state for given block, return None if not found."""
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT state_data FROM fallback_states
                WHERE block_index = ?
            """,
                (block_index,),
            )
            result = cursor.fetchone()
            cursor.close()
            if result:
                return json.loads(result[0])
            return None

    def get_oldest_failed_block(self) -> Optional[int]:
        """Get the smallest failed block index from states."""
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT MIN(block_index) FROM fallback_states")
            result = cursor.fetchone()
            cursor.close()
            return result[0] if result and result[0] else None

    def clear_fallback_state(self, block_index: int) -> None:
        """Remove fallback state after successful processing."""
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM fallback_states WHERE block_index = ?", (block_index,))
            self.conn.commit()
            cursor.close()
            logger.info(f"Cleared fallback state for block {block_index}")

    def clear_all_fallbacks(self) -> None:
        """Clear all fallback states (e.g., after full recovery)."""
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM fallback_states")
            self.conn.commit()
            cursor.close()
            logger.info("Cleared all fallback states from DB")
