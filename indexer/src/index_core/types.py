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
