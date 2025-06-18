# Bitcoin Stamps Indexer Test Suite

## Test Organization

Our test suite uses pytest markers to categorize tests based on their dependencies and characteristics. This allows for flexible test execution in different environments (CI, local development, etc.).

## Pytest Markers

### Available Markers

1. **`@pytest.mark.unit`** - Pure unit tests with no external dependencies
   - Use when: Test uses only mocks and doesn't require database/network
   - Example: Testing utility functions, data transformations

2. **`@pytest.mark.integration`** - Integration tests requiring external services
   - Use when: Test filename contains "integration" or tests end-to-end workflows
   - Example: API integration tests, full pipeline tests

3. **`@pytest.mark.requires_db`** - Tests that need database access
   - Use when: Test uses DatabaseManager, executes SQL, or needs database state
   - Example: Database operation tests, transaction tests

4. **`@pytest.mark.requires_network`** - Tests that make network calls
   - Use when: Test uses requests, Bitcoin RPC, or external APIs
   - Example: Blockchain tests, market data API tests

5. **`@pytest.mark.slow`** - Tests that take significant time to run
   - Use when: Test has sleep() calls, large loops, or performance benchmarks
   - Example: Stress tests, performance tests

## Guidelines for New Tests

### 1. Always Add Appropriate Markers

Every new test should have at least one marker. If unsure, run:
```bash
poetry run python tools/apply_test_markers.py
```

### 2. Marker Selection Guide

```python
# Unit test example
@pytest.mark.unit
def test_calculate_hash():
    """Test hash calculation with mocked inputs."""
    with patch('some.module'):
        assert calculate_hash("data") == "expected_hash"

# Database test example  
@pytest.mark.requires_db
def test_database_insert(db_connection):
    """Test database insertion."""
    cursor = db_connection.cursor()
    cursor.execute("INSERT INTO...")
    
# Integration test example
@pytest.mark.integration
@pytest.mark.requires_network
def test_bitcoin_rpc_integration():
    """Test Bitcoin RPC integration."""
    response = bitcoin_client.getblockcount()
```

### 3. Multiple Markers

Tests can have multiple markers:
```python
@pytest.mark.integration
@pytest.mark.requires_db
@pytest.mark.requires_network
@pytest.mark.slow
def test_full_block_processing():
    """Test complete block processing pipeline."""
    # Test that uses database, network, and takes time
```

## Running Tests

### CI Environment (Unit Tests Only)
```bash
# Default in CI - excludes integration tests
poetry run pytest -m "not integration"

# Or use the run_checks tool
poetry run run-checks
```

### Local Development (All Tests)
```bash
# Run everything
poetry run pytest

# Run only unit tests
poetry run pytest -m "unit"

# Run tests that don't need external services  
poetry run pytest -m "not requires_db and not requires_network"

# Run only integration tests (requires local services)
poetry run pytest -m "integration"
```

### Coverage Reports
```bash
# Quick coverage (excludes integration tests)
poetry run coverage-quick

# Full coverage analysis
poetry run pytest --cov=src --cov-report=html
```

## Test Detection Patterns

The `apply_test_markers.py` tool detects test types based on:

### Database Patterns
- `DatabaseManager`, `.connect()`, `.cursor()`, `.execute()`
- SQL keywords: `INSERT INTO`, `SELECT FROM`, `UPDATE SET`

### Network Patterns
- `requests.`, `urllib`, `http.client`
- Bitcoin RPC: `backend_instance`, `getblockcount`, `getblockhash`
- APIs: `api.kucoin`, `api.openstamp`, `api.stampscan`

### Integration Patterns
- Filename contains "integration"
- End-to-end workflows

### Unit Test Patterns
- Uses `@patch`, `MagicMock`, `Mock()`
- No database or network patterns detected

## Maintaining Test Quality

1. **Check for missing markers**: Run `poetry run python tools/apply_test_markers.py` regularly
2. **Update markers when test changes**: If a unit test starts using database, add `@pytest.mark.requires_db`
3. **Keep tests focused**: Prefer many small unit tests over few large integration tests
4. **Mock external dependencies**: Use mocks in unit tests to avoid needing `requires_db`/`requires_network`

## Common Issues

### "Test not running in CI"
- Check if test has `@pytest.mark.integration` marker
- CI only runs tests without integration marker

### "Coverage dropped after adding markers"  
- Ensure test isn't marked as `integration` if it's actually a unit test
- Run `apply_test_markers.py` to verify correct markers

### "Test fails in CI but passes locally"
- Test might be missing `requires_db` or `requires_network` marker
- Check for hardcoded paths or environment assumptions