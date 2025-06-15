"""
SRC-20 Processing Worker for Bitcoin Stamps Indexer

This module provides specialized worker functions for fetching and processing
SRC-20 token market data from exchange APIs, including KuCoin API for the STAMP
token and OpenStamp API for comprehensive SRC-20 market data.
"""

import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Set

import requests

from index_core.fetch_utils import RateLimiter
from index_core.openstamp_client import OpenStampApiError, get_openstamp_client
from index_core.src20_market_processor import SRC20MarketDataProcessor

logger = logging.getLogger(__name__)

# Rate limiting for exchange APIs
KUCOIN_RATE_LIMITER = RateLimiter(calls_per_second=1.0)
EXCHANGE_RATE_LIMITER = RateLimiter(calls_per_second=0.5)

# KuCoin API configuration
KUCOIN_BASE_URL = "https://api.kucoin.com"
KUCOIN_API_VERSION = "v1"

# SRC-20 token mappings for exchanges
SRC20_EXCHANGE_MAPPINGS = {
    "STAMP": {"kucoin": "STAMP-USDT", "symbol": "STAMP", "base_currency": "USDT"}
    # Future tokens can be added here
}

# Request timeouts and retry settings
REQUEST_TIMEOUT = 10
MAX_RETRIES = 3
RETRY_DELAY = 2


class SRC20Worker:
    """
    Worker class for processing SRC-20 token market data from exchange APIs.

    Initially focuses on KuCoin API for STAMP token with extensible design
    for additional exchanges and tokens.
    """

    # Class-level shared processor to avoid repeated initialization
    _shared_processor = None

    def __init__(self):
        if SRC20Worker._shared_processor is None:
            SRC20Worker._shared_processor = SRC20MarketDataProcessor()
        self.processor = SRC20Worker._shared_processor
        self.kucoin_rate_limiter = KUCOIN_RATE_LIMITER
        self.exchange_rate_limiter = EXCHANGE_RATE_LIMITER

    def process_src20_market_data(self, tick: str) -> Optional[Dict]:
        """
        Process complete market data for a single SRC-20 token.

        Args:
            tick: SRC-20 token ticker (e.g., "STAMP")

        Returns:
            Dictionary with processed market data or None if failed
        """
        try:
            logger.debug(f"Processing market data for SRC-20 token {tick}")
            start_time = time.time()

            # Fetch market data from ALL available sources
            source_data = {}

            # Fetch from KuCoin if we have exchange mapping for this token
            if tick in SRC20_EXCHANGE_MAPPINGS:
                token_config = SRC20_EXCHANGE_MAPPINGS[tick]
                if "kucoin" in token_config:
                    logger.debug(f"Fetching KuCoin data for {tick}")
                    kucoin_data = self._fetch_kucoin_data(tick, token_config)
                    if kucoin_data:
                        source_data["kucoin"] = kucoin_data
                        logger.debug(f"Successfully fetched KuCoin data for {tick}")

            # Always try OpenStamp API for all SRC-20 tokens
            logger.debug(f"Fetching OpenStamp data for {tick}")
            openstamp_data = self._fetch_openstamp_data(tick)
            if openstamp_data:
                source_data["openstamp"] = openstamp_data
                logger.debug(f"Successfully fetched OpenStamp data for {tick}")

            # TODO: Add StampScan and other exchanges here
            # if tick in SRC20_EXCHANGE_MAPPINGS and "stampscan" in SRC20_EXCHANGE_MAPPINGS[tick]:
            #     stampscan_data = self._fetch_stampscan_data(tick, token_config)
            #     if stampscan_data:
            #         source_data["stampscan"] = stampscan_data

            # Check if we got any data from any source
            if not source_data:
                logger.warning(f"Failed to fetch market data for {tick} from all sources")
                return None

            # Aggregate multi-source data
            logger.debug(f"Aggregating data from {len(source_data)} sources for {tick}: {list(source_data.keys())}")
            aggregated_data = self._aggregate_multi_source_data(tick, source_data)

            if aggregated_data:
                # Add processing metadata
                aggregated_data["processing_time_ms"] = int((time.time() - start_time) * 1000)
                aggregated_data["last_updated"] = datetime.now()
                aggregated_data["source_count"] = len(source_data)
                aggregated_data["sources"] = list(source_data.keys())

                # Validate the aggregated data
                validated_data = self.processor.validate_src20_market_data(aggregated_data)
                if validated_data:
                    logger.debug(f"Successfully processed aggregated market data for {tick}")

                    # Store individual source data for transparency
                    self._store_source_data(tick, source_data)

                    return validated_data
                else:
                    logger.warning(f"Market data validation failed for {tick}")
                    return None
            else:
                logger.warning(f"Failed to aggregate market data for {tick}")
                return None

        except Exception as e:
            logger.error(f"Error processing market data for {tick}: {e}")
            return None

    def _fetch_kucoin_data(self, tick: str, token_config: Dict) -> Optional[Dict]:
        """
        Fetch market data from KuCoin API.

        Args:
            tick: SRC-20 token ticker
            token_config: Token configuration with exchange mappings

        Returns:
            Dictionary with market data or None if failed
        """
        try:
            symbol = token_config["kucoin"]
            logger.debug(f"Fetching KuCoin data for {tick} (symbol: {symbol})")

            # Fetch ticker data (24h stats)
            ticker_data = self._kucoin_api_call(f"/api/{KUCOIN_API_VERSION}/market/stats", {"symbol": symbol})

            # Fetch order book for current price
            orderbook_data = self._kucoin_api_call(f"/api/{KUCOIN_API_VERSION}/market/orderbook/level1", {"symbol": symbol})

            # Fetch 24h klines for additional metrics
            klines_data = self._kucoin_api_call(
                f"/api/{KUCOIN_API_VERSION}/market/candles",
                {"symbol": symbol, "type": "1day", "startAt": int((datetime.now().timestamp() - 86400))},
            )

            # Process the raw data into market metrics
            market_data = self._process_kucoin_data(tick, ticker_data, orderbook_data, klines_data)

            if market_data:
                market_data["data_source"] = "kucoin"
                market_data["exchange_symbol"] = symbol

            return market_data

        except Exception as e:
            logger.error(f"Error fetching KuCoin data for {tick}: {e}")
            return None

    def _kucoin_api_call(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """
        Make a rate-limited API call to KuCoin.

        Args:
            endpoint: API endpoint path
            params: Query parameters

        Returns:
            API response data or None if failed
        """
        try:
            # Rate limiting
            self.kucoin_rate_limiter.acquire()

            url = f"{KUCOIN_BASE_URL}{endpoint}"

            for attempt in range(MAX_RETRIES):
                try:
                    logger.debug(f"KuCoin API call: {endpoint} (attempt {attempt + 1})")

                    response = requests.get(
                        url,
                        params=params,
                        timeout=REQUEST_TIMEOUT,
                        headers={"User-Agent": "BitcoinStamps-Indexer/1.0", "Accept": "application/json"},
                    )

                    response.raise_for_status()
                    data = response.json()

                    # Check KuCoin response format
                    if data.get("code") == "200000" and "data" in data:
                        return data["data"]
                    else:
                        logger.warning(f"KuCoin API error: {data.get('msg', 'Unknown error')}")
                        return None

                except requests.exceptions.RequestException as e:
                    logger.warning(f"KuCoin API request failed (attempt {attempt + 1}): {e}")
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(RETRY_DELAY * (attempt + 1))  # Exponential backoff
                    else:
                        raise

            return None

        except Exception as e:
            logger.error(f"Error in KuCoin API call: {e}")
            return None

    def _fetch_openstamp_data(self, tick: str) -> Optional[Dict]:
        """
        Fetch market data from OpenStamp API.

        Args:
            tick: SRC-20 token ticker

        Returns:
            Dictionary with market data or None if failed
        """
        try:
            logger.debug(f"Fetching OpenStamp data for {tick}")

            # Get OpenStamp client and fetch token data
            openstamp_client = get_openstamp_client()
            token_data = openstamp_client.fetch_token_data(tick)

            if token_data:
                market_data = token_data.to_market_data_dict()
                market_data["data_source"] = "openstamp"
                market_data["exchange_symbol"] = tick

                logger.debug(f"Successfully fetched OpenStamp data for {tick}")
                return market_data
            else:
                logger.debug(f"Token {tick} not found in OpenStamp data")
                return None

        except OpenStampApiError as e:
            logger.error(f"OpenStamp API error for {tick}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error fetching OpenStamp data for {tick}: {e}")
            return None

    def _process_kucoin_data(
        self, tick: str, ticker_data: Optional[Dict], orderbook_data: Optional[Dict], klines_data: Optional[List]
    ) -> Optional[Dict]:
        """
        Process raw KuCoin data into standardized market metrics.

        Args:
            tick: SRC-20 token ticker
            ticker_data: 24h ticker statistics
            orderbook_data: Current order book data
            klines_data: Historical kline data

        Returns:
            Dictionary with processed market data
        """
        try:
            market_data = {
                "tick": tick,
                "price_btc": None,
                "price_usd": None,
                "volume_24h_btc": None,
                "volume_24h_usd": None,
                "price_change_24h": None,
                "price_change_24h_percent": None,
                "high_24h_btc": None,
                "low_24h_btc": None,
                "market_cap_btc": None,
                "trading_pairs_count": 1,  # At least KuCoin
                "quality_score": 0.0,
                "confidence_level": "medium",
            }

            # Get BTC/USDT rate for volume conversion
            btc_usdt_rate = self._get_btc_usdt_rate()

            # If we can't get BTC/USDT rate, log warning but continue with USDT values
            if not btc_usdt_rate:
                logger.warning(f"Could not fetch BTC/USDT rate for {tick}, using USDT values without conversion")

            # Process ticker data (24h statistics)
            if ticker_data:
                # Price is in USDT, convert to BTC if rate available
                price_usdt = self._safe_float(ticker_data.get("last"))
                if price_usdt:
                    market_data["price_usd"] = price_usdt
                    if btc_usdt_rate:
                        market_data["price_btc"] = price_usdt / btc_usdt_rate
                    else:
                        # Store USDT price as BTC equivalent for now
                        market_data["price_btc"] = price_usdt

                # Volume is in USDT, convert to BTC if rate available
                volume_usdt = self._safe_float(ticker_data.get("vol"))
                if volume_usdt:
                    market_data["volume_24h_usd"] = volume_usdt
                    if btc_usdt_rate:
                        market_data["volume_24h_btc"] = volume_usdt / btc_usdt_rate
                    else:
                        # Store USDT volume as BTC equivalent for now
                        market_data["volume_24h_btc"] = volume_usdt

                # High/Low prices in USDT, convert to BTC if rate available
                high_usdt = self._safe_float(ticker_data.get("high"))
                low_usdt = self._safe_float(ticker_data.get("low"))
                if high_usdt:
                    if btc_usdt_rate:
                        market_data["high_24h_btc"] = high_usdt / btc_usdt_rate
                    else:
                        market_data["high_24h_btc"] = high_usdt
                if low_usdt:
                    if btc_usdt_rate:
                        market_data["low_24h_btc"] = low_usdt / btc_usdt_rate
                    else:
                        market_data["low_24h_btc"] = low_usdt

                # Calculate price change
                current_price_usdt = self._safe_float(ticker_data.get("last"))
                change_rate = self._safe_float(ticker_data.get("changeRate"))

                if current_price_usdt and change_rate:
                    market_data["price_change_24h_percent"] = change_rate * 100
                    price_change_usdt = current_price_usdt * change_rate
                    if btc_usdt_rate:
                        market_data["price_change_24h"] = price_change_usdt / btc_usdt_rate
                    else:
                        market_data["price_change_24h"] = price_change_usdt

            # Process order book data (current best prices)
            if orderbook_data:
                # Use best bid/ask if available, fallback to ticker price
                best_bid_usdt = self._safe_float(orderbook_data.get("bestBid"))
                best_ask_usdt = self._safe_float(orderbook_data.get("bestAsk"))

                if best_bid_usdt and best_ask_usdt:
                    # Use mid-price for more accurate current price
                    mid_price_usdt = (best_bid_usdt + best_ask_usdt) / 2
                    if btc_usdt_rate:
                        market_data["price_btc"] = mid_price_usdt / btc_usdt_rate
                    else:
                        market_data["price_btc"] = mid_price_usdt
                elif best_bid_usdt:
                    if btc_usdt_rate:
                        market_data["price_btc"] = best_bid_usdt / btc_usdt_rate
                    else:
                        market_data["price_btc"] = best_bid_usdt
                elif best_ask_usdt:
                    if btc_usdt_rate:
                        market_data["price_btc"] = best_ask_usdt / btc_usdt_rate
                    else:
                        market_data["price_btc"] = best_ask_usdt

            # Process klines data for additional metrics
            if klines_data and len(klines_data) > 0:
                # KuCoin klines format: [time, open, close, high, low, volume, turnover]
                latest_kline = klines_data[0]  # Most recent
                if len(latest_kline) >= 7:
                    kline_volume_usdt = self._safe_float(latest_kline[5])
                    if kline_volume_usdt:
                        if btc_usdt_rate:
                            market_data["volume_24h_btc"] = kline_volume_usdt / btc_usdt_rate
                        else:
                            market_data["volume_24h_btc"] = kline_volume_usdt

            # Calculate derived metrics
            market_data["quality_score"] = self._calculate_kucoin_quality_score(market_data)
            market_data["confidence_level"] = self._determine_kucoin_confidence_level(market_data)

            # TODO: Calculate market cap when we have supply data
            # market_data['market_cap_btc'] = price * circulating_supply

            return market_data

        except Exception as e:
            logger.error(f"Error processing KuCoin data for {tick}: {e}")
            return None

    def _get_btc_usdt_rate(self) -> Optional[float]:
        """
        Get current BTC/USDT exchange rate from KuCoin.

        Returns:
            BTC/USDT rate or None if fetch fails
        """
        try:
            # Use cached rate if available and fresh (< 5 minutes old)
            cache_key = "btc_usdt_rate"
            cached_rate = getattr(self, "_btc_usdt_cache", {})

            if cache_key in cached_rate and time.time() - cached_rate[cache_key]["timestamp"] < 300:  # 5 minutes
                return cached_rate[cache_key]["rate"]

            # Fetch fresh rate
            response = self._kucoin_api_call("/api/v1/market/orderbook/level1", {"symbol": "BTC-USDT"})

            if response:
                # KuCoin API returns data directly, not wrapped in code/data structure
                best_bid = self._safe_float(response.get("bestBid"))
                best_ask = self._safe_float(response.get("bestAsk"))

                if best_bid and best_ask:
                    rate = (best_bid + best_ask) / 2

                    # Cache the rate
                    if not hasattr(self, "_btc_usdt_cache"):
                        self._btc_usdt_cache = {}
                    self._btc_usdt_cache[cache_key] = {"rate": rate, "timestamp": time.time()}

                    logger.debug(f"Fetched BTC/USDT rate: {rate}")
                    return rate

            logger.warning("Failed to fetch BTC/USDT rate from KuCoin")
            return None

        except Exception as e:
            logger.error(f"Error fetching BTC/USDT rate: {e}")
            return None

    def _safe_float(self, value) -> Optional[float]:
        """
        Safely convert a value to float.

        Args:
            value: Value to convert

        Returns:
            Float value or None if conversion fails
        """
        try:
            if value is None or value == "":
                return None
            return float(value)
        except (ValueError, TypeError):
            return None

    def _calculate_kucoin_quality_score(self, market_data: Dict) -> float:
        """
        Calculate data quality score for KuCoin data.

        Args:
            market_data: Dictionary with market data

        Returns:
            Quality score (0-10)
        """
        try:
            score = 7.0  # Base score for KuCoin (reputable exchange)

            # Check data completeness
            required_fields = ["price_btc", "volume_24h_btc"]
            missing_fields = sum(1 for field in required_fields if market_data.get(field) is None)

            if missing_fields > 0:
                score -= missing_fields * 2.0  # Deduct 2 points per missing field

            # Bonus for additional data
            if market_data.get("price_change_24h_percent") is not None:
                score += 1.0

            if market_data.get("high_24h_btc") is not None and market_data.get("low_24h_btc") is not None:
                score += 1.0

            # Safe volume check
            volume_24h_btc = market_data.get("volume_24h_btc")
            if volume_24h_btc is not None and volume_24h_btc > 0:
                score += 1.0

            return max(0.0, min(10.0, score))

        except Exception as e:
            logger.error(f"Error calculating KuCoin quality score: {e}")
            return 5.0  # Default medium quality

    def _determine_kucoin_confidence_level(self, market_data: Dict) -> float:
        """
        Determine confidence level for KuCoin data.

        Args:
            market_data: Dictionary with market data

        Returns:
            Confidence level as float (0.0-10.0)
        """
        try:
            quality_score = market_data.get("quality_score", 0)
            volume_24h = market_data.get("volume_24h_btc", 0)

            # Handle None volume safely
            if volume_24h is None:
                volume_24h = 0

            # Higher confidence for higher volume (return numeric values)
            if quality_score >= 8.0 and volume_24h > 0.001:  # > 0.001 BTC volume
                return 9.0  # High confidence
            elif quality_score >= 6.0 and volume_24h > 0.0001:  # > 0.0001 BTC volume
                return 7.0  # Medium confidence
            elif quality_score >= 4.0:
                return 5.0  # Low confidence
            else:
                return 3.0  # Very low confidence

        except Exception as e:
            logger.error(f"Error determining KuCoin confidence level: {e}")
            return 5.0  # Default medium confidence

    def _create_placeholder_data(self, tick: str) -> Dict:
        """
        Create placeholder market data for tokens without exchange data.

        Args:
            tick: SRC-20 token ticker

        Returns:
            Dictionary with placeholder market data
        """
        return {
            "tick": tick,
            "price_btc": None,
            "price_usd": None,
            "volume_24h_btc": None,
            "volume_24h_usd": None,
            "price_change_24h": None,
            "price_change_24h_percent": None,
            "high_24h_btc": None,
            "low_24h_btc": None,
            "market_cap_btc": None,
            "trading_pairs_count": 0,
            "last_updated": datetime.now(),
            "data_source": "placeholder",
            "quality_score": 1.0,  # Low quality for placeholder
            "confidence_level": "very_low",
        }

    def discover_new_tokens(self, known_tokens: Set[str]) -> Set[str]:
        """
        Discover new SRC-20 tokens from OpenStamp API.

        Since OpenStamp returns all tokens in one call, this just compares
        the complete list against known tokens.

        Args:
            known_tokens: Set of already known token tickers

        Returns:
            Set of newly discovered token tickers
        """
        try:
            logger.debug(f"Discovering new tokens. Known tokens: {len(known_tokens)}")

            # Get all available tokens from OpenStamp
            all_openstamp_tokens = set(self.get_all_available_tokens())

            # Find new tokens
            new_tokens = all_openstamp_tokens - known_tokens

            if new_tokens:
                logger.info(
                    f"Discovered {len(new_tokens)} new SRC-20 tokens: {', '.join(sorted(list(new_tokens)[:10]))}{'...' if len(new_tokens) > 10 else ''}"
                )
            else:
                logger.debug("No new tokens discovered")

            return new_tokens

        except Exception as e:
            logger.error(f"Error discovering new tokens: {e}")
            return set()

    def get_all_available_tokens(self) -> List[str]:
        """
        Get all available SRC-20 tokens from OpenStamp API.

        Returns:
            List of all available token tickers
        """
        try:
            openstamp_client = get_openstamp_client()
            all_tokens = openstamp_client.get_all_available_tokens()

            logger.info(f"Retrieved {len(all_tokens)} total SRC-20 tokens from OpenStamp")
            return all_tokens

        except Exception as e:
            logger.error(f"Error getting all available tokens: {e}")
            return []

    def _aggregate_multi_source_data(self, tick: str, source_data: Dict[str, Dict]) -> Optional[Dict]:
        """
        Aggregate market data from multiple sources with confidence weighting.

        Args:
            tick: SRC-20 token ticker
            source_data: Dictionary mapping source names to their data

        Returns:
            Aggregated market data dictionary
        """
        try:
            # Source confidence weights (higher = more trusted)
            confidence_weights = {
                "kucoin": 9.0,  # High - real exchange data
                "openstamp": 8.0,  # High - comprehensive SRC-20 data
                "stampscan": 7.0,  # Medium-High - specialized Bitcoin stamps
                "placeholder": 1.0,  # Low - fallback data
            }

            aggregated = {
                "tick": tick,
                "price_btc": None,
                "price_usd": None,
                "volume_24h_btc": None,
                "volume_24h_usd": None,
                "holder_count": None,
                "market_cap_btc": None,
                "price_change_24h_percent": None,
                "price_change_7d_percent": None,
                "circulating_supply": None,
                "max_supply": None,
                "data_quality_score": 0.0,
                "confidence_level": 0.0,
                "primary_exchange": None,
                "exchange_sources": ",".join(source_data.keys()),
                "update_frequency_minutes": 5,
            }

            # Weighted aggregation for numeric fields
            price_values = []
            volume_values = []
            holder_counts = []
            quality_scores = []
            total_confidence = 0.0

            for source, data in source_data.items():
                weight = confidence_weights.get(source, 5.0)  # Default medium confidence
                total_confidence += weight

                # Collect price data with weights
                if data.get("price_btc") is not None:
                    price_values.append((float(data["price_btc"]), weight))

                # Collect volume data with weights
                if data.get("volume_24h_btc") is not None:
                    volume_values.append((float(data["volume_24h_btc"]), weight))

                # Collect holder counts (use highest confidence source)
                if data.get("holder_count") is not None:
                    holder_counts.append((int(data["holder_count"]), weight))

                # Collect quality scores
                if data.get("data_quality_score") is not None:
                    quality_scores.append((float(data["data_quality_score"]), weight))

            # Calculate weighted averages for prices
            if price_values:
                weighted_price = sum(price * weight for price, weight in price_values) / sum(
                    weight for _, weight in price_values
                )
                aggregated["price_btc"] = weighted_price

                # Set primary exchange to highest confidence source with price
                primary_source = max(
                    [
                        (source, confidence_weights.get(source, 5.0))
                        for source in source_data.keys()
                        if source_data[source].get("price_btc") is not None
                    ],
                    key=lambda x: x[1],
                    default=(None, 0),
                )[0]
                if primary_source:
                    aggregated["primary_exchange"] = primary_source

            # Sum volumes (different exchanges = additive volume)
            if volume_values:
                total_volume = sum(volume for volume, _ in volume_values)
                aggregated["volume_24h_btc"] = total_volume

            # Use highest confidence holder count
            if holder_counts:
                best_holder_data = max(holder_counts, key=lambda x: x[1])
                aggregated["holder_count"] = best_holder_data[0]

            # Calculate weighted quality score
            if quality_scores:
                weighted_quality = sum(score * weight for score, weight in quality_scores) / sum(
                    weight for _, weight in quality_scores
                )
                aggregated["data_quality_score"] = weighted_quality

            # Set confidence level based on source diversity and quality
            if total_confidence > 0:
                # Higher confidence for multiple high-quality sources
                source_diversity_bonus = min(len(source_data) * 0.5, 2.0)
                base_confidence = (total_confidence / len(source_data)) if source_data else 0
                aggregated["confidence_level"] = min(base_confidence + source_diversity_bonus, 10.0)

            # Copy other fields from highest confidence source
            best_source = max(source_data.keys(), key=lambda x: confidence_weights.get(x, 5.0))
            best_data = source_data[best_source]

            for field in [
                "price_usd",
                "volume_24h_usd",
                "market_cap_btc",
                "circulating_supply",
                "max_supply",
                "price_change_24h_percent",
                "price_change_7d_percent",
            ]:
                if field in best_data and best_data[field] is not None:
                    aggregated[field] = best_data[field]

            logger.debug(
                f"Aggregated data for {tick}: price_btc={aggregated.get('price_btc')}, "
                f"volume_24h_btc={aggregated.get('volume_24h_btc')}, "
                f"sources={aggregated['exchange_sources']}"
            )

            return aggregated

        except Exception as e:
            logger.error(f"Error aggregating multi-source data for {tick}: {e}")
            return None

    def _store_source_data(self, tick: str, source_data: Dict[str, Dict]) -> None:
        """
        Store individual source data in market_data_sources table for transparency.

        Args:
            tick: SRC-20 token ticker
            source_data: Dictionary mapping source names to their data
        """
        try:
            from index_core.database import insert_market_data_source

            # Get database connection
            db = self.processor.db_manager.get_long_running_connection()

            for source, data in source_data.items():
                # Calculate source confidence based on data quality
                confidence = self._calculate_source_confidence(source, data)

                # Store source data record
                source_record = {
                    "asset_type": "src20",
                    "asset_id": tick,
                    "source_name": source,
                    "price_btc": data.get("price_btc"),
                    "volume_24h_btc": data.get("volume_24h_btc"),
                    "holder_count": data.get("holder_count"),
                    "market_cap_btc": data.get("market_cap_btc"),
                    "source_confidence": confidence,
                    "api_response_time_ms": data.get("processing_time_ms", 0),
                    "last_updated": data.get("last_updated") or datetime.now(),
                    "success_rate_24h": 100.0,  # TODO: Track this over time
                    "consecutive_failures": 0,  # TODO: Track this over time
                    "last_success": datetime.now(),
                    "last_failure": None,
                }

                try:
                    insert_market_data_source(db, source_record)
                    logger.debug(f"Stored source data for {tick} from {source}")
                except Exception as e:
                    logger.warning(f"Failed to store source data for {tick} from {source}: {e}")

            db.close()

        except Exception as e:
            logger.error(f"Error storing source data for {tick}: {e}")

    def _calculate_source_confidence(self, source: str, data: Dict) -> float:
        """
        Calculate confidence score for a data source based on data quality.

        Args:
            source: Source name
            data: Source data dictionary

        Returns:
            Confidence score (0-10)
        """
        base_confidence = {"kucoin": 9.0, "openstamp": 8.0, "stampscan": 7.0, "placeholder": 1.0}.get(source, 5.0)

        # Adjust based on data completeness
        has_price = data.get("price_btc") is not None
        has_volume = data.get("volume_24h_btc") is not None
        has_holders = data.get("holder_count") is not None

        completeness_bonus = 0.0
        if has_price:
            completeness_bonus += 1.0
        if has_volume:
            completeness_bonus += 0.5
        if has_holders:
            completeness_bonus += 0.5

        return min(base_confidence + completeness_bonus, 10.0)

    def get_active_tokens(self, min_volume: float = 0.0, min_holders: int = 1) -> List[str]:
        """
        Get active SRC-20 tokens based on criteria.

        Args:
            min_volume: Minimum 24h volume requirement
            min_holders: Minimum number of holders requirement

        Returns:
            List of active token tickers
        """
        try:
            from decimal import Decimal

            openstamp_client = get_openstamp_client()
            active_tokens = openstamp_client.get_active_tokens(min_volume=Decimal(str(min_volume)), min_holders=min_holders)

            logger.info(f"Found {len(active_tokens)} active SRC-20 tokens")
            return active_tokens

        except Exception as e:
            logger.error(f"Error getting active tokens: {e}")
            return []


# Global worker instance
src20_worker = SRC20Worker()


def process_src20_batch(ticks: List[str]) -> Dict[str, Optional[Dict]]:
    """
    Process a batch of SRC-20 tokens for market data.

    Args:
        ticks: List of SRC-20 token tickers

    Returns:
        Dictionary mapping tickers to their market data (or None if failed)
    """
    results = {}

    for tick in ticks:
        try:
            market_data = src20_worker.process_src20_market_data(tick)
            results[tick] = market_data
        except Exception as e:
            logger.error(f"Error processing SRC-20 token {tick}: {e}")
            results[tick] = None

    return results


def get_src20_market_data(tick: str) -> Optional[Dict]:
    """
    Get market data for a single SRC-20 token.

    Args:
        tick: SRC-20 token ticker

    Returns:
        Market data dictionary or None if failed
    """
    return src20_worker.process_src20_market_data(tick)


def add_src20_exchange_mapping(tick: str, exchange: str, symbol: str, base_currency: str = "BTC"):
    """
    Add exchange mapping for a new SRC-20 token.

    Args:
        tick: SRC-20 token ticker
        exchange: Exchange name (e.g., "kucoin", "openstamp")
        symbol: Trading symbol on the exchange
        base_currency: Base currency for trading pair
    """
    if tick not in SRC20_EXCHANGE_MAPPINGS:
        SRC20_EXCHANGE_MAPPINGS[tick] = {"symbol": tick, "base_currency": base_currency}

    SRC20_EXCHANGE_MAPPINGS[tick][exchange] = symbol
    logger.info(f"Added exchange mapping: {tick} -> {exchange}:{symbol}")


def get_supported_src20_tokens() -> List[str]:
    """
    Get list of SRC-20 tokens with exchange mappings.

    Returns:
        List of supported token tickers
    """
    return list(SRC20_EXCHANGE_MAPPINGS.keys())


def discover_new_src20_tokens(known_tokens: Set[str]) -> Set[str]:
    """
    Discover new SRC-20 tokens using the global worker instance.

    Args:
        known_tokens: Set of already known token tickers

    Returns:
        Set of newly discovered token tickers
    """
    return src20_worker.discover_new_tokens(known_tokens)


def get_all_src20_tokens() -> List[str]:
    """
    Get all available SRC-20 tokens using the global worker instance.

    Returns:
        List of all available token tickers
    """
    return src20_worker.get_all_available_tokens()


def get_active_src20_tokens(min_volume: float = 0.0, min_holders: int = 1) -> List[str]:
    """
    Get active SRC-20 tokens using the global worker instance.

    Args:
        min_volume: Minimum 24h volume requirement
        min_holders: Minimum number of holders requirement

    Returns:
        List of active token tickers
    """
    return src20_worker.get_active_tokens(min_volume, min_holders)
