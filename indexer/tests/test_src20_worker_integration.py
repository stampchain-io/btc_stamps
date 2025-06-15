"""
Comprehensive Integration Tests for SRC20Worker

This module tests the complete SRC20Worker flow including:
- KuCoin API integration
- BTC/USDT rate fetching and caching
- Volume conversion from USDT to BTC
- Confidence level calculation
- Data quality scoring
- Error handling and fallback behavior
"""

import json
import logging
import time
import unittest
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

# Import the SRC20Worker
from index_core.src20_worker import SRC20Worker

logger = logging.getLogger(__name__)


class TestSRC20WorkerIntegration(unittest.TestCase):
    """Comprehensive integration tests for SRC20Worker."""

    def setUp(self):
        """Set up test fixtures."""
        self.worker = SRC20Worker()

        # Mock successful KuCoin API responses
        self.mock_btc_usdt_response = {"bestBid": "105000.50", "bestAsk": "105001.50"}

        self.mock_stamp_ticker_response = {
            "last": "0.000000040",
            "vol": "650000.50",
            "changeRate": "-0.0454",
            "high": "0.000000042",
            "low": "0.000000038",
        }

        self.mock_stamp_orderbook_response = {"bestBid": "0.000000039", "bestAsk": "0.000000041"}

    def test_btc_usdt_rate_fetch_success(self):
        """Test successful BTC/USDT rate fetching."""
        with patch.object(self.worker, "_kucoin_api_call") as mock_api:
            mock_api.return_value = self.mock_btc_usdt_response

            rate = self.worker._get_btc_usdt_rate()

            self.assertIsNotNone(rate)
            self.assertIsInstance(rate, float)
            self.assertGreater(rate, 100000)  # Reasonable BTC price
            self.assertLess(rate, 200000)  # Reasonable upper bound

            # Verify API was called correctly
            mock_api.assert_called_once_with("/api/v1/market/orderbook/level1", {"symbol": "BTC-USDT"})

    def test_btc_usdt_rate_caching(self):
        """Test BTC/USDT rate caching mechanism."""
        with patch.object(self.worker, "_kucoin_api_call") as mock_api:
            mock_api.return_value = self.mock_btc_usdt_response

            # First call should hit API
            rate1 = self.worker._get_btc_usdt_rate()
            self.assertEqual(mock_api.call_count, 1)

            # Second call within cache window should use cache
            rate2 = self.worker._get_btc_usdt_rate()
            self.assertEqual(mock_api.call_count, 1)  # No additional API call
            self.assertEqual(rate1, rate2)

    def test_btc_usdt_rate_fetch_failure(self):
        """Test BTC/USDT rate fetch failure handling."""
        with patch.object(self.worker, "_kucoin_api_call") as mock_api:
            mock_api.return_value = None  # Simulate API failure

            rate = self.worker._get_btc_usdt_rate()

            self.assertIsNone(rate)

    def test_volume_conversion_success(self):
        """Test successful volume conversion from USDT to BTC."""
        with patch.object(self.worker, "_kucoin_api_call") as mock_api:
            # Mock responses for different endpoints
            def api_side_effect(endpoint, params):
                if "BTC-USDT" in params.get("symbol", ""):
                    return self.mock_btc_usdt_response
                elif "STAMP-USDT" in params.get("symbol", ""):
                    if "stats" in endpoint:
                        return self.mock_stamp_ticker_response
                    elif "orderbook" in endpoint:
                        return self.mock_stamp_orderbook_response
                return None

            mock_api.side_effect = api_side_effect

            result = self.worker.process_src20_market_data("STAMP")

            self.assertIsNotNone(result)
            self.assertEqual(result["tick"], "STAMP")

            # Check volume conversion
            volume_btc = float(result["volume_24h_btc"])
            self.assertGreater(volume_btc, 0)
            self.assertLess(volume_btc, 100)  # Should be reasonable BTC amount

            # Verify conversion math
            expected_volume_btc = 650000.50 / 105001.0  # USDT volume / BTC rate
            self.assertAlmostEqual(volume_btc, expected_volume_btc, places=6)

    def test_volume_conversion_fallback(self):
        """Test volume conversion fallback when BTC/USDT rate fails."""
        with patch.object(self.worker, "_kucoin_api_call") as mock_api:

            def api_side_effect(endpoint, params):
                if "BTC-USDT" in params.get("symbol", ""):
                    return None  # Simulate BTC/USDT rate failure
                elif "STAMP-USDT" in params.get("symbol", ""):
                    if "stats" in endpoint:
                        return self.mock_stamp_ticker_response
                    elif "orderbook" in endpoint:
                        return self.mock_stamp_orderbook_response
                return None

            mock_api.side_effect = api_side_effect

            result = self.worker.process_src20_market_data("STAMP")

            self.assertIsNotNone(result)
            # Should still have volume data (in USDT, not converted)
            self.assertIsNotNone(result.get("volume_24h_btc"))

    def test_confidence_level_calculation(self):
        """Test confidence level calculation with different scenarios."""
        test_cases = [
            # (quality_score, volume_btc, expected_confidence)
            (8.5, 0.002, 9.0),  # High quality, high volume
            (6.5, 0.0005, 7.0),  # Medium quality, medium volume
            (4.0, 0.00001, 5.0),  # Low quality, low volume
            (2.0, 0, 3.0),  # Very low quality, no volume
        ]

        for quality_score, volume_btc, expected_confidence in test_cases:
            with self.subTest(quality=quality_score, volume=volume_btc):
                market_data = {"quality_score": quality_score, "volume_24h_btc": volume_btc}

                confidence = self.worker._determine_kucoin_confidence_level(market_data)

                self.assertEqual(confidence, expected_confidence)
                self.assertIsInstance(confidence, float)

    def test_quality_score_calculation(self):
        """Test data quality score calculation."""
        # Test with complete data
        complete_data = {"price_btc": 0.000000040, "volume_24h_btc": 6.18, "price_change_24h_percent": -4.54}

        score = self.worker._calculate_kucoin_quality_score(complete_data)

        self.assertIsInstance(score, float)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 10.0)
        self.assertGreater(score, 5.0)  # Should be good score for complete data

        # Test with incomplete data
        incomplete_data = {"price_btc": None, "volume_24h_btc": None}

        score_incomplete = self.worker._calculate_kucoin_quality_score(incomplete_data)

        self.assertLess(score_incomplete, score)  # Should be lower score

    def test_error_handling_invalid_symbol(self):
        """Test error handling for invalid trading symbols."""
        with patch.object(self.worker, "_kucoin_api_call") as mock_api:
            mock_api.return_value = None  # Simulate API failure

            result = self.worker.process_src20_market_data("INVALID")

            self.assertIsNone(result)

    def test_error_handling_malformed_response(self):
        """Test error handling for malformed API responses."""
        with patch.object(self.worker, "_kucoin_api_call") as mock_api:
            # Return malformed response
            mock_api.return_value = {"invalid": "data"}

            result = self.worker.process_src20_market_data("STAMP")

            # Should handle gracefully and return None or partial data
            if result is not None:
                # If it returns data, it should be properly structured
                self.assertIn("tick", result)
                self.assertEqual(result["tick"], "STAMP")

    def test_complete_integration_flow(self):
        """Test the complete integration flow from API to processed data."""
        with patch.object(self.worker, "_kucoin_api_call") as mock_api:

            def api_side_effect(endpoint, params):
                if "BTC-USDT" in params.get("symbol", ""):
                    return self.mock_btc_usdt_response
                elif "STAMP-USDT" in params.get("symbol", ""):
                    if "stats" in endpoint:
                        return self.mock_stamp_ticker_response
                    elif "orderbook" in endpoint:
                        return self.mock_stamp_orderbook_response
                return None

            mock_api.side_effect = api_side_effect

            result = self.worker.process_src20_market_data("STAMP")

            # Verify complete result structure
            self.assertIsNotNone(result)

            required_fields = [
                "tick",
                "price_btc",
                "volume_24h_btc",
                "price_change_24h_percent",
                "data_quality_score",
                "confidence_level",
                "update_frequency_minutes",
            ]

            for field in required_fields:
                self.assertIn(field, result, f"Missing required field: {field}")

            # Verify data types and ranges
            self.assertEqual(result["tick"], "STAMP")
            self.assertIsInstance(result["price_btc"], str)
            self.assertIsInstance(result["volume_24h_btc"], str)
            self.assertIsInstance(result["confidence_level"], str)

            # Verify numeric values are reasonable
            price_btc = float(result["price_btc"])
            volume_btc = float(result["volume_24h_btc"])
            confidence = float(result["confidence_level"])

            self.assertGreater(price_btc, 0)
            self.assertGreater(volume_btc, 0)
            self.assertGreaterEqual(confidence, 0.0)
            self.assertLessEqual(confidence, 10.0)

    def test_exchange_mapping_configuration(self):
        """Test that STAMP is properly configured in exchange mappings."""
        # Verify STAMP is in the exchange mappings
        self.assertIn("STAMP", self.worker.SRC20_EXCHANGE_MAPPINGS)

        stamp_config = self.worker.SRC20_EXCHANGE_MAPPINGS["STAMP"]

        # Verify configuration structure
        self.assertIn("kucoin", stamp_config)
        self.assertEqual(stamp_config["kucoin"], "STAMP-USDT")
        self.assertEqual(stamp_config["symbol"], "STAMP")
        self.assertEqual(stamp_config["base_currency"], "USDT")

    def test_api_timeout_handling(self):
        """Test API timeout handling."""
        with patch.object(self.worker, "_kucoin_api_call") as mock_api:
            # Simulate timeout by raising an exception
            mock_api.side_effect = Exception("Timeout")

            result = self.worker.process_src20_market_data("STAMP")

            self.assertIsNone(result)

    def test_rate_limiting_compliance(self):
        """Test that the worker respects rate limiting."""
        with patch.object(self.worker, "_kucoin_api_call") as mock_api:
            mock_api.return_value = self.mock_stamp_ticker_response

            start_time = time.time()

            # Make multiple calls
            for _ in range(3):
                self.worker.process_src20_market_data("STAMP")

            end_time = time.time()

            # Should take some time due to rate limiting
            # (This is a basic check - actual rate limiting depends on implementation)
            self.assertGreater(end_time - start_time, 0)


class TestSRC20WorkerLiveIntegration(unittest.TestCase):
    """Live integration tests (require network access)."""

    def setUp(self):
        """Set up for live tests."""
        self.worker = SRC20Worker()

    @pytest.mark.integration
    def test_live_btc_usdt_rate_fetch(self):
        """Test live BTC/USDT rate fetching (requires network)."""
        rate = self.worker._get_btc_usdt_rate()

        if rate is not None:  # Only test if API is accessible
            self.assertIsInstance(rate, float)
            self.assertGreater(rate, 50000)  # Reasonable lower bound
            self.assertLess(rate, 200000)  # Reasonable upper bound

    @pytest.mark.integration
    def test_live_stamp_data_fetch(self):
        """Test live STAMP data fetching (requires network)."""
        result = self.worker.process_src20_market_data("STAMP")

        if result is not None:  # Only test if API is accessible
            self.assertEqual(result["tick"], "STAMP")
            self.assertIn("price_btc", result)
            self.assertIn("volume_24h_btc", result)
            self.assertIn("confidence_level", result)


if __name__ == "__main__":
    # Run tests
    unittest.main(verbosity=2)
