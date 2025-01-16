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
  PRIMARY KEY (`stamp`),
  UNIQUE `tx_hash` (`tx_hash`),
  UNIQUE `stamp_hash` (`stamp_hash`),
  INDEX `cpid_index` (`cpid`(20)),
  INDEX `ident_index` (`ident`),
  INDEX `creator_index` (`creator`(42)),
  INDEX `is_btc_stamp_index` (`is_btc_stamp`),
  INDEX `idx_stamp` (`is_btc_stamp`, `ident`, `stamp` DESC, `tx_index` DESC),
  INDEX `idx_tx_index_block_time` (`tx_index`, `block_time`),
  INDEX `idx_ident_stamp` (`ident`, `stamp`),
  INDEX `idx_creator_tx_index` (`creator`(42), `tx_index`),
  INDEX `idx_stamp_url_mimetype` (`stamp_url`(97), `stamp_mimetype`),
  INDEX `idx_stamp_file` (`stamp_hash`, `stamp_mimetype`, `stamp_url`(97)),
  INDEX `idx_cpid_ident` (`cpid`(20), `ident`),
  INDEX `idx_stamp_count` (`is_btc_stamp`, `ident`, `creator`(42)),
  INDEX `idx_stamp_details` (
    `stamp`,
    `block_index`,
    `cpid`(20),
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
  UNIQUE KEY `p_deploy_hash_tokenid_unique` (`p`, `deploy_hash`, `tokenid`),
  INDEX `index_deploy_hash` (`index`, `deploy_hash`),
  INDEX `owner` (`owner`),
  INDEX `deploy_hash` (`deploy_hash`),
  INDEX `p_deploy_hash_tokenid_utf8` (`p`,`deploy_hash`,`tokenid_utf8`)
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
  `price`BIGINT NOT NULL,
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

-- -- Remove redundant indexes
-- ALTER TABLE transactions DROP INDEX idx_block_time;
-- ALTER TABLE StampTableV4 DROP INDEX block_index;
-- ALTER TABLE StampTableV4 DROP INDEX stamp_index;
-- ALTER TABLE balances DROP INDEX address;
-- ALTER TABLE balances DROP INDEX tick;
-- ALTER TABLE balances DROP INDEX idx_address_tick_amt;
-- ALTER TABLE balances DROP INDEX idx_tick_last_update;
-- ALTER TABLE collection_stamps DROP INDEX stamp;

-- -- Add new optimized indexes
-- ALTER TABLE transactions ADD INDEX idx_block_index_time (block_index, block_time);

-- ALTER TABLE StampTableV4 ADD INDEX idx_tx_index_block_time (tx_index, block_time);
-- ALTER TABLE StampTableV4 ADD INDEX idx_ident_stamp (ident, stamp);
-- ALTER TABLE StampTableV4 ADD INDEX idx_creator_tx_index (creator, tx_index);
-- ALTER TABLE StampTableV4 ADD INDEX idx_stamp_url_mimetype (stamp_url(100), stamp_mimetype(50));
-- ALTER TABLE StampTableV4 ADD INDEX idx_stamp_file (stamp_hash, stamp_mimetype, stamp_url(100));
-- ALTER TABLE StampTableV4 ADD INDEX idx_cpid_ident (cpid, ident);
-- ALTER TABLE StampTableV4 ADD INDEX idx_stamp_count (is_btc_stamp, ident, creator);
-- ALTER TABLE StampTableV4 ADD INDEX idx_stamp_details (
--   stamp,
--   block_index,
--   cpid,
--   creator,
--   stamp_url,
--   stamp_mimetype,
--   block_time,
--   tx_hash,
--   ident
-- );

-- ALTER TABLE creator ADD INDEX idx_creator_name (creator(100));
-- ALTER TABLE creator ADD INDEX idx_address_creator (address, creator);

-- ALTER TABLE balances ADD INDEX idx_address_tick_amt_update (address, tick, amt, last_update);
-- ALTER TABLE balances ADD INDEX idx_balance_stats (tick, amt, address);

-- ALTER TABLE collection_stamps ADD INDEX idx_collection_stamp (collection_id, stamp);

-- ALTER TABLE collections ADD INDEX idx_collection_lookup (collection_id, collection_name, collection_onchain);

-- ALTER TABLE SRC20Valid ADD INDEX idx_tick_block_time (tick, block_time);
-- ALTER TABLE SRC20Valid ADD INDEX idx_tick_hash (tick_hash);
-- ALTER TABLE SRC20Valid ADD INDEX idx_tick_block_index (tick, block_index);
-- ALTER TABLE SRC20Valid ADD INDEX idx_tick_creator_time (tick, creator, block_time);
-- ALTER TABLE SRC20Valid ADD INDEX idx_creator_destination (creator, destination);
-- ALTER TABLE SRC20Valid ADD INDEX idx_src20_common_lookup (
--   block_index, 
--   tx_hash,
--   p,
--   op,
--   tick,
--   creator,
--   amt,
--   deci,
--   lim,
--   max,
--   destination,
--   block_time
-- );
-- ALTER TABLE SRC20Valid ADD INDEX idx_deploy_lookup (
--   op,
--   tick,
--   block_index,
--   tx_hash,
--   creator,
--   amt,
--   deci,
--   lim,
--   max,
--   block_time
-- );

-- ALTER TABLE SRC101 ADD INDEX idx_deploy_hash_tokenid (deploy_hash, tokenid);
-- ALTER TABLE SRC101 ADD INDEX idx_creator_tick (creator, tick);

-- ALTER TABLE SRC101Valid ADD INDEX idx_deploy_hash (deploy_hash);
-- ALTER TABLE SRC101Valid ADD INDEX idx_tokenid_utf8 (tokenid_utf8);
-- ALTER TABLE SRC101Valid ADD INDEX idx_creator (creator);
-- ALTER TABLE SRC101Valid ADD INDEX idx_deploy_hash_tokenid_time (deploy_hash, tokenid, block_time);

-- -- Remove redundant indexes that are covered by the new ones
-- ALTER TABLE SRC20Valid DROP INDEX creator;
-- ALTER TABLE SRC20Valid DROP INDEX block_index;