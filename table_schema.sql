Table	Create Table
StampTableV4	CREATE TABLE `StampTableV4` (
  `stamp` int DEFAULT NULL,
  `block_index` int DEFAULT NULL,
  `cpid` varchar(255) DEFAULT NULL,
  `creator` varchar(255) DEFAULT NULL,
  `divisible` tinyint(1) DEFAULT NULL,
  `keyburn` tinyint(1) DEFAULT NULL,
  `locked` tinyint(1) DEFAULT NULL,
  `message_index` int DEFAULT NULL,
  `stamp_base64` mediumtext,
  `stamp_mimetype` varchar(255) DEFAULT NULL,
  `stamp_url` varchar(255) DEFAULT NULL,
  `supply` int DEFAULT NULL,
  `timestamp` timestamp NULL DEFAULT NULL,
  `tx_hash` varchar(255) NOT NULL,
  `tx_index` int DEFAULT NULL,
  `src_data` json DEFAULT NULL,
  `ident` varchar(16) DEFAULT NULL,
  `creator_name` varchar(255) DEFAULT NULL,
  `stamp_gen` int DEFAULT NULL,
  PRIMARY KEY (`tx_hash`),
  KEY `cpid_index` (`cpid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
Table	Create Table
blocks	CREATE TABLE `blocks` (
  `block_index` int NOT NULL,
  `block_hash` varchar(64) CHARACTER SET utf8 COLLATE utf8_general_ci NOT NULL,
  `block_time` int DEFAULT NULL,
  `previous_block_hash` varchar(64) DEFAULT NULL,
  `difficulty` float DEFAULT NULL,
  `ledger_hash` text,
  `txlist_hash` text,
  `messages_hash` text,
  PRIMARY KEY (`block_index`,`block_hash`),
  UNIQUE KEY `block_hash` (`block_hash`),
  UNIQUE KEY `previous_block_hash` (`previous_block_hash`),
  UNIQUE KEY `previous_block_hash_2` (`previous_block_hash`),
  UNIQUE KEY `unique_previous_block_hash` (`previous_block_hash`),
  KEY `block_index_idx` (`block_index`),
  KEY `index_hash_idx` (`block_index`,`block_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
Table	Create Table
dispensers	CREATE TABLE `dispensers` (
  `tx_index` int DEFAULT NULL,
  `tx_hash` varchar(255) NOT NULL,
  `block_index` int DEFAULT NULL,
  `source` varchar(255) DEFAULT NULL,
  `asset` varchar(255) DEFAULT NULL,
  `give_quantity` bigint DEFAULT NULL,
  `escrow_quantity` bigint DEFAULT NULL,
  `satoshirate` bigint DEFAULT NULL,
  `status` int DEFAULT NULL,
  `give_remaining` bigint DEFAULT NULL,
  `oracle_address` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`tx_hash`),
  UNIQUE KEY `tx_hash` (`tx_hash`),
  KEY `asset` (`asset`),
  CONSTRAINT `dispensers_ibfk_1` FOREIGN KEY (`asset`) REFERENCES `StampTableV4` (`cpid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
Table	Create Table
srcx	CREATE TABLE `srcx` (
  `tx_hash` varchar(255) NOT NULL,
  `tx_index` int DEFAULT NULL,
  `amt` decimal(37,18) DEFAULT NULL,
  `block_index` int DEFAULT NULL,
  `c` varchar(255) DEFAULT NULL,
  `creator` varchar(255) DEFAULT NULL,
  `deci` int DEFAULT '18',
  `lim` int DEFAULT NULL,
  `max` int DEFAULT NULL,
  `op` varchar(255) DEFAULT NULL,
  `p` varchar(255) DEFAULT NULL,
  `stamp` int DEFAULT NULL,
  `stamp_url` text,
  `tick` varchar(255) DEFAULT NULL,
  `ts` json DEFAULT NULL,
  `stamp_gen` int DEFAULT NULL,
  `destination` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`tx_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
Table	Create Table
transactions	CREATE TABLE `transactions` (
  `tx_index` int NOT NULL,
  `tx_hash` varchar(64) CHARACTER SET utf8 COLLATE utf8_general_ci DEFAULT NULL,
  `block_index` int DEFAULT NULL,
  `block_hash` varchar(64) CHARACTER SET utf8 COLLATE utf8_general_ci DEFAULT NULL,
  `block_time` int DEFAULT NULL,
  `source` varchar(64) CHARACTER SET utf8 COLLATE utf8_general_ci DEFAULT NULL,
  `destination` varchar(64) CHARACTER SET utf8 COLLATE utf8_general_ci DEFAULT NULL,
  `btc_amount` bigint DEFAULT NULL,
  `fee` bigint DEFAULT NULL,
  `data` longtext,
  `supported` bit(1) DEFAULT b'1',
  PRIMARY KEY (`tx_index`),
  UNIQUE KEY `tx_hash` (`tx_hash`),
  KEY `block_index` (`block_index`,`block_hash`),
  KEY `transactions_ibfk_1` (`block_hash`,`block_index`),
  KEY `block_index_idx` (`block_index`),
  KEY `tx_index_idx` (`tx_index`),
  KEY `tx_hash_idx` (`tx_hash`),
  KEY `index_index_idx` (`block_index`,`tx_index`),
  KEY `index_hash_index_idx` (`tx_index`,`tx_hash`,`block_index`),
  CONSTRAINT `transactions_ibfk_1` FOREIGN KEY (`block_hash`, `block_index`) REFERENCES `blocks` (`block_hash`, `block_index`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
Table	Create Table
srcbackground	CREATE TABLE `srcbackground` (
  `tick` varchar(16) NOT NULL,
  `base64` mediumtext,
  `font_size` varchar(8) DEFAULT NULL,
  `text_color` varchar(16) DEFAULT NULL,
  `unicode` varchar(16) DEFAULT NULL,
  `p` varchar(16) NOT NULL,
  PRIMARY KEY (`tick`,`p`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
Table	Create Table
cp_wallet	CREATE TABLE `cp_wallet` (
  `address` varchar(255) DEFAULT NULL,
  `cpid` varchar(255) DEFAULT NULL,
  `quantity` bigint DEFAULT NULL,
  KEY `index_name` (`address`,`cpid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
Table	Create Table
creator	CREATE TABLE `creator` (
  `address` varchar(255) NOT NULL,
  `creator` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`address`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
