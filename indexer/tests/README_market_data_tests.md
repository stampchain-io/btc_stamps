# Market Data Test Suite

This document describes the test cases for the market data functionality in the Bitcoin Stamps indexer.

## Test Files

### 1. `test_market_data_service.py`

This file contains comprehensive tests for the `MarketDataService` class, including tests for the SQL query construction bugs that were fixed.

#### TestMarketDataBugFixes Class

This class specifically tests the fixes for the market data bugs:

- **test_update_src20_sql_query_construction**: Verifies that the SQL query for SRC-20 updates uses the `VALUES()` function correctly in the `ON DUPLICATE KEY UPDATE` clause.

- **test_update_collection_hex_string_handling**: Ensures collection IDs are properly handled as hex strings with `UNHEX()` function.

- **test_field_filtering_removes_invalid_fields**: Tests that invalid fields and primary keys are filtered out before SQL construction.

- **test_empty_data_logs_warning**: Verifies that empty data dictionaries log warnings and don't execute SQL.

- **test_get_collection_with_hex_query**: Tests that `get_collection_market_data` uses `HEX()` in SELECT queries.

- **test_decimal_precision_preserved**: Ensures Decimal precision is maintained through updates.

- **test_null_values_handled_correctly**: Verifies proper handling of None/NULL values.

### 2. `test_market_data_jobs.py`

This file tests the market data job scheduler functionality.

#### TestMarketDataJobScheduler Class

Tests for the background job scheduler:

- **test_get_collections_needing_update_returns_hex_strings**: Verifies that collection IDs are returned as hex strings from the database query.

- **test_process_collection_update_no_collection_id_in_data**: Ensures collection_id is passed as a parameter, not in the data dict.

- **test_process_src20_batch_no_tick_in_data**: Verifies that tick is passed as a parameter, not in the data dict.

- **test_transform_counterparty_asset_no_cpid_in_data**: Tests that cpid is not included in transformed market data.

- **test_get_stamps_needing_update_query**: Verifies the SQL query structure for getting stamps.

- **test_get_src20_tokens_needing_update_query**: Tests the SQL query for getting SRC-20 tokens.

- **test_error_handling_in_get_collections**: Tests error handling when database queries fail.

- **test_split_into_batches**: Tests the batch splitting utility function.

- **test_update_stamp_market_data_job_integration**: Integration test for the stamp update job flow.

## Running the Tests

To run all market data tests:
```bash
cd indexer
poetry run pytest tests/test_market_data_service.py tests/test_market_data_jobs.py -v
```

To run only the bug fix tests:
```bash
poetry run pytest tests/test_market_data_service.py::TestMarketDataBugFixes -v
```

To run with coverage:
```bash
poetry run pytest tests/test_market_data_service.py tests/test_market_data_jobs.py --cov=index_core.market_data_service --cov=index_core.market_data_jobs
```

## Key Bugs Fixed

1. **SQL Query Construction Error**: The `INSERT INTO ... ON DUPLICATE KEY UPDATE` queries were using incorrect parameter handling. Fixed by using `VALUES(column)` syntax.

2. **Collection ID Format Issue**: Collection IDs were being returned as binary data instead of hex strings. Fixed by using `HEX()` function in SQL queries.

3. **Invalid Field Names**: Fixed field name mappings and removed primary keys from data dictionaries. 