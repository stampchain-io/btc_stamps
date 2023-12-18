USE `btc_stamps`;
CREATE TABLE IF NOT EXISTS blocks (
  `block_index` INT,
  `block_hash` VARCHAR(64),
  `block_time` datetime,
  `previous_block_hash` VARCHAR(64) UNIQUE,
  `difficulty` FLOAT,
  `ledger_hash` TEXT,
  `txlist_hash` TEXT,
  `messages_hash` TEXT,
  `indexed` tinyint(1) DEFAULT NULL,
  PRIMARY KEY (`block_index`, `block_hash`),
  UNIQUE (`block_hash`),
  UNIQUE (`previous_block_hash`),
  INDEX `block_index_idx` (`block_index`),
  INDEX `index_hash_idx` (`block_index`, `block_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS transactions (
  `tx_index` INT,
  `tx_hash` VARCHAR(64),
  `block_index` INT,
  `block_hash` VARCHAR(64),
  `block_time` datetime,
  `source` VARCHAR(64),
  `destination` TEXT,
  `btc_amount` BIGINT,
  `fee` BIGINT,
  `data` MEDIUMTEXT,
  `supported` BIT DEFAULT 1,
  `keyburn` tinyint(1) DEFAULT NULL,
  PRIMARY KEY (`tx_index`, `tx_hash`),
  UNIQUE (`tx_hash`),
  INDEX `block_hash_index` (`block_index`, `block_hash`),
  CONSTRAINT transactions_blocks_fk FOREIGN KEY (`block_index`, `block_hash`) REFERENCES blocks(`block_index`, `block_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `StampTableV4` (
  `stamp` int DEFAULT NULL,
  `block_index` int DEFAULT NULL,
  `cpid` varchar(255) DEFAULT NULL,
  `asset_longname` varchar(255) DEFAULT NULL,
  `creator` varchar(64) DEFAULT NULL,
  `divisible` tinyint(1) DEFAULT NULL,
  `keyburn` tinyint(1) DEFAULT NULL,
  `locked` tinyint(1) DEFAULT NULL,
  `message_index` int DEFAULT NULL,
  `stamp_base64` mediumtext,
  `stamp_mimetype` varchar(255) DEFAULT NULL,
  `stamp_url` varchar(255) DEFAULT NULL,
  `supply` bigint DEFAULT NULL,
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
  INDEX `creator_index` (`creator`),
  INDEX `block_index` (`block_index`),
  INDEX `is_btc_stamp_index` (`is_btc_stamp`),
  FOREIGN KEY (`tx_hash`) REFERENCES transactions(`tx_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `srcbackground` (
  `tick` varchar(16) NOT NULL,
  `base64` mediumtext,
  `font_size` varchar(8) DEFAULT NULL,
  `text_color` varchar(16) DEFAULT NULL,
  `unicode` varchar(16) DEFAULT NULL,
  `p` varchar(16) NOT NULL,
  PRIMARY KEY (`tick`,`p`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `dispensers` (
  `tx_index` int,
  `tx_hash` varchar(64) NOT NULL,
  `block_index` int DEFAULT NULL,
  `source` varchar(255) DEFAULT NULL,
  `origin` varchar(255) DEFAULT NULL,
  `cpid` varchar(255) DEFAULT NULL,
  `give_quantity` bigint DEFAULT NULL,
  `escrow_quantity` bigint DEFAULT NULL,
  `satoshirate` bigint DEFAULT NULL,
  `status` int DEFAULT NULL,
  `give_remaining` bigint DEFAULT NULL,
  `oracle_address` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`tx_index`),
  INDEX `block_index` (`block_index`), 
  INDEX `cpid_index` (`cpid`),
  FOREIGN KEY (`cpid`) REFERENCES `StampTableV4` (`cpid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `sends` (
  `from` varchar(255) DEFAULT NULL,
  `to` varchar(255) DEFAULT NULL,
  `cpid` varchar(255) DEFAULT NULL,
  `tick` varchar(255) DEFAULT NULL,
  `memo` varchar(255) DEFAULT NULL,
  `satoshirate` bigint DEFAULT NULL,
  `quantity` bigint DEFAULT NULL,
  `tx_hash` VARCHAR(64),
  `tx_index` int,
  `block_index` int,
  INDEX `block_index` (`block_index`), 
  KEY `index_name` (`cpid`,`tick`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `cp_wallet` (
  `address` varchar(255) DEFAULT NULL,
  `cpid` varchar(255) DEFAULT NULL,
  `quantity` bigint DEFAULT NULL,
  KEY `index_name` (`address`,`cpid`),
  INDEX `cpid_index` (`cpid`),
  INDEX `address_index` (`address`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `creator` (
  `address` varchar(64) NOT NULL,
  `creator` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`address`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `SRC20` (
  `tx_hash` VARCHAR(64) NOT NULL,
  `tx_index` int NOT NULL,
  `block_index` int DEFAULT NULL,
  `p` varchar(32) DEFAULT NULL,
  `op` varchar(32) DEFAULT NULL,
  `tick` varchar(32) DEFAULT NULL,
  `creator` varchar(64) DEFAULT NULL,
  `amt` decimal(38,18) DEFAULT NULL,
  `deci` int DEFAULT '18',
  `lim` BIGINT UNSIGNED DEFAULT NULL,
  `max` BIGINT UNSIGNED DEFAULT NULL,
  `destination` varchar(255) DEFAULT NULL,
  `block_time` datetime DEFAULT NULL,
  PRIMARY KEY (`tx_index`, `tx_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `SRC20Valid` (
  `tx_hash` VARCHAR(64) NOT NULL,
  `tx_index` int NOT NULL,
  `block_index` int DEFAULT NULL,
  `p` varchar(32) DEFAULT NULL,
  `op` varchar(32) DEFAULT NULL,
  `tick` varchar(32) DEFAULT NULL,
  `creator` varchar(64) DEFAULT NULL,
  `amt` decimal(38,18) DEFAULT NULL,
  `deci` int DEFAULT '18',
  `lim` BIGINT UNSIGNED DEFAULT NULL,
  `max` BIGINT UNSIGNED DEFAULT NULL,
  `destination` varchar(255) DEFAULT NULL,
  `block_time` datetime DEFAULT NULL,
  `status` varchar(64) DEFAULT NULL,
  PRIMARY KEY (`tx_index`, `tx_hash`),
  INDEX `tick` (`tick`), 
  INDEX `creator` (`creator`), 
  INDEX `block_index` (`block_index`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


CREATE TABLE IF NOT EXISTS `balances` (
  `id` VARCHAR(255) NOT NULL,
  `address` varchar(64) NOT NULL,
  `cpid` varchar(255) DEFAULT NULL,
  `p` varchar(32) DEFAULT NULL,
  `tick` varchar(32) DEFAULT NULL,
  `amt` decimal(38,18),
  `block_time` datetime,
  `last_update` int,
  PRIMARY KEY (`id`),
  UNIQUE KEY `address_p_tick_unique` (`address`, `p`, `tick`),
  UNIQUE KEY `address_cpid_unique` (`address`, `cpid`),
  INDEX `cpid` (`cpid`),
  INDEX `address` (`address`),
  INDEX `tick` (`tick`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;