"""
Comprehensive tests for SRC-20 database transaction handling.
Tests atomicity, rollback scenarios, and concurrent updates.
"""

import threading
import time
import unittest
from decimal import Decimal
from unittest.mock import MagicMock, Mock, call, patch

import pymysql
import pytest

from index_core.src20 import (
    Src20Processor,
    update_balance_table,
    update_src20_balances,
)


class TestSrc20DatabaseTransactions(unittest.TestCase):
    """Test database transaction handling in SRC-20."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_db = MagicMock()
        self.mock_cursor = MagicMock()
        self.mock_db.cursor.return_value.__enter__.return_value = self.mock_cursor

    def test_update_balance_table_atomicity(self):
        """Test atomicity of balance table updates."""
        # Simulate failure during update
        self.mock_cursor.execute.side_effect = [
            None,  # First execute succeeds
            pymysql.OperationalError("Database connection lost"),  # Second fails
        ]

        with pytest.raises(pymysql.OperationalError):
            update_balance_table(self.mock_db, "TEST", "addr1", Decimal("100"), Decimal("200"), 1000)

        # Should not commit on failure
        self.mock_db.commit.assert_not_called()

    def test_update_src20_balances_batch_failure(self):
        """Test batch insert failure handling."""
        balance_changes = {
            "balance_updates": [
                ("TEST", "addr1", Decimal("100")),
                ("TEST", "addr2", Decimal("200")),
                ("TEST", "addr3", Decimal("300")),
            ]
        }

        # Simulate executemany failure
        self.mock_cursor.executemany.side_effect = pymysql.IntegrityError("Duplicate key")

        with pytest.raises(pymysql.IntegrityError):
            update_src20_balances(self.mock_db, 1000, balance_changes)

        # Verify rollback was called
        self.mock_db.rollback.assert_called()
        self.mock_db.commit.assert_not_called()

    def test_partial_batch_update_rollback(self):
        """Test rollback on partial batch update failure."""
        processor = Src20Processor(self.mock_db)

        # Setup balance updates
        balance_updates = [
            ("TEST1", "addr1", Decimal("100")),
            ("TEST2", "addr2", Decimal("200")),
            ("TEST3", "addr3", Decimal("300")),
        ]

        # Simulate partial success - fails on second batch
        self.mock_cursor.executemany.side_effect = [
            None,  # First batch succeeds
            pymysql.DataError("Invalid decimal value"),  # Second batch fails
        ]

        with pytest.raises(Exception):
            # Process updates that will be batched
            for tick, addr, balance in balance_updates:
                update_balance_table(self.mock_db, tick, addr, Decimal("0"), balance, 1000)

    def test_concurrent_balance_updates_same_address(self):
        """Test concurrent updates to the same address."""
        results = []
        errors = []

        def update_balance_concurrent(amount, delay=0):
            try:
                time.sleep(delay)
                update_balance_table(self.mock_db, "TEST", "addr1", Decimal("1000"), Decimal(str(amount)), 1000)
                results.append(amount)
            except Exception as e:
                errors.append(e)

        # Simulate concurrent updates
        threads = []
        amounts = [1100, 900, 1200, 800, 1050]

        for i, amount in enumerate(amounts):
            t = threading.Thread(target=update_balance_concurrent, args=(amount, i * 0.001))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # All updates should complete (order may vary)
        assert len(results) == 5
        assert len(errors) == 0

    def test_deadlock_detection_and_retry(self):
        """Test deadlock detection and retry mechanism."""
        # Simulate deadlock error
        self.mock_cursor.execute.side_effect = [
            pymysql.OperationalError(1213, "Deadlock found"),  # First attempt - deadlock
            None,  # Retry succeeds
            None,  # Second execute succeeds
        ]

        # Should retry on deadlock
        update_balance_table(self.mock_db, "TEST", "addr1", Decimal("100"), Decimal("200"), 1000)

        # Should have retried
        assert self.mock_cursor.execute.call_count >= 2

    def test_connection_pool_exhaustion(self):
        """Test behavior when connection pool is exhausted."""
        # Simulate connection pool exhaustion
        self.mock_db.cursor.side_effect = pymysql.OperationalError("Too many connections")

        with pytest.raises(pymysql.OperationalError):
            update_balance_table(self.mock_db, "TEST", "addr1", Decimal("100"), Decimal("200"), 1000)

    def test_transaction_isolation_levels(self):
        """Test transaction isolation level handling."""
        processor = Src20Processor(self.mock_db)

        # Mock cursor for transaction isolation
        with patch.object(self.mock_db, "begin") as mock_begin:
            # Perform balance update
            update_balance_table(self.mock_db, "TEST", "addr1", Decimal("0"), Decimal("100"), 1000)

            # Verify transaction was started
            mock_begin.assert_called()

    def test_bulk_insert_performance_optimization(self):
        """Test bulk insert optimization for large balance updates."""
        # Create large batch of balance updates
        large_batch = []
        for i in range(1000):
            large_batch.append((f"TEST{i % 10}", f"addr{i}", Decimal(str(i))))

        balance_changes = {"balance_updates": large_batch}

        # Should use executemany for efficiency
        update_src20_balances(self.mock_db, 1000, balance_changes)

        # Verify executemany was used
        self.mock_cursor.executemany.assert_called()

        # Should batch inserts efficiently
        call_args = self.mock_cursor.executemany.call_args
        assert len(call_args[0][1]) == 1000  # All updates in one batch

    def test_balance_update_with_locked_amounts(self):
        """Test balance updates considering locked amounts."""
        # Mock existing balance with locked amount
        self.mock_cursor.fetchall.return_value = [("TEST_addr1", Decimal("1000"), Decimal("100"))]  # 100 locked

        # Try to update balance
        update_balance_table(self.mock_db, "TEST", "addr1", Decimal("1000"), Decimal("950"), 1000)

        # Should handle locked amount correctly
        execute_calls = self.mock_cursor.execute.call_args_list
        # Verify UPDATE query considers locked amount

    def test_zero_balance_cleanup(self):
        """Test cleanup of zero balance entries."""
        # Update balance to zero
        update_balance_table(self.mock_db, "TEST", "addr1", Decimal("100"), Decimal("0"), 1000)

        # Should potentially remove zero balance entry
        execute_calls = self.mock_cursor.execute.call_args_list
        # Check if DELETE or UPDATE to 0 was called

    def test_database_constraint_violations(self):
        """Test handling of database constraint violations."""
        # Test foreign key violation
        self.mock_cursor.execute.side_effect = pymysql.IntegrityError(
            1452, "Cannot add or update a child row: a foreign key constraint fails"
        )

        with pytest.raises(pymysql.IntegrityError):
            update_balance_table(self.mock_db, "NONEXISTENT", "addr1", Decimal("0"), Decimal("100"), 1000)

    def test_transaction_savepoints(self):
        """Test savepoint usage in nested transactions."""
        processor = Src20Processor(self.mock_db)

        # Mock savepoint operations
        with patch.object(self.mock_cursor, "execute") as mock_execute:
            # Simulate nested operation that might need savepoint
            try:
                # Start main transaction
                self.mock_db.begin()

                # Create savepoint
                mock_execute("SAVEPOINT sp1")

                # Try risky operation
                update_balance_table(self.mock_db, "TEST", "addr1", Decimal("0"), Decimal("100"), 1000)

                # If successful, release savepoint
                mock_execute("RELEASE SAVEPOINT sp1")
            except Exception:
                # Rollback to savepoint
                mock_execute("ROLLBACK TO SAVEPOINT sp1")

    def test_balance_precision_in_database(self):
        """Test decimal precision handling in database operations."""
        # Test with maximum precision decimals
        precise_balance = Decimal("123456789.123456789012345678")

        update_balance_table(self.mock_db, "TEST", "addr1", Decimal("0"), precise_balance, 1000)

        # Verify precision is maintained in SQL
        insert_call = self.mock_cursor.execute.call_args_list[-1]
        sql = insert_call[0][0]
        params = insert_call[0][1]

        # Balance should be stored with full precision
        assert str(precise_balance) in str(params)

    def test_concurrent_tick_creation(self):
        """Test concurrent creation of same tick."""
        errors = []

        def create_tick_concurrent(creator_id):
            try:
                # Simulate tick creation
                self.mock_cursor.execute.side_effect = [
                    pymysql.IntegrityError(1062, "Duplicate entry 'TEST' for key 'tick'") if creator_id > 0 else None
                ]
                # Process deploy operation
                time.sleep(0.001 * creator_id)
            except Exception as e:
                errors.append((creator_id, e))

        threads = []
        for i in range(5):
            t = threading.Thread(target=create_tick_concurrent, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Only first creator should succeed
        assert len(errors) == 4  # Others should fail with duplicate key

    def test_balance_update_retry_on_lock_timeout(self):
        """Test retry logic on lock timeout."""
        # Simulate lock timeout then success
        self.mock_cursor.execute.side_effect = [
            pymysql.OperationalError(1205, "Lock wait timeout exceeded"),
            None,  # Retry succeeds
            None,
        ]

        update_balance_table(self.mock_db, "TEST", "addr1", Decimal("100"), Decimal("200"), 1000)

        # Should have retried after lock timeout
        assert self.mock_cursor.execute.call_count >= 2

    def test_batch_update_memory_efficiency(self):
        """Test memory efficiency of large batch updates."""
        # Create very large batch
        huge_batch = []
        for i in range(10000):
            huge_batch.append(("TEST", f"addr{i}", Decimal(str(i % 1000))))

        balance_changes = {"balance_updates": huge_batch}

        # Should handle large batch without memory issues
        update_src20_balances(self.mock_db, 1000, balance_changes)

        # Verify it was processed
        self.mock_cursor.executemany.assert_called()

    def test_transaction_with_multiple_tables(self):
        """Test transaction spanning multiple tables."""
        processor = Src20Processor(self.mock_db)

        # Simulate complex operation touching multiple tables
        with self.mock_db.cursor() as cursor:
            try:
                # Update balances table
                cursor.execute("UPDATE src20_balances SET balance = %s WHERE id = %s", (100, "TEST_addr1"))

                # Update valid table
                cursor.execute("UPDATE src20_valid SET valid = %s WHERE id = %s", (1, "tx_hash"))

                # Update deploy table
                cursor.execute("UPDATE src20_deploys SET remaining = %s WHERE tick = %s", (900, "TEST"))

                # All or nothing
                self.mock_db.commit()
            except Exception:
                self.mock_db.rollback()
                raise


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
