# Database Fixtures Migration Guide

## Overview

This guide helps migrate existing database tests to use the new standardized fixtures from `tests/fixtures/database_fixtures.py`.

## Benefits of Migration

1. **Reduced Boilerplate**: No more manual mock setup in each test
2. **Consistency**: All tests use the same mock patterns
3. **Maintainability**: Changes to mock behavior in one place
4. **Better Isolation**: Fixtures handle setup/teardown automatically
5. **Reusable Data**: Pre-populated fixtures for common scenarios

## Available Fixtures

### Basic Mocks
- `mock_db_manager` - Mock DatabaseManager instance
- `mock_db_connection` - Mock database connection
- `mock_cursor` - Mock database cursor

### Pre-populated Data
- `populated_stamp_db` - Cursor with sample stamp data
- `populated_src20_db` - Cursor with sample SRC-20 data
- `mock_transaction_response` - Sample transaction data
- `mock_block_response` - Sample block data

### Error Testing
- `mock_db_with_errors` - Cursor that raises exceptions
- `db_error_scenarios` - List of common error scenarios

### Utilities
- `assert_database_called` - Helper for verifying DB calls
- `mock_database_transaction` - Context manager for transactions

## Migration Examples

### Example 1: Simple Query Test

**Before:**
```python
def test_get_stamp(self):
    # Manual mock setup
    mock_db = Mock()
    mock_cursor = Mock()
    mock_db.cursor.return_value.__enter__.return_value = mock_cursor
    mock_cursor.fetchone.return_value = {'cpid': 'A123', 'stamp': 'TEST'}
    
    # Test the function
    result = get_stamp(mock_db, 'A123')
    assert result['stamp'] == 'TEST'
```

**After:**
```python
def test_get_stamp(self, mock_db_connection, mock_cursor):
    # Fixtures provide ready-to-use mocks
    mock_cursor.fetchone.return_value = {'cpid': 'A123', 'stamp': 'TEST'}
    
    # Test the function
    result = get_stamp(mock_db_connection, 'A123')
    assert result['stamp'] == 'TEST'
```

### Example 2: Using Pre-populated Data

**Before:**
```python
def test_list_stamps(self):
    # Manual data setup
    mock_cursor = Mock()
    test_data = [
        {'cpid': 'A123', 'stamp': 'STAMP1'},
        {'cpid': 'A456', 'stamp': 'STAMP2'}
    ]
    mock_cursor.fetchall.return_value = test_data
    # ... rest of test
```

**After:**
```python
def test_list_stamps(self, populated_stamp_db):
    # Fixture provides pre-configured data
    cursor = populated_stamp_db
    cursor.execute("SELECT * FROM stamps")
    results = cursor.fetchall()
    
    assert len(results) == 2
    assert results[0]['stamp'] == 'STAMPY'
```

### Example 3: Error Handling

**Before:**
```python
def test_database_error(self):
    mock_cursor = Mock()
    mock_cursor.execute.side_effect = Exception("DB Error")
    
    with pytest.raises(Exception):
        some_db_function(mock_cursor)
```

**After:**
```python
def test_database_error(self, mock_db_with_errors):
    with pytest.raises(Exception) as exc_info:
        some_db_function(mock_db_with_errors)
    
    assert "Database error" in str(exc_info.value)
```

### Example 4: Transaction Testing

**Before:**
```python
def test_transaction(self):
    mock_db = Mock()
    # Complex setup for transaction testing...
    try:
        # Test code
        mock_db.commit()
    except:
        mock_db.rollback()
        raise
```

**After:**
```python
def test_transaction(self, mock_db_connection):
    from tests.fixtures.database_fixtures import mock_database_transaction
    
    with mock_database_transaction(mock_db_connection) as (db, cursor):
        # Test code - commit/rollback handled automatically
        cursor.execute("INSERT INTO ...")
```

## Migration Checklist

1. [ ] Identify tests with manual database mocks
2. [ ] Add appropriate fixtures to test method parameters
3. [ ] Remove manual mock setup code
4. [ ] Replace mock configuration with fixture usage
5. [ ] Use `assert_database_called` for verification
6. [ ] Run tests to ensure they still pass
7. [ ] Remove unused imports (Mock, MagicMock, etc.)

## Best Practices

1. **Use specific fixtures**: Choose the most appropriate fixture for your test
2. **Avoid modifying fixtures**: If you need different data, create a new fixture
3. **Keep fixtures focused**: Each fixture should have a single responsibility
4. **Document custom fixtures**: Add docstrings explaining what the fixture provides
5. **Share fixtures**: Put reusable fixtures in `conftest.py` or `database_fixtures.py`

## Common Patterns

### Pattern 1: Query with Parameters
```python
def test_query_with_params(self, mock_cursor, assert_database_called):
    # Execute query
    mock_cursor.execute("SELECT * FROM stamps WHERE cpid = %s", ('A123',))
    
    # Verify using helper
    assert_database_called(
        mock_cursor,
        expected_query="SELECT * FROM stamps",
        expected_params=('A123',),
        times=1
    )
```

### Pattern 2: Multiple Queries
```python
def test_multiple_queries(self, mock_cursor):
    # Configure different responses
    mock_cursor.fetchone.side_effect = [
        {'id': 1, 'name': 'First'},
        {'id': 2, 'name': 'Second'}
    ]
    
    # Test multiple calls
    result1 = get_by_id(mock_cursor, 1)
    result2 = get_by_id(mock_cursor, 2)
    
    assert result1['name'] == 'First'
    assert result2['name'] == 'Second'
```

### Pattern 3: Testing None/Empty Results
```python
def test_no_results(self, mock_cursor):
    # Fixture defaults to empty results
    mock_cursor.fetchall.return_value = []
    mock_cursor.fetchone.return_value = None
    
    # Test handling of no data
    results = get_all_stamps(mock_cursor)
    assert results == []
```

## Gradual Migration

You don't need to migrate all tests at once:

1. Start with new tests - use fixtures from the beginning
2. Migrate tests when you're already modifying them
3. Focus on tests with the most boilerplate first
4. Create additional fixtures as patterns emerge
5. Share successful patterns with the team

## Need Help?

- See `tests/test_database_fixtures_example.py` for complete examples
- Check existing migrated tests for patterns
- Add new fixtures to `database_fixtures.py` as needed
- Ask team members who have successfully migrated tests