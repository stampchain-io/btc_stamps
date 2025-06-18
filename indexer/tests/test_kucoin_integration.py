"""
KuCoin API Integration Tests

This module provides comprehensive testing for KuCoin API integration
for SRC-20 token market data, including STAMP token and BTC/USDT rate fetching.
"""

import logging
import time
import unittest

import pytest
import requests

# Mark all tests in this file as integration tests
pytestmark = pytest.mark.integration

logger = logging.getLogger(__name__)

# KuCoin API Configuration
KUCOIN_BASE_URL = "https://api.kucoin.com"
KUCOIN_API_VERSION = "v1"
REQUEST_TIMEOUT = 10
MAX_RETRIES = 3
RETRY_DELAY = 2


class KuCoinIntegrationTest(unittest.TestCase):
    """
    Integration tests for KuCoin API functionality.
    """

    def setUp(self):
        """Initialize test fixtures."""
        self.base_url = KUCOIN_BASE_URL
        self.timeout = REQUEST_TIMEOUT

    def test_kucoin_api_health(self):
        """Test KuCoin API health and connectivity."""
        try:
            response = requests.get(f"{self.base_url}/api/v1/timestamp", timeout=self.timeout)
            self.assertEqual(response.status_code, 200)

            data = response.json()
            self.assertIn("data", data)
            self.assertIsInstance(data["data"], int)

            logger.info("✅ KuCoin API health check passed")
        except Exception as e:
            self.fail(f"KuCoin API health check failed: {e}")

    def test_btc_usdt_ticker(self):
        """Test BTC/USDT ticker data retrieval."""
        try:
            response = requests.get(
                f"{self.base_url}/api/v1/market/orderbook/level1", params={"symbol": "BTC-USDT"}, timeout=self.timeout
            )
            self.assertEqual(response.status_code, 200)

            data = response.json()
            self.assertIn("data", data)

            ticker_data = data["data"]
            required_fields = ["bestBid", "bestAsk", "price", "size", "time"]

            for field in required_fields:
                self.assertIn(field, ticker_data, f"Missing field: {field}")

            # Validate data types and ranges
            best_bid = float(ticker_data["bestBid"])
            best_ask = float(ticker_data["bestAsk"])

            self.assertGreater(best_bid, 50000)  # Reasonable BTC price lower bound
            self.assertLess(best_bid, 200000)  # Reasonable BTC price upper bound
            self.assertGreater(best_ask, best_bid)  # Ask should be higher than bid

            logger.info(f"✅ BTC/USDT ticker: Bid={best_bid}, Ask={best_ask}")

        except Exception as e:
            self.fail(f"BTC/USDT ticker test failed: {e}")

    def test_stamp_usdt_ticker(self):
        """Test STAMP/USDT ticker data retrieval."""
        try:
            response = requests.get(
                f"{self.base_url}/api/v1/market/stats", params={"symbol": "STAMP-USDT"}, timeout=self.timeout
            )
            self.assertEqual(response.status_code, 200)

            data = response.json()
            self.assertIn("data", data)

            ticker_data = data["data"]
            required_fields = ["symbol", "last", "vol", "changeRate"]

            for field in required_fields:
                self.assertIn(field, ticker_data, f"Missing field: {field}")

            # Validate STAMP-specific data
            self.assertEqual(ticker_data["symbol"], "STAMP-USDT")

            last_price = float(ticker_data["last"])
            volume = float(ticker_data["vol"])

            self.assertGreater(last_price, 0)
            self.assertGreaterEqual(volume, 0)

            logger.info(f"✅ STAMP/USDT ticker: Price={last_price}, Volume={volume}")

        except Exception as e:
            self.fail(f"STAMP/USDT ticker test failed: {e}")

    def test_stamp_usdt_orderbook(self):
        """Test STAMP/USDT orderbook data retrieval."""
        try:
            response = requests.get(
                f"{self.base_url}/api/v1/market/orderbook/level1", params={"symbol": "STAMP-USDT"}, timeout=self.timeout
            )
            self.assertEqual(response.status_code, 200)

            data = response.json()
            self.assertIn("data", data)

            orderbook_data = data["data"]
            required_fields = ["bestBid", "bestAsk"]

            for field in required_fields:
                self.assertIn(field, orderbook_data, f"Missing field: {field}")

            best_bid = float(orderbook_data["bestBid"])
            best_ask = float(orderbook_data["bestAsk"])

            self.assertGreater(best_bid, 0)
            self.assertGreater(best_ask, 0)
            self.assertGreaterEqual(best_ask, best_bid)  # Ask >= Bid

            logger.info(f"✅ STAMP/USDT orderbook: Bid={best_bid}, Ask={best_ask}")

        except Exception as e:
            self.fail(f"STAMP/USDT orderbook test failed: {e}")

    def test_volume_conversion_calculation(self):
        """Test volume conversion from USDT to BTC calculation."""
        try:
            # Get BTC/USDT rate
            btc_response = requests.get(
                f"{self.base_url}/api/v1/market/orderbook/level1", params={"symbol": "BTC-USDT"}, timeout=self.timeout
            )
            self.assertEqual(btc_response.status_code, 200)
            btc_data = btc_response.json()["data"]

            # Get STAMP/USDT volume
            stamp_response = requests.get(
                f"{self.base_url}/api/v1/market/stats", params={"symbol": "STAMP-USDT"}, timeout=self.timeout
            )
            self.assertEqual(stamp_response.status_code, 200)
            stamp_data = stamp_response.json()["data"]

            # Calculate conversion
            btc_rate = (float(btc_data["bestBid"]) + float(btc_data["bestAsk"])) / 2
            volume_usdt = float(stamp_data["vol"])
            volume_btc = volume_usdt / btc_rate

            # Validate conversion
            self.assertGreater(btc_rate, 50000)
            self.assertGreaterEqual(volume_usdt, 0)
            self.assertGreaterEqual(volume_btc, 0)
            self.assertLess(volume_btc, volume_usdt)  # BTC volume should be much smaller

            logger.info(f"✅ Volume conversion: {volume_usdt} USDT = {volume_btc:.8f} BTC (rate: {btc_rate})")

        except Exception as e:
            self.fail(f"Volume conversion test failed: {e}")

    def test_api_rate_limiting(self):
        """Test API rate limiting behavior."""
        try:
            start_time = time.time()

            # Make multiple rapid requests
            for i in range(3):
                response = requests.get(
                    f"{self.base_url}/api/v1/market/stats", params={"symbol": "STAMP-USDT"}, timeout=self.timeout
                )
                self.assertEqual(response.status_code, 200)

                # Small delay between requests
                time.sleep(0.1)

            end_time = time.time()
            duration = end_time - start_time

            # Should complete within reasonable time (not be heavily rate limited)
            self.assertLess(duration, 10.0)

            logger.info(f"✅ Rate limiting test: 3 requests completed in {duration:.2f}s")

        except Exception as e:
            self.fail(f"Rate limiting test failed: {e}")

    def test_error_handling_invalid_symbol(self):
        """Test error handling for invalid trading symbols."""
        try:
            response = requests.get(
                f"{self.base_url}/api/v1/market/stats", params={"symbol": "INVALID-SYMBOL"}, timeout=self.timeout
            )

            # KuCoin should return an error for invalid symbols
            # The exact status code may vary, but it shouldn't be 200 with valid data
            if response.status_code == 200:
                data = response.json()
                # If status is 200, the data should indicate an error
                self.assertIn("code", data)
                self.assertNotEqual(data.get("code"), "200000")

            logger.info("✅ Invalid symbol error handling works correctly")

        except Exception as e:
            self.fail(f"Error handling test failed: {e}")

    @pytest.mark.integration
    def test_complete_market_data_flow(self):
        """Test the complete market data retrieval flow."""
        try:
            # Step 1: Get BTC/USDT rate
            btc_response = requests.get(
                f"{self.base_url}/api/v1/market/orderbook/level1", params={"symbol": "BTC-USDT"}, timeout=self.timeout
            )
            self.assertEqual(btc_response.status_code, 200)
            btc_data = btc_response.json()["data"]
            btc_rate = (float(btc_data["bestBid"]) + float(btc_data["bestAsk"])) / 2

            # Step 2: Get STAMP ticker data
            ticker_response = requests.get(
                f"{self.base_url}/api/v1/market/stats", params={"symbol": "STAMP-USDT"}, timeout=self.timeout
            )
            self.assertEqual(ticker_response.status_code, 200)
            ticker_data = ticker_response.json()["data"]

            # Step 3: Get STAMP orderbook data
            orderbook_response = requests.get(
                f"{self.base_url}/api/v1/market/orderbook/level1", params={"symbol": "STAMP-USDT"}, timeout=self.timeout
            )
            self.assertEqual(orderbook_response.status_code, 200)
            orderbook_data = orderbook_response.json()["data"]

            # Step 4: Process and validate complete market data
            market_data = {
                "tick": "STAMP",
                "price_usdt": float(ticker_data["last"]),
                "price_btc": float(ticker_data["last"]) / btc_rate,
                "volume_24h_usdt": float(ticker_data["vol"]),
                "volume_24h_btc": float(ticker_data["vol"]) / btc_rate,
                "price_change_24h_percent": float(ticker_data["changeRate"]) * 100,
                "best_bid": float(orderbook_data["bestBid"]),
                "best_ask": float(orderbook_data["bestAsk"]),
                "btc_usdt_rate": btc_rate,
            }

            # Validate complete market data structure
            required_fields = [
                "tick",
                "price_usdt",
                "price_btc",
                "volume_24h_usdt",
                "volume_24h_btc",
                "price_change_24h_percent",
                "best_bid",
                "best_ask",
            ]

            for field in required_fields:
                self.assertIn(field, market_data)
                self.assertIsNotNone(market_data[field])

            # Validate data relationships
            self.assertEqual(market_data["tick"], "STAMP")
            self.assertGreater(market_data["price_btc"], 0)
            self.assertGreater(market_data["volume_24h_btc"], 0)
            self.assertLess(market_data["volume_24h_btc"], market_data["volume_24h_usdt"])

            logger.info("✅ Complete market data flow test passed")
            logger.info(f"   STAMP Price: {market_data['price_btc']:.10f} BTC")
            logger.info(f"   24h Volume: {market_data['volume_24h_btc']:.6f} BTC")
            logger.info(f"   24h Change: {market_data['price_change_24h_percent']:.2f}%")

        except Exception as e:
            self.fail(f"Complete market data flow test failed: {e}")


if __name__ == "__main__":
    # Configure logging for standalone execution
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    # Run tests
    unittest.main(verbosity=2)
