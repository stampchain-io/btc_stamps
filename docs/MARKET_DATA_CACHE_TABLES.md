# Market Data Cache Tables

This document describes the database schema for the market data caching system, including table structures, relationships, and indexing strategies.

## Database Schema Overview

The market data cache system uses five main tables to store pre-computed market information for stamps, SRC-20 tokens, collections, and detailed holder data.

## Table Relationships

```mermaid
erDiagram
    stamp_market_data {
        string cpid PK
        decimal floor_price_btc
        decimal recent_sale_price_btc
        int open_dispensers_count
        int closed_dispensers_count
        int total_dispensers_count
        int holder_count
        int unique_holder_count
        decimal top_holder_percentage
        decimal holder_distribution_score
        decimal volume_24h_btc
        decimal volume_7d_btc
        decimal volume_30d_btc
        string price_source
        json volume_sources
        decimal data_quality_score
        timestamp last_updated
        int last_dispenser_block
        int last_balance_block
        timestamp created_at
    }

    src20_market_data {
        string tick PK
        decimal floor_price_btc
        decimal best_bid_btc
        decimal best_ask_btc
        decimal volume_24h_btc
        decimal volume_7d_btc
        decimal volume_30d_btc
        decimal market_cap_btc
        int holder_count
        decimal total_supply
        decimal price_change_24h
        decimal price_change_7d
        string price_source
        json volume_sources
        decimal data_quality_score
        timestamp last_updated
        string deploy_tx_hash
        int deploy_block
    }

    collection_market_data {
        string collection_id PK
        decimal min_floor_price_btc
        decimal max_floor_price_btc
        decimal avg_floor_price_btc
        decimal median_floor_price_btc
        decimal total_volume_24h_btc
        int stamps_with_prices_count
        int min_holder_count
        int max_holder_count
        decimal avg_holder_count
        int median_holder_count
        int total_unique_holders
        decimal avg_distribution_score
        int total_stamps_count
        timestamp last_updated
    }

    stamp_holder_cache {
        bigint id PK
        string cpid FK
        string address
        decimal quantity
        decimal percentage
        int rank_position
        string balance_source
        int last_tx_block
        timestamp last_updated
    }

    market_data_sources {
        bigint id PK
        string asset_type
        string asset_id
        string source
        decimal price_btc
        decimal volume_24h_btc
        int holder_count
        decimal market_cap_btc
        decimal source_confidence
        int api_response_time_ms
        timestamp last_updated
    }

    %% Relationships
    stamp_market_data ||--o{ stamp_holder_cache : "cpid"
    stamp_market_data ||--o{ market_data_sources : "asset_id (stamp)"
    src20_market_data ||--o{ market_data_sources : "asset_id (src20)"
    collection_market_data ||--o{ stamp_market_data : "aggregates"
```

## Table Specifications

### stamp_market_data
Stores comprehensive market data for Bitcoin Stamps including floor prices, holder metrics, and volume data.

**Key Features:**
- **Floor Price Tracking**: Current and recent sale prices in BTC
- **Dispenser Analytics**: Open, closed, and total dispenser counts
- **Holder Metrics**: Count, distribution, and concentration analysis
- **Volume Data**: 24h, 7d, and 30d volume tracking
- **Multi-Source Attribution**: Source tracking and quality scoring

**Primary Indexes:**
- `cpid` (Primary Key)
- `floor_price_btc` (Performance)
- `holder_count` (Filtering)
- `last_updated` (Maintenance)
- `volume_24h_btc` (Sorting)

### src20_market_data
Stores market data for SRC-20 tokens with multi-exchange aggregation support.

**Key Features:**
- **Exchange Data**: Floor price, bid/ask spreads from multiple sources
- **Market Metrics**: Market cap, supply, and holder analysis
- **Price Changes**: 24h and 7d percentage changes
- **Volume Tracking**: Multi-timeframe volume analysis
- **Source Attribution**: Exchange-specific data tracking

**Primary Indexes:**
- `tick` (Primary Key)
- `floor_price_btc` (Performance)
- `market_cap_btc` (Filtering)
- `volume_24h_btc` (Sorting)
- `price_change_24h` (Trending)

### collection_market_data
Aggregated market data at the collection level for comprehensive collection analytics.

**Key Features:**
- **Price Aggregates**: Min, max, average, and median floor prices
- **Volume Summation**: Total collection volume across timeframes
- **Holder Analytics**: Distribution and concentration metrics
- **Collection Size**: Total stamps and active market participation

**Primary Indexes:**
- `collection_id` (Primary Key)
- `min_floor_price_btc` (Filtering)
- `total_volume_24h_btc` (Sorting)
- `total_unique_holders` (Analytics)

### stamp_holder_cache
Detailed holder information for individual stamps with ranking and percentage data.

**Key Features:**
- **Individual Holdings**: Precise quantity and percentage ownership
- **Ranking System**: Position-based holder rankings
- **Source Attribution**: Balance source tracking (Counterparty, etc.)
- **Transaction Context**: Last transaction block reference

**Primary Indexes:**
- `id` (Primary Key)
- `cpid, address` (Unique constraint)
- `cpid, rank_position` (Ranking queries)
- `cpid, quantity DESC` (Sorting)

### market_data_sources
Multi-source data tracking for transparency and source reliability analysis.

**Key Features:**
- **Source Attribution**: Track data origin and confidence
- **Performance Metrics**: API response time monitoring
- **Data Quality**: Confidence scoring for each source
- **Asset Agnostic**: Supports both stamps and SRC-20 tokens

**Primary Indexes:**
- `id` (Primary Key)
- `asset_type, asset_id, source` (Unique constraint)
- `asset_type, asset_id` (Asset queries)
- `source` (Source analysis)
- `source_confidence` (Quality filtering)

## Data Flow and Relationships

### Stamp Data Flow
1. **StampWorker** fetches data from Counterparty API
2. **stamp_market_data** stores aggregated market metrics
3. **stamp_holder_cache** stores individual holder details
4. **market_data_sources** tracks Counterparty API source data
5. **collection_market_data** aggregates related stamps

### SRC-20 Data Flow
1. **SRC20Worker** fetches from multiple exchange APIs
2. **src20_market_data** stores aggregated multi-source data
3. **market_data_sources** tracks each exchange source separately
4. Source confidence weighting determines final aggregated values

### Collection Aggregation
1. Query all stamps belonging to a collection
2. Calculate statistical aggregates (min, max, avg, median)
3. Sum volume data across all collection stamps
4. Count unique holders across all stamps in collection
5. Store results in **collection_market_data**

## Performance Optimizations

### Query Optimization
- **Covering Indexes**: Include commonly queried columns in indexes
- **Composite Indexes**: Multi-column indexes for complex filtering
- **Partial Indexes**: Filter-specific indexes for performance

### Cache Strategies
- **TTL-Based Updates**: Update frequency based on asset volatility
- **Batch Processing**: Group updates to minimize database load
- **Read Replicas**: Separate read/write workloads for scalability

### Maintenance Operations
- **Cleanup Jobs**: Remove stale data and optimize indexes
- **Statistics Updates**: Keep query planner statistics current
- **Archival**: Move historical data to separate tables

## Data Integrity

### Constraints
- **Foreign Key Relationships**: Ensure referential integrity
- **Check Constraints**: Validate data ranges and formats
- **Unique Constraints**: Prevent duplicate records

### Validation
- **Source Confidence**: 0-10 scale validation
- **Percentage Fields**: 0-100% range validation
- **Price Fields**: Non-negative decimal validation
- **Timestamp Consistency**: Update time validation

## Monitoring and Alerting

### Cache Health Metrics
- **Data Freshness**: Monitor last_updated timestamps
- **Coverage**: Track percentage of assets with current data
- **Source Quality**: Monitor confidence scores and API health
- **Performance**: Track query response times and throughput

### Alerting Thresholds
- **Stale Data**: Alert if data older than 2x update interval
- **Low Coverage**: Alert if <95% of assets have current data
- **Source Failures**: Alert if source confidence drops below threshold
- **Performance**: Alert if query times exceed SLA thresholds 