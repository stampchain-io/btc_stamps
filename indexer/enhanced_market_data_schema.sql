-- =====================================================================
-- Bitcoin Stamps Enhanced Market Data Cache Schema
-- =====================================================================
-- This schema extends the existing Bitcoin Stamps database with market
-- data caching tables to solve performance issues with external API calls.
-- 
-- Performance Goals:
-- - Reduce page load times from 10+ seconds to <2 seconds
-- - Eliminate 95% of external API calls
-- - Enable sub-second query times for cached data
-- - Support both Bitcoin Stamps and SRC-20 token market data
-- =====================================================================

-- =====================================================================
-- STAMP MARKET DATA CACHE
-- =====================================================================

-- Enhanced stamp market data cache with multi-source support
CREATE TABLE IF NOT EXISTS `stamp_market_data` (
  `cpid` VARCHAR(255) PRIMARY KEY COMMENT 'Counterparty asset ID (unique identifier)',
  
  -- Floor Price Data (from Counterparty dispensers)
  `floor_price_btc` DECIMAL(16,8) NULL COMMENT 'Current floor price in BTC',
  `recent_sale_price_btc` DECIMAL(16,8) NULL COMMENT 'Most recent sale price in BTC',
  `open_dispensers_count` INTEGER DEFAULT 0 COMMENT 'Number of active dispensers',
  `closed_dispensers_count` INTEGER DEFAULT 0 COMMENT 'Number of closed dispensers',
  `total_dispensers_count` INTEGER DEFAULT 0 COMMENT 'Total dispensers ever created',
  
  -- Holder Data (from Counterparty balances API)
  `holder_count` INTEGER DEFAULT 0 COMMENT 'Total number of holders',
  `unique_holder_count` INTEGER DEFAULT 0 COMMENT 'Unique holders (excluding zero balances)',
  `top_holder_percentage` DECIMAL(5,2) DEFAULT 0 COMMENT 'Percentage held by largest holder',
  `holder_distribution_score` DECIMAL(5,2) DEFAULT 0 COMMENT 'Distribution metric (0-100, higher = more distributed)',
  
  -- Volume Data (calculated from dispenser activity)
  `volume_24h_btc` DECIMAL(16,8) DEFAULT 0 COMMENT '24-hour trading volume in BTC',
  `volume_7d_btc` DECIMAL(16,8) DEFAULT 0 COMMENT '7-day trading volume in BTC',
  `volume_30d_btc` DECIMAL(16,8) DEFAULT 0 COMMENT '30-day trading volume in BTC',
  `total_volume_btc` DECIMAL(20,8) DEFAULT 0 COMMENT 'All-time trading volume in BTC',
  
  -- Multi-Source Attribution
  `price_source` VARCHAR(50) NULL COMMENT 'Source of price data: counterparty, exchange_a, opensea',
  `volume_sources` JSON NULL COMMENT 'Volume data sources with weights: {"counterparty": 0.5, "exchange_a": 1.2}',
  `data_quality_score` DECIMAL(3,1) DEFAULT 0 COMMENT 'Data quality score 0-10 based on source reliability',
  `confidence_level` DECIMAL(3,1) DEFAULT 0 COMMENT 'Confidence in data accuracy 0-10',
  
  -- Metadata and Tracking
  `last_updated` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Last cache update time',
  `last_dispenser_block` INTEGER NULL COMMENT 'Last block where dispenser data was updated',
  `last_balance_block` INTEGER NULL COMMENT 'Last block where balance data was updated',
  `last_price_update` TIMESTAMP NULL COMMENT 'Last time price data was refreshed',
  `update_frequency_minutes` INTEGER DEFAULT 30 COMMENT 'How often this stamp should be updated (adaptive)',
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'When this record was first created',
  
  -- Performance Indexes
  INDEX `idx_floor_price_btc` (`floor_price_btc` DESC) COMMENT 'For floor price filtering and sorting',
  INDEX `idx_holder_count` (`holder_count` DESC) COMMENT 'For holder count filtering',
  INDEX `idx_last_updated` (`last_updated`) COMMENT 'For cache freshness checks',
  INDEX `idx_volume_24h` (`volume_24h_btc` DESC) COMMENT 'For volume-based sorting',
  INDEX `idx_holder_distribution` (`holder_distribution_score` DESC) COMMENT 'For distribution analysis',
  INDEX `idx_price_source` (`price_source`) COMMENT 'For source-based queries',
  INDEX `idx_data_quality` (`data_quality_score` DESC) COMMENT 'For quality-based filtering',
  INDEX `idx_update_schedule` (`last_updated`, `update_frequency_minutes`) COMMENT 'For background job scheduling',
  INDEX `idx_volume_composite` (`volume_24h_btc` DESC, `volume_7d_btc` DESC, `holder_count` DESC) COMMENT 'For trending/popular stamps',
  INDEX `idx_market_overview` (`floor_price_btc`, `holder_count`, `volume_24h_btc`, `data_quality_score`) COMMENT 'For market overview pages'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_ci 
COMMENT='Cached market data for Bitcoin Stamps to eliminate external API calls';

-- =====================================================================
-- STAMP HOLDER CACHE
-- =====================================================================

-- Detailed holder cache for individual stamp holder pages
CREATE TABLE IF NOT EXISTS `stamp_holder_cache` (
  `id` BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT 'Unique record identifier',
  `cpid` VARCHAR(255) NOT NULL COMMENT 'Counterparty asset ID',
  `address` VARCHAR(255) NOT NULL COMMENT 'Bitcoin address holding the stamp',
  `quantity` DECIMAL(20,8) NOT NULL COMMENT 'Quantity held by this address',
  `percentage` DECIMAL(5,2) NOT NULL COMMENT 'Percentage of total supply held',
  `rank_position` INTEGER NOT NULL COMMENT 'Ranking by quantity (1 = largest holder)',
  `balance_source` VARCHAR(50) DEFAULT 'counterparty' COMMENT 'Source of balance data',
  `last_updated` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Last update time',
  `last_tx_block` INTEGER NULL COMMENT 'Block of last transaction affecting this balance',
  
  -- Ensure one record per stamp-address combination
  UNIQUE KEY `unique_cpid_address` (`cpid`, `address`) COMMENT 'One record per stamp-address pair',
  
  -- Performance Indexes
  INDEX `idx_cpid_rank` (`cpid`, `rank_position`) COMMENT 'For holder ranking pages',
  INDEX `idx_cpid_quantity` (`cpid`, `quantity` DESC) COMMENT 'For quantity-based sorting',
  INDEX `idx_address` (`address`) COMMENT 'For address-based lookups',
  INDEX `idx_last_updated` (`last_updated`) COMMENT 'For cache freshness',
  INDEX `idx_percentage` (`percentage` DESC) COMMENT 'For percentage-based analysis',
  INDEX `idx_holder_analysis` (`cpid`, `percentage` DESC, `quantity` DESC) COMMENT 'For distribution analysis',
  
  -- Foreign key relationship to existing stamps table
  CONSTRAINT `fk_stamp_holder_cpid` FOREIGN KEY (`cpid`) REFERENCES `StampTableV4`(`cpid`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_ci 
COMMENT='Detailed holder information cache for stamps to avoid real-time API calls';

-- =====================================================================
-- MARKET DATA SOURCES TRACKING
-- =====================================================================

-- Track reliability and performance of different data sources
CREATE TABLE IF NOT EXISTS `market_data_sources` (
  `id` BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT 'Unique source record identifier',
  `asset_type` ENUM('stamp', 'src20') NOT NULL COMMENT 'Type of asset this source provides data for',
  `asset_id` VARCHAR(255) NOT NULL COMMENT 'Asset identifier (cpid for stamps, tick for src20)',
  `source_name` VARCHAR(50) NOT NULL COMMENT 'Source identifier: counterparty, openstamp, kucoin, etc.',
  
  -- Current Data
  `price_btc` DECIMAL(16,8) NULL COMMENT 'Current price from this source',
  `volume_24h_btc` DECIMAL(16,8) DEFAULT 0 COMMENT '24h volume from this source',
  `holder_count` INTEGER DEFAULT 0 COMMENT 'Holder count from this source',
  `market_cap_btc` DECIMAL(20,8) DEFAULT 0 COMMENT 'Market cap from this source',
  
  -- Source Reliability Metrics
  `source_confidence` DECIMAL(3,1) DEFAULT 5.0 COMMENT 'Confidence score 0-10 for this source',
  `api_response_time_ms` INTEGER DEFAULT 0 COMMENT 'Average API response time in milliseconds',
  `success_rate_24h` DECIMAL(5,2) DEFAULT 100.0 COMMENT 'Success rate over last 24 hours (0-100%)',
  `last_success` TIMESTAMP NULL COMMENT 'Last successful data fetch',
  `last_failure` TIMESTAMP NULL COMMENT 'Last failed data fetch',
  `consecutive_failures` INTEGER DEFAULT 0 COMMENT 'Number of consecutive failures',
  
  -- Update Tracking
  `last_updated` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Last update time',
  `update_count_24h` INTEGER DEFAULT 0 COMMENT 'Number of updates in last 24 hours',
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'When this source was first tracked',
  
  -- Ensure one record per asset-source combination
  UNIQUE KEY `unique_asset_source` (`asset_type`, `asset_id`, `source_name`) COMMENT 'One record per asset-source pair',
  
  -- Performance Indexes
  INDEX `idx_asset` (`asset_type`, `asset_id`) COMMENT 'For asset-based source lookups',
  INDEX `idx_source` (`source_name`) COMMENT 'For source-based analysis',
  INDEX `idx_last_updated` (`last_updated`) COMMENT 'For freshness checks',
  INDEX `idx_confidence` (`source_confidence` DESC) COMMENT 'For reliability-based selection',
  INDEX `idx_success_rate` (`success_rate_24h` DESC) COMMENT 'For performance monitoring',
  INDEX `idx_response_time` (`api_response_time_ms`) COMMENT 'For performance analysis',
  INDEX `idx_reliability_score` (`source_confidence` DESC, `success_rate_24h` DESC, `api_response_time_ms`) COMMENT 'For source ranking'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_ci 
COMMENT='Track reliability and performance metrics for different market data sources';

-- =====================================================================
-- PERFORMANCE OPTIMIZATION VIEWS
-- =====================================================================

-- View for quick stamp market overview (most common query)
CREATE OR REPLACE VIEW `v_stamp_market_overview` AS
SELECT 
    smd.cpid,
    s.stamp,
    s.creator,
    s.stamp_url,
    s.stamp_mimetype,
    smd.floor_price_btc,
    smd.holder_count,
    smd.volume_24h_btc,
    smd.data_quality_score,
    smd.last_updated,
    CASE 
        WHEN smd.last_updated > DATE_SUB(NOW(), INTERVAL 1 HOUR) THEN 'fresh'
        WHEN smd.last_updated > DATE_SUB(NOW(), INTERVAL 6 HOUR) THEN 'stale'
        ELSE 'expired'
    END as cache_status
FROM stamp_market_data smd
JOIN StampTableV4 s ON smd.cpid = s.cpid
WHERE smd.data_quality_score >= 5.0  -- Only include reliable data
ORDER BY smd.volume_24h_btc DESC, smd.holder_count DESC;

-- View for trending stamps (high volume, good distribution)
CREATE OR REPLACE VIEW `v_trending_stamps` AS
SELECT 
    smd.cpid,
    s.stamp,
    s.creator,
    smd.floor_price_btc,
    smd.holder_count,
    smd.volume_24h_btc,
    smd.volume_7d_btc,
    smd.holder_distribution_score,
    -- Calculate trending score
    (
        (smd.volume_24h_btc * 1000000) * 0.4 +  -- 24h volume weight
        (smd.holder_count) * 0.3 +               -- Holder count weight  
        (smd.holder_distribution_score) * 0.2 +  -- Distribution weight
        (smd.data_quality_score) * 0.1           -- Quality weight
    ) as trending_score
FROM stamp_market_data smd
JOIN StampTableV4 s ON smd.cpid = s.cpid
WHERE smd.volume_24h_btc > 0 
  AND smd.data_quality_score >= 6.0
  AND smd.last_updated > DATE_SUB(NOW(), INTERVAL 2 HOUR)
ORDER BY trending_score DESC
LIMIT 100;

-- =====================================================================
-- CACHE MAINTENANCE PROCEDURES
-- =====================================================================

-- Procedure to identify stale cache entries that need updating
DELIMITER //
CREATE PROCEDURE IF NOT EXISTS GetStaleStampCache(
    IN max_age_hours INT DEFAULT 2,
    IN limit_count INT DEFAULT 100
)
BEGIN
    SELECT 
        cpid,
        last_updated,
        update_frequency_minutes,
        TIMESTAMPDIFF(MINUTE, last_updated, NOW()) as minutes_since_update,
        data_quality_score
    FROM stamp_market_data 
    WHERE last_updated < DATE_SUB(NOW(), INTERVAL max_age_hours HOUR)
       OR (update_frequency_minutes > 0 AND 
           TIMESTAMPDIFF(MINUTE, last_updated, NOW()) > update_frequency_minutes)
    ORDER BY 
        data_quality_score DESC,  -- Prioritize high-quality stamps
        minutes_since_update DESC -- Then by staleness
    LIMIT limit_count;
END //
DELIMITER ;

-- Procedure to update cache statistics
DELIMITER //
CREATE PROCEDURE IF NOT EXISTS UpdateCacheStatistics()
BEGIN
    -- Update cache hit rates and performance metrics
    SELECT 
        COUNT(*) as total_stamps,
        COUNT(CASE WHEN last_updated > DATE_SUB(NOW(), INTERVAL 1 HOUR) THEN 1 END) as fresh_count,
        COUNT(CASE WHEN last_updated > DATE_SUB(NOW(), INTERVAL 6 HOUR) THEN 1 END) as acceptable_count,
        AVG(data_quality_score) as avg_quality_score,
        AVG(holder_count) as avg_holder_count,
        SUM(volume_24h_btc) as total_24h_volume
    FROM stamp_market_data;
END //
DELIMITER ;

-- =====================================================================
-- INITIAL DATA POPULATION QUERIES
-- =====================================================================

-- Query to identify stamps that need initial market data population
-- (This will be used by the background job system)
/*
SELECT DISTINCT s.cpid, s.stamp, s.creator
FROM StampTableV4 s
LEFT JOIN stamp_market_data smd ON s.cpid = smd.cpid
WHERE s.is_btc_stamp = 1 
  AND s.cpid IS NOT NULL
  AND smd.cpid IS NULL  -- Not yet in cache
ORDER BY s.stamp DESC  -- Start with newest stamps
LIMIT 1000;
*/

-- =====================================================================
-- SCHEMA VALIDATION AND CONSTRAINTS
-- =====================================================================

-- Add constraints to ensure data integrity
ALTER TABLE `stamp_market_data` 
ADD CONSTRAINT `chk_floor_price_positive` CHECK (`floor_price_btc` >= 0),
ADD CONSTRAINT `chk_holder_count_positive` CHECK (`holder_count` >= 0),
ADD CONSTRAINT `chk_volume_positive` CHECK (`volume_24h_btc` >= 0 AND `volume_7d_btc` >= 0 AND `volume_30d_btc` >= 0),
ADD CONSTRAINT `chk_percentage_valid` CHECK (`top_holder_percentage` >= 0 AND `top_holder_percentage` <= 100),
ADD CONSTRAINT `chk_distribution_score_valid` CHECK (`holder_distribution_score` >= 0 AND `holder_distribution_score` <= 100),
ADD CONSTRAINT `chk_quality_score_valid` CHECK (`data_quality_score` >= 0 AND `data_quality_score` <= 10),
ADD CONSTRAINT `chk_confidence_valid` CHECK (`confidence_level` >= 0 AND `confidence_level` <= 10);

ALTER TABLE `stamp_holder_cache`
ADD CONSTRAINT `chk_quantity_positive` CHECK (`quantity` >= 0),
ADD CONSTRAINT `chk_percentage_valid_holder` CHECK (`percentage` >= 0 AND `percentage` <= 100),
ADD CONSTRAINT `chk_rank_positive` CHECK (`rank_position` > 0);

ALTER TABLE `market_data_sources`
ADD CONSTRAINT `chk_price_positive_source` CHECK (`price_btc` >= 0),
ADD CONSTRAINT `chk_volume_positive_source` CHECK (`volume_24h_btc` >= 0),
ADD CONSTRAINT `chk_confidence_valid_source` CHECK (`source_confidence` >= 0 AND `source_confidence` <= 10),
ADD CONSTRAINT `chk_success_rate_valid` CHECK (`success_rate_24h` >= 0 AND `success_rate_24h` <= 100),
ADD CONSTRAINT `chk_response_time_positive` CHECK (`api_response_time_ms` >= 0);

-- =====================================================================
-- SCHEMA DOCUMENTATION
-- =====================================================================

/*
SCHEMA DESIGN NOTES:

1. PERFORMANCE OPTIMIZATIONS:
   - Composite indexes for common query patterns
   - Separate holder cache table to avoid JOIN overhead
   - Views for frequently accessed data combinations
   - Stored procedures for maintenance operations

2. DATA INTEGRITY:
   - Foreign key constraints where appropriate
   - Check constraints for data validation
   - Unique constraints to prevent duplicates
   - Proper data types with sufficient precision

3. SCALABILITY CONSIDERATIONS:
   - Partitioning-ready design (can partition by cpid hash)
   - Adaptive update frequencies to reduce load
   - Source reliability tracking for smart fallbacks
   - Efficient cache invalidation strategies

4. MONITORING AND MAINTENANCE:
   - Built-in cache freshness tracking
   - Source performance metrics
   - Data quality scoring
   - Automated stale data identification

5. MULTI-SOURCE SUPPORT:
   - JSON fields for flexible source attribution
   - Confidence scoring for data reliability
   - Source-specific performance tracking
   - Conflict resolution through weighted averaging

This schema is designed to support the Bitcoin Stamps Market Data Cache System
with the goal of reducing page load times from 10+ seconds to <2 seconds by
eliminating 95% of external API calls while maintaining data accuracy and freshness.
*/ 