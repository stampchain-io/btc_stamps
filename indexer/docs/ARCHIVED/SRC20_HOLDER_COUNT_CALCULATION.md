# SRC-20 Holder Count Calculation Strategy

## Overview

This document outlines the strategy for accurately calculating and maintaining `holder_count` values in the `src20_market_data` table. Current analysis shows many missing and mismatched holder counts, particularly for tokens not tracked by external market data providers (OpenStamp, KuCoin).

## Usage with Poetry

All commands in this document assume you're working within the indexer's poetry environment:

```bash
cd indexer
poetry shell  # Enter the virtual environment
# OR prefix each command with 'poetry run'
```

## Current State Analysis

### Problem Identification

The following query reveals the extent of missing/mismatched holder counts:

```sql
SELECT 
    smd.tick,
    smd.holder_count as stored_count,
    COALESCE(actual.holder_count, 0) as actual_count,
    CASE 
        WHEN smd.holder_count IS NULL THEN 'MISSING'
        WHEN smd.holder_count != COALESCE(actual.holder_count, 0) THEN 'MISMATCH'
        ELSE 'OK'
    END as status
FROM src20_market_data smd
LEFT JOIN (
    SELECT 
        tick,
        COUNT(DISTINCT address) as holder_count
    FROM balances 
    WHERE amt > 0
    GROUP BY tick
) actual ON smd.tick = actual.tick
ORDER BY smd.tick;
```

### Root Causes

1. **External API Limitations**: OpenStamp and KuCoin only provide data for actively traded tokens
2. **New Token Gap**: Newly created tokens don't immediately appear in external APIs
3. **Low Activity Tokens**: Tokens with minimal trading activity are often not tracked
4. **Timing Issues**: Holder counts can change between external API updates

## Proposed Solutions

### Option 1: Smart Monitoring (Recommended)

Track only affected tokens on each block, updating holder counts for:
- Tokens with new deployments (DEPLOY operations)
- Tokens with transfers (TRANSFER operations)
- Tokens with mints (MINT operations)

**Advantages:**
- Minimal performance impact
- Real-time accuracy
- Scales well with blockchain growth

**Implementation:**

```python
class SRC20HolderCountUpdater:
    """Updates holder counts for SRC-20 tokens affected in each block."""
    
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.affected_tokens = set()
    
    def track_affected_token(self, tick: str):
        """Track a token that needs holder count update."""
        self.affected_tokens.add(tick.upper())
    
    def update_holder_counts(self, block_index: int):
        """Update holder counts for all affected tokens in this block."""
        if not self.affected_tokens:
            return
        
        db = self.db_manager.connect()
        try:
            # Batch update holder counts
            placeholders = ','.join(['%s'] * len(self.affected_tokens))
            
            db.execute(f"""
                UPDATE src20_market_data smd
                JOIN (
                    SELECT 
                        tick,
                        COUNT(DISTINCT address) as holder_count
                    FROM balances
                    WHERE tick IN ({placeholders})
                    AND amt > 0
                    GROUP BY tick
                ) counts ON smd.tick = counts.tick
                SET 
                    smd.holder_count = counts.holder_count,
                    smd.last_updated = NOW()
                WHERE smd.tick IN ({placeholders})
            """, list(self.affected_tokens) * 2)
            
            db.commit()
            logger.debug(f"Updated holder counts for {len(self.affected_tokens)} tokens at block {block_index}")
            
        finally:
            db.close()
            self.affected_tokens.clear()
```

### Option 2: Full Recalculation

Periodically recalculate all holder counts (e.g., every N blocks or on a schedule).

**Advantages:**
- Simple implementation
- Catches any drift or inconsistencies
- Good for initial population

**Disadvantages:**
- Performance intensive
- Not real-time
- Scales poorly

**Implementation:**

```sql
-- One-time full population
UPDATE src20_market_data smd
JOIN (
    SELECT 
        tick,
        COUNT(DISTINCT address) as holder_count
    FROM balances
    WHERE amt > 0
    GROUP BY tick
) counts ON smd.tick = counts.tick
SET 
    smd.holder_count = counts.holder_count,
    smd.last_updated = NOW();

-- Handle tokens with 0 holders
UPDATE src20_market_data
SET holder_count = 0
WHERE holder_count IS NULL;
```

## Recommended Implementation Strategy

### Phase 1: Initial Population
1. Run full recalculation to populate all missing holder counts
2. Identify and log any significant mismatches for investigation

### Phase 2: Smart Monitoring Integration

1. **Modify SRC20 Processing Pipeline**:
   ```python
   # In src/index_core/src20.py
   def process_src20_operations(db, operations, block_index):
       holder_updater = SRC20HolderCountUpdater(db_manager)
       
       for op in operations:
           # Existing processing...
           
           # Track affected tokens
           if op['op'] in ['DEPLOY', 'MINT', 'TRANSFER']:
               holder_updater.track_affected_token(op['tick'])
       
       # Update holder counts for affected tokens
       holder_updater.update_holder_counts(block_index)
   ```

2. **Add to Block Processing**:
   ```python
   # In blocks.py after SRC20 validation
   if src20_affected_tokens:
       update_src20_holder_counts(db, src20_affected_tokens)
   ```

### Phase 3: Monitoring and Validation

1. **Add Monitoring Query**:
   ```sql
   -- Check for drift over time
   SELECT 
       COUNT(*) as total_tokens,
       SUM(CASE WHEN status = 'OK' THEN 1 ELSE 0 END) as accurate_count,
       SUM(CASE WHEN status = 'MISSING' THEN 1 ELSE 0 END) as missing_count,
       SUM(CASE WHEN status = 'MISMATCH' THEN 1 ELSE 0 END) as mismatch_count
   FROM (
       -- Original analysis query here
   ) analysis;
   ```

2. **Use Validation Tool**:
   ```bash
   cd indexer
   
   # Generate report only
   poetry run python tools/validate_src20_holder_counts.py --report
   
   # Fix missing holder counts
   poetry run python tools/validate_src20_holder_counts.py --fix-missing
   
   # Fix mismatched holder counts  
   poetry run python tools/validate_src20_holder_counts.py --fix-mismatches
   
   # Fix all issues at once
   poetry run python tools/validate_src20_holder_counts.py --fix-all
   
   # Custom batch size for large datasets
   poetry run python tools/validate_src20_holder_counts.py --fix-all --batch-size 200
   ```

## Performance Considerations

### Indexing Strategy
Ensure proper indexes exist:
```sql
-- For efficient holder count queries
CREATE INDEX idx_balances_tick_amt ON balances(tick, amt) WHERE amt > 0;
CREATE INDEX idx_balances_address_tick ON balances(address, tick) WHERE amt > 0;

-- For market data updates
CREATE INDEX idx_src20_market_data_tick ON src20_market_data(tick);
CREATE INDEX idx_src20_market_data_updated ON src20_market_data(last_updated);
```

### Batch Processing
- Process updates in batches of 50-100 tokens
- Use single UPDATE with JOIN instead of individual queries
- Consider using temporary tables for very large updates

## Maintenance Tasks

### Daily Validation
```python
# Run as scheduled job
def validate_holder_counts():
    """Daily validation of holder counts accuracy."""
    mismatches = check_holder_count_accuracy()
    if mismatches > threshold:
        alert_admin(f"Found {mismatches} holder count mismatches")
        run_targeted_fixes()
```

### Weekly Full Sync
```bash
# Optional weekly full recalculation for drift correction
cd indexer
poetry run python tools/validate_src20_holder_counts.py --fix-all
```

## Migration Plan

1. **Backup Current Data**:
   ```sql
   CREATE TABLE src20_market_data_backup AS 
   SELECT * FROM src20_market_data;
   ```

2. **Run Initial Population**:
   ```bash
   cd indexer
   poetry run python tools/validate_src20_holder_counts.py --fix-all
   ```

3. **Deploy Smart Monitoring**:
   - Update src20.py with holder tracking
   - Add holder count updater to block processing
   - Monitor logs for first 24 hours

4. **Validate Results**:
   ```bash
   cd indexer
   poetry run python tools/validate_src20_holder_counts.py --report
   ```

## Expected Outcomes

- **Immediate**: All tokens have accurate holder counts
- **Ongoing**: Real-time holder count updates as tokens are used
- **Performance**: Minimal impact (<50ms per block with affected tokens)
- **Accuracy**: 100% accuracy for all tracked tokens

## Future Enhancements

1. **Historical Tracking**: Store holder count history for trend analysis
2. **Alert System**: Notify when holder counts change significantly
3. **API Endpoint**: Expose holder count data via REST API
4. **Analytics**: Track holder growth rates and patterns