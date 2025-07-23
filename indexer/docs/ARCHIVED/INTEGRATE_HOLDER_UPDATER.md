# Integrating SRC-20 Holder Count Updater

## Current Status

The SRC-20 holder count updater has been created but is **NOT YET INTEGRATED** into the main indexer loop. This document explains how to complete the integration.

## Components Created

1. **`src/index_core/src20_holder_updater.py`** - The updater class
2. **`tools/validate_src20_holder_counts.py`** - Manual validation/fix tool  
3. **`docs/SRC20_HOLDER_COUNT_CALCULATION.md`** - Strategy documentation

## Database Configuration Issue

The current error indicates incorrect database credentials. Ensure your `.env` file has:

```bash
# REQUIRED - Set these to your actual database credentials
RDS_HOSTNAME=your_actual_hostname
RDS_USER=your_actual_username
RDS_PASSWORD=your_actual_password  # NOT "your_db_password" or "YES"
RDS_DATABASE=btc_stamps
RDS_PORT=3306
```

## Integration Steps

### Step 1: Import the Holder Updater

In `src/index_core/blocks.py`, add near the top imports:

```python
from index_core.src20_holder_updater import get_holder_updater
```

### Step 2: Initialize in Block Processing

Find where SRC-20 transactions are processed in the block loop. Look for functions that:
- Process SRC-20 operations (DEPLOY, MINT, TRANSFER)
- Update the balances table
- Insert into SRC20Valid table

### Step 3: Track Affected Tokens

When processing SRC-20 operations, track affected tokens:

```python
# Example integration point (find the actual location in your code)
holder_updater = get_holder_updater()

# When processing a SRC-20 operation
if operation['op'] in ['DEPLOY', 'MINT', 'TRANSFER']:
    holder_updater.track_affected_token(operation['tick'])
```

### Step 4: Update Holder Counts After Block

After all SRC-20 operations in a block are processed:

```python
# At the end of block processing
if holder_updater.get_affected_token_count() > 0:
    holder_updater.update_holder_counts(block_index)
```

## Alternative: Market Data Integration

If SRC-20 processing is handled by the market data jobs, you can integrate there:

In `src/index_core/market_data_jobs.py` or `src/index_core/src20_worker.py`:

```python
from index_core.src20_holder_updater import get_holder_updater

# After SRC-20 market data updates
holder_updater = get_holder_updater()
holder_updater.update_holder_counts(current_block_index, force=True)
```

## Testing the Integration

1. First, fix your database credentials in `.env`
2. Test the manual tool works:
   ```bash
   poetry run python tools/validate_src20_holder_counts.py --report
   ```
3. Once working, run initial population:
   ```bash
   poetry run python tools/validate_src20_holder_counts.py --fix-all
   ```
4. Then integrate into the indexer and monitor logs

## Finding the Integration Point

To find where to integrate, look for:

```bash
# Find where balances are updated
grep -r "INSERT INTO balances\|UPDATE balances" src/

# Find where SRC20Valid is populated  
grep -r "INSERT INTO SRC20Valid" src/

# Find main processing functions
grep -r "process.*src20\|handle.*src20" src/
```

## Monitoring

After integration, monitor logs for:
- "Updated holder counts for X tokens at block Y"
- Any errors mentioning holder counts
- Performance impact on block processing