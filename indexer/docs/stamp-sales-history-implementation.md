# Stamp Sales History Implementation Plan

## Overview
Implement a unified sales history system that stores ALL types of stamp sales (dispensers, atomic swaps, OTC, etc.) enabling:
- Comprehensive "Recent Sales" feature
- Historical price charts
- Accurate volume calculations
- Multi-source sales tracking
- Proper rollback support

## Implementation Status

### ✅ Completed Tasks

#### 1. Database Schema Design and Implementation
- **File**: `table_schema.sql`
- **Table**: `stamp_sales_history`
- **Status**: ✅ COMPLETE
- **Details**: 
  - Created unified table supporting multiple sale types
  - Added comprehensive indexes for performance
  - Supports dispensers, atomic swaps, OTC, auctions, DEX trades

#### 2. Rollback Support
- **File**: `src/index_core/database.py`
- **Function**: `purge_block_db()`
- **Status**: ✅ COMPLETE
- **Details**: Added `stamp_sales_history` to tables list for proper rollback during reorgs

#### 3. Sales History Processor
- **File**: `src/index_core/sales_history_processor.py`
- **Class**: `SalesHistoryProcessor`
- **Status**: ✅ COMPLETE
- **Features Implemented**:
  - CPID cache management with 5-minute refresh
  - Dual-mode processing (catchup and real-time)
  - Progress tracking for monitoring
  - Rate limiting (2 req/sec)
  - Parallel processing with ThreadPoolExecutor
  - Methods:
    - `process_block_dispenses()` - Real-time mode
    - `start_catchup_mode()` - Historical backfill
    - `get_recent_sales()` - Query recent sales
    - `calculate_volume_from_history()` - Volume metrics

#### 4. Recent Sales Enhancement Fields
- **File**: `src/index_core/stamp_worker.py`
- **Status**: ✅ COMPLETE
- **Details**: 
  - Fixed field mappings for Counterparty API
  - Added verbose=true for nested dispenser data
  - Fixed btc_amount calculation bug
  - Added enhanced logging

#### 5. Market Data Enhancement Fields
- **File**: `table_schema.sql`
- **Table**: `stamp_market_data`
- **Status**: ✅ COMPLETE
- **Details**:
  - Added `last_sale_block_index` column for frontend recent sales index
  - Added `last_sale_tx_hash` for transaction reference
  - Added `last_sale_buyer_address` and `last_sale_dispenser_address`
  - Added `last_sale_btc_amount` for exact sale amount
  - Added `last_sale_dispenser_tx_hash` (optional) for dispenser reference
  - Created `idx_recent_sales` index as requested by frontend team

#### 6. Database Initialization Fix
- **File**: `src/index_core/database.py`
- **Function**: `initialize_tables()`
- **Status**: ✅ COMPLETE
- **Details**:
  - Fixed issue where ALTER statements weren't running when all tables exist
  - Now always runs ALTER statements for schema updates
  - Ensures production databases get schema updates on restart

### 🚧 In Progress Tasks

#### 1. Testing Infrastructure (NEEDS FIX)
- **Unit Tests**: 🔧 25 tests created but FAILING in bulk runs
- **Integration Tests**: 🔧 15 tests created but FAILING in bulk runs
- **Status**: Tests pass individually but fail when run with other tests
- **Issues Identified**:
  - All tests showing ERROR status when run in bulk
  - Likely fixture conflicts or shared state issues
  - Need to investigate test isolation problems
- **Remaining**: 
  - 🔧 Fix test isolation issues causing bulk run failures
  - ⏳ Add rollback tests for sales history data
  - ⏳ Performance test CPID filtering with large datasets

### 📝 Recent Updates

#### Stamp Worker Integration (Completed)
- **File**: `src/index_core/stamp_worker.py`
- **Changes Made**:
  1. Added import for `sales_history_processor`
  2. Created new method `_calculate_volume_metrics_from_history()` that queries the sales history table
  3. Updated `_calculate_market_metrics()` to use the new method instead of API dispenses
  4. Modified `process_stamp_market_data()` to stop fetching dispenses from API
  5. Marked `_fetch_dispenses()` as DEPRECATED
  
- **Key Benefits**:
  - Market data now uses the same source of truth as the sales history
  - Eliminates redundant API calls for dispense data
  - Ensures volume calculations are consistent across the system
  - Reduces load on Counterparty API

### ⏳ Pending Tasks

#### 1. ~~Remove Old Dispense Fetching System~~ ✅ COMPLETED
- **File**: `src/index_core/stamp_worker.py`
- **Status**: ✅ Completed - Method marked as DEPRECATED, no longer called

#### 2. ~~Update Volume Calculations~~ ✅ COMPLETED
- **File**: `src/index_core/stamp_worker.py`
- **Status**: ✅ Completed - Created `_calculate_volume_metrics_from_history()` that uses sales history table

#### 3. ~~Integrate with Block Pipeline~~ ✅ COMPLETED
- **File**: `src/index_core/blocks.py`
- **Status**: ✅ Completed - Added to `finalize_block()` method
- **Details**: Processes dispenses in real-time as blocks are indexed

#### 4. ~~Migrate Market Data Jobs~~ ✅ COMPLETED
- **File**: `src/index_core/market_data_jobs.py`
- **Status**: ✅ Completed - Added `_check_and_start_sales_catchup()` method
- **Details**: 
  - Auto-starts catchup mode when indexer starts
  - Only runs when `ENABLE_MARKET_DATA_SCHEDULER=true`
  - Background processing doesn't block other jobs

#### 5. Frontend Team Handoff
- **Tasks**:
  - Document database schema and fields
  - Provide example SQL queries for:
    - Recent sales across all stamps
    - Sales history for specific stamp
    - Chart data aggregation
  - Document data reliability and update frequency
  - Note: Frontend team has direct database access and will implement their own API endpoints

#### 6. Testing (NEEDS FIX)
- **Files**: 
  - `tests/test_sales_history_processor.py` - Unit tests
  - `tests/test_sales_history_processor_integration.py` - Integration tests
- **Status**: 
  - 🔧 Unit tests: 25 tests created but failing in bulk runs
  - 🔧 Integration tests: 15 tests created and properly marked
  - ✅ Tests properly marked with `@pytest.mark.integration`
  - ✅ Integration tests excluded from CI runs (run with `poetry run pytest -m integration`)
  - 🔧 **Critical Issue**: All tests showing ERROR when run with other tests
- **Remaining**:
  - 🔧 Fix test isolation issues
  - ⏳ Rollback tests for data consistency
  - ⏳ Performance tests for CPID filtering with large datasets

## Database Schema

### Table: stamp_sales_history
```sql
CREATE TABLE IF NOT EXISTS `stamp_sales_history` (
  `id` BIGINT AUTO_INCREMENT PRIMARY KEY,
  
  -- Core Transaction Data (common to all sale types)
  `tx_hash` VARCHAR(64) NOT NULL COMMENT 'Sale transaction hash',
  `block_index` INT NOT NULL COMMENT 'Block number of the sale',
  `block_time` INT NULL COMMENT 'Unix timestamp of the block',
  `cpid` VARCHAR(255) NOT NULL COMMENT 'Counterparty asset ID',
  `sale_type` ENUM('dispenser', 'atomic_swap', 'otc', 'auction', 'dex') NOT NULL COMMENT 'Type of sale',
  
  -- Parties Involved
  `buyer_address` VARCHAR(64) NOT NULL COMMENT 'Address that bought the stamp',
  `seller_address` VARCHAR(64) NOT NULL COMMENT 'Address that sold the stamp',
  
  -- Sale Details
  `quantity` BIGINT NOT NULL COMMENT 'Number of stamps sold',
  `btc_amount` BIGINT NOT NULL COMMENT 'Total BTC amount in satoshis',
  `unit_price_sats` BIGINT NOT NULL COMMENT 'Price per stamp in satoshis',
  
  -- Type-Specific Fields (NULL when not applicable)
  `dispenser_tx_hash` VARCHAR(64) NULL COMMENT 'For dispensers: tx that created the dispenser',
  `swap_contract_id` VARCHAR(64) NULL COMMENT 'For atomic swaps: contract identifier',
  `platform` VARCHAR(50) NULL COMMENT 'For external sales: platform name',
  `external_id` VARCHAR(100) NULL COMMENT 'External reference ID',
  
  -- Metadata
  `data_source` VARCHAR(50) DEFAULT 'counterparty' COMMENT 'Source of this data',
  `notes` TEXT NULL COMMENT 'Additional notes or metadata',
  `processed_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  
  -- Ensure uniqueness (some external sales might share tx_hash)
  UNIQUE KEY `unique_sale` (`tx_hash`, `sale_type`, `cpid`),
  
  -- Performance indexes
  INDEX `idx_cpid` (`cpid`) COMMENT 'For CPID-based queries',
  INDEX `idx_block` (`block_index`) COMMENT 'For rollback operations',
  INDEX `idx_block_time` (`block_time` DESC) COMMENT 'For recent sales queries',
  INDEX `idx_cpid_time` (`cpid`, `block_time` DESC) COMMENT 'For CPID price history',
  INDEX `idx_sale_type` (`sale_type`) COMMENT 'For type-specific queries',
  INDEX `idx_recent_sales` (`block_time` DESC, `btc_amount` DESC) COMMENT 'For global recent sales',
  INDEX `idx_buyer` (`buyer_address`) COMMENT 'For buyer history',
  INDEX `idx_seller` (`seller_address`) COMMENT 'For seller history'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_ci 
COMMENT='Unified sales history for all stamp transactions - enables charts, recent sales, and analytics';
```

## Architecture

### Data Flow

#### Historical Catchup Mode
```
1. Get CPIDs needing catchup from database
2. For each CPID batch (100 CPIDs):
   a. Fetch dispensers: GET /assets/{cpid}/dispensers
   b. For each dispenser:
      - Fetch dispenses: GET /addresses/{source}/dispenses?asset={cpid}&verbose=true
   c. Store sales in stamp_sales_history
3. Track progress and handle errors
```

#### Real-time Mode (at block tip)
```
1. New block arrives
2. Fetch all dispenses: GET /blocks/{block_index}/dispenses?verbose=true
3. Filter by CPID cache (in-memory set)
4. Store matching sales in stamp_sales_history
```

### Key Components

#### SalesHistoryProcessor
- **CPID Cache**: In-memory set updated every 5 minutes
- **Rate Limiter**: 2 requests/second to Counterparty API
- **Progress Tracking**: Monitor catchup status
- **Thread Pool**: 5 workers for parallel processing

#### Integration Points
1. **Block Processing** (`blocks.py`): Add real-time processing
2. **Market Data Jobs** (`market_data_jobs.py`): Use for volume calculations
3. **Stamp Worker** (`stamp_worker.py`): Remove old dispense fetching
4. **API Layer**: New endpoints for sales data

## Usage Examples

### Start Catchup Mode
```python
from index_core.sales_history_processor import sales_history_processor

# Start backfilling from genesis
sales_history_processor.start_catchup_mode()

# Check progress
progress = sales_history_processor.get_progress()
print(f"Processed {progress['processed_cpids']}/{progress['total_cpids']} CPIDs")
```

### Process New Block
```python
# In block processing pipeline
sales_count = sales_history_processor.process_block_dispenses(block_index)
```

### Query Recent Sales
```python
# Get recent sales across all stamps
recent_sales = sales_history_processor.get_recent_sales(limit=100)

# Get sales for specific stamp
stamp_sales = sales_history_processor.get_recent_sales(limit=50, cpid="A1234...")
```

### Calculate Volumes
```python
# Get 24h volume for a stamp
volume_data = sales_history_processor.calculate_volume_from_history(
    cpid="A1234...",
    hours=24
)
```

## Frontend Team Integration Guide

### Database Tables Available

#### 1. `stamp_sales_history` - Complete sales transaction data
- **Purpose**: Store all stamp sales with full transaction details
- **Update Frequency**: Real-time as blocks are processed
- **Key Fields**:
  - `cpid` - Stamp identifier
  - `tx_hash` - Sale transaction hash
  - `block_time` - Unix timestamp of sale
  - `buyer_address` - Who bought the stamp
  - `seller_address` - Who sold the stamp (dispenser address)
  - `btc_amount` - Total BTC in satoshis
  - `unit_price_sats` - Price per stamp in satoshis
  - `quantity` - Number of stamps sold
  - `sale_type` - Type of sale (currently only 'dispenser')

#### 2. `stamp_market_data` - Aggregated market metrics
- **Purpose**: Pre-calculated market data for performance
- **Update Frequency**: Every 5 minutes via market data jobs
- **Enhanced Fields for Recent Sales**:
  - `last_sale_block_index` - Block number of most recent sale
  - `last_sale_tx_hash` - Transaction hash of most recent sale
  - `last_sale_buyer_address` - Buyer of most recent sale
  - `last_sale_dispenser_address` - Dispenser that made the sale
  - `last_sale_btc_amount` - Amount in satoshis
  - `last_sale_dispenser_tx_hash` - Original dispenser creation tx
  - `volume_24h_btc`, `volume_7d_btc`, `volume_30d_btc` - Pre-calculated volumes

### Example SQL Queries

#### Get Recent Sales Across All Stamps
```sql
SELECT 
    ssh.*,
    s.stamp,
    s.stamp_url,
    s.stamp_mimetype
FROM stamp_sales_history ssh
JOIN StampTableV4 s ON ssh.cpid = s.cpid
ORDER BY ssh.block_time DESC
LIMIT 100;
```

#### Get Sales History for Specific Stamp
```sql
SELECT * FROM stamp_sales_history
WHERE cpid = 'A123456789'
ORDER BY block_time DESC
LIMIT 50;
```

#### Get 24h Volume for a Stamp
```sql
SELECT 
    SUM(btc_amount) as total_volume_sats,
    COUNT(*) as trade_count,
    MAX(unit_price_sats) as high_price,
    MIN(unit_price_sats) as low_price
FROM stamp_sales_history
WHERE cpid = 'A123456789'
AND block_time > UNIX_TIMESTAMP() - (24 * 3600);
```

#### Get Price Chart Data (Hourly)
```sql
SELECT 
    FROM_UNIXTIME(block_time, '%Y-%m-%d %H:00:00') as hour,
    AVG(unit_price_sats) as avg_price,
    MAX(unit_price_sats) as high_price,
    MIN(unit_price_sats) as low_price,
    SUM(btc_amount) as volume,
    COUNT(*) as trade_count
FROM stamp_sales_history
WHERE cpid = 'A123456789'
AND block_time > UNIX_TIMESTAMP() - (7 * 24 * 3600)
GROUP BY hour
ORDER BY hour;
```

## Benefits

1. **Performance**: Query sales from database instead of API calls
2. **Features**: Enables charting, recent sales page, analytics
3. **Extensibility**: Easy to add new sale types
4. **Reliability**: Survives rollbacks with proper data purging
5. **Scalability**: Efficient batch processing and caching

## Next Implementation Steps

1. **Test Infrastructure Fix** (Priority: CRITICAL):
   - 🔧 Fix test isolation issues causing bulk run failures:
     - Reset global `sales_history_processor` state between tests
     - Add proper cleanup for database mock fixtures
     - Clear CPID cache and other internal state
     - Ensure thread pool executors are shut down properly
   - 🔧 Add test fixtures for better isolation
   - 🔧 Ensure tests can run reliably in CI/CD pipeline
   - ⏳ Add rollback tests for data consistency
   - ⏳ Performance tests for CPID filtering
   - Note: Keep real API calls in integration tests to validate implementation

2. **Frontend Handoff Documentation** (Priority: High):
   - ⏳ Create comprehensive database schema documentation
   - ⏳ Document all available fields and their meanings
   - ⏳ Provide example SQL queries for common use cases:
     - Recent sales across all stamps
     - Sales history for specific CPID
     - Price chart data aggregation
     - Volume calculations by time period
   - ⏳ Document data update frequency and reliability

3. **Production Readiness** (Priority: High):
   - ✅ Core functionality implemented
   - ✅ Integration with block pipeline
   - ✅ Market data jobs integration
   - 🔧 Tests need fixing for CI/CD reliability
   - ⏳ Ensure market data aggregation uses sales history
   - ⏳ Verify no impact on:
     - SRC-20 market data
     - Holder cache updates
     - Other market data types

4. **Documentation Phase** (Priority: Medium):
   - ⏳ Migration guide for existing deployments
   - ⏳ Performance tuning guide for database queries
   - ⏳ Operational monitoring guidelines

## Important Learnings and Gotchas

### 1. Counterparty API Field Mappings
- **Issue**: Initial implementation used incorrect field names
- **Fix**: Correct mappings discovered through debugging:
  - `dispense_quantity` (not `quantity`)
  - `source` = buyer address (who received assets)
  - `destination` = dispenser address
  - `btc_amount` is already in satoshis
  - `dispenser` object contains `satoshirate` when using `verbose=true`

### 2. Two-Step Dispense Fetching
- **Issue**: Dispenses don't contain pricing data directly
- **Fix**: Must fetch dispensers first, then dispenses:
  1. GET `/assets/{cpid}/dispensers` - Contains satoshirate
  2. GET `/addresses/{source}/dispenses?asset={cpid}&verbose=true` - Contains sales

### 3. Database Environment Variables
- **Issue**: Different environments use different variable names
- **Fix**: Production uses `RDS_*` variables, development uses `ST3_*`

### 4. MySQL Version Compatibility
- **Issue**: `IF NOT EXISTS` not supported for ADD COLUMN in older MySQL
- **Fix**: Remove `IF NOT EXISTS` from ALTER TABLE statements

### 5. Worker Count Bottleneck
- **Issue**: Only 3 workers processing 59K+ stamps = slow
- **Fix**: Increased to 10 workers for better throughput

### 6. Impact on Other Market Data Jobs
- **Important**: Changes to stamp_worker.py only affect STAMP dispense fetching
- **No Impact On**:
  - SRC-20 market data fetching
  - Holder cache updates
  - Dispenser data fetching (still uses API)
  - Balance calculations
- **Ensures**: Each market data type remains independent and isolated

## Recent Integration Updates

### Block Pipeline Integration (COMPLETED)
- **File**: `src/index_core/blocks.py`
- **Method**: `BlockProcessor.finalize_block()`
- **Details**:
  - Added sales history processing after stamps are processed
  - Processes dispenses in real-time as blocks are indexed
  - Non-blocking - errors don't fail block processing
  - Automatically captures all sales as they happen

### Market Data Jobs Integration (COMPLETED)
- **File**: `src/index_core/market_data_jobs.py`
- **Method**: `MarketDataJobScheduler._check_and_start_sales_catchup()`
- **Details**:
  - Auto-detects CPIDs needing historical sales data
  - Starts catchup mode automatically on indexer startup
  - Only runs when `ENABLE_MARKET_DATA_SCHEDULER=true`
  - Background processing doesn't block other market data jobs

### Testing Infrastructure (NEEDS FIX)
- **Integration Tests**: `tests/test_sales_history_processor_integration.py`
  - Tests actual Counterparty API interactions
  - Validates data parsing and field mappings
  - Marked with `@pytest.mark.integration`
  - Run with: `poetry run pytest -m integration`
  - 🔧 **Status**: Failing when run in bulk with other tests
  
- **Unit Tests**: `tests/test_sales_history_processor.py`
  - Full test coverage with mocked dependencies
  - Tests all internal logic and edge cases
  - Should run in CI pipeline
  - Run with: `poetry run pytest tests/test_sales_history_processor.py`
  - 🔧 **Status**: Failing when run in bulk with other tests

- **Known Issues**:
  - Tests pass when run individually
  - All tests show ERROR status in bulk runs
  - Integration tests intentionally make REAL API calls to validate implementation:
    - `test_counterparty_api_dispense_fetch` - Fetches from `/blocks/800000/dispenses`
    - `test_process_single_cpid_dispenses` - Makes real dispenser/dispense API calls
  - Root cause likely: **Shared state and isolation issues**
    - Global `sales_history_processor` instance may retain state between tests
    - Database mock fixtures may conflict between test modules
    - CPID cache or other internal state not properly reset
    - Thread pool executors may not be cleaned up properly
  - **Solution needed**: Better test isolation and cleanup between tests

## Migration Notes

### For Existing Deployments
1. Run database migration to create `stamp_sales_history` table
2. Start catchup mode to backfill historical data
3. Monitor progress until catchup completes
4. Switch market data jobs to use new system
5. Remove old dispense fetching code

### Rollback Procedure
The system automatically handles rollbacks via `purge_block_db()`. No manual intervention required.

## Future Enhancements

1. **Additional Sale Types**:
   - Atomic swap integration
   - OTC/private sales import
   - DEX integrations

2. **Analytics Features**:
   - Price trend analysis
   - Whale tracking
   - Market maker identification

3. **Performance Optimizations**:
   - Materialized views for common queries
   - Redis caching layer
   - GraphQL API