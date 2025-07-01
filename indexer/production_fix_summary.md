# Production Fix Summary for Market Data Population

## Issues Identified

1. **`price_source` field is NULL for all records (100%)**
   - Root cause: Field wasn't initialized with default value
   
2. **`volume_sources` field is empty `{}` for all records (100%)**
   - Root cause: Field is JSON type but was being set as string, failing validation
   
3. **Volume data is mostly 0**
   - This is expected - only stamps with dispense transactions will have volume

4. **Exchange data (OpenStamp/KuCoin) is working**
   - STAMP token shows KuCoin data
   - Other SRC-20 tokens show OpenStamp data where available

## Code Changes Required

### 1. `src/index_core/stamp_worker.py`

**Line 220-221**: Initialize default values
```python
"price_source": "counterparty",  # Always set default
"volume_sources": {"counterparty": 1.0},  # Always set default as JSON
```

**Line 236**: Set volume_sources as JSON when dispensers found
```python
market_data["volume_sources"] = {"dispenser": 1.0}
```

**Lines 74-77**: Remove redundant price_source setting
```python
# Remove these lines:
# if market_data.get("price_source") is None:
#     market_data["price_source"] = "counterparty"
```

### 2. `src/index_core/stamp_market_processor.py`

**Lines 147-165**: Fix validation for JSON field
```python
# Validate price_source (string field)
if "price_source" in data and data["price_source"] is not None:
    if isinstance(data["price_source"], str) and len(data["price_source"]) <= 255:
        validated_data["price_source"] = data["price_source"]
    else:
        logger.warning(f"Invalid price_source format, using default: {data.get('price_source')}")
        validated_data["price_source"] = "counterparty"
else:
    validated_data["price_source"] = "counterparty"

# Validate volume_sources (JSON field)
if "volume_sources" in data and data["volume_sources"] is not None:
    if isinstance(data["volume_sources"], dict):
        validated_data["volume_sources"] = data["volume_sources"]
    else:
        logger.warning(f"Invalid volume_sources format, using default: {data.get('volume_sources')}")
        validated_data["volume_sources"] = {"counterparty": 1.0}
else:
    validated_data["volume_sources"] = {"counterparty": 1.0}
```

### 3. `src/index_core/market_data_service.py`

**Lines 314-322**: Convert JSON to string for database
```python
# Prepare values for INSERT only
# Convert JSON fields to strings
import json
values = [cpid]
for field, value in valid_fields.items():
    if field == "volume_sources" and isinstance(value, dict):
        values.append(json.dumps(value))
    else:
        values.append(value)
```

## Database Fix Script

Run `fix_market_data_source_fields.py` to update existing NULL records in production:
- Updates NULL `price_source` to 'counterparty'
- Sets `price_source` to 'dispenser' for stamps with active dispensers
- Sets `volume_sources` to 'dispenser' for stamps with volume data

## Deployment Steps

1. Deploy code changes to production
2. Restart the indexer (market data scheduler will pick up changes)
3. Run the database fix script for existing records
4. Monitor that new records have proper source fields populated

## Expected Results

After deployment:
- All stamps will have `price_source` = 'counterparty' or 'dispenser'
- All stamps will have `volume_sources` = {"counterparty": 1.0} or {"dispenser": 1.0}
- Frontend will see proper source attribution for all market data
- No more NULL or empty source fields

## Timeline

The market data scheduler runs:
- Stamp updates: Every 15-30 minutes
- SRC-20 updates: Every 5-10 minutes
- Collection updates: Every 30 minutes

Full population should complete within 1-2 hours after deployment.