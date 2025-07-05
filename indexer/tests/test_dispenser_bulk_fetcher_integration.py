"""
Integration tests for DispenserBulkFetcher

These tests make real API calls to the Counterparty API to validate:
- Bulk dispenser fetching works correctly
- Pagination handles large datasets
- Floor price calculations are accurate
- Cache behavior works as expected

Run with: poetry run pytest tests/test_dispenser_bulk_fetcher_integration.py -v -m integration
"""

import time
from unittest.mock import patch

import pytest

from index_core.dispenser_bulk_fetcher import DispenserBulkFetcher
from index_core.fetch_utils import fetch_xcp

# Mark all tests in this module as integration tests
pytestmark = pytest.mark.integration


@pytest.mark.integration
class TestDispenserBulkFetcherIntegration:
    """Integration tests for DispenserBulkFetcher that validate real API interactions"""

    @pytest.fixture
    def fetcher(self):
        """Create a fresh fetcher instance for each test"""
        return DispenserBulkFetcher()

    @pytest.fixture(autouse=True)
    def cleanup(self):
        """Cleanup between tests to ensure isolation"""
        yield
        # Reset any global state if needed

    def test_fetch_all_open_dispensers_real_api(self, fetcher):
        """Test fetching all open dispensers from real Counterparty API"""
        # This makes real API calls
        dispensers_by_cpid = fetcher.fetch_all_open_dispensers()

        # Verify we got some data
        assert isinstance(dispensers_by_cpid, dict)

        # Should have at least some dispensers (unless market is completely dead)
        # We'll be lenient here since this depends on live market conditions
        print(f"Fetched dispensers for {len(dispensers_by_cpid)} unique assets")

        # Verify structure of returned data
        if dispensers_by_cpid:
            # Pick a sample CPID
            sample_cpid = next(iter(dispensers_by_cpid))
            sample_dispensers = dispensers_by_cpid[sample_cpid]

            assert isinstance(sample_dispensers, list)
            if sample_dispensers:
                dispenser = sample_dispensers[0]
                assert isinstance(dispenser, dict)

                # Verify expected fields exist
                assert "asset" in dispenser
                assert "status" in dispenser
                assert dispenser["status"] == 0  # Should only be open dispensers
                assert "satoshirate" in dispenser

    def test_dispenser_cache_behavior(self, fetcher):
        """Test that caching works correctly across multiple calls"""
        # First call should fetch from API
        start_time = time.time()
        dispensers1, _ = fetcher.get_dispensers_for_cpid("A123456789", current_block=100)
        first_call_time = time.time() - start_time

        # Second call with same block should use cache
        start_time = time.time()
        dispensers2, _ = fetcher.get_dispensers_for_cpid("A123456789", current_block=100)
        second_call_time = time.time() - start_time

        # Second call should be much faster (cache hit)
        assert second_call_time < first_call_time

        # Results should be identical
        assert dispensers1 == dispensers2

    def test_cache_refresh_on_new_block(self, fetcher):
        """Test that cache refreshes when block height increases"""
        # First call at block 100
        dispensers1, refreshed1 = fetcher.get_dispensers_for_cpid("A123456789", current_block=100)
        assert refreshed1 is True  # First call should refresh

        # Second call at same block
        dispensers2, refreshed2 = fetcher.get_dispensers_for_cpid("A123456789", current_block=100)
        assert refreshed2 is False  # Should use cache

        # Third call at higher block
        dispensers3, refreshed3 = fetcher.get_dispensers_for_cpid("A123456789", current_block=101)
        assert refreshed3 is True  # Should refresh for new block

    def test_floor_price_calculation(self, fetcher):
        """Test floor price calculation with real dispenser data"""
        # Create test dispenser data
        test_dispensers = [
            {"status": 0, "satoshirate": 1000000},  # 0.01 BTC
            {"status": 0, "satoshirate": 500000},  # 0.005 BTC (floor)
            {"status": 0, "satoshirate": 2000000},  # 0.02 BTC
            {"status": 10, "satoshirate": 100000},  # Closed - should be ignored
        ]

        floor_price = fetcher.calculate_floor_price(test_dispensers)

        # Floor should be 0.005 BTC (500000 sats)
        expected_floor = 500000 / 100_000_000
        assert floor_price == expected_floor

    def test_floor_price_no_dispensers(self, fetcher):
        """Test floor price calculation with no dispensers"""
        floor_price = fetcher.calculate_floor_price([])
        assert floor_price is None

    def test_floor_price_only_closed_dispensers(self, fetcher):
        """Test floor price calculation with only closed dispensers"""
        closed_dispensers = [
            {"status": 10, "satoshirate": 1000000},  # Closed
            {"status": 10, "satoshirate": 500000},  # Closed
        ]

        floor_price = fetcher.calculate_floor_price(closed_dispensers)
        assert floor_price is None

    def test_get_all_cpids_with_dispensers(self, fetcher):
        """Test getting all CPIDs that have dispensers"""
        cpids = fetcher.get_all_cpids_with_dispensers(current_block=100)

        assert isinstance(cpids, list)

        # All entries should be strings (CPIDs)
        for cpid in cpids:
            assert isinstance(cpid, str)
            assert len(cpid) > 0

    def test_cache_stats(self, fetcher):
        """Test cache statistics tracking"""
        # Get initial stats
        stats = fetcher.get_cache_stats()

        assert isinstance(stats, dict)
        assert "last_fetch_block" in stats
        assert "last_fetch_time" in stats
        assert "unique_assets_cached" in stats
        assert "total_dispensers_cached" in stats
        assert "cache_age_seconds" in stats

        # Initially should be empty
        assert stats["last_fetch_block"] == 0
        assert stats["unique_assets_cached"] == 0
        assert stats["total_dispensers_cached"] == 0

        # After fetching, stats should update
        fetcher.get_dispensers_for_cpid("A123456789", current_block=100)

        updated_stats = fetcher.get_cache_stats()
        assert updated_stats["last_fetch_block"] == 100
        assert updated_stats["last_fetch_time"] > 0

    def test_pagination_handling(self, fetcher):
        """Test that pagination works correctly for large dispenser lists"""
        # This test verifies that the fetcher can handle multiple pages
        # We'll mock the response to simulate pagination

        original_fetch = fetch_xcp
        call_count = 0

        def mock_fetch_xcp(endpoint, params):
            nonlocal call_count
            call_count += 1

            if endpoint != "/dispensers":
                return original_fetch(endpoint, params)

            # Simulate pagination - return 2 pages then stop
            if call_count == 1:
                return {"result": [{"asset": "A123456789", "status": 0, "satoshirate": 1000000}], "next_cursor": "page2"}
            elif call_count == 2:
                return {
                    "result": [{"asset": "A987654321", "status": 0, "satoshirate": 2000000}],
                    "next_cursor": None,  # No more pages
                }
            else:
                return {"result": []}

        with patch("index_core.dispenser_bulk_fetcher.fetch_xcp", side_effect=mock_fetch_xcp):
            dispensers_by_cpid = fetcher.fetch_all_open_dispensers()

            # Should have gotten data from both pages
            assert len(dispensers_by_cpid) == 2
            assert "A123456789" in dispensers_by_cpid
            assert "A987654321" in dispensers_by_cpid
            assert call_count == 2  # Should have made 2 calls

    def test_error_handling_api_failure(self, fetcher):
        """Test graceful handling of API failures"""

        def mock_failing_fetch(endpoint, params):
            return None  # Simulate API failure

        with patch("index_core.dispenser_bulk_fetcher.fetch_xcp", side_effect=mock_failing_fetch):
            dispensers_by_cpid = fetcher.fetch_all_open_dispensers()

            # Should return empty dict on failure, not crash
            assert dispensers_by_cpid == {}

    def test_real_api_response_structure(self, fetcher):
        """Test that real API responses have expected structure"""
        # Make a single API call to verify response structure
        response = fetch_xcp("/dispensers", {"status": 0, "limit": 5})

        if response and "result" in response:
            dispensers = response["result"]

            if dispensers:  # Only test if we have data
                dispenser = dispensers[0]

                # Verify all expected fields are present
                required_fields = ["asset", "status", "satoshirate", "tx_hash"]
                for field in required_fields:
                    assert field in dispenser, f"Missing field: {field}"

                # Verify data types
                assert isinstance(dispenser["asset"], str)
                assert isinstance(dispenser["status"], int)
                assert isinstance(dispenser["satoshirate"], int)
                assert dispenser["status"] == 0  # Should only get open dispensers

    def test_performance_benchmarking(self, fetcher):
        """Test performance of bulk fetching vs individual calls"""
        # This test measures the performance benefit of bulk fetching

        # Time bulk fetch
        start_time = time.time()
        all_dispensers = fetcher.fetch_all_open_dispensers()
        bulk_fetch_time = time.time() - start_time

        print(f"Bulk fetch time: {bulk_fetch_time:.2f}s for {len(all_dispensers)} assets")

        # For comparison, time a few individual calls
        if all_dispensers:
            sample_cpids = list(all_dispensers.keys())[:5]  # Test 5 assets

            start_time = time.time()
            for cpid in sample_cpids:
                # Simulate individual API call
                response = fetch_xcp("/dispensers", {"asset": cpid, "limit": 100})
            individual_calls_time = time.time() - start_time

            print(f"Individual calls time for 5 assets: {individual_calls_time:.2f}s")

            # Extrapolate to full dataset
            estimated_individual_time = (individual_calls_time / 5) * len(all_dispensers)
            print(f"Estimated time for individual calls to all assets: {estimated_individual_time:.2f}s")

            # Bulk should be significantly faster
            if len(all_dispensers) > 10:  # Only assert if we have meaningful data
                speedup = estimated_individual_time / bulk_fetch_time
                print(f"Bulk fetch speedup: {speedup:.1f}x")
                assert speedup > 5  # Should be at least 5x faster
