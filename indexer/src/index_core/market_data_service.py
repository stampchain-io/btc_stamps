"""
Market Data Service for Bitcoin Stamps Indexer

This module provides a centralized service for managing market data operations,
including data retrieval, caching, and updates for stamps, SRC-20 tokens, and collections.

The service is designed to eliminate external API calls and improve performance
from 10+ seconds to <2 seconds by implementing a comprehensive caching system.
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple, Union

import index_core.exceptions as exceptions
import index_core.log as log
from config import (
    COLLECTION_MARKET_DATA_TABLE,
    SRC20_MARKET_DATA_TABLE,
    STAMP_HOLDER_CACHE_TABLE,
    STAMP_MARKET_DATA_TABLE,
)
from index_core.caching import cache_manager
from index_core.database_manager import DatabaseManager

logger = logging.getLogger(__name__)
log.set_logger(logger)

D = Decimal

# Type definitions for market data structures
StampMarketData = Dict[str, Union[str, int, float, Decimal, datetime, None]]
SRC20MarketData = Dict[str, Union[str, int, float, Decimal, datetime, None]]
CollectionMarketData = Dict[str, Union[str, int, float, Decimal, datetime, None]]
HolderData = Dict[str, Union[str, int, float, Decimal, datetime, None]]
SourceData = Dict[str, Union[str, int, float, Decimal, datetime, None]]

# Cache keys for different data types
CACHE_KEY_STAMP_MARKET = "stamp_market"
CACHE_KEY_SRC20_MARKET = "src20_market"
CACHE_KEY_COLLECTION_MARKET = "collection_market"
CACHE_KEY_HOLDER_DATA = "holder_data"
CACHE_KEY_SOURCE_DATA = "source_data"

# Default cache expiration times (in seconds)
DEFAULT_CACHE_EXPIRY = 1800  # 30 minutes
HOLDER_CACHE_EXPIRY = 3600  # 1 hour
SOURCE_CACHE_EXPIRY = 300  # 5 minutes


class MarketDataService:
    """
    Central service for managing market data operations.

    This service provides methods for retrieving, updating, and caching market data
    for stamps, SRC-20 tokens, and collections. It follows the existing patterns
    in the indexer codebase for database operations and error handling.
    """

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        """Initialize the MarketDataService."""
        self.db_manager = db_manager or DatabaseManager()
        logger.info("MarketDataService initialized")

    def get_stamp_market_data(self, cpid: str, use_cache: bool = True, db=None) -> Optional[StampMarketData]:
        """
        Retrieve market data for a specific stamp.

        Args:
            cpid: Counterparty asset ID for the stamp
            use_cache: Whether to use cached data if available
            db: Optional database connection to reuse (if None, creates new connection)

        Returns:
            Dictionary containing stamp market data or None if not found

        Raises:
            DatabaseError: If database operation fails
        """
        try:
            # Check cache first if enabled
            if use_cache:
                cache_key = f"{CACHE_KEY_STAMP_MARKET}:{cpid}"
                cached_data = cache_manager.get_cache_value("market_data", cache_key)
                if cached_data is not None:
                    logger.debug(f"Cache hit for stamp market data: {cpid}")
                    return cached_data

            # Fetch from database
            own_connection = db is None
            if own_connection:
                db = self.db_manager.connect()
            try:
                with db.cursor() as cursor:
                    query = f"""
                        SELECT
                            cpid, floor_price_btc, recent_sale_price_btc,
                            open_dispensers_count, closed_dispensers_count, total_dispensers_count,
                            holder_count, unique_holder_count, top_holder_percentage, holder_distribution_score,
                            volume_24h_btc, volume_7d_btc, volume_30d_btc, total_volume_btc,
                            price_source, volume_sources, data_quality_score, confidence_level,
                            last_updated, last_dispenser_block, last_balance_block, last_price_update,
                            update_frequency_minutes, created_at
                        FROM {STAMP_MARKET_DATA_TABLE}
                        WHERE cpid = %s
                    """
                    cursor.execute(query, (cpid,))
                    result = cursor.fetchone()

                    if result is None:
                        logger.debug(f"No market data found for stamp: {cpid}")
                        return None

                    # Convert result to dictionary
                    market_data = self._row_to_stamp_market_data(result)

                    # Cache the result
                    if use_cache:
                        cache_key = f"{CACHE_KEY_STAMP_MARKET}:{cpid}"
                        cache_manager.set_cache_value("market_data", cache_key, market_data)

                    logger.debug(f"Retrieved stamp market data for: {cpid}")
                    return market_data

            finally:
                if own_connection:
                    db.close()

        except Exception as e:
            logger.error(f"Error retrieving stamp market data for {cpid}: {e}")
            raise exceptions.DatabaseError(f"Failed to retrieve stamp market data: {e}")

    def get_src20_market_data(self, tick: str, use_cache: bool = True, db=None) -> Optional[SRC20MarketData]:
        """
        Retrieve market data for a specific SRC-20 token.

        Args:
            tick: SRC-20 token ticker symbol
            use_cache: Whether to use cached data if available
            db: Optional database connection to reuse (if None, creates new connection)

        Returns:
            Dictionary containing SRC-20 market data or None if not found

        Raises:
            DatabaseError: If database operation fails
        """
        try:
            # Check cache first if enabled
            if use_cache:
                cache_key = f"{CACHE_KEY_SRC20_MARKET}:{tick}"
                cached_data = cache_manager.get_cache_value("market_data", cache_key)
                if cached_data is not None:
                    logger.debug(f"Cache hit for SRC-20 market data: {tick}")
                    return cached_data

            # Fetch from database
            own_connection = db is None
            if own_connection:
                db = self.db_manager.connect()
            try:
                with db.cursor() as cursor:
                    query = f"""
                        SELECT
                            tick, price_btc, price_usd, floor_price_btc, market_cap_btc, market_cap_usd,
                            volume_24h_btc, volume_7d_btc, volume_30d_btc, total_volume_btc,
                            price_change_24h_percent, price_change_7d_percent, price_change_30d_percent,
                            holder_count, circulating_supply, max_supply,
                            primary_exchange, exchange_sources, data_quality_score, confidence_level,
                            last_updated, last_price_update, update_frequency_minutes, created_at
                        FROM {SRC20_MARKET_DATA_TABLE}
                        WHERE tick = %s
                    """
                    cursor.execute(query, (tick,))
                    result = cursor.fetchone()

                    if result is None:
                        logger.debug(f"No market data found for SRC-20 token: {tick}")
                        return None

                    # Convert result to dictionary
                    market_data = self._row_to_src20_market_data(result)

                    # Cache the result
                    if use_cache:
                        cache_key = f"{CACHE_KEY_SRC20_MARKET}:{tick}"
                        cache_manager.set_cache_value("market_data", cache_key, market_data)

                    logger.debug(f"Retrieved SRC-20 market data for: {tick}")
                    return market_data

            finally:
                if own_connection:
                    db.close()

        except Exception as e:
            logger.error(f"Error retrieving SRC-20 market data for {tick}: {e}")
            raise exceptions.DatabaseError(f"Failed to retrieve SRC-20 market data: {e}")

    def get_collection_market_data(
        self, collection_id: str, use_cache: bool = True, db=None
    ) -> Optional[CollectionMarketData]:
        """
        Retrieve market data for a specific collection.

        Args:
            collection_id: Collection identifier (binary UUID as hex string)
            use_cache: Whether to use cached data if available
            db: Optional database connection to reuse (if None, creates new connection)

        Returns:
            Dictionary containing collection market data or None if not found

        Raises:
            DatabaseError: If database operation fails
        """
        try:
            # Check cache first if enabled
            if use_cache:
                cache_key = f"{CACHE_KEY_COLLECTION_MARKET}:{collection_id}"
                cached_data = cache_manager.get_cache_value("market_data", cache_key)
                if cached_data is not None:
                    logger.debug(f"Cache hit for collection market data: {collection_id}")
                    return cached_data

            # Fetch from database
            own_connection = db is None
            if own_connection:
                db = self.db_manager.connect()
            try:
                with db.cursor() as cursor:
                    query = f"""
                        SELECT
                            HEX(collection_id) as collection_id, floor_price_btc, avg_price_btc, total_value_btc,
                            volume_24h_btc, volume_7d_btc, volume_30d_btc, total_volume_btc,
                            total_stamps, unique_holders, listed_stamps, sold_stamps_24h,
                            last_updated, created_at
                        FROM {COLLECTION_MARKET_DATA_TABLE}
                        WHERE collection_id = UNHEX(%s)
                    """
                    cursor.execute(query, (collection_id,))
                    result = cursor.fetchone()

                    if result is None:
                        logger.debug(f"No market data found for collection: {collection_id}")
                        return None

                    # Convert result to dictionary
                    market_data = self._row_to_collection_market_data(result)

                    # Cache the result
                    if use_cache:
                        cache_key = f"{CACHE_KEY_COLLECTION_MARKET}:{collection_id}"
                        cache_manager.set_cache_value("market_data", cache_key, market_data)

                    logger.debug(f"Retrieved collection market data for: {collection_id}")
                    return market_data

            finally:
                if own_connection:
                    db.close()

        except Exception as e:
            logger.error(f"Error retrieving collection market data for {collection_id}: {e}")
            raise exceptions.DatabaseError(f"Failed to retrieve collection market data: {e}")

    def update_stamp_market_data(self, cpid: str, data: Dict[str, Any], db=None) -> None:
        """
        Update market data for a specific stamp.

        Args:
            cpid: Counterparty asset ID for the stamp
            data: Dictionary containing market data fields to update
            db: Optional database connection to reuse (if None, creates new connection)

        Raises:
            DatabaseError: If database operation fails
        """
        try:
            # Use provided connection or create a new one
            own_connection = db is None
            if own_connection:
                db = self.db_manager.connect()
            try:
                with db.cursor() as cursor:
                    # Map of allowed fields to database columns
                    field_mapping = {
                        "floor_price_btc": "floor_price_btc",
                        "recent_sale_price_btc": "recent_sale_price_btc",
                        "open_dispensers_count": "open_dispensers_count",
                        "closed_dispensers_count": "closed_dispensers_count",
                        "total_dispensers_count": "total_dispensers_count",
                        "holder_count": "holder_count",
                        "unique_holder_count": "unique_holder_count",
                        "top_holder_percentage": "top_holder_percentage",
                        "holder_distribution_score": "holder_distribution_score",
                        "volume_24h_btc": "volume_24h_btc",
                        "volume_7d_btc": "volume_7d_btc",
                        "volume_30d_btc": "volume_30d_btc",
                        "total_volume_btc": "total_volume_btc",
                        "price_source": "price_source",
                        "volume_sources": "volume_sources",
                        "data_quality_score": "data_quality_score",
                        "confidence_level": "confidence_level",
                        "last_dispenser_block": "last_dispenser_block",
                        "last_balance_block": "last_balance_block",
                        "last_price_update": "last_price_update",
                        "update_frequency_minutes": "update_frequency_minutes",
                    }

                    # Filter data to only include valid fields
                    valid_fields = {k: v for k, v in data.items() if k in field_mapping}

                    if not valid_fields:
                        logger.warning(f"No valid fields provided for stamp market data update: {cpid}")
                        return

                    # Build column names and update fields
                    columns = [field_mapping[f] for f in valid_fields.keys()]
                    update_fields = [f"{col} = VALUES({col})" for col in columns]

                    # Always update last_updated timestamp
                    update_fields.append("last_updated = NOW()")

                    query = f"""
                        INSERT INTO {STAMP_MARKET_DATA_TABLE} (cpid, {', '.join(columns)}, last_updated, created_at)
                        VALUES (%s, {', '.join(['%s'] * len(columns))}, NOW(), NOW())
                        ON DUPLICATE KEY UPDATE {', '.join(update_fields)}
                    """

                    # Prepare values for INSERT only
                    # Convert JSON fields to strings
                    import json

                    values = [cpid]
                    for field, value in valid_fields.items():
                        if field == "volume_sources" and isinstance(value, dict):
                            values.append(json.dumps(value))
                        else:
                            values.append(value)

                    cursor.execute(query, values)
                    db.commit()

                    # Invalidate cache
                    cache_key = f"{CACHE_KEY_STAMP_MARKET}:{cpid}"
                    cache_manager.invalidate_cache_entry("market_data", cache_key)

                    logger.debug(f"Updated stamp market data for: {cpid}")

            finally:
                # Only close if we created the connection
                if own_connection:
                    db.close()

        except Exception as e:
            logger.error(f"Error updating stamp market data for {cpid}: {e}")
            raise exceptions.DatabaseError(f"Failed to update stamp market data: {e}")

    def update_src20_market_data(self, tick: str, data: Dict[str, Any], db=None) -> None:
        """
        Update market data for a specific SRC-20 token.

        Args:
            tick: SRC-20 token ticker symbol
            data: Dictionary containing market data fields to update
            db: Optional database connection to reuse (if None, creates new connection)

        Raises:
            DatabaseError: If database operation fails
        """
        try:
            # Use provided connection or create a new one
            own_connection = db is None
            if own_connection:
                db = self.db_manager.connect()
            try:
                with db.cursor() as cursor:
                    # Map of allowed fields to database columns
                    field_mapping = {
                        "price_btc": "price_btc",
                        "price_usd": "price_usd",
                        "floor_price_btc": "floor_price_btc",
                        "market_cap_btc": "market_cap_btc",
                        "market_cap_usd": "market_cap_usd",
                        "volume_24h_btc": "volume_24h_btc",
                        "volume_7d_btc": "volume_7d_btc",
                        "volume_30d_btc": "volume_30d_btc",
                        "total_volume_btc": "total_volume_btc",
                        "price_change_24h_percent": "price_change_24h_percent",
                        "price_change_7d_percent": "price_change_7d_percent",
                        "price_change_30d_percent": "price_change_30d_percent",
                        "holder_count": "holder_count",
                        "circulating_supply": "circulating_supply",
                        "max_supply": "max_supply",
                        "primary_exchange": "primary_exchange",
                        "exchange_sources": "exchange_sources",
                        "data_quality_score": "data_quality_score",
                        "confidence_level": "confidence_level",
                        "last_price_update": "last_price_update",
                        "update_frequency_minutes": "update_frequency_minutes",
                    }

                    # Filter data to only include valid fields
                    valid_fields = {k: v for k, v in data.items() if k in field_mapping}

                    if not valid_fields:
                        logger.warning(f"No valid fields provided for SRC-20 market data update: {tick}")
                        return

                    # Build column names and update fields
                    columns = [field_mapping[f] for f in valid_fields.keys()]
                    update_fields = [f"{col} = VALUES({col})" for col in columns]

                    # Always update last_updated timestamp
                    update_fields.append("last_updated = NOW()")

                    query = f"""
                        INSERT INTO {SRC20_MARKET_DATA_TABLE} (tick, {', '.join(columns)}, last_updated, created_at)
                        VALUES (%s, {', '.join(['%s'] * len(columns))}, NOW(), NOW())
                        ON DUPLICATE KEY UPDATE {', '.join(update_fields)}
                    """

                    # Prepare values for INSERT only
                    values = [tick] + list(valid_fields.values())

                    cursor.execute(query, values)
                    db.commit()

                    # Invalidate cache
                    cache_key = f"{CACHE_KEY_SRC20_MARKET}:{tick}"
                    cache_manager.invalidate_cache_entry("market_data", cache_key)

                    logger.debug(f"Updated SRC-20 market data for: {tick}")

            finally:
                # Only close if we created the connection
                if own_connection:
                    db.close()

        except Exception as e:
            logger.error(f"Error updating SRC-20 market data for {tick}: {e}")
            raise exceptions.DatabaseError(f"Failed to update SRC-20 market data: {e}")

    def update_collection_market_data(self, collection_id: str, data: Dict[str, Any], db=None) -> None:
        """
        Update market data for a specific collection.

        Args:
            collection_id: Collection identifier (binary UUID as hex string)
            data: Dictionary containing market data fields to update
            db: Optional database connection to reuse (if None, creates new connection)

        Raises:
            DatabaseError: If database operation fails
        """
        try:
            # Use provided connection or create a new one
            own_connection = db is None
            if own_connection:
                db = self.db_manager.connect()
            try:
                with db.cursor() as cursor:
                    # Map of allowed fields to database columns
                    field_mapping = {
                        "floor_price_btc": "floor_price_btc",
                        "avg_price_btc": "avg_price_btc",
                        "total_value_btc": "total_value_btc",
                        "volume_24h_btc": "volume_24h_btc",
                        "volume_7d_btc": "volume_7d_btc",
                        "volume_30d_btc": "volume_30d_btc",
                        "total_volume_btc": "total_volume_btc",
                        "total_stamps": "total_stamps",
                        "unique_holders": "unique_holders",
                        "listed_stamps": "listed_stamps",
                        "sold_stamps_24h": "sold_stamps_24h",
                    }

                    # Filter data to only include valid fields
                    valid_fields = {k: v for k, v in data.items() if k in field_mapping}

                    if not valid_fields:
                        logger.warning(f"No valid fields provided for collection market data update: {collection_id}")
                        return

                    # Build column names and update fields
                    columns = [field_mapping[f] for f in valid_fields.keys()]
                    update_fields = [f"{col} = VALUES({col})" for col in columns]

                    # Always update last_updated timestamp
                    update_fields.append("last_updated = NOW()")

                    query = f"""
                        INSERT INTO {COLLECTION_MARKET_DATA_TABLE} (collection_id, {', '.join(columns)}, last_updated, created_at)
                        VALUES (UNHEX(%s), {', '.join(['%s'] * len(columns))}, NOW(), NOW())
                        ON DUPLICATE KEY UPDATE {', '.join(update_fields)}
                    """

                    # Prepare values for INSERT only
                    values = [collection_id] + list(valid_fields.values())

                    cursor.execute(query, values)
                    db.commit()

                    # Invalidate cache
                    cache_key = f"{CACHE_KEY_COLLECTION_MARKET}:{collection_id}"
                    cache_manager.invalidate_cache_entry("market_data", cache_key)

                    logger.debug(f"Updated collection market data for: {collection_id}")

            finally:
                # Only close if we created the connection
                if own_connection:
                    db.close()

        except Exception as e:
            logger.error(f"Error updating collection market data for {collection_id}: {e}")
            raise exceptions.DatabaseError(f"Failed to update collection market data: {e}")

    def get_stamp_holders(self, cpid: str, limit: int = 100, use_cache: bool = True, db=None) -> List[HolderData]:
        """
        Retrieve holder information for a specific stamp.

        Args:
            cpid: Counterparty asset ID for the stamp
            limit: Maximum number of holders to return
            use_cache: Whether to use cached data if available
            db: Optional database connection to reuse (if None, creates new connection)

        Returns:
            List of dictionaries containing holder information

        Raises:
            DatabaseError: If database operation fails
        """
        try:
            # Check cache first if enabled
            if use_cache:
                cache_key = f"{CACHE_KEY_HOLDER_DATA}:{cpid}:{limit}"
                cached_data = cache_manager.get_cache_value("market_data", cache_key)
                if cached_data is not None:
                    logger.debug(f"Cache hit for stamp holder data: {cpid}")
                    return cached_data

            # Fetch from database
            own_connection = db is None
            if own_connection:
                db = self.db_manager.connect()
            try:
                with db.cursor() as cursor:
                    query = f"""
                        SELECT
                            cpid, address, quantity, percentage, rank_position,
                            balance_source, last_updated, last_tx_block
                        FROM {STAMP_HOLDER_CACHE_TABLE}
                        WHERE cpid = %s
                        ORDER BY rank_position ASC
                        LIMIT %s
                    """
                    cursor.execute(query, (cpid, limit))
                    results = cursor.fetchall()

                    # Convert results to list of dictionaries
                    holders = []
                    for result in results:
                        holder_data = self._row_to_holder_data(result)
                        holders.append(holder_data)

                    # Cache the result
                    if use_cache:
                        cache_key = f"{CACHE_KEY_HOLDER_DATA}:{cpid}:{limit}"
                        cache_manager.set_cache_value("market_data", cache_key, holders)

                    logger.debug(f"Retrieved {len(holders)} holders for stamp: {cpid}")
                    return holders

            finally:
                if own_connection:
                    db.close()

        except Exception as e:
            logger.error(f"Error retrieving stamp holders for {cpid}: {e}")
            raise exceptions.DatabaseError(f"Failed to retrieve stamp holders: {e}")

    def _row_to_stamp_market_data(self, row: Tuple) -> StampMarketData:
        """Convert database row to stamp market data dictionary."""
        return {
            "cpid": row[0],
            "floor_price_btc": row[1],
            "recent_sale_price_btc": row[2],
            "open_dispensers_count": row[3],
            "closed_dispensers_count": row[4],
            "total_dispensers_count": row[5],
            "holder_count": row[6],
            "unique_holder_count": row[7],
            "top_holder_percentage": row[8],
            "holder_distribution_score": row[9],
            "volume_24h_btc": row[10],
            "volume_7d_btc": row[11],
            "volume_30d_btc": row[12],
            "total_volume_btc": row[13],
            "price_source": row[14],
            "volume_sources": row[15],
            "data_quality_score": row[16],
            "confidence_level": row[17],
            "last_updated": row[18],
            "last_dispenser_block": row[19],
            "last_balance_block": row[20],
            "last_price_update": row[21],
            "update_frequency_minutes": row[22],
            "created_at": row[23],
        }

    def _row_to_src20_market_data(self, row: Tuple) -> SRC20MarketData:
        """Convert database row to SRC-20 market data dictionary."""
        return {
            "tick": row[0],
            "price_btc": row[1],
            "price_usd": row[2],
            "floor_price_btc": row[3],
            "market_cap_btc": row[4],
            "market_cap_usd": row[5],
            "volume_24h_btc": row[6],
            "volume_7d_btc": row[7],
            "volume_30d_btc": row[8],
            "total_volume_btc": row[9],
            "price_change_24h_percent": row[10],
            "price_change_7d_percent": row[11],
            "price_change_30d_percent": row[12],
            "holder_count": row[13],
            "circulating_supply": row[14],
            "max_supply": row[15],
            "primary_exchange": row[16],
            "exchange_sources": row[17],
            "data_quality_score": row[18],
            "confidence_level": row[19],
            "last_updated": row[20],
            "last_price_update": row[21],
            "update_frequency_minutes": row[22],
            "created_at": row[23],
        }

    def _row_to_collection_market_data(self, row: Tuple) -> CollectionMarketData:
        """Convert database row to collection market data dictionary."""
        return {
            "collection_id": row[0],
            "floor_price_btc": row[1],
            "avg_price_btc": row[2],
            "total_value_btc": row[3],
            "volume_24h_btc": row[4],
            "volume_7d_btc": row[5],
            "volume_30d_btc": row[6],
            "total_volume_btc": row[7],
            "total_stamps": row[8],
            "unique_holders": row[9],
            "listed_stamps": row[10],
            "sold_stamps_24h": row[11],
            "last_updated": row[12],
            "created_at": row[13],
        }

    def _row_to_holder_data(self, row: Tuple) -> HolderData:
        """Convert database row to holder data dictionary."""
        return {
            "cpid": row[0],
            "address": row[1],
            "quantity": row[2],
            "percentage": row[3],
            "rank_position": row[4],
            "balance_source": row[5],
            "last_updated": row[6],
            "last_tx_block": row[7],
        }


# Global instance for easy access
market_data_service = MarketDataService()


def get_stamp_market_data(cpid: str, use_cache: bool = True) -> Optional[StampMarketData]:
    """
    Convenience function to get stamp market data.

    Args:
        cpid: Counterparty asset ID for the stamp
        use_cache: Whether to use cached data if available

    Returns:
        Dictionary containing stamp market data or None if not found
    """
    return market_data_service.get_stamp_market_data(cpid, use_cache)


def get_src20_market_data(tick: str, use_cache: bool = True) -> Optional[SRC20MarketData]:
    """
    Convenience function to get SRC-20 market data.

    Args:
        tick: SRC-20 token ticker symbol
        use_cache: Whether to use cached data if available

    Returns:
        Dictionary containing SRC-20 market data or None if not found
    """
    return market_data_service.get_src20_market_data(tick, use_cache)


def get_collection_market_data(collection_id: str, use_cache: bool = True) -> Optional[CollectionMarketData]:
    """
    Convenience function to get collection market data.

    Args:
        collection_id: Collection identifier
        use_cache: Whether to use cached data if available

    Returns:
        Dictionary containing collection market data or None if not found
    """
    return market_data_service.get_collection_market_data(collection_id, use_cache)


def update_stamp_market_data(cpid: str, data: Dict[str, Any]) -> None:
    """
    Convenience function to update stamp market data.

    Args:
        cpid: Counterparty asset ID for the stamp
        data: Dictionary containing market data fields to update
    """
    return market_data_service.update_stamp_market_data(cpid, data)


def update_src20_market_data(tick: str, data: Dict[str, Any]) -> None:
    """
    Convenience function to update SRC-20 market data.

    Args:
        tick: SRC-20 token ticker symbol
        data: Dictionary containing market data fields to update
    """
    return market_data_service.update_src20_market_data(tick, data)


def update_collection_market_data(collection_id: str, data: Dict[str, Any]) -> None:
    """
    Convenience function to update collection market data.

    Args:
        collection_id: Collection identifier (binary UUID as hex string)
        data: Dictionary containing market data fields to update
    """
    return market_data_service.update_collection_market_data(collection_id, data)


def get_stamp_holders(cpid: str, limit: int = 100, use_cache: bool = True) -> List[HolderData]:
    """
    Convenience function to get stamp holder information.

    Args:
        cpid: Counterparty asset ID for the stamp
        limit: Maximum number of holders to return
        use_cache: Whether to use cached data if available

    Returns:
        List of dictionaries containing holder information
    """
    return market_data_service.get_stamp_holders(cpid, limit, use_cache)
