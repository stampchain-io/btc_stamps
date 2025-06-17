"""Type definitions for the indexer."""

import json
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

# Deploy result type: (lim, max, dec)
DeployResult = Tuple[Optional[int], Optional[int], Optional[int]]
NO_DEPLOY: DeployResult = (None, None, None)

# SRC-101 deploy result type
SRC101DeployResult = Tuple[
    int,  # lim
    Optional[Any],  # pri
    int,  # mintstart
    int,  # mintend
    Optional[List[str]],  # rec
    Optional[Any],  # wla
    Optional[Any],  # imglp
    Optional[Any],  # imgf
    int,  # idua
]


# OpenStamp API response types for SRC-20 market data
class OpenStampTokenData:
    """Type definition for individual token data from OpenStamp API."""

    def __init__(self, data: Dict[str, Any]):
        self.token_id: int = data.get("tokenId", 0)
        self.name: str = data.get("name", "")  # This is the ticker symbol
        self.total_supply: int = data.get("totalSupply", 0)
        self.holders_count: int = data.get("holdersCount", 0)
        self.price: Decimal = Decimal(str(data.get("price", "0")))
        self.amount_24h: Decimal = Decimal(str(data.get("amount24", "0")))
        self.volume_24h: Decimal = Decimal(str(data.get("volume24", "0")))
        self.volume_24h_change: Decimal = Decimal(str(data.get("volume24Change", "0")))
        self.change_24h: Decimal = Decimal(str(data.get("change24", "0")))
        self.change_7d: Decimal = Decimal(str(data.get("change7d", "0")))

    def to_market_data_dict(self) -> Dict[str, Any]:
        """Convert to standardized market data dictionary format."""
        # Convert both price and volume from satoshis to BTC (1 BTC = 100,000,000 satoshis)
        # Verified with BMWK: volume24="118746583" satoshis = 1.18746583 BTC (matches expected ~1.1875)
        satoshis_to_btc = Decimal("100000000")

        return {
            "tick": self.name,
            "price_btc": self.price / satoshis_to_btc,  # Convert satoshis to BTC
            "volume_24h_btc": self.volume_24h / satoshis_to_btc,  # Convert satoshis to BTC
            "holder_count": self.holders_count,
            "circulating_supply": Decimal(str(self.total_supply)),
            "max_supply": Decimal(str(self.total_supply)),
            "price_change_24h_percent": self.change_24h * Decimal("100"),  # Convert to percentage
            "price_change_7d_percent": self.change_7d * Decimal("100"),  # Convert to percentage
            "volume_24h_change_percent": self.volume_24h_change * Decimal("100"),
            "primary_exchange": "openstamp",
            "exchange_sources": json.dumps(["openstamp"]),
            "data_quality_score": Decimal("8.0"),  # High quality for OpenStamp
            "confidence_level": Decimal("8.0"),
            "update_frequency_minutes": 5,  # More frequent for exchange data
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert to raw dictionary format."""
        return {
            "tokenId": self.token_id,
            "name": self.name,
            "totalSupply": self.total_supply,
            "holdersCount": self.holders_count,
            "price": str(self.price),
            "amount24": str(self.amount_24h),
            "volume24": str(self.volume_24h),
            "volume24Change": str(self.volume_24h_change),
            "change24": str(self.change_24h),
            "change7d": str(self.change_7d),
        }


class OpenStampApiResponse:
    """Type definition for complete OpenStamp API response."""

    def __init__(self, response_data: Dict[str, Any]):
        self.code: int = response_data.get("code", 0)
        self.tokens: List[OpenStampTokenData] = []

        data_list = response_data.get("data", [])
        if isinstance(data_list, list):
            self.tokens = [OpenStampTokenData(token_data) for token_data in data_list]

    def get_token_by_name(self, ticker: str) -> Optional[OpenStampTokenData]:
        """Get token data by ticker symbol."""
        ticker_upper = ticker.upper()
        for token in self.tokens:
            if token.name.upper() == ticker_upper:
                return token
        return None

    def get_all_tickers(self) -> List[str]:
        """Get list of all available ticker symbols."""
        return [token.name for token in self.tokens]

    def get_tokens_with_volume(self, min_volume: Decimal = Decimal("0")) -> List[OpenStampTokenData]:
        """Get tokens that have trading volume above threshold."""
        return [token for token in self.tokens if token.volume_24h > min_volume]


# StampScan API response types for SRC-20 market data
class StampScanTokenData:
    """Type definition for individual token data from StampScan API."""

    def __init__(self, data: Dict[str, Any]):
        self.tick: str = data.get("tick", "")
        self.floor_unit_price: Optional[float] = data.get("floor_unit_price")  # Already in BTC
        self.mcap: Optional[float] = data.get("mcap")  # Market cap in BTC
        self.sum_7d: Optional[float] = data.get("sum_7d")  # 7-day volume in BTC
        self.sum_3d: Optional[float] = data.get("sum_3d")  # 3-day volume in BTC
        self.sum_1d: Optional[float] = data.get("sum_1d")  # 1-day volume in BTC
        self.stamp_url: Optional[str] = data.get("stamp_url")
        self.tx_hash: Optional[str] = data.get("tx_hash")  # Latest transaction hash
        self.holder_count: Optional[int] = data.get("holder_count")

    def to_market_data_dict(self) -> Dict[str, Any]:
        """Convert to standardized market data dictionary format."""
        return {
            "tick": self.tick,
            "price_btc": self.floor_unit_price,  # Already in BTC format
            "volume_24h_btc": self.sum_1d,  # Use 1-day volume as 24h approximation
            "market_cap_btc": self.mcap,
            "holder_count": self.holder_count,
            "latest_tx_hash": self.tx_hash,
            "primary_exchange": "stampscan",
            "exchange_sources": json.dumps(["stampscan"]),
            "data_quality_score": self._calculate_quality_score(),
            "confidence_level": self._calculate_confidence_level(),
            "update_frequency_minutes": 5,
        }

    def _calculate_quality_score(self) -> float:
        """Calculate data quality score based on available fields."""
        score = 6.0  # Base score for StampScan
        if self.floor_unit_price is not None:
            score += 2.0
        if self.mcap is not None:
            score += 1.0
        if self.holder_count is not None:
            score += 1.0
        if self.sum_1d is not None:
            score += 1.0
        return min(10.0, score)

    def _calculate_confidence_level(self) -> float:
        """Calculate confidence level based on data quality and holder count."""
        quality_score = self._calculate_quality_score()
        holder_count = self.holder_count or 0

        if quality_score >= 8.0 and holder_count > 1000:
            return 8.0  # High confidence
        elif quality_score >= 6.0 and holder_count > 100:
            return 7.0  # Medium-high confidence
        elif quality_score >= 4.0:
            return 6.0  # Medium confidence
        else:
            return 4.0  # Low confidence

    def to_dict(self) -> Dict[str, Any]:
        """Convert to raw dictionary format."""
        return {
            "tick": self.tick,
            "floor_unit_price": self.floor_unit_price,
            "mcap": self.mcap,
            "sum_7d": self.sum_7d,
            "sum_3d": self.sum_3d,
            "sum_1d": self.sum_1d,
            "stamp_url": self.stamp_url,
            "tx_hash": self.tx_hash,
            "holder_count": self.holder_count,
        }


class StampScanApiResponse:
    """Type definition for complete StampScan API response."""

    def __init__(self, response_data):
        self.tokens: List[StampScanTokenData] = []

        # Handle both single token dict and list of tokens
        if isinstance(response_data, dict):
            self.tokens = [StampScanTokenData(response_data)]
        elif isinstance(response_data, list):
            self.tokens = [StampScanTokenData(token_data) for token_data in response_data]

    def get_token_by_tick(self, tick: str) -> Optional[StampScanTokenData]:
        """Get token data by ticker symbol."""
        tick_upper = tick.upper()
        for token in self.tokens:
            if token.tick.upper() == tick_upper:
                return token
        return None

    def get_all_ticks(self) -> List[str]:
        """Get list of all available ticker symbols."""
        return [token.tick for token in self.tokens]
