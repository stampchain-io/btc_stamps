# Market Data Fetching Architecture

This document provides visual diagrams of the market data fetching system implemented in the Bitcoin Stamps indexer.

## System Overview

The market data system consists of background jobs that pre-compute and cache market information for both Bitcoin Stamps and SRC-20 tokens, eliminating the need for real-time API calls during page loads.

## Architecture Diagram

The following diagram shows the complete system architecture including data sources, processing components, and cache tables:

```mermaid
graph TB
    %% Main Indexer Process
    subgraph "Main Indexer (blocks.py)"
        BI[Block Indexer]
        MDS[Market Data Scheduler]
        BI -->|Start background jobs| MDS
    end

    %% Background Job Scheduler
    subgraph "Background Jobs (market_data_jobs.py)"
        MDJS[MarketDataJobScheduler]
        SJ[Stamp Jobs<br/>Every 15min]
        SRC20J[SRC-20 Jobs<br/>Every 5min]
        CJ[Collection Jobs<br/>Every 30min]
        
        MDJS --> SJ
        MDJS --> SRC20J
        MDJS --> CJ
    end

    %% Worker Processes
    subgraph "Data Workers"
        SW[StampWorker]
        SRC20W[SRC20Worker]
        
        SJ -->|Process batches| SW
        SRC20J -->|Process batches| SRC20W
    end

    %% External Data Sources
    subgraph "External APIs"
        CP[Counterparty API<br/>dispensers, balances]
        KC[KuCoin API<br/>STAMP-USDT]
        OS[OpenStamp API<br/>SRC-20 data]
        SS[StampScan API<br/>SRC-20 data]
    end

    %% Database Cache Tables
    subgraph "Cache Database Tables"
        SMD[(stamp_market_data<br/>- floor_price_btc<br/>- holder_count<br/>- volume_data)]
        SRC20MD[(src20_market_data<br/>- floor_price_btc<br/>- market_cap<br/>- volume_data)]
        CMD[(collection_market_data<br/>- aggregated metrics)]
        SHC[(stamp_holder_cache<br/>- individual holders<br/>- rankings)]
        MDS_TABLE[(market_data_sources<br/>- source attribution<br/>- confidence scores)]
    end

    %% Selection Queries
    subgraph "Selection Logic"
        GSU[get_stamps_needing_update<br/>LIMIT 10,000]
        GSTU[get_src20_tokens_needing_update<br/>LIMIT 1,000]
        GCU[get_collections_needing_update<br/>LIMIT 50]
    end

    %% Data Flow Connections
    SJ --> GSU
    GSU -->|Valid CPIDs| SW
    SW -->|API calls| CP
    SW -->|Update cache| SMD
    SW -->|Populate holders| SHC

    SRC20J --> GSTU
    GSTU -->|Token ticks| SRC20W
    SRC20W -->|API calls| KC
    SRC20W -->|API calls| OS
    SRC20W -->|API calls| SS
    SRC20W -->|Update cache| SRC20MD

    CJ --> GCU
    GCU -->|Collection IDs| CJ
    CJ -->|Aggregate data| CMD

    %% Source Tracking
    SW -->|Track sources| MDS_TABLE
    SRC20W -->|Track sources| MDS_TABLE

    %% Frontend Access
    subgraph "Frontend API"
        API[Enhanced Controllers]
        CACHE[Cache Service]
    end

    SMD -->|Fast queries| CACHE
    SRC20MD -->|Fast queries| CACHE
    CMD -->|Fast queries| CACHE
    CACHE --> API

    %% Styling
    classDef external fill:#e1f5fe
    classDef database fill:#f3e5f5
    classDef process fill:#e8f5e8
    classDef scheduler fill:#fff3e0

    class CP,KC,OS,SS external
    class SMD,SRC20MD,CMD,SHC,MDS_TABLE database
    class SW,SRC20W,BI process
    class MDJS,SJ,SRC20J,CJ scheduler
```

## Key Components

### Main Indexer (`blocks.py`)
- **Block Indexer**: Main blockchain parsing process
- **Market Data Scheduler**: Initializes and manages background market data jobs

### Background Job Scheduler (`market_data_jobs.py`)
- **MarketDataJobScheduler**: Central coordinator for all market data jobs
- **Stamp Jobs**: Process stamp market data every 15 minutes
- **SRC-20 Jobs**: Process SRC-20 token data every 5 minutes  
- **Collection Jobs**: Aggregate collection-level data every 30 minutes

### Data Workers
- **StampWorker**: Processes individual stamp market data from Counterparty API
- **SRC20Worker**: Processes SRC-20 token data from multiple exchange APIs

### External APIs
- **Counterparty API**: Source for dispenser, balance, and send data for stamps
- **KuCoin API**: Exchange data for STAMP-USDT trading pairs
- **OpenStamp API**: SRC-20 token market data and metrics
- **StampScan API**: Additional SRC-20 token information

### Cache Database Tables
- **stamp_market_data**: Floor prices, holder counts, volume metrics for stamps
- **src20_market_data**: Exchange prices, market cap, trading volumes for SRC-20 tokens
- **collection_market_data**: Aggregated collection-level statistics
- **stamp_holder_cache**: Individual holder rankings and percentages
- **market_data_sources**: Source attribution and confidence tracking

## Processing Scale

- **Stamps**: Up to 10,000 stamps processed per 15-minute cycle
- **SRC-20 Tokens**: Up to 1,000 tokens processed per 5-minute cycle
- **Collections**: Up to 50 collections processed per 30-minute cycle
- **Batch Sizes**: 100 stamps or 50 SRC-20 tokens per batch to manage API rate limits

## Performance Benefits

- **Eliminates Real-Time API Calls**: Replaces 40+ concurrent API calls with instant database queries
- **Sub-Second Response Times**: All market data served from optimized cache tables
- **Multi-Source Aggregation**: Combines data from multiple exchanges and sources
- **Intelligent Rate Limiting**: Respects external API limits while maximizing throughput 