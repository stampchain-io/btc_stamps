"""
SRC20 Market Data Processor for Bitcoin Stamps Indexer

This module provides specialized processing logic for SRC20 token market data operations,
including validation, transformation, and business logic specific to SRC20 tokens.

The processor follows the existing patterns in the indexer codebase for error handling,
logging, and database operations.
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional

import index_core.exceptions as exceptions
import index_core.log as log
from index_core.database import insert_src20_market_data
from index_core.database_manager import DatabaseManager

logger = logging.getLogger(__name__)
log.set_logger(logger)

D = Decimal

# Validation constants for SRC20 market data
MIN_PRICE = D("0.00000001")  # 1 satoshi in BTC
MAX_PRICE = D("21000000")    # Max possible BTC
MIN_MARKET_CAP = D("0")
MAX_MARKET_CAP = D("21000000000")  # 21M BTC * 1000 for max supply
MIN_VOLUME = D("0")
MAX_VOLUME = D("21000000")
MIN_SUPPLY = D("0")
MAX_SUPPLY = D("21000000000000000000")  # 21 quintillion (max SRC20 supply)
MIN_HOLDER_COUNT = 0
MAX_HOLDER_COUNT = 1000000
MIN_PRICE_CHANGE = D("-100.0")  # -100% (total loss)
MAX_PRICE_CHANGE = D("10000.0")  # 10,000% gain
MIN_QUALITY_SCORE = D("0.0")
MAX_QUALITY_SCORE = D("10.0")
MIN_CONFIDENCE_LEVEL = D("0.0")
MAX_CONFIDENCE_LEVEL = D("10.0")

# Default values for missing data
DEFAULT_QUALITY_SCORE = D("6.0")  # Slightly lower than stamps due to exchange volatility
DEFAULT_CONFIDENCE_LEVEL = D("7.0")
DEFAULT_UPDATE_FREQUENCY = 10  # minutes (more frequent than stamps)


class SRC20MarketDataProcessor:
    """
    Processor for SRC20-specific market data operations.
    
    This class handles validation, transformation, and business logic
    specific to SRC20 token market data processing.
    """

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        """Initialize the SRC20MarketDataProcessor."""
        self.db_manager = db_manager or DatabaseManager()
        logger.info("SRC20MarketDataProcessor initialized")

    def validate_src20_market_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate and sanitize SRC20 market data.

        Args:
            data: Raw market data dictionary

        Returns:
            Validated and sanitized market data dictionary

        Raises:
            InvalidInputDataError: If validation fails
        """
        try:
            validated_data = {}

            # Validate tick (required field)
            tick = data.get("tick")
            if not tick or not isinstance(tick, str):
                raise exceptions.InvalidInputDataError("Tick is required and must be a string")
            
            # Validate tick format (SRC20 tickers are typically 1-32 characters)
            if not (1 <= len(tick) <= 32):
                raise exceptions.InvalidInputDataError(f"Invalid tick format: {tick}")
            
            validated_data["tick"] = tick.upper()  # Normalize to uppercase

            # Validate price fields (optional)
            for field in ["price_btc", "price_usd", "floor_price_btc"]:
                if field in data:
                    price = self._validate_decimal_field(
                        data[field], field, MIN_PRICE, MAX_PRICE
                    )
                    if price is not None:
                        validated_data[field] = price

            # Validate market cap fields (optional)
            for field in ["market_cap_btc", "market_cap_usd"]:
                if field in data:
                    market_cap = self._validate_decimal_field(
                        data[field], field, MIN_MARKET_CAP, MAX_MARKET_CAP
                    )
                    if market_cap is not None:
                        validated_data[field] = market_cap

            # Validate volume fields (optional)
            for field in ["volume_24h_btc", "volume_7d_btc", "volume_30d_btc", "total_volume_btc"]:
                if field in data:
                    volume = self._validate_decimal_field(data[field], field, MIN_VOLUME, MAX_VOLUME)
                    if volume is not None:
                        validated_data[field] = volume

            # Validate price change fields (optional)
            for field in ["price_change_24h_percent", "price_change_7d_percent", "price_change_30d_percent"]:
                if field in data:
                    change = self._validate_decimal_field(
                        data[field], field, MIN_PRICE_CHANGE, MAX_PRICE_CHANGE
                    )
                    if change is not None:
                        validated_data[field] = change

            # Validate holder count (optional)
            if "holder_count" in data:
                count = self._validate_integer_field(data["holder_count"], "holder_count", MIN_HOLDER_COUNT, MAX_HOLDER_COUNT)
                if count is not None:
                    validated_data["holder_count"] = count

            # Validate supply fields (optional)
            for field in ["circulating_supply", "max_supply"]:
                if field in data:
                    supply = self._validate_decimal_field(data[field], field, MIN_SUPPLY, MAX_SUPPLY)
                    if supply is not None:
                        validated_data[field] = supply

            # Validate exchange and source fields (optional)
            for field in ["primary_exchange", "exchange_sources"]:
                if field in data and data[field] is not None:
                    if isinstance(data[field], str) and len(data[field]) <= 255:
                        validated_data[field] = data[field]
                    else:
                        logger.warning(f"Invalid {field} format, skipping: {data[field]}")

            # Validate quality metrics (optional, with defaults)
            quality_score = data.get("data_quality_score", DEFAULT_QUALITY_SCORE)
            validated_quality = self._validate_decimal_field(
                quality_score, "data_quality_score", MIN_QUALITY_SCORE, MAX_QUALITY_SCORE
            )
            validated_data["data_quality_score"] = validated_quality or DEFAULT_QUALITY_SCORE

            confidence_level = data.get("confidence_level", DEFAULT_CONFIDENCE_LEVEL)
            validated_confidence = self._validate_decimal_field(
                confidence_level, "confidence_level", MIN_CONFIDENCE_LEVEL, MAX_CONFIDENCE_LEVEL
            )
            validated_data["confidence_level"] = validated_confidence or DEFAULT_CONFIDENCE_LEVEL

            # Validate timestamps (optional)
            if "last_price_update" in data:
                timestamp = self._validate_timestamp_field(data["last_price_update"], "last_price_update")
                if timestamp is not None:
                    validated_data["last_price_update"] = timestamp

            # Validate update frequency (optional, with default)
            update_freq = data.get("update_frequency_minutes", DEFAULT_UPDATE_FREQUENCY)
            validated_freq = self._validate_integer_field(update_freq, "update_frequency_minutes", 1, 1440)  # 1 min to 1 day
            validated_data["update_frequency_minutes"] = validated_freq or DEFAULT_UPDATE_FREQUENCY

            logger.debug(f"Validated SRC20 market data for tick: {tick}")
            return validated_data

        except Exception as e:
            logger.error(f"Validation failed for SRC20 market data: {e}")
            raise exceptions.InvalidInputDataError(f"SRC20 market data validation failed: {e}")

    def transform_exchange_data(self, raw_data: Dict[str, Any], exchange_name: str) -> Dict[str, Any]:
        """
        Transform raw exchange API data into standardized market data format.

        Args:
            raw_data: Raw data from exchange API
            exchange_name: Name of the exchange (openstamp, kucoin, etc.)

        Returns:
            Transformed market data dictionary

        Raises:
            DataConversionError: If transformation fails
        """
        try:
            transformed_data = {}

            # Extract tick from various possible fields
            tick = None
            for field in ["tick", "symbol", "token", "asset"]:
                if field in raw_data and raw_data[field]:
                    tick = str(raw_data[field]).upper()
                    break
            
            if not tick:
                raise exceptions.DataConversionError("No tick/symbol found in raw data")
            
            transformed_data["tick"] = tick

            # Transform price data based on exchange format
            if exchange_name.lower() == "openstamp":
                # OpenStamp API format
                if "floor_price" in raw_data:
                    transformed_data["floor_price_btc"] = D(str(raw_data["floor_price"]))
                if "last_price" in raw_data:
                    transformed_data["price_btc"] = D(str(raw_data["last_price"]))
                if "volume_24h" in raw_data:
                    transformed_data["volume_24h_btc"] = D(str(raw_data["volume_24h"]))

            elif exchange_name.lower() == "kucoin":
                # KuCoin API format
                if "price" in raw_data:
                    transformed_data["price_btc"] = D(str(raw_data["price"]))
                if "vol" in raw_data:
                    transformed_data["volume_24h_btc"] = D(str(raw_data["vol"]))
                if "changeRate" in raw_data:
                    change_rate = D(str(raw_data["changeRate"])) * D("100")  # Convert to percentage
                    transformed_data["price_change_24h_percent"] = change_rate

            elif exchange_name.lower() == "stampscan":
                # StampScan API format
                if "current_price" in raw_data:
                    transformed_data["price_btc"] = D(str(raw_data["current_price"]))
                if "market_cap" in raw_data:
                    transformed_data["market_cap_btc"] = D(str(raw_data["market_cap"]))
                if "holders" in raw_data:
                    transformed_data["holder_count"] = int(raw_data["holders"])

            else:
                # Generic exchange format
                price_fields = ["price", "last_price", "current_price", "price_btc"]
                for field in price_fields:
                    if field in raw_data and raw_data[field] is not None:
                        transformed_data["price_btc"] = D(str(raw_data[field]))
                        break

                volume_fields = ["volume_24h", "vol", "volume", "volume_24h_btc"]
                for field in volume_fields:
                    if field in raw_data and raw_data[field] is not None:
                        transformed_data["volume_24h_btc"] = D(str(raw_data[field]))
                        break

            # Transform market cap if available
            if "market_cap" in raw_data:
                transformed_data["market_cap_btc"] = D(str(raw_data["market_cap"]))

            # Transform supply data
            if "circulating_supply" in raw_data:
                transformed_data["circulating_supply"] = D(str(raw_data["circulating_supply"]))
            if "max_supply" in raw_data:
                transformed_data["max_supply"] = D(str(raw_data["max_supply"]))

            # Transform holder count
            if "holders" in raw_data:
                transformed_data["holder_count"] = int(raw_data["holders"])

            # Add metadata
            transformed_data["primary_exchange"] = exchange_name
            transformed_data["exchange_sources"] = exchange_name
            
            # Set quality and confidence based on exchange reliability
            exchange_quality = {
                "openstamp": D("8.0"),    # High quality for SRC20-specific exchange
                "kucoin": D("7.5"),       # Good quality for established exchange
                "stampscan": D("7.0"),    # Good quality for specialized service
            }
            transformed_data["data_quality_score"] = exchange_quality.get(exchange_name.lower(), D("6.0"))
            transformed_data["confidence_level"] = exchange_quality.get(exchange_name.lower(), D("6.0"))
            
            transformed_data["last_price_update"] = datetime.now()
            transformed_data["update_frequency_minutes"] = 10  # More frequent updates for volatile tokens

            logger.debug(f"Transformed {exchange_name} data for tick: {tick}")
            return transformed_data

        except Exception as e:
            logger.error(f"Error transforming {exchange_name} data: {e}")
            raise exceptions.DataConversionError(f"Failed to transform {exchange_name} data: {e}")

    def calculate_derived_metrics(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate derived metrics from base market data.

        Args:
            market_data: Base market data dictionary

        Returns:
            Market data with additional derived metrics

        Raises:
            DataConversionError: If calculation fails
        """
        try:
            enhanced_data = market_data.copy()

            # Calculate market cap if price and supply are available
            price_btc = market_data.get("price_btc")
            circulating_supply = market_data.get("circulating_supply")
            
            if price_btc and circulating_supply:
                market_cap_btc = D(str(price_btc)) * D(str(circulating_supply))
                enhanced_data["market_cap_btc"] = market_cap_btc

            # Calculate volume ratios and liquidity metrics
            volume_24h = market_data.get("volume_24h_btc", D("0"))
            market_cap = enhanced_data.get("market_cap_btc", D("0"))
            
            if market_cap > 0 and volume_24h > 0:
                volume_to_mcap_ratio = (D(str(volume_24h)) / D(str(market_cap))) * D("100")
                enhanced_data["volume_to_mcap_ratio"] = min(volume_to_mcap_ratio, D("1000"))  # Cap at 1000%

            # Calculate trading activity score
            holder_count = market_data.get("holder_count", 0)
            volume_24h_float = float(volume_24h) if volume_24h else 0
            
            activity_score = D("0")
            
            # Volume component (0-6 points)
            if volume_24h_float > 0:
                import math
                volume_score = min(math.log10(volume_24h_float * 1000000) * D("1.2"), D("6"))
                activity_score += max(D("0"), volume_score)
            
            # Holder component (0-4 points)
            if holder_count > 0:
                import math
                holder_score = min(math.log10(holder_count + 1) * D("1.5"), D("4"))
                activity_score += holder_score
            
            enhanced_data["trading_activity_score"] = min(activity_score, D("10"))

            # Calculate volatility indicator from price changes
            price_changes = []
            for field in ["price_change_24h_percent", "price_change_7d_percent", "price_change_30d_percent"]:
                if field in market_data and market_data[field] is not None:
                    price_changes.append(abs(D(str(market_data[field]))))
            
            if price_changes:
                avg_volatility = sum(price_changes) / len(price_changes)
                # Normalize volatility to 0-10 scale (higher = more volatile)
                volatility_score = min(avg_volatility / D("10"), D("10"))
                enhanced_data["volatility_score"] = volatility_score

            # Update quality score based on data completeness
            completeness_score = D("0")
            required_fields = ["price_btc", "volume_24h_btc", "holder_count"]
            optional_fields = ["market_cap_btc", "circulating_supply", "price_change_24h_percent"]
            
            for field in required_fields:
                if field in market_data and market_data[field] is not None:
                    completeness_score += D("2")  # 2 points per required field
            
            for field in optional_fields:
                if field in market_data and market_data[field] is not None:
                    completeness_score += D("1")  # 1 point per optional field
            
            # Adjust quality score based on completeness
            base_quality = market_data.get("data_quality_score", DEFAULT_QUALITY_SCORE)
            adjusted_quality = (D(str(base_quality)) + completeness_score) / D("2")
            enhanced_data["data_quality_score"] = min(adjusted_quality, D("10"))

            # Calculate price performance indicators
            price_change_24h = market_data.get("price_change_24h_percent")
            if price_change_24h is not None:
                change_val = D(str(price_change_24h))
                if change_val > D("50"):
                    enhanced_data["performance_indicator"] = "strong_bullish"
                elif change_val > D("10"):
                    enhanced_data["performance_indicator"] = "bullish"
                elif change_val > D("-10"):
                    enhanced_data["performance_indicator"] = "neutral"
                elif change_val > D("-50"):
                    enhanced_data["performance_indicator"] = "bearish"
                else:
                    enhanced_data["performance_indicator"] = "strong_bearish"

            tick = market_data.get("tick", "unknown")
            logger.debug(f"Calculated derived metrics for tick: {tick}")
            return enhanced_data

        except Exception as e:
            logger.error(f"Error calculating derived metrics: {e}")
            raise exceptions.DataConversionError(f"Failed to calculate derived metrics: {e}")

    def process_src20_market_update(self, tick: str, raw_data: Dict[str, Any], exchange_name: str = "generic") -> Dict[str, Any]:
        """
        Process a complete SRC20 market data update.

        Args:
            tick: SRC20 token ticker symbol
            raw_data: Raw market data from external sources
            exchange_name: Name of the exchange providing the data

        Returns:
            Processed and validated market data

        Raises:
            InvalidInputDataError: If processing fails
            DataConversionError: If transformation fails
        """
        try:
            # Ensure tick is included in raw data
            if "tick" not in raw_data:
                raw_data["tick"] = tick.upper()

            # Transform raw data to standardized format
            transformed_data = self.transform_exchange_data(raw_data, exchange_name)

            # Calculate derived metrics
            enhanced_data = self.calculate_derived_metrics(transformed_data)

            # Validate the final data
            validated_data = self.validate_src20_market_data(enhanced_data)

            # Store in database
            db = self.db_manager.connect()
            try:
                insert_src20_market_data(db, validated_data)
                db.commit()
                logger.info(f"Successfully processed SRC20 market update for tick: {tick}")
            finally:
                db.close()

            return validated_data

        except Exception as e:
            logger.error(f"Error processing SRC20 market update for {tick}: {e}")
            raise

    def _validate_decimal_field(self, value: Any, field_name: str, min_val: Decimal, max_val: Decimal) -> Optional[Decimal]:
        """Validate a decimal field with range checking."""
        if value is None:
            return None
        
        try:
            decimal_val = D(str(value))
            if decimal_val < min_val or decimal_val > max_val:
                logger.warning(f"Field {field_name} value {decimal_val} out of range [{min_val}, {max_val}]")
                return None
            return decimal_val
        except (ValueError, TypeError, Decimal.InvalidOperation):
            logger.warning(f"Invalid decimal value for {field_name}: {value}")
            return None

    def _validate_integer_field(self, value: Any, field_name: str, min_val: int, max_val: int) -> Optional[int]:
        """Validate an integer field with range checking."""
        if value is None:
            return None
        
        try:
            int_val = int(value)
            if int_val < min_val or int_val > max_val:
                logger.warning(f"Field {field_name} value {int_val} out of range [{min_val}, {max_val}]")
                return None
            return int_val
        except (ValueError, TypeError):
            logger.warning(f"Invalid integer value for {field_name}: {value}")
            return None

    def _validate_timestamp_field(self, value: Any, field_name: str) -> Optional[datetime]:
        """Validate a timestamp field."""
        if value is None:
            return None
        
        try:
            if isinstance(value, datetime):
                return value
            elif isinstance(value, (int, float)):
                return datetime.fromtimestamp(value)
            elif isinstance(value, str):
                # Try to parse ISO format
                return datetime.fromisoformat(value.replace('Z', '+00:00'))
            else:
                logger.warning(f"Invalid timestamp format for {field_name}: {value}")
                return None
        except (ValueError, TypeError, OSError):
            logger.warning(f"Invalid timestamp value for {field_name}: {value}")
            return None


# Global processor instance for easy access
src20_market_processor = SRC20MarketDataProcessor()


# Convenience functions for common operations
def process_src20_market_data(tick: str, raw_data: Dict[str, Any], exchange_name: str = "generic") -> Dict[str, Any]:
    """
    Process SRC20 market data using the global processor instance.
    
    Args:
        tick: SRC20 token ticker symbol
        raw_data: Raw market data from external sources
        exchange_name: Name of the exchange providing the data
    
    Returns:
        Processed and validated market data
    """
    return src20_market_processor.process_src20_market_update(tick, raw_data, exchange_name)


def validate_src20_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate SRC20 market data using the global processor instance.
    
    Args:
        data: Market data dictionary to validate
    
    Returns:
        Validated market data dictionary
    """
    return src20_market_processor.validate_src20_market_data(data)


def transform_exchange_response(raw_data: Dict[str, Any], exchange_name: str) -> Dict[str, Any]:
    """
    Transform exchange API response using the global processor instance.
    
    Args:
        raw_data: Raw data from exchange API
        exchange_name: Name of the exchange
    
    Returns:
        Transformed market data dictionary
    """
    return src20_market_processor.transform_exchange_data(raw_data, exchange_name) 