"""
Bulk dispenser fetcher for optimization.

Instead of making 49,177 individual API calls, this fetches ALL open
dispensers in ~50-100 paginated calls and caches them per block.
"""

import logging
import time
from typing import Dict, List, Optional, Tuple

from index_core.fetch_utils import fetch_xcp

logger = logging.getLogger(__name__)


class DispenserBulkFetcher:
    """Manages bulk fetching and caching of dispenser data"""

    def __init__(self):
        self.dispenser_cache: Dict[str, List[Dict]] = {}  # cpid -> dispensers
        self.last_fetch_block: int = 0
        self.last_fetch_time: float = 0
        self.total_dispensers_fetched: int = 0

    def should_refresh_cache(self, current_block: int) -> bool:
        """
        Determine if dispenser cache needs refresh

        Dispensers can only change when a new block is mined,
        so we only need to fetch once per block.
        """
        return current_block > self.last_fetch_block

    def should_fetch(self, current_time: float) -> bool:
        """
        Determine if we should fetch dispensers based on time

        We cache dispensers for 1 hour to reduce API calls
        """
        # First fetch or cache expired (1 hour)
        return self.last_fetch_time == 0 or (current_time - self.last_fetch_time) > 3600

    def fetch_all_open_dispensers(self) -> Dict[str, List[Dict]]:
        """
        Bulk fetch ALL open dispensers from Counterparty API

        Returns:
            Dict mapping cpid -> list of dispensers
        """
        logger.debug("Starting bulk dispenser fetch...")
        start_time = time.time()

        all_dispensers = []
        cursor = None
        page = 0

        try:
            while True:
                params = {
                    "status": 0,  # 0 = open/active dispensers only
                    "limit": 1000,
                    "verbose": "true",  # Get full dispenser details
                }

                if cursor:
                    params["cursor"] = cursor

                logger.debug(f"Fetching dispenser page {page + 1}...")
                response = fetch_xcp("/dispensers", params)

                if not response or "result" not in response:
                    logger.error("Failed to fetch dispensers")
                    break

                dispensers = response["result"]
                if not dispensers:
                    break

                all_dispensers.extend(dispensers)
                page += 1

                # Check for next page
                cursor = response.get("next_cursor")
                if not cursor:
                    break

                # Small delay to respect rate limits
                time.sleep(0.1)

            # Group by asset (cpid)
            dispensers_by_cpid: Dict[str, List[Dict]] = {}
            for dispenser in all_dispensers:
                cpid = dispenser.get("asset")
                if cpid:
                    if cpid not in dispensers_by_cpid:
                        dispensers_by_cpid[cpid] = []
                    dispensers_by_cpid[cpid].append(dispenser)

            elapsed = time.time() - start_time
            self.total_dispensers_fetched = len(all_dispensers)

            # Update cache and timestamp
            self.dispenser_cache = dispensers_by_cpid
            self.last_fetch_time = time.time()

            logger.debug(
                f"Bulk dispenser fetch complete: "
                f"{len(all_dispensers)} dispensers for "
                f"{len(dispensers_by_cpid)} unique assets in "
                f"{elapsed:.2f}s ({page} API calls)"
            )

            return dispensers_by_cpid

        except Exception as e:
            logger.error(f"Error during bulk dispenser fetch: {e}")
            return {}

    def get_dispensers_for_cpid(self, cpid: str, current_block: int) -> Tuple[List[Dict], bool]:
        """
        Get dispensers for a specific CPID from cache

        Args:
            cpid: Asset identifier
            current_block: Current block height

        Returns:
            Tuple of (dispensers list, was_cache_refreshed)
        """
        cache_refreshed = False

        # Check if we need to refresh cache
        if self.should_refresh_cache(current_block):
            logger.debug(f"Refreshing dispenser cache for block {current_block}")
            self.dispenser_cache = self.fetch_all_open_dispensers()
            self.last_fetch_block = current_block
            self.last_fetch_time = time.time()
            cache_refreshed = True

        # Return dispensers for this CPID (empty list if none)
        return self.dispenser_cache.get(cpid, []), cache_refreshed

    def get_all_cpids_with_dispensers(self, current_block: int) -> List[str]:
        """
        Get list of all CPIDs that have open dispensers

        Useful for updating activity levels in bulk.
        """
        if self.should_refresh_cache(current_block):
            self.dispenser_cache = self.fetch_all_open_dispensers()
            self.last_fetch_block = current_block
            self.last_fetch_time = time.time()

        return list(self.dispenser_cache.keys())

    def calculate_floor_price(self, dispensers: List[Dict]) -> Optional[float]:
        """
        Calculate floor price from list of dispensers

        Args:
            dispensers: List of dispenser dicts

        Returns:
            Lowest satoshi rate converted to BTC, or None
        """
        if not dispensers:
            return None

        # Get all satoshi rates from open dispensers
        satoshi_rates = []
        for dispenser in dispensers:
            if dispenser.get("status") == 0:  # Open
                rate = dispenser.get("satoshirate")
                if rate and rate > 0:
                    satoshi_rates.append(rate)

        if not satoshi_rates:
            return None

        # Floor price is the minimum rate
        floor_sats = min(satoshi_rates)
        floor_btc = floor_sats / 100_000_000  # Convert to BTC

        return floor_btc

    def get_cache_stats(self) -> Dict:
        """Get statistics about the dispenser cache"""
        return {
            "last_fetch_block": self.last_fetch_block,
            "last_fetch_time": self.last_fetch_time,
            "unique_assets_cached": len(self.dispenser_cache),
            "total_dispensers_cached": self.total_dispensers_fetched,
            "cache_age_seconds": time.time() - self.last_fetch_time if self.last_fetch_time else 0,
        }


# Global instance for reuse across the application
dispenser_bulk_fetcher = DispenserBulkFetcher()
