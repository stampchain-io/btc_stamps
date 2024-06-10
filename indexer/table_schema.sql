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
  INDEX `block_index_idx` (`block_index`),
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
  INDEX `block_hash_index` (`block_index`, `block_hash`),
  CONSTRAINT transactions_blocks_fk FOREIGN KEY (`block_index`, `block_hash`) REFERENCES blocks(`block_index`, `block_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_ci;

CREATE TABLE IF NOT EXISTS `StampTableV4` (
  `stamp` int DEFAULT NULL,
  `block_index` int,
  `cpid` varchar(255) DEFAULT NULL,
  `asset_longname` varchar(255) DEFAULT NULL,
  `creator` varchar(64) COLLATE utf8mb4_bin,
  `divisible` tinyint(1) DEFAULT NULL,
  `keyburn` tinyint(1) DEFAULT NULL,
  `locked` tinyint(1) DEFAULT NULL,
  `message_index` int DEFAULT NULL,
  `stamp_base64` mediumtext,
  `stamp_mimetype` varchar(255) DEFAULT NULL,
  `stamp_url` varchar(255) DEFAULT NULL,
  `supply` bigint unsigned DEFAULT NULL,
  `block_time` datetime NULL DEFAULT NULL,
  `tx_hash` varchar(64) NOT NULL,
  `tx_index` int NOT NULL,
  `src_data` json DEFAULT NULL,
  `ident` varchar(16) DEFAULT NULL,
  `stamp_hash` varchar(255) DEFAULT NULL,
  `is_btc_stamp` tinyint(1) DEFAULT NULL,
  `is_reissue` tinyint(1) DEFAULT NULL,
  `file_hash` varchar(255) DEFAULT NULL,
  `is_valid_base64` tinyint(1) DEFAULT NULL,
  PRIMARY KEY (`tx_index`, `tx_hash`),
  UNIQUE `tx_hash` (`tx_hash`),
  UNIQUE `stamp_hash` (`stamp_hash`),
  INDEX `cpid_index` (`cpid`),
  INDEX `ident_index` (`ident`),
  INDEX `creator_index` (`creator`),
  INDEX `block_index` (`block_index`),
  INDEX `is_btc_stamp_index` (`is_btc_stamp`),
  INDEX `stamp_index` (`stamp`),
  INDEX `idx_stamp` (`is_btc_stamp`, `ident`, `stamp` DESC, `tx_index` DESC),
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
  PRIMARY KEY (`address`)
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
  INDEX `creator` (`creator`), 
  INDEX `block_index` (`block_index`)
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
  INDEX `address` (`address`),
  INDEX `tick` (`tick`),
  INDEX `tick_tick_hash` (`tick`, `tick_hash`)
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
  `creator_address` VARCHAR(64) COLLATE utf8mb4_bin,
  FOREIGN KEY (creator_address) REFERENCES creator(address),
  INDEX (collection_name),
  INDEX (creator_address)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_ci;

CREATE TABLE IF NOT EXISTS collection_stamps (
  `collection_id` BINARY(16),
  `stamp_id` INT,
  FOREIGN KEY (collection_id) REFERENCES collections(collection_id),
  FOREIGN KEY (stamp_id) REFERENCES StampTableV4(stamp),
  PRIMARY KEY (collection_id, stamp_id),
  INDEX (stamp_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_ci;

-- example for insert into collections
-- START TRANSACTION;

-- -- Insert into collections table
-- INSERT INTO collections (collection_id, collection_name, creator_address)
-- VALUES (UNHEX(MD5(CONCAT('My Collection', 'creator_address_value'))), 'My Collection', 'creator_address_value');

-- -- Insert into collection_stamps table
-- INSERT INTO collection_stamps (collection_id, stamp_id)
-- VALUES
--   (UNHEX(MD5(CONCAT('My Collection', 'creator_address_value'))), 1),
--   (UNHEX(MD5(CONCAT('My Collection', 'creator_address_value'))), 2);

-- COMMIT;

-- Find collection by stamp
-- SELECT c.collection_name
-- FROM collections c
-- JOIN collection_stamps cs ON c.collection_id = cs.collection_id
-- WHERE cs.stamp_id = ?;

-- find all stamps in a collection
-- SELECT s.stamp, s.stamp_base64, s.stamp_mimetype, s.stamp_url
-- FROM StampTableV4 s
-- JOIN collection_stamps cs ON s.stamp = cs.stamp_id
-- WHERE cs.collection_id = ?;