import logging
import random
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import config  # Assuming configs like REPROCESS_DB_PATH, REPROCESS_MAX_ATTEMPTS=5, REPROCESS_CLEANUP_AGE=86400 (24h)
from index_core.reprocess_safety import (
    ReprocessSafetyError,
    get_safe_reprocess_db_path,
    log_safety_check,
    validate_block_number,
    validate_fallback_state,
)

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

    def __init__(self, db_path: Optional[str] = None):
        """Initialize SQLite-based queue with WAL mode for thread-safety."""
        if ReprocessingQueue._instance is not None:
            raise Exception("Singleton instance already exists")

        # Use safety module to get appropriate DB path
        if db_path is None:
            db_path = get_safe_reprocess_db_path()

        self.db_path = db_path
        log_safety_check(f"Initializing reprocess queue at: {self.db_path}")
        self.lock = threading.Lock()
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")  # Enable Write-Ahead Logging for concurrency
        self._create_table()
        self._init_fallback_table()
        self.migrate_old_json()

    def _create_table(self) -> None:
        """Create queue table if not exists."""
        with self.lock:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS reprocess_queue (
                    tx_hash TEXT PRIMARY KEY,
                    attempts INTEGER DEFAULT 0,
                    next_retry_time REAL,  -- Unix timestamp
                    status TEXT DEFAULT 'pending',  -- pending, processing, failed, done
                    added_at REAL DEFAULT (CAST(strftime('%s', 'now') AS INTEGER)),  -- Creation timestamp
                    last_attempt_at REAL  -- Last retry timestamp
                )
            """)
            self.conn.commit()

    def enqueue(self, tx_hash: str) -> None:
        """Add tx to queue with initial values."""
        with self.lock:
            try:
                self.conn.execute(
                    """
                    INSERT OR REPLACE INTO reprocess_queue
                    (tx_hash, attempts, next_retry_time, status, added_at, last_attempt_at)
                    VALUES (?, 0, ?, 'pending', CAST(strftime('%s', 'now') AS INTEGER), NULL)
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
                WHERE next_retry_time <= CAST(strftime('%s', 'now') AS INTEGER) AND status IN ('pending', 'failed')
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
                    "UPDATE reprocess_queue SET status = \"done\", last_attempt_at = CAST(strftime('%s', 'now') AS INTEGER) WHERE tx_hash = ?",
                    (tx_hash,),
                )
                logger.info(f"Successfully reprocessed {tx_hash}")
            elif attempts >= getattr(config, "REPROCESS_MAX_ATTEMPTS", 5):
                cur.execute(
                    "UPDATE reprocess_queue SET attempts = ?, status = \"failed\", last_attempt_at = CAST(strftime('%s', 'now') AS INTEGER) WHERE tx_hash = ?",
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
                    last_attempt_at = CAST(strftime('%s', 'now') AS INTEGER)
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
        """Initialize fallback states table with normalized structure."""
        with self.lock:
            cursor = self.conn.cursor()
            # Create the main fallback sessions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS fallback_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    start_block_index INTEGER NOT NULL UNIQUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Create the failed blocks table (normalized)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS failed_blocks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    block_index INTEGER NOT NULL,
                    needs_reprocessing BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES fallback_sessions(id) ON DELETE CASCADE,
                    UNIQUE(session_id, block_index)
                )
            """)
            # Create indexes for performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_failed_blocks_session ON failed_blocks(session_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_failed_blocks_block_index ON failed_blocks(block_index)")
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_fallback_sessions_start_block ON fallback_sessions(start_block_index)"
            )

            self.conn.commit()
            cursor.close()

    def migrate_old_json(self, json_path: str = "fallback_state.json"):
        """Migrate existing JSON fallback to normalized DB structure if file exists."""
        import json
        import os

        with self.lock:
            if os.path.exists(json_path):
                try:
                    with open(json_path, "r") as f:
                        state_data = json.load(f)
                    if state_data:
                        # Migrate each block state to the new normalized structure
                        for block_index_str, block_state in state_data.items():
                            block_index = int(block_index_str)
                            # Create a session for this block
                            self._create_fallback_session(block_index)
                            # Add the failed block to the session
                            if isinstance(block_state, dict):
                                for failed_block_str, _ in block_state.items():
                                    failed_block = int(str(failed_block_str))
                                    self._add_failed_block_to_session(block_index, failed_block)
                            else:
                                # Simple case: just add the block itself
                                self._add_failed_block_to_session(block_index, block_index)

                        os.rename(json_path, f"{json_path}.migrated")  # Backup old file
                        logger.info(f"Migrated {len(state_data)} fallback states from {json_path} to normalized DB")
                except Exception as e:
                    logger.warning(f"Failed to migrate old JSON: {e}")

    def save_fallback_state(self, start_block_index: int, failed_blocks: Dict[int, bool]) -> None:
        """Save fallback state using normalized table structure."""
        # Safety validation before saving
        try:
            validate_fallback_state(start_block_index, failed_blocks)
            log_safety_check(f"Validated fallback state for block {start_block_index} with {len(failed_blocks)} failed blocks")
        except ReprocessSafetyError as e:
            logger.error(f"SAFETY VIOLATION: Cannot save fallback state: {e}")
            raise

        with self.lock:
            cursor = self.conn.cursor()
            try:
                # Create or update the fallback session
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO fallback_sessions
                    (start_block_index, updated_at)
                    VALUES (?, CURRENT_TIMESTAMP)
                    """,
                    (start_block_index,),
                )

                # Get the session ID
                cursor.execute("SELECT id FROM fallback_sessions WHERE start_block_index = ?", (start_block_index,))
                session_id = cursor.fetchone()[0]

                # Clear existing failed blocks for this session
                cursor.execute("DELETE FROM failed_blocks WHERE session_id = ?", (session_id,))

                # Insert all failed blocks
                for block_index, needs_reprocessing in failed_blocks.items():
                    cursor.execute(
                        """
                        INSERT INTO failed_blocks (session_id, block_index, needs_reprocessing)
                        VALUES (?, ?, ?)
                        """,
                        (session_id, block_index, needs_reprocessing),
                    )

                self.conn.commit()
                logger.debug(
                    f"Saved fallback state for session starting at block {start_block_index} with {len(failed_blocks)} failed blocks"
                )
            except sqlite3.Error as e:
                logger.error(f"Failed to save fallback state: {e}")
                self.conn.rollback()
                raise
            finally:
                cursor.close()

    def load_fallback_state(self, start_block_index: int) -> Optional[Dict[int, bool]]:
        """Load fallback state for given session start block, return None if not found."""
        # Validate block number before loading
        try:
            validate_block_number(start_block_index, "fallback load block")
        except ReprocessSafetyError as e:
            logger.error(f"SAFETY VIOLATION: Cannot load fallback state: {e}")
            # Return None instead of raising to prevent crash, but log the issue
            return None

        with self.lock:
            cursor = self.conn.cursor()
            try:
                # Get the session ID
                cursor.execute("SELECT id FROM fallback_sessions WHERE start_block_index = ?", (start_block_index,))
                session_result = cursor.fetchone()
                if not session_result:
                    return None

                session_id = session_result[0]

                # Get all failed blocks for this session
                cursor.execute(
                    """
                    SELECT block_index, needs_reprocessing FROM failed_blocks
                    WHERE session_id = ?
                    ORDER BY block_index
                    """,
                    (session_id,),
                )

                failed_blocks = {}
                for block_index, needs_reprocessing in cursor.fetchall():
                    failed_blocks[block_index] = bool(needs_reprocessing)

                return failed_blocks if failed_blocks else None
            except sqlite3.Error as e:
                logger.error(f"Failed to load fallback state: {e}")
                return None
            finally:
                cursor.close()

    def get_oldest_failed_block(self) -> Optional[int]:
        """Get the smallest failed block index from all sessions."""
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT MIN(start_block_index) FROM fallback_sessions")
            result = cursor.fetchone()
            cursor.close()
            return result[0] if result and result[0] else None

    def clear_fallback_state(self, start_block_index: int) -> None:
        """Remove fallback state after successful processing."""
        with self.lock:
            cursor = self.conn.cursor()
            try:
                # Delete the session (CASCADE will delete associated failed_blocks)
                cursor.execute("DELETE FROM fallback_sessions WHERE start_block_index = ?", (start_block_index,))
                deleted_sessions = cursor.rowcount
                self.conn.commit()

                if deleted_sessions > 0:
                    logger.info(f"Cleared fallback state for session starting at block {start_block_index}")
                else:
                    logger.debug(f"No fallback state found for session starting at block {start_block_index}")
            except sqlite3.Error as e:
                logger.error(f"Failed to clear fallback state: {e}")
                self.conn.rollback()
                raise
            finally:
                cursor.close()

    def clear_all_fallbacks(self) -> None:
        """Clear all fallback states (e.g., after full recovery)."""
        with self.lock:
            cursor = self.conn.cursor()
            try:
                cursor.execute("DELETE FROM fallback_sessions")  # CASCADE will delete failed_blocks
                deleted_sessions = cursor.rowcount
                self.conn.commit()
                logger.info(f"Cleared all fallback states from DB ({deleted_sessions} sessions)")
            except sqlite3.Error as e:
                logger.error(f"Failed to clear all fallback states: {e}")
                self.conn.rollback()
                raise
            finally:
                cursor.close()

    def _create_fallback_session(self, start_block_index: int) -> int:
        """Create a new fallback session and return its ID."""
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                """
                INSERT OR IGNORE INTO fallback_sessions (start_block_index)
                VALUES (?)
                """,
                (start_block_index,),
            )
            cursor.execute("SELECT id FROM fallback_sessions WHERE start_block_index = ?", (start_block_index,))
            session_id = cursor.fetchone()[0]
            return session_id
        finally:
            cursor.close()

    def _add_failed_block_to_session(self, start_block_index: int, failed_block_index: int) -> None:
        """Add a failed block to an existing session."""
        cursor = self.conn.cursor()
        try:
            # Get session ID
            cursor.execute("SELECT id FROM fallback_sessions WHERE start_block_index = ?", (start_block_index,))
            session_result = cursor.fetchone()
            if not session_result:
                raise ValueError(f"No fallback session found for start block {start_block_index}")

            session_id = session_result[0]

            # Add failed block
            cursor.execute(
                """
                INSERT OR IGNORE INTO failed_blocks (session_id, block_index, needs_reprocessing)
                VALUES (?, ?, TRUE)
                """,
                (session_id, failed_block_index),
            )
        finally:
            cursor.close()

    def get_fallback_stats(self) -> Dict[str, Any]:
        """Get comprehensive fallback state statistics."""
        with self.lock:
            cursor = self.conn.cursor()
            try:
                # Get session count
                cursor.execute("SELECT COUNT(*) FROM fallback_sessions")
                session_count = cursor.fetchone()[0]

                # Get total failed blocks
                cursor.execute("SELECT COUNT(*) FROM failed_blocks")
                total_failed_blocks = cursor.fetchone()[0]

                # Get blocks needing reprocessing
                cursor.execute("SELECT COUNT(*) FROM failed_blocks WHERE needs_reprocessing = TRUE")
                blocks_needing_reprocessing = cursor.fetchone()[0]

                # Get oldest session
                cursor.execute("SELECT MIN(start_block_index) FROM fallback_sessions")
                oldest_session = cursor.fetchone()[0]

                # Get newest session
                cursor.execute("SELECT MAX(start_block_index) FROM fallback_sessions")
                newest_session = cursor.fetchone()[0]

                return {
                    "session_count": session_count,
                    "total_failed_blocks": total_failed_blocks,
                    "blocks_needing_reprocessing": blocks_needing_reprocessing,
                    "oldest_session_start_block": oldest_session,
                    "newest_session_start_block": newest_session,
                }
            finally:
                cursor.close()
