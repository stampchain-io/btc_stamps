USE `btc_stamps`;
CREATE TABLE IF NOT EXISTS blocks (
  `block_index` INT,
  `block_hash` NVARCHAR(64),
  `block_time` INT,
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

USE `btc_stamps`;
CREATE TABLE IF NOT EXISTS transactions (
  `tx_index` INT PRIMARY KEY,
  `tx_hash` NVARCHAR(64) UNIQUE,
  `block_index` INT,
  `block_hash` NVARCHAR(64),
  `block_time` INT,
  `source` NVARCHAR(64),
  `destination` LONGTEXT,
  `btc_amount` BIGINT,
  `fee` BIGINT,
  `data` LONGTEXT,
  `supported` BIT DEFAULT 1,
  `keyburn` tinyint(1) DEFAULT NULL,
  FOREIGN KEY (`block_index`, `block_hash`) REFERENCES blocks(`block_index`, `block_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

USE `btc_stamps`;
CREATE TABLE IF NOT EXISTS `StampTableV4` (
  `stamp` int DEFAULT NULL,
  `block_index` int DEFAULT NULL,
  `cpid` varchar(255) DEFAULT NULL,
  `asset_longname` varchar(255) DEFAULT NULL,
  `creator` varchar(255) DEFAULT NULL,
  `divisible` tinyint(1) DEFAULT NULL,
  `keyburn` tinyint(1) DEFAULT NULL,
  `locked` tinyint(1) DEFAULT NULL,
  `message_index` int DEFAULT NULL,
  `stamp_base64` mediumtext,
  `stamp_mimetype` varchar(255) DEFAULT NULL,
  `stamp_url` varchar(255) DEFAULT NULL,
  `supply` bigint DEFAULT NULL,
  `timestamp` timestamp NULL DEFAULT NULL,
  `tx_hash` varchar(255) NOT NULL,
  `tx_index` bigint DEFAULT NULL,
  `src_data` json DEFAULT NULL,
  `ident` varchar(16) DEFAULT NULL,
  `creator_name` varchar(255) DEFAULT NULL,
  `stamp_hash` varchar(255) DEFAULT NULL,
  `is_btc_stamp` tinyint(1) DEFAULT NULL,
  `is_reissue` tinyint(1) DEFAULT NULL,
  `file_hash` varchar(255) DEFAULT NULL,
  `is_valid_base64` tinyint(1) DEFAULT NULL,
  PRIMARY KEY (`tx_hash`),
  KEY `cpid_index` (`cpid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

USE `btc_stamps`;
CREATE TABLE IF NOT EXISTS `srcbackground` (
  `tick` varchar(16) NOT NULL,
  `base64` mediumtext,
  `font_size` varchar(8) DEFAULT NULL,
  `text_color` varchar(16) DEFAULT NULL,
  `unicode` varchar(16) DEFAULT NULL,
  `p` varchar(16) NOT NULL,
  PRIMARY KEY (`tick`,`p`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

USE `btc_stamps`;
CREATE TABLE IF NOT EXISTS `dispensers` (
  `tx_index` int DEFAULT NULL,
  `tx_hash` varchar(255) NOT NULL,
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
  PRIMARY KEY (`tx_hash`),
  UNIQUE KEY `tx_hash` (`tx_hash`),
  KEY `cpid` (`cpid`),
  CONSTRAINT `dispensers_ibfk_1` FOREIGN KEY (`cpid`) REFERENCES `StampTableV4` (`cpid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

USE `btc_stamps`;
CREATE TABLE IF NOT EXISTS `sends` (
  `from` varchar(255) DEFAULT NULL,
  `to` varchar(255) DEFAULT NULL,
  `cpid` varchar(255) DEFAULT NULL,
  `tick` varchar(255) DEFAULT NULL,
  `memo` varchar(255) DEFAULT NULL,
  `satoshirate` bigint DEFAULT NULL,
  `quantity` bigint DEFAULT NULL,
  `tx_hash` NVARCHAR(64),
  `tx_index` int DEFAULT NULL,
  `block_index` int DEFAULT NULL,
  KEY `index_name` (`cpid`,`tick`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

USE `btc_stamps`;
CREATE TABLE IF NOT EXISTS `balances` (
  `address` varchar(255) DEFAULT NULL,
  `cpid` varchar(255) DEFAULT NULL,
  `tick` varchar(255) DEFAULT NULL,
  `quantity` bigint DEFAULT NULL,
  `last_update` int DEFAULT NULL,
  `prev_quantity` bigint DEFAULT NULL,
  `prev_last_update` int DEFAULT NULL,
  KEY `index_name` (`cpid`,`tick`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

USE `btc_stamps`;
CREATE TABLE IF NOT EXISTS `creator` (
  `address` varchar(255) NOT NULL,
  `creator` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`address`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
