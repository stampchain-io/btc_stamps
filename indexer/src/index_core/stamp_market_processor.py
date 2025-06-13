"""
Stamp Market Data Processor for Bitcoin Stamps Indexer

This module provides specialized processing logic for stamp market data operations,
including validation, transformation, and business logic specific to Bitcoin Stamps.

The processor follows the existing patterns in the indexer codebase for error handling,
logging, and database operations.
"""

import decimal
import logging
import math
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional

import index_core.exceptions as exceptions
import index_core.log as log
from index_core.database import get_stamp_market_data_raw, insert_stamp_market_data
from index_core.database_manager import DatabaseManager

logger = logging.getLogger(__name__)
log.set_logger(logger)

D = Decimal

# Validation constants for stamp market data
MIN_FLOOR_PRICE = D("0.00000001")  # 1 satoshi in BTC
MAX_FLOOR_PRICE = D("21000000")  # Max possible BTC
MIN_HOLDER_COUNT = 0
MAX_HOLDER_COUNT = 1000000
MIN_VOLUME = D("0")
MAX_VOLUME = D("21000000")
MIN_QUALITY_SCORE = D("0.0")
MAX_QUALITY_SCORE = D("10.0")
MIN_CONFIDENCE_LEVEL = D("0.0")
MAX_CONFIDENCE_LEVEL = D("10.0")

# Default values for missing data
DEFAULT_QUALITY_SCORE = D("5.0")
DEFAULT_CONFIDENCE_LEVEL = D("5.0")
DEFAULT_UPDATE_FREQUENCY = 30  # minutes


class StampMarketDataProcessor:
    """
    Processor for stamp-specific market data operations.

    This class handles validation, transformation, and business logic
    specific to Bitcoin Stamps market data processing.
    """

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        """Initialize the StampMarketDataProcessor."""
        self.db_manager = db_manager or DatabaseManager()
        logger.info("StampMarketDataProcessor initialized")

    def validate_stamp_market_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate and sanitize stamp market data.

        Args:
            data: Raw market data dictionary

        Returns:
            Validated and sanitized market data dictionary

        Raises:
            InvalidInputDataError: If validation fails
        """
        try:
            validated_data = {}

            # Validate CPID (required field)
            cpid = data.get("cpid")
            if not cpid or not isinstance(cpid, str):
                raise exceptions.InvalidInputDataError("CPID is required and must be a string")

            # Validate CPID format (should be Counterparty asset ID)
            if not (cpid.startswith("A") and len(cpid) >= 13):
                raise exceptions.InvalidInputDataError(f"Invalid CPID format: {cpid}")

            validated_data["cpid"] = cpid

            # Validate floor price (optional)
            if "floor_price_btc" in data:
                floor_price = self._validate_decimal_field(
                    data["floor_price_btc"], "floor_price_btc", MIN_FLOOR_PRICE, MAX_FLOOR_PRICE
                )
                if floor_price is not None:
                    validated_data["floor_price_btc"] = floor_price

            # Validate recent sale price (optional)
            if "recent_sale_price_btc" in data:
                recent_price = self._validate_decimal_field(
                    data["recent_sale_price_btc"], "recent_sale_price_btc", MIN_FLOOR_PRICE, MAX_FLOOR_PRICE
                )
                if recent_price is not None:
                    validated_data["recent_sale_price_btc"] = recent_price

            # Validate dispenser counts (optional)
            for field in ["open_dispensers_count", "closed_dispensers_count", "total_dispensers_count"]:
                if field in data:
                    count = self._validate_integer_field(data[field], field, 0, 1000000)
                    if count is not None:
                        validated_data[field] = count

            # Validate holder counts (optional)
            for field in ["holder_count", "unique_holder_count"]:
                if field in data:
                    count = self._validate_integer_field(data[field], field, MIN_HOLDER_COUNT, MAX_HOLDER_COUNT)
                    if count is not None:
                        validated_data[field] = count

            # Validate holder distribution metrics (optional)
            if "top_holder_percentage" in data:
                percentage = self._validate_decimal_field(
                    data["top_holder_percentage"], "top_holder_percentage", D("0.0"), D("100.0")
                )
                if percentage is not None:
                    validated_data["top_holder_percentage"] = percentage

            if "holder_distribution_score" in data:
                score = self._validate_decimal_field(
                    data["holder_distribution_score"], "holder_distribution_score", D("0.0"), D("10.0")
                )
                if score is not None:
                    validated_data["holder_distribution_score"] = score

            # Validate volume fields (optional)
            for field in ["volume_24h_btc", "volume_7d_btc", "volume_30d_btc", "total_volume_btc"]:
                if field in data:
                    volume = self._validate_decimal_field(data[field], field, MIN_VOLUME, MAX_VOLUME)
                    if volume is not None:
                        validated_data[field] = volume

            # Validate source fields (optional)
            for field in ["price_source", "volume_sources"]:
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

            # Validate block numbers (optional)
            for field in ["last_dispenser_block", "last_balance_block"]:
                if field in data:
                    block_num = self._validate_integer_field(data[field], field, 0, 10000000)
                    if block_num is not None:
                        validated_data[field] = block_num

            # Validate timestamps (optional)
            if "last_price_update" in data:
                timestamp = self._validate_timestamp_field(data["last_price_update"], "last_price_update")
                if timestamp is not None:
                    validated_data["last_price_update"] = timestamp

            # Validate update frequency (optional, with default)
            update_freq = data.get("update_frequency_minutes", DEFAULT_UPDATE_FREQUENCY)
            validated_freq = self._validate_integer_field(update_freq, "update_frequency_minutes", 1, 10080)  # 1 min to 1 week
            validated_data["update_frequency_minutes"] = validated_freq or DEFAULT_UPDATE_FREQUENCY

            logger.debug(f"Validated stamp market data for CPID: {cpid}")
            return validated_data

        except Exception as e:
            logger.error(f"Validation failed for stamp market data: {e}")
            raise exceptions.InvalidInputDataError(f"Stamp market data validation failed: {e}")

    def transform_counterparty_data(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform raw Counterparty API data into standardized market data format.

        Args:
            raw_data: Raw data from Counterparty API

        Returns:
            Transformed market data dictionary

        Raises:
            DataConversionError: If transformation fails
        """
        try:
            transformed_data = {}

            # Extract CPID from asset data
            if "asset" in raw_data:
                transformed_data["cpid"] = raw_data["asset"]
            elif "cpid" in raw_data:
                transformed_data["cpid"] = raw_data["cpid"]
            else:
                raise exceptions.DataConversionError("No CPID found in raw data")

            # Transform dispenser data
            if "dispensers" in raw_data:
                dispensers = raw_data["dispensers"]
                if isinstance(dispensers, list):
                    open_count = sum(1 for d in dispensers if d.get("status") == 0)
                    closed_count = sum(1 for d in dispensers if d.get("status") == 10)
                    total_count = len(dispensers)

                    transformed_data["open_dispensers_count"] = open_count
                    transformed_data["closed_dispensers_count"] = closed_count
                    transformed_data["total_dispensers_count"] = total_count

                    # Calculate floor price from open dispensers
                    open_dispensers = [d for d in dispensers if d.get("status") == 0]
                    if open_dispensers:
                        prices = []
                        for dispenser in open_dispensers:
                            if "satoshirate" in dispenser and dispenser["satoshirate"]:
                                # Convert satoshirate to BTC price
                                satoshi_rate = D(str(dispenser["satoshirate"]))
                                btc_price = satoshi_rate / D("100000000")  # Convert satoshis to BTC
                                prices.append(btc_price)

                        if prices:
                            transformed_data["floor_price_btc"] = min(prices)

            # Transform balance/holder data
            if "balances" in raw_data:
                balances = raw_data["balances"]
                if isinstance(balances, list):
                    # Filter out zero balances
                    non_zero_balances = [b for b in balances if b.get("quantity", 0) > 0]
                    transformed_data["holder_count"] = len(non_zero_balances)
                    transformed_data["unique_holder_count"] = len(set(b.get("address") for b in non_zero_balances))

                    # Calculate holder distribution metrics
                    if non_zero_balances:
                        quantities = [D(str(b.get("quantity", 0))) for b in non_zero_balances]
                        total_supply = sum(quantities)

                        if total_supply > 0:
                            max_holding = max(quantities)
                            top_holder_percentage = (max_holding / total_supply) * D("100")
                            transformed_data["top_holder_percentage"] = top_holder_percentage

                            # Calculate distribution score (lower score = more distributed)
                            # Using Gini coefficient approximation
                            sorted_quantities = sorted(quantities, reverse=True)
                            n = len(sorted_quantities)
                            cumulative_sum = sum((i + 1) * q for i, q in enumerate(sorted_quantities))
                            gini = (D("2") * cumulative_sum) / (D(str(n)) * total_supply) - D(str(n + 1)) / D(str(n))
                            distribution_score = (D("1") - gini) * D("10")  # Convert to 0-10 scale
                            transformed_data["holder_distribution_score"] = max(D("0"), min(D("10"), distribution_score))

            # Transform volume data from dispenses
            if "dispenses" in raw_data:
                dispenses = raw_data["dispenses"]
                if isinstance(dispenses, list):
                    now = datetime.now()
                    volume_24h = D("0")
                    volume_7d = D("0")
                    volume_30d = D("0")
                    total_volume = D("0")

                    for dispense in dispenses:
                        if "block_time" in dispense and "btc_amount" in dispense:
                            try:
                                block_time = datetime.fromtimestamp(dispense["block_time"])
                                btc_amount = D(str(dispense["btc_amount"])) / D("100000000")  # Convert satoshis to BTC

                                total_volume += btc_amount

                                time_diff = now - block_time
                                if time_diff.days <= 1:
                                    volume_24h += btc_amount
                                if time_diff.days <= 7:
                                    volume_7d += btc_amount
                                if time_diff.days <= 30:
                                    volume_30d += btc_amount
                            except (ValueError, TypeError) as e:
                                logger.debug(f"Error processing dispense data: {e}")
                                continue

                    transformed_data["volume_24h_btc"] = volume_24h
                    transformed_data["volume_7d_btc"] = volume_7d
                    transformed_data["volume_30d_btc"] = volume_30d
                    transformed_data["total_volume_btc"] = total_volume

            # Add metadata
            transformed_data["price_source"] = "counterparty"
            transformed_data["volume_sources"] = "counterparty"
            transformed_data["data_quality_score"] = D("8.0")  # High quality for Counterparty data
            transformed_data["confidence_level"] = D("9.0")  # High confidence for official API
            transformed_data["last_price_update"] = datetime.now()
            transformed_data["update_frequency_minutes"] = 30

            logger.debug(f"Transformed Counterparty data for CPID: {transformed_data.get('cpid')}")
            return transformed_data

        except Exception as e:
            logger.error(f"Error transforming Counterparty data: {e}")
            raise exceptions.DataConversionError(f"Failed to transform Counterparty data: {e}")

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

            # Calculate price change indicators
            cpid = market_data.get("cpid")
            if cpid:
                # Get historical data for comparison
                db = self.db_manager.connect()
                try:
                    historical_data = get_stamp_market_data_raw(db, cpid)
                    if historical_data:
                        old_floor_price = historical_data[1]  # floor_price_btc column
                        new_floor_price = market_data.get("floor_price_btc")

                        if old_floor_price and new_floor_price:
                            old_price = D(str(old_floor_price))
                            new_price = D(str(new_floor_price))

                            if old_price > 0:
                                price_change = ((new_price - old_price) / old_price) * D("100")
                                enhanced_data["price_change_percent"] = price_change
                finally:
                    db.close()

            # Calculate liquidity score based on dispensers and volume
            open_dispensers = market_data.get("open_dispensers_count", 0)
            volume_24h = market_data.get("volume_24h_btc", D("0"))

            liquidity_score = D("0")
            if open_dispensers > 0:
                liquidity_score += min(D(str(open_dispensers)), D("10")) * D("0.3")  # Max 3 points for dispensers
            if volume_24h > 0:
                # Log scale for volume contribution (max 7 points)
                volume_float = float(volume_24h)
                if volume_float > 0:
                    volume_score = min(D(str(math.log10(volume_float * 1000000))) * D("1.5"), D("7"))  # Scale factor
                    liquidity_score += max(D("0"), volume_score)

            enhanced_data["liquidity_score"] = min(liquidity_score, D("10"))

            # Calculate market activity score
            holder_count = market_data.get("holder_count", 0)
            total_dispensers = market_data.get("total_dispensers_count", 0)

            activity_score = D("0")
            if holder_count > 0:
                # Log scale for holder contribution
                holder_score = min(D(str(math.log10(holder_count + 1))) * D("2"), D("6"))  # Max 6 points
                activity_score += holder_score
            if total_dispensers > 0:
                dispenser_score = min(D(str(total_dispensers)) * D("0.1"), D("4"))  # Max 4 points
                activity_score += dispenser_score

            enhanced_data["market_activity_score"] = min(activity_score, D("10"))

            # Update quality score based on data completeness
            completeness_score = D("0")
            required_fields = ["floor_price_btc", "holder_count", "volume_24h_btc"]
            optional_fields = ["recent_sale_price_btc", "open_dispensers_count", "top_holder_percentage"]

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

            logger.debug(f"Calculated derived metrics for CPID: {cpid}")
            return enhanced_data

        except Exception as e:
            logger.error(f"Error calculating derived metrics: {e}")
            raise exceptions.DataConversionError(f"Failed to calculate derived metrics: {e}")

    def process_stamp_market_update(self, cpid: str, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a complete stamp market data update.

        Args:
            cpid: Counterparty asset ID
            raw_data: Raw market data from external sources

        Returns:
            Processed and validated market data

        Raises:
            InvalidInputDataError: If processing fails
            DataConversionError: If transformation fails
        """
        try:
            # Ensure CPID is included in raw data
            if "cpid" not in raw_data:
                raw_data["cpid"] = cpid

            # Transform raw data to standardized format
            transformed_data = self.transform_counterparty_data(raw_data)

            # Calculate derived metrics
            enhanced_data = self.calculate_derived_metrics(transformed_data)

            # Validate the final data
            validated_data = self.validate_stamp_market_data(enhanced_data)

            # Store in database
            db = self.db_manager.connect()
            try:
                insert_stamp_market_data(db, validated_data)
                db.commit()
                logger.info(f"Successfully processed stamp market update for CPID: {cpid}")
            finally:
                db.close()

            return validated_data

        except Exception as e:
            logger.error(f"Error processing stamp market update for {cpid}: {e}")
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
        except (ValueError, TypeError, decimal.InvalidOperation):
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
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            else:
                logger.warning(f"Invalid timestamp format for {field_name}: {value}")
                return None
        except (ValueError, TypeError, OSError):
            logger.warning(f"Invalid timestamp value for {field_name}: {value}")
            return None


# Global processor instance for easy access
stamp_market_processor = StampMarketDataProcessor()


def process_stamp_market_data(cpid: str, raw_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convenience function to process stamp market data using the global processor.

    Args:
        cpid: Counterparty asset ID
        raw_data: Raw market data from external sources

    Returns:
        Processed and validated market data
    """
    return stamp_market_processor.process_stamp_market_update(cpid, raw_data)


def validate_stamp_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convenience function to validate stamp market data using the global processor.

    Args:
        data: Market data to validate

    Returns:
        Validated market data
    """
    return stamp_market_processor.validate_stamp_market_data(data)


def transform_counterparty_response(raw_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convenience function to transform Counterparty API data using the global processor.

    Args:
        raw_data: Raw data from Counterparty API

    Returns:
        Transformed market data
    """
    return stamp_market_processor.transform_counterparty_data(raw_data)
