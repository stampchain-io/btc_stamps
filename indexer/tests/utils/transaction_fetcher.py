"""
Transaction data fetcher for integration testing.

This module provides utilities to fetch raw Bitcoin transaction data from public APIs
and cache it locally for repeatable integration testing. Addresses GitHub issue #278
by enabling tests with real transaction data without requiring a local Bitcoin node.
"""

import json
import logging
import time
from pathlib import Path
from typing import Dict, Optional

import requests

logger = logging.getLogger(__name__)

# Public API endpoints
BLOCKCYPHER_API_BASE = "https://api.blockcypher.com/v1/btc/main"
BLOCKSTREAM_API_BASE = "https://blockstream.info/api"

# Rate limiting
DEFAULT_RATE_LIMIT_DELAY = 1.0  # seconds between requests
MAX_RETRIES = 3

# Cache directory
CACHE_DIR = Path(__file__).parent.parent / "fixtures" / "transaction_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


class TransactionFetcher:
    """
    Fetches and caches Bitcoin transaction data from public APIs.
    """

    def __init__(self, cache_dir: Optional[Path] = None, rate_limit_delay: float = DEFAULT_RATE_LIMIT_DELAY):
        self.cache_dir = cache_dir or CACHE_DIR
        self.rate_limit_delay = rate_limit_delay
        self.last_request_time = 0

    def _wait_for_rate_limit(self):
        """Enforce rate limiting between API requests."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self.last_request_time = time.time()

    def _get_cache_path(self, tx_hash: str) -> Path:
        """Get the cache file path for a transaction hash."""
        return self.cache_dir / f"{tx_hash}.json"

    def _load_from_cache(self, tx_hash: str) -> Optional[Dict]:
        """Load transaction data from cache if available."""
        cache_path = self._get_cache_path(tx_hash)
        if cache_path.exists():
            try:
                with open(cache_path, "r") as f:
                    data = json.load(f)
                logger.debug(f"Loaded transaction {tx_hash} from cache")
                return data
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load cached data for {tx_hash}: {e}")
                # Remove corrupted cache file
                cache_path.unlink(missing_ok=True)
        return None

    def _save_to_cache(self, tx_hash: str, data: Dict):
        """Save transaction data to cache."""
        cache_path = self._get_cache_path(tx_hash)
        try:
            with open(cache_path, "w") as f:
                json.dump(data, f, indent=2, sort_keys=True)
            logger.debug(f"Cached transaction {tx_hash}")
        except IOError as e:
            logger.warning(f"Failed to cache transaction {tx_hash}: {e}")

    def _fetch_from_blockcypher(self, tx_hash: str) -> Optional[Dict]:
        """Fetch transaction data from BlockCypher API."""
        url = f"{BLOCKCYPHER_API_BASE}/txs/{tx_hash}?includeHex=true"

        for attempt in range(MAX_RETRIES):
            try:
                self._wait_for_rate_limit()
                response = requests.get(url, timeout=10)

                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"Fetched transaction {tx_hash} from BlockCypher")
                    return {
                        "source": "blockcypher",
                        "tx_hash": tx_hash,
                        "hex": data.get("hex"),
                        "block_hash": data.get("block_hash"),
                        "block_height": data.get("block_height"),
                        "confirmations": data.get("confirmations"),
                        "received": data.get("received"),
                        "fees": data.get("fees"),
                        "inputs": data.get("inputs", []),
                        "outputs": data.get("outputs", []),
                        "raw_data": data,
                    }
                elif response.status_code == 429:  # Rate limited
                    wait_time = 2**attempt
                    logger.warning(f"Rate limited by BlockCypher, waiting {wait_time}s")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.warning(f"BlockCypher API error {response.status_code} for {tx_hash}")

            except requests.RequestException as e:
                logger.warning(f"Request failed (attempt {attempt + 1}): {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2**attempt)

        return None

    def _fetch_from_blockstream(self, tx_hash: str) -> Optional[Dict]:
        """Fetch transaction data from Blockstream API as fallback."""
        url = f"{BLOCKSTREAM_API_BASE}/tx/{tx_hash}"
        hex_url = f"{BLOCKSTREAM_API_BASE}/tx/{tx_hash}/hex"

        for attempt in range(MAX_RETRIES):
            try:
                self._wait_for_rate_limit()

                # Get transaction details
                response = requests.get(url, timeout=10)
                if response.status_code != 200:
                    continue

                tx_data = response.json()

                # Get raw hex data
                self._wait_for_rate_limit()
                hex_response = requests.get(hex_url, timeout=10)
                if hex_response.status_code != 200:
                    continue

                hex_data = hex_response.text.strip()

                logger.info(f"Fetched transaction {tx_hash} from Blockstream")
                return {
                    "source": "blockstream",
                    "tx_hash": tx_hash,
                    "hex": hex_data,
                    "block_hash": tx_data.get("status", {}).get("block_hash"),
                    "block_height": tx_data.get("status", {}).get("block_height"),
                    "confirmations": tx_data.get("status", {}).get("confirmed"),
                    "fees": tx_data.get("fee"),
                    "inputs": tx_data.get("vin", []),
                    "outputs": tx_data.get("vout", []),
                    "raw_data": tx_data,
                }

            except requests.RequestException as e:
                logger.warning(f"Blockstream request failed (attempt {attempt + 1}): {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2**attempt)

        return None

    def fetch_transaction(self, tx_hash: str, force_refresh: bool = False) -> Optional[Dict]:
        """
        Fetch transaction data from public APIs with caching.

        Args:
            tx_hash: Bitcoin transaction hash
            force_refresh: If True, bypass cache and fetch fresh data

        Returns:
            Dictionary containing transaction data, or None if fetch failed
        """
        if not force_refresh:
            cached_data = self._load_from_cache(tx_hash)
            if cached_data:
                return cached_data

        # Try BlockCypher first
        data = self._fetch_from_blockcypher(tx_hash)

        # Fallback to Blockstream if BlockCypher fails
        if not data:
            logger.info(f"Falling back to Blockstream API for {tx_hash}")
            data = self._fetch_from_blockstream(tx_hash)

        if data:
            self._save_to_cache(tx_hash, data)
            return data
        else:
            logger.error(f"Failed to fetch transaction {tx_hash} from all APIs")
            return None

    def fetch_multiple_transactions(self, tx_hashes: list, force_refresh: bool = False) -> Dict[str, Optional[Dict]]:
        """
        Fetch multiple transactions with rate limiting.

        Args:
            tx_hashes: List of transaction hashes to fetch
            force_refresh: If True, bypass cache and fetch fresh data

        Returns:
            Dictionary mapping tx_hash -> transaction data (or None if failed)
        """
        results = {}
        total = len(tx_hashes)

        for i, tx_hash in enumerate(tx_hashes):
            logger.info(f"Fetching transaction {i + 1}/{total}: {tx_hash}")
            results[tx_hash] = self.fetch_transaction(tx_hash, force_refresh)

            # Small delay between transactions to be respectful to APIs
            if i < total - 1:
                time.sleep(0.5)

        return results

    def clear_cache(self):
        """Clear all cached transaction data."""
        if self.cache_dir.exists():
            for cache_file in self.cache_dir.glob("*.json"):
                cache_file.unlink()
            logger.info("Cleared transaction cache")


# Convenience functions for direct usage
def fetch_transaction(tx_hash: str, force_refresh: bool = False) -> Optional[Dict]:
    """Convenience function to fetch a single transaction."""
    fetcher = TransactionFetcher()
    return fetcher.fetch_transaction(tx_hash, force_refresh)


def fetch_multiple_transactions(tx_hashes: list, force_refresh: bool = False) -> Dict[str, Optional[Dict]]:
    """Convenience function to fetch multiple transactions."""
    fetcher = TransactionFetcher()
    return fetcher.fetch_multiple_transactions(tx_hashes, force_refresh)


if __name__ == "__main__":
    # Example usage for testing
    import sys

    if len(sys.argv) > 1:
        tx_hash = sys.argv[1]
        print(f"Fetching transaction: {tx_hash}")
        data = fetch_transaction(tx_hash)
        if data:
            print(f"Success! Data cached at: {CACHE_DIR / f'{tx_hash}.json'}")
            print(f"Block height: {data.get('block_height')}")
            print(f"Confirmations: {data.get('confirmations')}")
        else:
            print("Failed to fetch transaction")
    else:
        print("Usage: python transaction_fetcher.py <tx_hash>")
