"""
OpenStamp API Client for SRC-20 Market Data

This module provides a client for integrating with the OpenStamp API to fetch
SRC-20 token market data. It includes smart token discovery and handles the
dynamic nature of tokens being frequently added to the platform.
"""

import json
import logging
import os
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set

import requests

from index_core.fetch_utils import RateLimiter
from index_core.types import OpenStampApiResponse, OpenStampTokenData

logger = logging.getLogger(__name__)

# API Configuration
OPENSTAMP_BASE_URL = "https://openapi.openstamp.io/v1"
OPENSTAMP_MARKET_DATA_ENDPOINT = "/src20MarketData"
DEFAULT_TIMEOUT = 30
MAX_RETRIES = 3
RATE_LIMIT_CALLS_PER_SECOND = 2.0  # Conservative rate limiting

# Cache settings for token discovery
TOKEN_DISCOVERY_CACHE_TTL = 300  # 5 minutes
LAST_TOKEN_DISCOVERY: float = 0.0
CACHED_TOKEN_LIST: Set[str] = set()


class OpenStampApiError(Exception):
    """Custom exception for OpenStamp API errors."""

    pass


class OpenStampClient:
    """
    Client for interacting with the OpenStamp API.

    Provides methods for fetching SRC-20 token market data with smart token
    discovery that adapts to new tokens being added to the platform.
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the OpenStamp API client.

        Args:
            api_key: OpenStamp API key. If not provided, will be read from environment.
        """
        self.api_key = api_key or os.getenv("OPENSTAMP_API_KEY")
        if not self.api_key:
            raise ValueError("OpenStamp API key is required. Set OPENSTAMP_API_KEY environment variable.")

        self.base_url = OPENSTAMP_BASE_URL
        self.rate_limiter = RateLimiter(calls_per_second=RATE_LIMIT_CALLS_PER_SECOND)
        self.session = requests.Session()

        # Set default headers
        self.session.headers.update(
            {"Authorization": self.api_key, "Content-Type": "application/json", "User-Agent": "BitcoinStamps-Indexer/1.0"}
        )

        logger.debug("OpenStamp API client initialized")

    def fetch_all_market_data(self) -> OpenStampApiResponse:
        """
        Fetch market data for all available SRC-20 tokens.

        Returns:
            OpenStampApiResponse containing all token market data

        Raises:
            OpenStampApiError: If API request fails
        """
        try:
            # Apply rate limiting
            self.rate_limiter.acquire()

            url = f"{self.base_url}{OPENSTAMP_MARKET_DATA_ENDPOINT}"

            logger.debug(f"Fetching market data from OpenStamp API: {url}")

            response = self.session.get(url, timeout=DEFAULT_TIMEOUT)

            if response.status_code != 200:
                raise OpenStampApiError(f"OpenStamp API request failed with status {response.status_code}: {response.text}")

            response_data = response.json()

            if response_data.get("code") != 200:
                raise OpenStampApiError(f"OpenStamp API returned error code {response_data.get('code')}")

            api_response = OpenStampApiResponse(response_data)

            logger.debug(f"Successfully fetched market data for {len(api_response.tokens)} tokens from OpenStamp")

            # Update cached token list for discovery
            global CACHED_TOKEN_LIST, LAST_TOKEN_DISCOVERY
            CACHED_TOKEN_LIST = set(api_response.get_all_tickers())
            LAST_TOKEN_DISCOVERY = time.time()

            return api_response

        except requests.RequestException as e:
            logger.error(f"Network error fetching OpenStamp market data: {e}")
            raise OpenStampApiError(f"Network error: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response from OpenStamp API: {e}")
            raise OpenStampApiError(f"Invalid JSON response: {e}")
        except Exception as e:
            logger.error(f"Unexpected error fetching OpenStamp market data: {e}")
            raise OpenStampApiError(f"Unexpected error: {e}")

    def fetch_token_data(self, ticker: str) -> Optional[OpenStampTokenData]:
        """
        Fetch market data for a specific token.

        Args:
            ticker: Token ticker symbol (e.g., "PEPE", "STAMP")

        Returns:
            OpenStampTokenData for the token, or None if not found

        Raises:
            OpenStampApiError: If API request fails
        """
        try:
            # Fetch all data and filter for the specific token
            all_data = self.fetch_all_market_data()
            return all_data.get_token_by_name(ticker)

        except Exception as e:
            logger.error(f"Error fetching token data for {ticker}: {e}")
            raise

    def discover_new_tokens(self, known_tokens: Set[str]) -> Set[str]:
        """
        Discover newly added tokens by comparing against known tokens.

        Args:
            known_tokens: Set of already known token tickers

        Returns:
            Set of newly discovered token tickers

        Raises:
            OpenStampApiError: If API request fails
        """
        try:
            # Check if we need to refresh the discovery cache
            global CACHED_TOKEN_LIST, LAST_TOKEN_DISCOVERY
            current_time = time.time()

            if current_time - LAST_TOKEN_DISCOVERY > TOKEN_DISCOVERY_CACHE_TTL:
                logger.debug("Token discovery cache expired, fetching fresh data")
                api_response = self.fetch_all_market_data()
                current_tokens = set(api_response.get_all_tickers())
                # Update cache
                CACHED_TOKEN_LIST = current_tokens
                LAST_TOKEN_DISCOVERY = current_time
            else:
                logger.debug("Using cached token list for discovery")
                current_tokens = CACHED_TOKEN_LIST

            # Find new tokens
            new_tokens = current_tokens - known_tokens

            if new_tokens:
                logger.debug(f"Discovered {len(new_tokens)} new tokens: {', '.join(sorted(new_tokens))}")
            else:
                logger.debug("No new tokens discovered")

            return new_tokens

        except Exception as e:
            logger.error(f"Error discovering new tokens: {e}")
            raise

    def get_active_tokens(self, min_volume: Decimal = Decimal("0"), min_holders: int = 1) -> List[str]:
        """
        Get list of active tokens based on volume and holder criteria.

        Args:
            min_volume: Minimum 24h volume requirement
            min_holders: Minimum number of holders requirement

        Returns:
            List of active token tickers

        Raises:
            OpenStampApiError: If API request fails
        """
        try:
            all_data = self.fetch_all_market_data()

            active_tokens = []
            for token in all_data.tokens:
                if token.volume_24h >= min_volume and token.holders_count >= min_holders:
                    active_tokens.append(token.name)

            logger.info(f"Found {len(active_tokens)} active tokens (min_volume={min_volume}, min_holders={min_holders})")
            return active_tokens

        except Exception as e:
            logger.error(f"Error getting active tokens: {e}")
            raise

    def fetch_market_data_batch(self, tickers: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Fetch market data for a batch of tokens efficiently.

        Since OpenStamp API returns all tokens in one call, this method
        fetches all data once and filters for the requested tickers.

        Args:
            tickers: List of token ticker symbols

        Returns:
            Dictionary mapping ticker to market data dict

        Raises:
            OpenStampApiError: If API request fails
        """
        try:
            all_data = self.fetch_all_market_data()

            result = {}
            found_count = 0

            for ticker in tickers:
                token_data = all_data.get_token_by_name(ticker)
                if token_data:
                    result[ticker] = token_data.to_market_data_dict()
                    found_count += 1
                else:
                    logger.warning(f"Token {ticker} not found in OpenStamp data")

            logger.info(f"Fetched market data for {found_count}/{len(tickers)} requested tokens")
            return result

        except Exception as e:
            logger.error(f"Error fetching market data batch: {e}")
            raise

    def get_all_available_tokens(self) -> List[str]:
        """
        Get complete list of all available tokens on OpenStamp.

        Returns:
            List of all available token tickers

        Raises:
            OpenStampApiError: If API request fails
        """
        try:
            all_data = self.fetch_all_market_data()
            return all_data.get_all_tickers()

        except Exception as e:
            logger.error(f"Error getting all available tokens: {e}")
            raise

    def health_check(self) -> bool:
        """
        Perform a health check on the OpenStamp API.

        Returns:
            True if API is healthy, False otherwise
        """
        try:
            all_data = self.fetch_all_market_data()
            is_healthy = len(all_data.tokens) > 0

            if is_healthy:
                logger.info(f"OpenStamp API health check passed - {len(all_data.tokens)} tokens available")
            else:
                logger.warning("OpenStamp API health check failed - no tokens returned")

            return is_healthy

        except Exception as e:
            logger.error(f"OpenStamp API health check failed: {e}")
            return False


# Global client instance for easy access
_openstamp_client: Optional[OpenStampClient] = None


def get_openstamp_client() -> OpenStampClient:
    """
    Get the global OpenStamp API client instance.

    Returns:
        Initialized OpenStamp client
    """
    global _openstamp_client

    if _openstamp_client is None:
        _openstamp_client = OpenStampClient()

    return _openstamp_client


# Convenience functions for common operations
def fetch_all_src20_market_data() -> OpenStampApiResponse:
    """
    Convenience function to fetch all SRC-20 market data.

    Returns:
        OpenStampApiResponse containing all token data
    """
    client = get_openstamp_client()
    return client.fetch_all_market_data()


def fetch_src20_token_data(ticker: str) -> Optional[Dict[str, Any]]:
    """
    Convenience function to fetch market data for a specific SRC-20 token.

    Args:
        ticker: Token ticker symbol

    Returns:
        Market data dictionary or None if not found
    """
    client = get_openstamp_client()
    token_data = client.fetch_token_data(ticker)
    return token_data.to_market_data_dict() if token_data else None


def discover_new_src20_tokens(known_tokens: Set[str]) -> Set[str]:
    """
    Convenience function to discover new SRC-20 tokens.

    Args:
        known_tokens: Set of already known token tickers

    Returns:
        Set of newly discovered token tickers
    """
    client = get_openstamp_client()
    return client.discover_new_tokens(known_tokens)


def get_all_src20_tokens() -> List[str]:
    """
    Convenience function to get all available SRC-20 tokens.

    Returns:
        List of all available token tickers
    """
    client = get_openstamp_client()
    return client.get_all_available_tokens()


def check_openstamp_health() -> bool:
    """
    Convenience function to check OpenStamp API health.

    Returns:
        True if API is healthy, False otherwise
    """
    client = get_openstamp_client()
    return client.health_check()
