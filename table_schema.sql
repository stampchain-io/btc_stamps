USE `stamps`;
CREATE TABLE IF NOT EXISTS `StampTableV4` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `dispensers` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `srcx` (
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

CREATE TABLE IF NOT EXISTS `cp_wallet` (
  `address` varchar(255) DEFAULT NULL,
  `cpid` varchar(255) DEFAULT NULL,
  `quantity` bigint DEFAULT NULL,
  KEY `index_name` (`address`,`cpid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `creator` (
  `address` varchar(255) NOT NULL,
  `creator` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`address`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
