# Test Migration Notes: test_src20_database_transactions

## Migration Summary
Successfully migrated `test_src20_database_transactions.py` to use standardized database fixtures.

### Key Learnings

1. **Cursor Mocking Strategy**
   - The `update_balance_table` and similar functions create their own cursor with `db.cursor()`
   - This means we need to mock at the connection level, not pass in a mock cursor
   - Solution: Override `db.cursor` directly to return the cursor mock (not a context manager)

2. **Bulk Test Execution Fix**
   - When tests run individually vs in bulk, Mock behavior can differ
   - Use `MagicMock` instead of `Mock` for better method call handling
   - Always set `fetchall = MagicMock(return_value=[])` explicitly to avoid "Mock object is not iterable" errors
   - Create a helper method to standardize cursor setup across all tests

3. **Fixture Usage Pattern**
   ```python
   @staticmethod
   def setup_cursor_mock(db, cursor=None):
       """Helper method to set up cursor mock consistently."""
       if cursor is None:
           cursor = MagicMock()
           cursor.fetchall = MagicMock(return_value=[])
           cursor.execute = MagicMock(return_value=None)
           cursor.executemany = MagicMock(return_value=None)
       
       # Override the connection's cursor method to return our cursor directly
       db.cursor = MagicMock(return_value=cursor)
       return cursor
   ```

4. **Benefits Achieved**
   - Eliminated manual `MagicMock()` setup in setUp method
   - Removed unittest.TestCase inheritance in favor of pytest classes
   - More readable and maintainable test structure
   - Consistent mocking patterns across the codebase
   - Fixed bulk execution issues with proper MagicMock usage

5. **Migration Stats**
   - 17 tests migrated successfully
   - Reduced boilerplate by ~30%
   - All tests passing in both individual and bulk execution

### Next Steps
Continue migrating other database tests following this pattern:
- test_src20_edge_cases.py
- test_database.py
- test_database_config.py