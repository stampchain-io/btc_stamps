# Counterparty API Verbose Pagination Workaround

## Overview

This document describes the workaround implemented for the Counterparty API v11.0.1 pagination bug that occurs when using `verbose=true` with transaction queries.

## The Problem

As of Counterparty API v11.0.1, there is a critical bug when fetching transactions with `verbose=true`:

1. **Response Size Limitation**: When `limit >= 26` for blocks with many transactions, the API returns HTTP 500 "Internal server error"
2. **Pagination Failure**: The third page of paginated requests consistently fails with HTTP 500
3. **Impact**: Applications cannot retrieve complete transaction data with events for blocks containing more than 25 transactions

For detailed analysis, see `counterparty_api_error.md`.

## The Workaround

We implemented a 2-step approach that fetches transactions and events separately:

1. **Step 1**: Fetch all transactions with `verbose=false` (supports high limits up to 2000)
2. **Step 2**: Fetch all events for the block separately using `/blocks/{block_index}/events`
3. **Step 3**: Match events to their corresponding transactions locally

### Benefits
- Works reliably for blocks of any size
- Minimizes API calls (typically 2-3 calls per block)
- Provides identical data structure to verbose=true
- Avoids the pagination bug entirely

### Trade-offs
- Slightly more complex implementation
- Requires separate event fetching and matching logic

## Configuration

The workaround is controlled by an environment variable:

```bash
# Enable workaround (default)
export CP_API_USE_VERBOSE_WORKAROUND=true

# Disable workaround (when upstream bug is fixed)
export CP_API_USE_VERBOSE_WORKAROUND=false
```

## How to Revert to Original Method

When the upstream Counterparty API bug is fixed:

1. **Set the environment variable**:
   ```bash
   export CP_API_USE_VERBOSE_WORKAROUND=false
   ```

2. **Test with problematic blocks**:
   ```bash
   # Run the test script to verify the fix
   poetry run python tools/test_api_methods.py
   ```

3. **Monitor logs** for any HTTP 500 errors or pagination failures

4. **If issues persist**, re-enable the workaround:
   ```bash
   export CP_API_USE_VERBOSE_WORKAROUND=true
   ```

## Testing Both Methods

### Manual Testing
A comprehensive test script is provided to validate both methods:

```bash
# Test both methods and compare results
poetry run python tools/test_api_methods.py

# Test specific blocks
poetry run python tools/test_api_methods.py --block 784320

# Test with verbose output
poetry run python tools/test_api_methods.py --verbose

# Show detailed field comparison
poetry run python tools/test_api_methods.py --compare-fields
```

The test script will:
- Fetch data using both methods
- Compare the data structures
- Verify all fields are present
- Check for data consistency

### Automated Testing
Run the pytest test suite to ensure data consistency:

```bash
# Run the Counterparty API tests
poetry run pytest tests/test_counterparty_api_methods.py -v

# Run with coverage
poetry run pytest tests/test_counterparty_api_methods.py --cov=src.index_core.fetch_utils

# Run integration tests (requires live API)
poetry run pytest tests/test_counterparty_api_methods.py -v -m integration
```

## Data Structure Validation

Both methods produce identical data structures:

```json
{
  "block_index": 784320,
  "xcp_block_hash": "hash...",
  "transactions": [
    {
      "tx_hash": "...",
      "block_index": 784320,
      "transaction_type": "issuance",
      "events": [
        {
          "event": "ASSET_ISSUANCE",
          "params": {
            "asset": "A1234567890",
            "description": "STAMP:...",
            ...
          }
        }
      ],
      ...
    }
  ],
  "issuances": [...]
}
```

## Implementation Details

### File: `src/index_core/fetch_utils.py`

- `fetch_block_transactions_with_pagination()`: Main entry point that checks the config flag
- `_fetch_block_transactions_workaround()`: Implements the 2-step workaround
- `_fetch_block_transactions_original()`: Original verbose=true implementation

### File: `src/config.py`

- `CP_API_USE_VERBOSE_WORKAROUND`: Configuration flag (default: true)

## Monitoring

When using the workaround, you'll see these log messages:
```
DEBUG: Fetching block 784320 transactions with 2-step workaround approach
DEBUG: Step 1: Fetching all transactions with verbose=false
DEBUG: Got 65 transactions
DEBUG: Step 2: Fetching all events for the block
DEBUG: Got 341 total events for block 784320
DEBUG: Step 3: Matching events to transactions
DEBUG: Step 4: Parsing issuances from transactions
DEBUG: Found 63 stamp issuances
```

When using the original method:
```
DEBUG: Fetching block 784320 transactions with original verbose=true method
DEBUG: Using original verbose=true method for block 784320
DEBUG: Fetching page 1 of transactions for block 784320
```

## Known Limitations

1. The original method with `verbose=true` is limited to 25 transactions per page
2. Blocks with > 50 transactions may require multiple pages even with the fix
3. The workaround requires the events endpoint to be functional

## References

- Counterparty API Issue: https://github.com/CounterpartyXCP/counterparty-core/issues/[TBD]
- Local Analysis: `counterparty_api_error.md`
- Test Scripts: `tools/test_api_methods.py`, `tools/test_api_limits.py`

## Support

If you encounter issues:
1. Check the `CP_API_USE_VERBOSE_WORKAROUND` setting
2. Run the test scripts to validate API behavior
3. Review logs for specific error messages
4. Report issues with full error details and block numbers