# Market Data Processing Flow

This document details the step-by-step processing flow for market data updates in the Bitcoin Stamps indexer.

## Processing Flow Overview

The market data system uses a time-based scheduling approach with three independent job types running at different intervals. Each job type processes data in batches to manage external API rate limits and ensure system stability.

## Detailed Processing Sequence

The following sequence diagram shows the complete processing flow from initialization through data collection and caching:

```mermaid
sequenceDiagram
    participant Indexer as Block Indexer
    participant Scheduler as MarketDataJobScheduler
    participant StampWorker as StampWorker
    participant SRC20Worker as SRC20Worker
    participant DB as Database
    participant CP as Counterparty API
    participant KuCoin as KuCoin API
    participant OpenStamp as OpenStamp API
    participant Cache as Cache Tables

    %% Initialization
    Indexer->>Scheduler: start_market_data_jobs()
    Scheduler->>Scheduler: Start 3 background schedulers

    %% Stamp Market Data Flow (Every 15 min)
    loop Every 15 minutes
        Scheduler->>DB: get_stamps_needing_update(limit=10000)
        DB-->>Scheduler: List of CPIDs needing updates
        
        loop For each batch of 100 stamps
            Scheduler->>StampWorker: process_stamp_batch(cpids)
            
            loop For each CPID in batch
                StampWorker->>CP: Get dispensers, balances, sends
                CP-->>StampWorker: Market data response
                StampWorker->>StampWorker: Calculate floor price, holder count
                StampWorker->>Cache: Update stamp_market_data
                StampWorker->>Cache: Populate stamp_holder_cache
            end
            
            StampWorker-->>Scheduler: Batch complete
            Note over Scheduler: 2 second delay between batches
        end
    end

    %% SRC-20 Market Data Flow (Every 5 min)
    loop Every 5 minutes
        Scheduler->>DB: get_src20_tokens_needing_update(limit=1000)
        DB-->>Scheduler: List of token ticks needing updates
        
        loop For each batch of 50 tokens
            Scheduler->>SRC20Worker: process_src20_batch(ticks)
            
            loop For each tick in batch
                par Parallel API calls
                    SRC20Worker->>KuCoin: Get STAMP-USDT price
                    SRC20Worker->>OpenStamp: Get SRC-20 data
                    SRC20Worker->>OpenStamp: Get additional metrics
                end
                
                SRC20Worker->>SRC20Worker: Aggregate multi-source data
                SRC20Worker->>Cache: Update src20_market_data
                SRC20Worker->>Cache: Track market_data_sources
            end
            
            SRC20Worker-->>Scheduler: Batch complete
            Note over Scheduler: 1 second delay between batches
        end
    end

    %% Collection Aggregation (Every 30 min)
    loop Every 30 minutes
        Scheduler->>DB: get_collections_needing_update(limit=50)
        DB-->>Scheduler: List of collection IDs
        
        loop For each collection
            Scheduler->>Cache: Query stamps in collection
            Scheduler->>Scheduler: Calculate aggregated metrics
            Scheduler->>Cache: Update collection_market_data
        end
    end

    %% Error Handling & Monitoring
    Note over Scheduler,Cache: All operations include:<br/>- Rate limiting<br/>- Error handling<br/>- Source confidence tracking<br/>- Health monitoring
```

## Processing Details

### Initialization Phase
1. **Block Indexer** starts the market data job scheduler during startup
2. **MarketDataJobScheduler** initializes three independent background schedulers
3. Each scheduler runs on its own thread with configurable intervals

### Stamp Market Data Processing (Every 15 minutes)
1. **Selection Query**: Get up to 10,000 stamps needing updates based on last update time
2. **Batch Processing**: Process stamps in batches of 100 to manage API rate limits
3. **Data Fetching**: For each stamp, call Counterparty API to get:
   - Dispenser information
   - Balance data
   - Transaction history
4. **Calculation**: Compute floor prices, holder counts, and volume metrics
5. **Cache Update**: Store results in `stamp_market_data` and `stamp_holder_cache` tables
6. **Rate Limiting**: 2-second delay between batches to respect API limits

### SRC-20 Token Processing (Every 5 minutes)
1. **Selection Query**: Get up to 1,000 SRC-20 tokens needing updates
2. **Batch Processing**: Process tokens in batches of 50 for efficient API usage
3. **Multi-Source Fetching**: For each token, make parallel API calls to:
   - KuCoin API for STAMP-USDT trading data
   - OpenStamp API for SRC-20 market metrics
   - StampScan API for additional data points
4. **Data Aggregation**: Combine multi-source data with confidence weighting
5. **Cache Update**: Store results in `src20_market_data` and `market_data_sources` tables
6. **Rate Limiting**: 1-second delay between batches for faster SRC-20 updates

### Collection Aggregation (Every 30 minutes)
1. **Selection Query**: Get up to 50 collections needing metric updates
2. **Aggregation**: For each collection:
   - Query all stamps in the collection
   - Calculate min/max/average floor prices
   - Compute total volume and holder statistics
   - Generate distribution metrics
3. **Cache Update**: Store aggregated results in `collection_market_data` table

## Error Handling & Recovery

### Rate Limiting
- **Counterparty API**: 2 calls per second maximum
- **KuCoin API**: 0.5 calls per second maximum
- **OpenStamp/StampScan**: 1-2 calls per second maximum

### Error Recovery
- **Transient Errors**: Automatic retry with exponential backoff
- **API Failures**: Graceful degradation with source confidence tracking
- **Database Issues**: Transaction rollback and error logging
- **Network Issues**: Timeout handling and connection retry

### Monitoring
- **Success Rates**: Track completion rates for each data source
- **Processing Times**: Monitor batch processing performance
- **API Health**: Track external API response times and error rates
- **Cache Freshness**: Monitor data staleness and update frequency

## Performance Characteristics

### Processing Scale
- **10,000 stamps** processed every 15 minutes
- **1,000 SRC-20 tokens** processed every 5 minutes
- **50 collections** aggregated every 30 minutes
- **100+ API calls per minute** during peak processing

### Response Times
- **Cache Queries**: Sub-millisecond response times
- **API Calls**: 200-500ms average response time
- **Batch Processing**: 2-5 minutes per complete cycle
- **End-to-End Latency**: 5-30 minutes maximum data freshness

### Resource Usage
- **Memory**: Efficient batch processing with configurable limits
- **CPU**: Parallel processing with thread pool management
- **Network**: Intelligent rate limiting to prevent API throttling
- **Database**: Optimized indexing for fast cache queries 