"""
Stamp Processing Worker for Bitcoin Stamps Indexer

This module provides specialized worker functions for fetching and processing
stamp market data from the Counterparty API, specifically focusing on
dispensers and dispenses data for floor price and volume calculations.
"""

import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from index_core.fetch_utils import RateLimiter, fetch_xcp
from index_core.stamp_market_processor import StampMarketDataProcessor

logger = logging.getLogger(__name__)

# Rate limiting for Counterparty API calls
COUNTERPARTY_RATE_LIMITER = RateLimiter(calls_per_second=2.0)

# Constants for data processing
VOLUME_CALCULATION_DAYS = [1, 7, 30]  # Calculate volume for 1d, 7d, 30d
MAX_DISPENSERS_PER_REQUEST = 1000
MAX_DISPENSES_PER_REQUEST = 1000
MAX_BALANCES_PER_REQUEST = 1000


class StampWorker:
    """
    Worker class for processing stamp market data from Counterparty API.

    Handles fetching dispensers, dispenses, and balances data to calculate
    comprehensive market metrics for Bitcoin Stamps.
    """

    # Class-level shared processor to avoid repeated initialization
    _shared_processor = None

    def __init__(self):
        if StampWorker._shared_processor is None:
            StampWorker._shared_processor = StampMarketDataProcessor()
        self.processor = StampWorker._shared_processor
        self.rate_limiter = COUNTERPARTY_RATE_LIMITER

    def process_stamp_market_data(self, cpid: str) -> Optional[Dict]:
        """
        Process complete market data for a single stamp.

        Args:
            cpid: Counterparty asset ID

        Returns:
            Dictionary with processed market data or None if failed
        """
        try:
            # CPIDs are now pre-filtered as valid Counterparty assets in the SQL query (ident='STAMP')
            # No need for additional validation here!
            logger.debug(f"Processing market data for stamp {cpid}")
            start_time = time.time()

            # Fetch all required data from Counterparty API
            dispensers_data = self._fetch_dispensers(cpid)
            dispenses_data = self._fetch_dispenses(cpid)
            balances_data = self._fetch_balances(cpid)
            logger.debug(f"Fetched {len(balances_data) if balances_data else 0} balance records for {cpid}")

            # Process the raw data into market metrics
            market_data = self._calculate_market_metrics(cpid, dispensers_data, dispenses_data, balances_data)

            if market_data:
                # Add processing metadata
                market_data["processing_time_ms"] = int((time.time() - start_time) * 1000)
                market_data["last_updated"] = datetime.now()

                # Validate the processed data
                validated_data = self.processor.validate_stamp_market_data(market_data)
                if validated_data:
                    logger.debug(f"Successfully processed market data for {cpid}")
                    return validated_data
                else:
                    logger.warning(f"Market data validation failed for {cpid}")
                    return None
            else:
                logger.debug(f"No market data calculated for {cpid}")
                return None

        except Exception as e:
            logger.error(f"Error processing stamp market data for {cpid}: {e}")
            return None

    def _fetch_dispensers(self, cpid: str) -> Optional[List[Dict]]:
        """
        Fetch dispenser data for a stamp from Counterparty API.

        Args:
            cpid: Counterparty asset ID

        Returns:
            List of dispenser dictionaries or None if failed
        """
        try:
            # Rate limiting
            self.rate_limiter.acquire()

            endpoint = f"/assets/{cpid}/dispensers"
            params = {"limit": MAX_DISPENSERS_PER_REQUEST, "show_unconfirmed": "false"}

            logger.debug(f"Fetching dispensers for {cpid}")
            response = fetch_xcp(endpoint, params)

            if response and "result" in response:
                dispensers = response["result"]
                logger.debug(f"Found {len(dispensers)} dispensers for {cpid}")
                return dispensers
            else:
                logger.debug(f"No dispensers found for {cpid}")
                return []

        except Exception as e:
            logger.error(f"Error fetching dispensers for {cpid}: {e}")
            return None

    def _fetch_dispenses(self, cpid: str) -> Optional[List[Dict]]:
        """
        Fetch dispense history for a stamp from Counterparty API.

        Args:
            cpid: Counterparty asset ID

        Returns:
            List of dispense dictionaries or None if failed
        """
        try:
            # Rate limiting
            self.rate_limiter.acquire()

            endpoint = f"/assets/{cpid}/dispenses"
            params = {"limit": MAX_DISPENSES_PER_REQUEST, "show_unconfirmed": "false"}

            logger.debug(f"Fetching dispenses for {cpid}")
            response = fetch_xcp(endpoint, params)

            if response and "result" in response:
                dispenses = response["result"]
                if dispenses:
                    logger.info(f"Found {len(dispenses)} dispenses for {cpid}")
                else:
                    logger.debug(f"No dispenses found for {cpid}")
                return dispenses
            else:
                logger.debug(f"No dispenses found for {cpid}")
                return []

        except Exception as e:
            logger.error(f"Error fetching dispenses for {cpid}: {e}")
            return None

    def _fetch_balances(self, cpid: str) -> Optional[List[Dict]]:
        """
        Fetch balance data for a stamp from Counterparty API.

        Args:
            cpid: Counterparty asset ID

        Returns:
            List of balance dictionaries or None if failed
        """
        try:
            # Rate limiting
            self.rate_limiter.acquire()

            endpoint = f"/assets/{cpid}/balances"
            params = {"limit": MAX_BALANCES_PER_REQUEST, "show_unconfirmed": "false"}

            logger.debug(f"Fetching balances for {cpid}")
            response = fetch_xcp(endpoint, params)

            if response and "result" in response:
                balances = response["result"]
                logger.debug(f"Found {len(balances)} balance holders for {cpid}")
                return balances
            else:
                logger.debug(f"No balances found for {cpid}")
                return []

        except Exception as e:
            logger.error(f"Error fetching balances for {cpid}: {e}")
            return None

    def _calculate_market_metrics(
        self, cpid: str, dispensers: Optional[List[Dict]], dispenses: Optional[List[Dict]], balances: Optional[List[Dict]]
    ) -> Optional[Dict]:
        """
        Calculate comprehensive market metrics from raw Counterparty data.

        Args:
            cpid: Counterparty asset ID
            dispensers: List of dispenser data
            dispenses: List of dispense data
            balances: List of balance data

        Returns:
            Dictionary with calculated market metrics
        """
        try:
            market_data = {
                "cpid": cpid,
                "floor_price_btc": None,
                "recent_sale_price_btc": None,
                "volume_24h_btc": None,
                "volume_7d_btc": None,
                "volume_30d_btc": None,
                "holder_count": None,
                "open_dispensers_count": 0,
                "total_dispensers_count": 0,
                "liquidity_score": None,
                "market_activity_score": None,
                "quality_score": 0.0,
                "confidence_level": 3.0,
                "price_source": "counterparty",  # Always set default
                "volume_sources": {"counterparty": 1.0},  # Always set default as JSON
                "last_price_update": None,
                "last_sale_block_index": None,
            }

            # Calculate floor price from active dispensers
            if dispensers:
                floor_price, dispenser_metrics = self._calculate_floor_price(dispensers)
                market_data.update(dispenser_metrics)
                market_data["floor_price_btc"] = floor_price
                # Set price source if we found a floor price from dispensers
                if floor_price is not None:
                    market_data["price_source"] = "dispenser"

            # Calculate volume metrics from dispenses
            if dispenses:
                volume_metrics = self._calculate_volume_metrics(dispenses)
                market_data.update(volume_metrics)
                # Set volume sources if we found any volume data
                if any(volume_metrics.get(f"volume_{period}_btc", 0) > 0 for period in ["24h", "7d", "30d"]):
                    market_data["volume_sources"] = {"dispenser": 1.0}
                # Update volume fields to 0 if they weren't set by dispenses
                for vol_field in ["volume_24h_btc", "volume_7d_btc", "volume_30d_btc"]:
                    if market_data.get(vol_field) is None:
                        market_data[vol_field] = 0.0

            # Calculate holder metrics from balances
            if balances:
                holder_metrics = self._calculate_holder_metrics(balances)
                market_data.update(holder_metrics)

                # Store holder cache data separately for database population
                if "holder_cache_data" in holder_metrics:
                    market_data["_holder_cache_data"] = holder_metrics.pop("holder_cache_data")

            # Calculate derived metrics
            market_data["liquidity_score"] = self._calculate_liquidity_score(market_data)
            market_data["market_activity_score"] = self._calculate_activity_score(market_data)
            market_data["quality_score"] = self._calculate_quality_score(market_data)
            market_data["confidence_level"] = self._determine_confidence_level(market_data)

            return market_data

        except Exception as e:
            logger.error(f"Error calculating market metrics for {cpid}: {e}")
            return None

    def _calculate_floor_price(self, dispensers: List[Dict]) -> Tuple[Optional[float], Dict]:
        """
        Calculate floor price and dispenser metrics.

        Args:
            dispensers: List of dispenser data

        Returns:
            Tuple of (floor_price_btc, dispenser_metrics)
        """
        try:
            active_dispensers = []
            total_dispensers = len(dispensers)
            rates = []  # Initialize rates outside conditional block to avoid UnboundLocalError

            for dispenser in dispensers:
                status = dispenser.get("status", 1)
                if status == 0:  # 0 = active/open
                    active_dispensers.append(dispenser)

            open_dispensers_count = len(active_dispensers)

            # Calculate floor price from active dispensers
            floor_price_btc = None
            if active_dispensers:
                for dispenser in active_dispensers:
                    satoshirate = dispenser.get("satoshirate")
                    if satoshirate and float(satoshirate) > 0:
                        # Convert satoshis to BTC
                        btc_rate = float(satoshirate) / 100000000
                        rates.append(btc_rate)

                if rates:
                    floor_price_btc = min(rates)

            dispenser_metrics: Dict[str, Any] = {
                "open_dispensers_count": open_dispensers_count,
                "total_dispensers_count": total_dispensers,
                "avg_dispenser_rate": None,
                "max_dispenser_rate": None,
            }

            # Calculate additional dispenser metrics
            if rates:
                dispenser_metrics["avg_dispenser_rate"] = sum(rates) / len(rates)
                dispenser_metrics["max_dispenser_rate"] = max(rates)

            return floor_price_btc, dispenser_metrics

        except Exception as e:
            logger.error(f"Error calculating floor price: {e}")
            return None, {}

    def _calculate_volume_metrics(self, dispenses: List[Dict]) -> Dict[str, Any]:
        """
        Calculate volume metrics for different time periods and track most recent sale.

        Args:
            dispenses: List of dispense data

        Returns:
            Dictionary with volume metrics
        """
        try:
            now = datetime.now()
            volume_metrics: Dict[str, Any] = {
                "volume_24h_btc": 0.0,
                "volume_7d_btc": 0.0,
                "volume_30d_btc": 0.0,
                "total_dispenses_count": len(dispenses),
                "recent_dispenses_count": 0,
            }

            most_recent_sale_time = None
            most_recent_block_index = None
            most_recent_price = None
            most_recent_tx_hash = None
            most_recent_buyer = None
            most_recent_dispenser = None
            most_recent_btc_amount = None
            most_recent_dispenser_tx_hash = None

            for dispense in dispenses:
                try:
                    # Get dispense timestamp and block index
                    block_time = dispense.get("block_time")
                    block_index = dispense.get("block_index")
                    if not block_time:
                        continue

                    dispense_time = datetime.fromtimestamp(block_time)
                    time_diff = now - dispense_time

                    # Get dispense value in BTC
                    dispense_quantity = float(dispense.get("dispense_quantity", 0))
                    satoshirate = float(dispense.get("satoshirate", 0))

                    if dispense_quantity > 0 and satoshirate > 0:
                        # Calculate volume in BTC
                        volume_btc = (dispense_quantity * satoshirate) / 100000000
                        price_per_unit = satoshirate / 100000000

                        # Track most recent sale with all details
                        if most_recent_sale_time is None or block_time > most_recent_sale_time:
                            most_recent_sale_time = block_time
                            most_recent_price = price_per_unit
                            most_recent_block_index = block_index
                            most_recent_tx_hash = dispense.get("tx_hash")
                            most_recent_buyer = dispense.get("source")  # source is the buyer
                            most_recent_dispenser = dispense.get("destination")  # destination is the dispenser
                            # Calculate BTC amount in satoshis (dispense_quantity * satoshirate)
                            most_recent_btc_amount = int(dispense_quantity * satoshirate)
                            # Get the dispenser creation tx from the dispenser address field
                            most_recent_dispenser_tx_hash = dispense.get("dispenser_tx_hash")

                        # Add to appropriate time period buckets
                        if time_diff.days < 1:
                            volume_metrics["volume_24h_btc"] += volume_btc
                            volume_metrics["recent_dispenses_count"] += 1
                        if time_diff.days < 7:
                            volume_metrics["volume_7d_btc"] += volume_btc
                        if time_diff.days < 30:
                            volume_metrics["volume_30d_btc"] += volume_btc

                except (ValueError, TypeError) as e:
                    logger.debug(f"Error processing dispense data: {e}")
                    continue

            # Set the most recent sale data
            if most_recent_sale_time:
                volume_metrics["recent_sale_price_btc"] = most_recent_price
                volume_metrics["last_price_update"] = datetime.fromtimestamp(most_recent_sale_time).isoformat()
                volume_metrics["last_sale_block_index"] = most_recent_block_index
                volume_metrics["last_sale_tx_hash"] = most_recent_tx_hash
                volume_metrics["last_sale_buyer_address"] = most_recent_buyer
                volume_metrics["last_sale_dispenser_address"] = most_recent_dispenser
                volume_metrics["last_sale_btc_amount"] = most_recent_btc_amount
                volume_metrics["last_sale_dispenser_tx_hash"] = most_recent_dispenser_tx_hash
                
                # Log when we successfully capture recent sale data
                logger.info(f"Captured recent sale: tx={most_recent_tx_hash}, buyer={most_recent_buyer}, amount={most_recent_btc_amount} sats")

            return volume_metrics

        except Exception as e:
            logger.error(f"Error calculating volume metrics: {e}")
            return {}

    def _calculate_holder_metrics(self, balances: List[Dict]) -> Dict:
        """
        Calculate holder distribution metrics and populate holder cache.

        Args:
            balances: List of balance data

        Returns:
            Dictionary with holder metrics
        """
        try:
            total_supply = 0.0
            quantities = []

            # First pass: collect data and calculate totals
            valid_balances = []
            for balance in balances:
                try:
                    quantity = float(balance.get("quantity", 0))
                    address = balance.get("address", "")
                    if quantity > 0 and address:
                        quantities.append(quantity)
                        total_supply += quantity
                        valid_balances.append({"address": address, "quantity": quantity})
                except (ValueError, TypeError):
                    continue

            # Use valid holder count (not raw balance count)
            holder_count = len(valid_balances)

            logger.debug(f"Processed {len(balances)} raw balances, found {holder_count} valid holders with positive balance")

            holder_metrics: Dict[str, Any] = {
                "holder_count": holder_count,
                "total_supply": total_supply,
                "avg_holding": 0.0,
                "median_holding": 0.0,
                "gini_coefficient": 0.0,
            }

            # Only add holder cache data if we have valid holders
            if valid_balances:
                holder_metrics["holder_cache_data"] = valid_balances
                logger.debug(f"Generated holder cache data with {len(valid_balances)} valid holders")
            else:
                logger.debug("No valid holders found for holder cache data")

            if quantities:
                # Calculate basic statistics
                holder_metrics["avg_holding"] = float(total_supply / len(quantities))

                # Calculate median
                sorted_quantities = sorted(quantities)
                n = len(sorted_quantities)
                if n % 2 == 0:
                    holder_metrics["median_holding"] = float((sorted_quantities[n // 2 - 1] + sorted_quantities[n // 2]) / 2)
                else:
                    holder_metrics["median_holding"] = float(sorted_quantities[n // 2])

                # Calculate Gini coefficient (approximation)
                holder_metrics["gini_coefficient"] = self._calculate_gini_coefficient(sorted_quantities)

            return holder_metrics

        except Exception as e:
            logger.error(f"Error calculating holder metrics: {e}")
            return {}

    def _calculate_gini_coefficient(self, sorted_quantities: List[float]) -> float:
        """
        Calculate Gini coefficient for wealth distribution.

        Args:
            sorted_quantities: List of quantities sorted in ascending order

        Returns:
            Gini coefficient (0 = perfect equality, 1 = perfect inequality)
        """
        try:
            n = len(sorted_quantities)
            if n <= 1:
                return 0.0

            total = sum(sorted_quantities)
            if total == 0:
                return 0.0

            # Calculate Gini coefficient using the formula
            cumulative_sum = 0.0
            gini_sum = 0.0

            for i, quantity in enumerate(sorted_quantities):
                cumulative_sum += quantity
                gini_sum += (2 * (i + 1) - n - 1) * quantity

            gini_coefficient = gini_sum / (n * total)
            return max(0.0, min(1.0, gini_coefficient))  # Clamp between 0 and 1

        except Exception as e:
            logger.error(f"Error calculating Gini coefficient: {e}")
            return 0.0

    def _calculate_liquidity_score(self, market_data: Dict) -> float:
        """
        Calculate liquidity score based on dispensers and volume.

        Args:
            market_data: Dictionary with market data

        Returns:
            Liquidity score (0-10)
        """
        try:
            score = 0.0

            # Score based on open dispensers
            open_dispensers = market_data.get("open_dispensers_count") or 0
            if open_dispensers and open_dispensers > 0:
                score += min(3.0, open_dispensers * 0.5)  # Max 3 points

            # Score based on recent volume
            volume_24h = market_data.get("volume_24h_btc") or 0
            if volume_24h and volume_24h > 0:
                # Logarithmic scaling for volume
                import math

                volume_score = min(4.0, math.log10(volume_24h * 100000000 + 1) * 0.5)  # Max 4 points
                score += volume_score

            # Score based on holder count
            holder_count = market_data.get("holder_count") or 0
            if holder_count and holder_count > 0:
                import math

                holder_score = min(3.0, math.log10(holder_count + 1) * 1.5)  # Max 3 points
                score += holder_score

            return min(10.0, score)

        except Exception as e:
            logger.error(f"Error calculating liquidity score: {e}")
            return 0.0

    def _calculate_activity_score(self, market_data: Dict) -> float:
        """
        Calculate market activity score based on recent transactions.

        Args:
            market_data: Dictionary with market data

        Returns:
            Activity score (0-10)
        """
        try:
            score = 0.0

            # Score based on recent dispenses
            recent_dispenses = market_data.get("recent_dispenses_count") or 0
            if recent_dispenses and recent_dispenses > 0:
                import math

                dispense_score = min(5.0, math.log10(recent_dispenses + 1) * 2.0)  # Max 5 points
                score += dispense_score

            # Score based on volume ratio (24h vs 7d)
            volume_24h = market_data.get("volume_24h_btc") or 0
            volume_7d = market_data.get("volume_7d_btc") or 0

            if volume_7d and volume_7d > 0:
                volume_ratio = volume_24h / (volume_7d / 7)  # Daily average
                ratio_score = min(3.0, volume_ratio * 1.5)  # Max 3 points
                score += ratio_score

            # Score based on dispenser activity
            open_dispensers = market_data.get("open_dispensers_count") or 0
            total_dispensers = market_data.get("total_dispensers_count") or 0

            if total_dispensers and total_dispensers > 0:
                activity_ratio = open_dispensers / total_dispensers
                activity_score = min(2.0, activity_ratio * 2.0)  # Max 2 points
                score += activity_score

            return min(10.0, score)

        except Exception as e:
            logger.error(f"Error calculating activity score: {e}")
            return 0.0

    def _calculate_quality_score(self, market_data: Dict) -> float:
        """
        Calculate data quality score based on completeness and consistency.

        Args:
            market_data: Dictionary with market data

        Returns:
            Quality score (0-10)
        """
        try:
            score = 8.0  # Base score for Counterparty data

            # Check data completeness
            required_fields = ["floor_price_btc", "holder_count", "volume_24h_btc"]
            missing_fields = sum(1 for field in required_fields if market_data.get(field) is None)

            if missing_fields > 0:
                score -= missing_fields * 2.0  # Deduct 2 points per missing field

            # Bonus for rich data
            open_dispensers = market_data.get("open_dispensers_count") or 0
            if open_dispensers and open_dispensers > 0:
                score += 1.0

            volume_7d = market_data.get("volume_7d_btc") or 0
            if volume_7d and volume_7d > 0:
                score += 0.5

            gini_coeff = market_data.get("gini_coefficient") or 0
            if gini_coeff and gini_coeff > 0:
                score += 0.5

            return max(0.0, min(10.0, score))

        except Exception as e:
            logger.error(f"Error calculating quality score: {e}")
            return 5.0  # Default medium quality

    def _determine_confidence_level(self, market_data: Dict) -> str:
        """
        Determine confidence level based on data quality and completeness.

        Args:
            market_data: Dictionary with market data

        Returns:
            Confidence level string
        """
        try:
            quality_score = market_data.get("quality_score", 0)

            if quality_score >= 8.0:
                return "high"
            elif quality_score >= 6.0:
                return "medium"
            elif quality_score >= 4.0:
                return "low"
            else:
                return "very_low"

        except Exception as e:
            logger.error(f"Error determining confidence level: {e}")
            return "low"


# Global worker instance
stamp_worker = StampWorker()


def process_stamp_batch(cpids: List[str]) -> Dict[str, Optional[Dict]]:
    """
    Process a batch of stamps for market data.

    Args:
        cpids: List of Counterparty asset IDs

    Returns:
        Dictionary mapping CPIDs to their market data (or None if failed)
    """
    results = {}

    for cpid in cpids:
        try:
            market_data = stamp_worker.process_stamp_market_data(cpid)
            results[cpid] = market_data
        except Exception as e:
            logger.error(f"Error processing stamp {cpid}: {e}")
            results[cpid] = None

    return results


def get_stamp_market_data(cpid: str) -> Optional[Dict]:
    """
    Get market data for a single stamp.

    Args:
        cpid: Counterparty asset ID

    Returns:
        Market data dictionary or None if failed
    """
    return stamp_worker.process_stamp_market_data(cpid)
