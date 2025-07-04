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

### 🚧 In Progress Tasks

None currently - ready to proceed with integration tasks.

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

#### 3. Integrate with Block Pipeline
- **File**: `src/index_core/blocks.py`
- **Tasks**:
  - Add `sales_history_processor.process_block_dispenses()` to block processing
  - Ensure it runs after stamp processing but before market data

#### 4. Migrate Market Data Jobs
- **File**: `src/index_core/market_data_jobs.py`
- **Tasks**:
  - Start catchup mode on indexer startup if needed
  - Monitor catchup progress
  - Switch to using sales history for volumes

#### 5. Create API Endpoints
- **Tasks**:
  - `/api/v2/sales/recent` - Recent sales across all stamps
  - `/api/v2/sales/stamp/{cpid}` - Sales history for specific stamp
  - `/api/v2/sales/chart/{cpid}` - Chart data for stamp

#### 6. Testing
- **Files**: `tests/test_sales_history_processor.py`
- **Tests needed**:
  - Unit tests for processor methods
  - Integration tests for catchup mode
  - Performance tests for CPID filtering
  - Rollback tests

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

## Benefits

1. **Performance**: Query sales from database instead of API calls
2. **Features**: Enables charting, recent sales page, analytics
3. **Extensibility**: Easy to add new sale types
4. **Reliability**: Survives rollbacks with proper data purging
5. **Scalability**: Efficient batch processing and caching

## Next Implementation Steps

1. **Integration Phase**:
   - Remove old dispense fetching from stamp_worker.py
   - Add real-time processing to block pipeline
   - Update market data jobs

2. **API Phase**:
   - Create REST endpoints
   - Add WebSocket support for real-time updates

3. **Testing Phase**:
   - Unit tests for all components
   - Integration tests for full flow
   - Load testing for performance

4. **Documentation Phase**:
   - API documentation
   - Migration guide
   - Performance tuning guide

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