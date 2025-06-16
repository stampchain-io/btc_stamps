USE `btc_stamps`;
CREATE TABLE IF NOT EXISTS blocks (
  `block_index` INT,
  `block_hash` VARCHAR(64),
  `block_time` datetime,
  `previous_block_hash` VARCHAR(64) UNIQUE,
  `difficulty` FLOAT,
  `ledger_hash` VARCHAR(64),
  `txlist_hash` VARCHAR(64),
  `messages_hash` VARCHAR(64),
  `indexed` tinyint(1) DEFAULT NULL,
  PRIMARY KEY (`block_index`, `block_hash`),
  UNIQUE (`block_hash`),
  UNIQUE (`previous_block_hash`),
  INDEX `index_hash_idx` (`block_index`, `block_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_ci;

CREATE TABLE IF NOT EXISTS transactions (
  `tx_index` INT,
  `tx_hash` VARCHAR(64),
  `block_index` INT,
  `block_hash` VARCHAR(64),
  `block_time` datetime,
  `source` VARCHAR(64) COLLATE utf8mb4_bin,
  `destination` TEXT COLLATE utf8mb4_bin,
  `btc_amount` BIGINT,
  `fee` BIGINT,
  `data` MEDIUMBLOB,
  `supported` BIT DEFAULT 1,
  `keyburn` tinyint(1) DEFAULT NULL,
  PRIMARY KEY (`tx_index`),
  UNIQUE (`tx_hash`),
  UNIQUE KEY `tx_hash_index` (`tx_hash`, `tx_index`),
  INDEX `block_hash_index` (`block_index`, `block_hash`),
  INDEX `idx_block_index_time` (`block_index`, `block_time`),
  CONSTRAINT transactions_blocks_fk FOREIGN KEY (`block_index`, `block_hash`) REFERENCES blocks(`block_index`, `block_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_ci;

CREATE TABLE IF NOT EXISTS `StampTableV4` (
  `stamp` int NOT NULL,
  `block_index` int,
  `cpid` varchar(25) DEFAULT NULL,
  `asset_longname` varchar(255) DEFAULT NULL,
  `creator` varchar(62) COLLATE utf8mb4_bin,
  `divisible` tinyint(1) DEFAULT NULL,
  `keyburn` tinyint(1) DEFAULT NULL,
  `locked` tinyint(1) DEFAULT NULL,
  `message_index` int DEFAULT NULL,
  `stamp_base64` mediumtext,
  `stamp_mimetype` varchar(24) DEFAULT NULL,
  `stamp_url` varchar(106) DEFAULT NULL,
  `supply` bigint unsigned DEFAULT NULL,
  `block_time` datetime NULL DEFAULT NULL,
  `tx_hash` varchar(64) NOT NULL,
  `tx_index` int NOT NULL,
  `src_data` json DEFAULT NULL,
  `ident` varchar(7) DEFAULT NULL,
  `stamp_hash` varchar(255) DEFAULT NULL,
  `is_btc_stamp` tinyint(1) DEFAULT NULL,
  `is_reissue` tinyint(1) DEFAULT NULL,
  `file_hash` varchar(255) DEFAULT NULL,
  `is_valid_base64` tinyint(1) DEFAULT NULL,
  `file_size_bytes` int DEFAULT NULL COMMENT 'Size of the decoded stamp file in bytes',
  PRIMARY KEY (`stamp`),
  UNIQUE `tx_hash` (`tx_hash`),
  UNIQUE `stamp_hash` (`stamp_hash`),
  INDEX `cpid_index` (`cpid`),
  INDEX `ident_index` (`ident`),
  INDEX `creator_index` (`creator`(42)),
  INDEX `is_btc_stamp_index` (`is_btc_stamp`),
  INDEX `idx_stamp` (`is_btc_stamp`, `ident`, `stamp` DESC, `tx_index` DESC),
  INDEX `idx_tx_index_block_time` (`tx_index`, `block_time`),
  INDEX `idx_ident_stamp` (`ident`, `stamp`),
  INDEX `idx_creator_tx_index` (`creator`(42), `tx_index`),
  INDEX `idx_stamp_url_mimetype` (`stamp_url`(97), `stamp_mimetype`),
  INDEX `idx_stamp_file` (`stamp_hash`, `stamp_mimetype`, `stamp_url`(97)),
  INDEX `idx_cpid_ident` (`cpid`, `ident`),
  INDEX `idx_stamp_count` (`is_btc_stamp`, `ident`, `creator`(42)),
  INDEX `idx_stamp_details` (
    `stamp`,
    `block_index`,
    `cpid`,
    `creator`(42),
    `stamp_url`(97),
    `stamp_mimetype`,
    `block_time`,
    `tx_hash`,
    `ident`
  ),
  FOREIGN KEY (`tx_hash`, `tx_index`) REFERENCES transactions(`tx_hash`, `tx_index`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_ci;

CREATE TABLE IF NOT EXISTS `srcbackground` (
  `tick` varchar(16) NOT NULL,
  `tick_hash` varchar(64),
  `base64` mediumtext,
  `font_size` varchar(8) DEFAULT NULL,
  `text_color` varchar(16) DEFAULT NULL,
  `unicode` varchar(16) DEFAULT NULL,
  `p` varchar(16) NOT NULL,
  PRIMARY KEY (`tick`,`p`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_ci;

CREATE TABLE IF NOT EXISTS `creator` (
  `address` varchar(64) COLLATE utf8mb4_bin NOT NULL,
  `creator` varchar(255) COLLATE utf8mb4_bin DEFAULT NULL,
  PRIMARY KEY (`address`),
  INDEX `idx_creator_name` (`creator`(100)),
  INDEX `idx_address_creator` (`address`, `creator`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_ci;

CREATE TABLE IF NOT EXISTS `SRC20` (
  `id` VARCHAR(255) NOT NULL,
  `tx_hash` VARCHAR(64) NOT NULL,
  `tx_index` int NOT NULL,
  `block_index` int,
  `p` varchar(32),
  `op` varchar(32),
  `tick` varchar(32),
  `tick_hash` varchar(64),
  `creator` varchar(64) COLLATE utf8mb4_bin,
  `amt` decimal(38,18) DEFAULT NULL,
  `deci` int DEFAULT '18',
  `lim` BIGINT UNSIGNED DEFAULT NULL,
  `max` BIGINT UNSIGNED DEFAULT NULL,
  `destination` varchar(255) COLLATE utf8mb4_bin,
  `block_time` datetime DEFAULT NULL,
  `status` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_ci;

CREATE TABLE IF NOT EXISTS `SRC20Valid` (
  `id` VARCHAR(255) NOT NULL,
  `tx_hash` VARCHAR(64) NOT NULL,
  `tx_index` int NOT NULL,
  `block_index` int,
  `p` varchar(32),
  `op` varchar(32),
  `tick` varchar(32),
  `tick_hash` varchar(64),
  `creator` varchar(64) COLLATE utf8mb4_bin,
  `amt` decimal(38,18) DEFAULT NULL,
  `deci` int DEFAULT '18',
  `lim` BIGINT UNSIGNED DEFAULT NULL,
  `max` BIGINT UNSIGNED DEFAULT NULL,
  `destination` varchar(255) COLLATE utf8mb4_bin,
  `block_time` datetime DEFAULT NULL,
  `status` varchar(255) DEFAULT NULL,
  `locked_amt` decimal(38,18),
  `locked_block` int,
  `creator_bal` decimal(38,18) DEFAULT NULL,
  `destination_bal` decimal(38,18) DEFAULT NULL,
  PRIMARY KEY (`id`),
  INDEX `tick` (`tick`),
  INDEX `op` (`op`),
  INDEX `idx_src20valid_tick_op_max_deci_lim` (`tick`, `op`, `max`, `deci`, `lim`),
  INDEX `idx_tick_creator_bal` (`tick`, `creator`, `creator_bal`),
  INDEX `idx_tick_destination_bal` (`tick`, `destination`, `destination_bal`),
  INDEX `idx_tick_block_time` (`tick`, `block_time`),
  INDEX `idx_tick_hash` (`tick_hash`),
  INDEX `idx_tick_block_index` (`tick`, `block_index`),
  INDEX `idx_tick_creator_time` (`tick`, `creator`, `block_time`),
  INDEX `idx_creator_destination` (`creator`, `destination`),
  INDEX `idx_src20_common_lookup` (
    `block_index`, 
    `tx_hash`,
    `p`,
    `op`,
    `tick`,
    `creator`,
    `amt`,
    `deci`,
    `lim`,
    `max`,
    `destination`,
    `block_time`
  ),
  INDEX `idx_deploy_lookup` (
    `op`,
    `tick`,
    `block_index`,
    `tx_hash`,
    `creator`,
    `amt`,
    `deci`,
    `lim`,
    `max`,
    `block_time`
  )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_ci;

CREATE TABLE IF NOT EXISTS `balances` (
  `id` VARCHAR(255) NOT NULL,
  `address` varchar(64) COLLATE utf8mb4_bin NOT NULL,
  `p` varchar(32),
  `tick` varchar(32),
  `tick_hash` varchar(64),
  `amt` decimal(38,18),
  `locked_amt` decimal(38,18),
  `block_time` datetime,
  `last_update` int,
  PRIMARY KEY (`id`),
  UNIQUE KEY `address_p_tick_unique` (`address`, `p`, `tick`, `tick_hash`),
  INDEX `tick_tick_hash` (`tick`, `tick_hash`),
  INDEX `idx_address_tick_amt_update` (`address`, `tick`, `amt`, `last_update`),
  INDEX `idx_balance_stats` (`tick`, `amt`, `address`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_ci;

CREATE TABLE IF NOT EXISTS s3objects (
  `id` VARCHAR(255) NOT NULL,
  `path_key` VARCHAR(255) NOT NULL,
  `md5` VARCHAR(255) NOT NULL,
  PRIMARY KEY (id),
  index `path_key` (`path_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_ci;

CREATE TABLE IF NOT EXISTS collections (
  `collection_id` BINARY(16) PRIMARY KEY,
  `collection_name` VARCHAR(255) NOT NULL UNIQUE,
  `collection_description` VARCHAR(255),
  `collection_website` VARCHAR(255),
  `collection_tg` VARCHAR(32),
  `collection_x` VARCHAR(32),
  `collection_email` VARCHAR(255),
  `collection_onchain` TINYINT(1) DEFAULT 0,
  INDEX `idx_collection_lookup` (collection_id, collection_name, collection_onchain)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_ci;

CREATE TABLE IF NOT EXISTS collection_creators (
  `collection_id` BINARY(16),
  `creator_address` VARCHAR(64) COLLATE utf8mb4_bin,
  FOREIGN KEY (collection_id) REFERENCES collections(collection_id),
  FOREIGN KEY (creator_address) REFERENCES creator(address),
  PRIMARY KEY (collection_id, creator_address),
  INDEX (creator_address)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_ci;

CREATE TABLE IF NOT EXISTS collection_stamps (
  `collection_id` BINARY(16),
  `stamp` INT,
  FOREIGN KEY (collection_id) REFERENCES collections(collection_id),
  FOREIGN KEY (stamp) REFERENCES StampTableV4(stamp),
  PRIMARY KEY (collection_id, stamp),
  INDEX `idx_collection_stamp` (collection_id, stamp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_ci;

CREATE TABLE IF NOT EXISTS `src20_metadata` (
  `tick` varchar(32) NOT NULL,
  `tick_hash` varchar(64) NOT NULL,
  `description` varchar(255) DEFAULT NULL,
  `x` varchar(32) DEFAULT NULL,
  `tg` varchar(32) DEFAULT NULL,
  `web` varchar(255) DEFAULT NULL,
  `email` varchar(255) DEFAULT NULL,
  `deploy_block_index` int NOT NULL,
  `deploy_tx_hash` varchar(64) NOT NULL,
  PRIMARY KEY (`tick`, `tick_hash`),
  UNIQUE KEY `tick_unique` (`tick`),
  UNIQUE KEY `tick_hash_unique` (`tick_hash`),
  INDEX `deploy_block_index` (`deploy_block_index`),
  INDEX `deploy_tx_hash` (`deploy_tx_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_ci;

CREATE TABLE IF NOT EXISTS `SRC101` (
  `id` VARCHAR(255) NOT NULL,
  `tx_hash` VARCHAR(64) NOT NULL,
  `tx_index` int NOT NULL,
  `block_index` int,
  `p` varchar(32),
  `op` varchar(32),
  `name` varchar(32),
  `root` varchar(32),
  `tokenid_origin` varchar(255) DEFAULT NULL,
  `tokenid` varchar(255) DEFAULT NULL,
  `tokenid_utf8` varchar(255) DEFAULT NULL COLLATE utf8mb4_bin,
  `img` varchar(4096) DEFAULT NULL COLLATE utf8mb4_bin,
  `description` varchar(255),
  `tick` varchar(32),
  `imglp` varchar(255) DEFAULT NULL COLLATE utf8mb4_bin,
  `imgf` varchar(32) DEFAULT NULL COLLATE utf8mb4_bin,
  `wla` VARCHAR(66) DEFAULT NULL,
  `tick_hash` varchar(64),
  `deploy_hash` VARCHAR(64) DEFAULT NULL,
  `creator` varchar(64) COLLATE utf8mb4_bin,
  `pri` varchar(255) DEFAULT NULL COLLATE utf8mb4_bin,
  `dua` BIGINT UNSIGNED DEFAULT NULL,
  `idua` BIGINT UNSIGNED DEFAULT NULL,
  `coef` int DEFAULT NULL,
  `lim` BIGINT UNSIGNED DEFAULT NULL,
  `mintstart` BIGINT UNSIGNED DEFAULT NULL,
  `mintend` BIGINT UNSIGNED DEFAULT NULL,
  `prim` BOOLEAN DEFAULT NULL,
  `address_btc` varchar(255) DEFAULT NULL COLLATE utf8mb4_bin,
  `address_eth` varchar(255) DEFAULT NULL COLLATE utf8mb4_bin,
  `txt_data` TEXT DEFAULT NULL COLLATE utf8mb4_bin,
  `owner` varchar(255) COLLATE utf8mb4_bin,
  `toaddress` varchar(255) COLLATE utf8mb4_bin,
  `destination` varchar(255) COLLATE utf8mb4_bin,
  `destination_nvalue` BIGINT UNSIGNED DEFAULT NULL,
  `block_time` datetime DEFAULT NULL,
  `status` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  INDEX `block_index` (`block_index`),
  INDEX `idx_deploy_hash_tokenid` (`deploy_hash`, `tokenid`),
  INDEX `idx_creator_tick` (`creator`, `tick`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_ci;

CREATE TABLE IF NOT EXISTS `SRC101Valid` (
  `id` VARCHAR(255) NOT NULL,
  `tx_hash` VARCHAR(64) NOT NULL,
  `tx_index` int NOT NULL,
  `block_index` int,
  `p` varchar(32),
  `op` varchar(32),
  `name` varchar(32),
  `root` varchar(32),
  `tokenid_origin` varchar(255) DEFAULT NULL,
  `tokenid` varchar(255) DEFAULT NULL,
  `tokenid_utf8` varchar(255) DEFAULT NULL COLLATE utf8mb4_bin,
  `img` varchar(4096) DEFAULT NULL COLLATE utf8mb4_bin,
  `description` varchar(255),
  `tick` varchar(32),
  `imglp` varchar(255) DEFAULT NULL COLLATE utf8mb4_bin,
  `imgf` varchar(32) DEFAULT NULL COLLATE utf8mb4_bin,
  `wla` VARCHAR(66) DEFAULT NULL,
  `tick_hash` varchar(64),
  `deploy_hash` VARCHAR(64) DEFAULT NULL,
  `creator` varchar(64) COLLATE utf8mb4_bin,
  `pri` varchar(255) DEFAULT NULL COLLATE utf8mb4_bin,
  `dua` BIGINT UNSIGNED DEFAULT NULL,
  `idua` BIGINT UNSIGNED DEFAULT NULL,
  `coef` int DEFAULT NULL,
  `lim` BIGINT UNSIGNED DEFAULT NULL,
  `mintstart` BIGINT UNSIGNED DEFAULT NULL,
  `mintend` BIGINT UNSIGNED DEFAULT NULL,
  `prim` BOOLEAN DEFAULT NULL,
  `address_btc` varchar(255) DEFAULT NULL COLLATE utf8mb4_bin,
  `address_eth` varchar(255) DEFAULT NULL COLLATE utf8mb4_bin,
  `txt_data` TEXT DEFAULT NULL COLLATE utf8mb4_bin,
  `owner` varchar(255) COLLATE utf8mb4_bin,
  `toaddress` varchar(255) COLLATE utf8mb4_bin,
  `destination` varchar(255) COLLATE utf8mb4_bin,
  `destination_nvalue` BIGINT UNSIGNED DEFAULT NULL,
  `block_time` datetime DEFAULT NULL,
  `status` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  INDEX `block_index` (`block_index`),
  INDEX `idx_deploy_hash` (`deploy_hash`),
  INDEX `idx_tokenid_utf8` (`tokenid_utf8`),
  INDEX `idx_creator` (`creator`),
  INDEX `idx_deploy_hash_tokenid_time` (`deploy_hash`, `tokenid`, `block_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_ci;

CREATE TABLE IF NOT EXISTS `owners` (
  `index` INT NOT NULL,
  `id` VARCHAR(255) NOT NULL,
  `p` varchar(32),
  `deploy_hash` VARCHAR(64) NOT NULL,
  `tokenid` varchar(255) NOT NULL,
  `tokenid_utf8` varchar(255) DEFAULT NULL COLLATE utf8mb4_bin,
  `img` varchar(255) DEFAULT NULL COLLATE utf8mb4_bin,
  `preowner` varchar(64) COLLATE utf8mb4_bin,
  `owner` varchar(64) COLLATE utf8mb4_bin NOT NULL,
  `prim` BOOLEAN DEFAULT NULL,
  `address_btc` varchar(255) DEFAULT NULL COLLATE utf8mb4_bin,
  `address_eth` varchar(255) DEFAULT NULL COLLATE utf8mb4_bin,
  `txt_data` TEXT DEFAULT NULL COLLATE utf8mb4_bin,
  `expire_timestamp` BIGINT UNSIGNED DEFAULT NULL,
  `last_update` int,
  PRIMARY KEY (`id`),
  INDEX `index_deploy_hash` (`index`, `deploy_hash`),
  INDEX `owner` (`owner`),
  INDEX `deploy_hash` (`deploy_hash`),
  INDEX `p_deploy_hash_tokenid` (`p`,`deploy_hash`,`tokenid`),
  UNIQUE INDEX `p_deploy_hash_tokenid_utf8_unique` (`p`,`deploy_hash`,`tokenid_utf8`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_ci;

CREATE TABLE IF NOT EXISTS `recipients` (
  `id` VARCHAR(255) NOT NULL,
  `p` varchar(32),
  `deploy_hash` VARCHAR(64) NOT NULL,
  `address` varchar(64) COLLATE utf8mb4_bin NOT NULL,
  `block_index` int,
  PRIMARY KEY (`id`),
  UNIQUE KEY `p_deploy_hash_address_unique` (`p`, `deploy_hash`, `address`),
  INDEX `address` (`address`),
  INDEX `block_index` (`block_index`),
  INDEX `p_deploy_hash_address` (`p`,`deploy_hash`,`address`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_ci;

CREATE TABLE IF NOT EXISTS `src101price` (
  `id` VARCHAR(255) NOT NULL,
  `len` INT NOT NULL,
  `price` BIGINT NOT NULL,
  `deploy_hash` VARCHAR(64) NOT NULL,
  `block_index` int,
  PRIMARY KEY (`id`),
  INDEX `block_index` (`block_index`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_ci;

CREATE TABLE IF NOT EXISTS `src20_token_stats` (
  `tick` varchar(32) NOT NULL,
  `total_minted` decimal(38,18) DEFAULT NULL,
  `holders_count` int DEFAULT NULL,
  `last_updated` timestamp DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`tick`),
  INDEX `idx_token_stats` (`tick`, `total_minted`, `holders_count`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_ci;

CREATE TABLE IF NOT EXISTS `stamp_views` (
  `stamp` int NOT NULL,
  `view_count` bigint unsigned DEFAULT 0,
  `last_viewed` timestamp DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `created_at` timestamp DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`stamp`),
  FOREIGN KEY (`stamp`) REFERENCES StampTableV4(`stamp`) ON DELETE CASCADE,
  INDEX `idx_view_count` (`view_count` DESC),
  INDEX `idx_last_viewed` (`last_viewed` DESC),
  INDEX `idx_popular_stamps` (`view_count` DESC, `last_viewed` DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_ci;

CREATE OR REPLACE VIEW v_src20_token_stats AS
SELECT 
    b.tick,
    SUM(b.amt) as total_minted,
    COUNT(DISTINCT b.address) as holders_count
FROM balances b
WHERE b.amt > 0
GROUP BY b.tick;

-- Initial population of src20_token_stats
INSERT INTO src20_token_stats (tick, total_minted, holders_count)
SELECT * FROM v_src20_token_stats
ON DUPLICATE KEY UPDATE
    total_minted = VALUES(total_minted),
    holders_count = VALUES(holders_count);

-- =====================================================================
-- ENHANCED MARKET DATA CACHE TABLES
-- =====================================================================
-- These tables implement the Bitcoin Stamps Market Data Cache System
-- to eliminate external API calls and improve performance from 10+ seconds to <2 seconds
-- =====================================================================

-- Enhanced stamp market data cache with multi-source support
CREATE TABLE IF NOT EXISTS `stamp_market_data` (
  `cpid` VARCHAR(25) PRIMARY KEY COMMENT 'Counterparty asset ID (unique identifier)',
  
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
  
  -- Foreign Key Constraint (works with existing cpid index)
  CONSTRAINT `fk_stamp_market_cpid` FOREIGN KEY (`cpid`) REFERENCES `StampTableV4`(`cpid`),
  
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_ci COMMENT='Cached market data for Bitcoin Stamps to eliminate external API calls';

-- Detailed holder cache for individual stamp holder pages
CREATE TABLE IF NOT EXISTS `stamp_holder_cache` (
  `id` BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT 'Unique record identifier',
  `cpid` VARCHAR(25) NOT NULL COMMENT 'Counterparty asset ID',
  `address` VARCHAR(255) NOT NULL COMMENT 'Bitcoin address holding the stamp',
  `quantity` DECIMAL(20,8) NOT NULL COMMENT 'Quantity held by this address',
  `percentage` DECIMAL(5,2) NOT NULL COMMENT 'Percentage of total supply held',
  `rank_position` INTEGER NOT NULL COMMENT 'Ranking by quantity (1 = largest holder)',
  `balance_source` VARCHAR(50) DEFAULT 'counterparty' COMMENT 'Source of balance data',
  `last_updated` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Last update time',
  `last_tx_block` INTEGER NULL COMMENT 'Block of last transaction affecting this balance',
  
  -- Foreign Key Constraint (works with existing cpid index)
  CONSTRAINT `fk_stamp_holder_cpid` FOREIGN KEY (`cpid`) REFERENCES `StampTableV4`(`cpid`),
  
  -- Ensure one record per stamp-address combination
  UNIQUE KEY `unique_cpid_address` (`cpid`, `address`) COMMENT 'One record per stamp-address pair',
  
  -- Performance Indexes
  INDEX `idx_cpid_rank` (`cpid`, `rank_position`) COMMENT 'For holder ranking pages',
  INDEX `idx_cpid_quantity` (`cpid`, `quantity` DESC) COMMENT 'For quantity-based sorting',
  INDEX `idx_address` (`address`) COMMENT 'For address-based lookups',
  INDEX `idx_last_updated` (`last_updated`) COMMENT 'For cache freshness',
  INDEX `idx_percentage` (`percentage` DESC) COMMENT 'For percentage-based analysis',
  INDEX `idx_holder_analysis` (`cpid`, `percentage` DESC, `quantity` DESC) COMMENT 'For distribution analysis'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_ci COMMENT='Detailed holder information cache for stamps to avoid real-time API calls';

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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_ci COMMENT='Track reliability and performance metrics for different market data sources';

-- SRC-20 token market data cache for exchange-based data
CREATE TABLE IF NOT EXISTS `src20_market_data` (
  `tick` VARCHAR(32) PRIMARY KEY COMMENT 'SRC-20 token ticker symbol',
  
  -- Price Data (from multiple exchanges)
  `price_btc` DECIMAL(16,8) NULL COMMENT 'Current price in BTC',
  `price_usd` DECIMAL(16,8) NULL COMMENT 'Current price in USD',
  `floor_price_btc` DECIMAL(16,8) NULL COMMENT 'Floor price from marketplace',
  `market_cap_btc` DECIMAL(20,8) DEFAULT 0 COMMENT 'Market capitalization in BTC',
  `market_cap_usd` DECIMAL(20,8) DEFAULT 0 COMMENT 'Market capitalization in USD',
  
  -- Volume Data (aggregated from exchanges)
  `volume_24h_btc` DECIMAL(16,8) DEFAULT 0 COMMENT '24-hour trading volume in BTC',
  `volume_7d_btc` DECIMAL(16,8) DEFAULT 0 COMMENT '7-day trading volume in BTC',
  `volume_30d_btc` DECIMAL(16,8) DEFAULT 0 COMMENT '30-day trading volume in BTC',
  `total_volume_btc` DECIMAL(20,8) DEFAULT 0 COMMENT 'All-time trading volume in BTC',
  
  -- Price Change Data
  `price_change_24h_percent` DECIMAL(8,4) DEFAULT 0 COMMENT '24-hour price change percentage',
  `price_change_7d_percent` DECIMAL(8,4) DEFAULT 0 COMMENT '7-day price change percentage',
  `price_change_30d_percent` DECIMAL(8,4) DEFAULT 0 COMMENT '30-day price change percentage',
  
  -- Holder Data (from balances table)
  `holder_count` INTEGER DEFAULT 0 COMMENT 'Total number of holders',
  `circulating_supply` DECIMAL(38,18) DEFAULT 0 COMMENT 'Circulating supply',
  `max_supply` DECIMAL(38,18) DEFAULT 0 COMMENT 'Maximum supply',
  
  -- Multi-Source Attribution
  `primary_exchange` VARCHAR(50) NULL COMMENT 'Primary exchange for price data',
  `exchange_sources` JSON NULL COMMENT 'Exchange data sources with weights',
  `data_quality_score` DECIMAL(3,1) DEFAULT 0 COMMENT 'Data quality score 0-10',
  `confidence_level` DECIMAL(3,1) DEFAULT 0 COMMENT 'Confidence in data accuracy 0-10',
  
  -- Metadata and Tracking
  `last_updated` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Last cache update time',
  `last_price_update` TIMESTAMP NULL COMMENT 'Last time price data was refreshed',
  `update_frequency_minutes` INTEGER DEFAULT 10 COMMENT 'How often this token should be updated (adaptive)',
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'When this record was first created',
  
  -- Performance Indexes
  INDEX `idx_price_btc` (`price_btc` DESC) COMMENT 'For price filtering and sorting',
  INDEX `idx_market_cap` (`market_cap_btc` DESC) COMMENT 'For market cap sorting',
  INDEX `idx_volume_24h` (`volume_24h_btc` DESC) COMMENT 'For volume-based sorting',
  INDEX `idx_holder_count` (`holder_count` DESC) COMMENT 'For holder count filtering',
  INDEX `idx_price_change` (`price_change_24h_percent` DESC) COMMENT 'For price change sorting',
  INDEX `idx_last_updated` (`last_updated`) COMMENT 'For cache freshness checks',
  INDEX `idx_data_quality` (`data_quality_score` DESC) COMMENT 'For quality-based filtering',
  INDEX `idx_update_schedule` (`last_updated`, `update_frequency_minutes`) COMMENT 'For background job scheduling',
  INDEX `idx_market_overview` (`floor_price_btc`, `holder_count`, `volume_24h_btc`, `data_quality_score`) COMMENT 'For market overview pages'
  
  -- Note: Foreign key constraint removed to work with existing database constraints
  -- Data integrity maintained by application logic
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_ci COMMENT='Cached market data for SRC-20 tokens from multiple exchanges';

-- Collection-level market data aggregation
CREATE TABLE IF NOT EXISTS `collection_market_data` (
  `collection_id` BINARY(16) PRIMARY KEY COMMENT 'Collection identifier',
  
  -- Aggregated Price Data
  `floor_price_btc` DECIMAL(16,8) NULL COMMENT 'Collection floor price in BTC',
  `avg_price_btc` DECIMAL(16,8) NULL COMMENT 'Average price in BTC',
  `total_value_btc` DECIMAL(20,8) DEFAULT 0 COMMENT 'Total collection value in BTC',
  
  -- Volume Data
  `volume_24h_btc` DECIMAL(16,8) DEFAULT 0 COMMENT '24-hour trading volume in BTC',
  `volume_7d_btc` DECIMAL(16,8) DEFAULT 0 COMMENT '7-day trading volume in BTC',
  `volume_30d_btc` DECIMAL(16,8) DEFAULT 0 COMMENT '30-day trading volume in BTC',
  `total_volume_btc` DECIMAL(20,8) DEFAULT 0 COMMENT 'All-time trading volume in BTC',
  
  -- Collection Statistics
  `total_stamps` INTEGER DEFAULT 0 COMMENT 'Total stamps in collection',
  `unique_holders` INTEGER DEFAULT 0 COMMENT 'Number of unique holders',
  `listed_stamps` INTEGER DEFAULT 0 COMMENT 'Number of stamps currently listed',
  `sold_stamps_24h` INTEGER DEFAULT 0 COMMENT 'Stamps sold in last 24 hours',
  
  -- Metadata and Tracking
  `last_updated` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Last cache update time',
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'When this record was first created',
  
  -- Performance Indexes
  INDEX `idx_floor_price` (`floor_price_btc` DESC) COMMENT 'For floor price sorting',
  INDEX `idx_volume_24h` (`volume_24h_btc` DESC) COMMENT 'For volume sorting',
  INDEX `idx_total_value` (`total_value_btc` DESC) COMMENT 'For total value sorting',
  INDEX `idx_unique_holders` (`unique_holders` DESC) COMMENT 'For holder count sorting',
  INDEX `idx_last_updated` (`last_updated`) COMMENT 'For cache freshness checks'
  
  -- Note: Foreign key constraint removed to work with existing database constraints
  -- Data integrity maintained by application logic
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_ci COMMENT='Aggregated market data for stamp collections';

-- Performance optimization views
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
-- END ENHANCED MARKET DATA CACHE TABLES
-- =====================================================================

-- fix owners table