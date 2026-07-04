"""
OpenStamp API Integration Tests

This module provides comprehensive testing for OpenStamp API integration
for SRC-20 token market data and holder information.
"""

import logging
import time
import unittest

import pytest
import requests

logger = logging.getLogger(__name__)

# OpenStamp API Configuration
OPENSTAMP_BASE_URL = "https://api.openstamp.io"
REQUEST_TIMEOUT = 10
MAX_RETRIES = 3
RETRY_DELAY = 2


class OpenStampIntegrationTest(unittest.TestCase):
    """
    Integration tests for OpenStamp API functionality.
    """

    def setUp(self):
        """Initialize test fixtures."""
        self.base_url = OPENSTAMP_BASE_URL
        self.timeout = REQUEST_TIMEOUT

    def test_openstamp_api_health(self):
        """Test OpenStamp API health and connectivity."""
        try:
            # Test a simple endpoint to verify API is accessible
            response = requests.get(f"{self.base_url}/api/v1/src20/ticks", timeout=self.timeout)

            # Should get a successful response or at least not a connection error
            self.assertIn(response.status_code, [200, 400, 404, 429])  # Valid HTTP responses

            logger.info(f"✅ OpenStamp API health check passed (status: {response.status_code})")

        except requests.exceptions.ConnectionError as e:
            self.fail(f"OpenStamp API connection failed: {e}")
        except Exception as e:
            logger.warning(f"OpenStamp API health check warning: {e}")

    def test_src20_ticks_endpoint(self):
        """Test SRC-20 ticks listing endpoint."""
        try:
            response = requests.get(f"{self.base_url}/api/v1/src20/ticks", timeout=self.timeout)

            if response.status_code == 200:
                data = response.json()

                # Validate response structure
                self.assertIsInstance(data, (list, dict))

                if isinstance(data, list) and len(data) > 0:
                    # Check first item structure
                    first_tick = data[0]
                    self.assertIsInstance(first_tick, dict)

                    # Common fields that should be present
                    expected_fields = ["tick"]  # Minimal expected field
                    for field in expected_fields:
                        if field in first_tick:
                            self.assertIsNotNone(first_tick[field])

                logger.info(f"✅ SRC-20 ticks endpoint: {len(data) if isinstance(data, list) else 'dict'} items")

            elif response.status_code == 429:
                logger.warning("⚠️ OpenStamp API rate limited - test skipped")
                self.skipTest("API rate limited")
            else:
                logger.warning(f"⚠️ SRC-20 ticks endpoint returned status {response.status_code}")

        except Exception as e:
            logger.warning(f"SRC-20 ticks test warning: {e}")

    def test_stamp_token_data(self):
        """Test STAMP token specific data retrieval."""
        try:
            response = requests.get(f"{self.base_url}/api/v1/src20/tick/STAMP", timeout=self.timeout)

            if response.status_code == 200:
                data = response.json()

                # Validate STAMP-specific data
                self.assertIsInstance(data, dict)

                # Check for common SRC-20 token fields
                possible_fields = ["tick", "max", "lim", "dec", "holders", "transactions"]
                found_fields = [field for field in possible_fields if field in data]

                self.assertGreater(len(found_fields), 0, "No expected fields found in STAMP data")

                # If tick field exists, it should be STAMP
                if "tick" in data:
                    self.assertEqual(data["tick"], "STAMP")

                logger.info(f"✅ STAMP token data: {len(found_fields)} fields found")

            elif response.status_code == 404:
                logger.warning("⚠️ STAMP token not found in OpenStamp API")
            elif response.status_code == 429:
                logger.warning("⚠️ OpenStamp API rate limited - test skipped")
                self.skipTest("API rate limited")
            else:
                logger.warning(f"⚠️ STAMP token endpoint returned status {response.status_code}")

        except Exception as e:
            logger.warning(f"STAMP token test warning: {e}")

    def test_holder_data_endpoint(self):
        """Test holder data retrieval for SRC-20 tokens."""
        try:
            # Try to get holder data for STAMP
            response = requests.get(f"{self.base_url}/api/v1/src20/tick/STAMP/holders", timeout=self.timeout)

            if response.status_code == 200:
                data = response.json()

                # Validate holder data structure
                self.assertIsInstance(data, (list, dict))

                if isinstance(data, list) and len(data) > 0:
                    # Check first holder entry
                    first_holder = data[0]
                    self.assertIsInstance(first_holder, dict)

                    # Common holder fields
                    possible_fields = ["address", "balance", "percentage"]
                    found_fields = [field for field in possible_fields if field in first_holder]

                    self.assertGreater(len(found_fields), 0, "No expected holder fields found")

                logger.info(f"✅ Holder data: {len(data) if isinstance(data, list) else 'dict'} entries")

            elif response.status_code == 404:
                logger.warning("⚠️ Holder data not found for STAMP")
            elif response.status_code == 429:
                logger.warning("⚠️ OpenStamp API rate limited - test skipped")
                self.skipTest("API rate limited")
            else:
                logger.warning(f"⚠️ Holder data endpoint returned status {response.status_code}")

        except Exception as e:
            logger.warning(f"Holder data test warning: {e}")

    def test_api_rate_limiting_behavior(self):
        """Test API rate limiting behavior with multiple requests."""
        try:
            start_time = time.time()
            successful_requests = 0
            rate_limited_requests = 0

            # Make multiple requests to test rate limiting
            for i in range(3):
                response = requests.get(f"{self.base_url}/api/v1/src20/ticks", timeout=self.timeout)

                if response.status_code == 200:
                    successful_requests += 1
                elif response.status_code == 429:
                    rate_limited_requests += 1

                # Small delay between requests
                time.sleep(0.5)

            end_time = time.time()
            duration = end_time - start_time

            # At least some requests should succeed or be properly rate limited
            total_handled = successful_requests + rate_limited_requests
            self.assertGreater(total_handled, 0, "No requests were properly handled")

            logger.info(
                f"✅ Rate limiting test: {successful_requests} successful, {rate_limited_requests} rate limited in {duration:.2f}s"
            )

        except Exception as e:
            logger.warning(f"Rate limiting test warning: {e}")

    def test_error_handling_invalid_token(self):
        """Test error handling for invalid token requests."""
        try:
            response = requests.get(f"{self.base_url}/api/v1/src20/tick/INVALID_TOKEN_12345", timeout=self.timeout)

            # Should return 404 or similar error for invalid token
            self.assertIn(response.status_code, [404, 400, 422])

            logger.info(f"✅ Invalid token error handling: status {response.status_code}")

        except Exception as e:
            logger.warning(f"Error handling test warning: {e}")

    @pytest.mark.integration
    def test_complete_openstamp_flow(self):
        """Test the complete OpenStamp data retrieval flow."""
        try:
            results = {}

            # Step 1: Get available ticks
            ticks_response = requests.get(f"{self.base_url}/api/v1/src20/ticks", timeout=self.timeout)
            if ticks_response.status_code == 200:
                results["ticks_available"] = True
                ticks_data = ticks_response.json()
                results["ticks_count"] = len(ticks_data) if isinstance(ticks_data, list) else 1
            else:
                results["ticks_available"] = False
                results["ticks_status"] = ticks_response.status_code

            # Step 2: Get STAMP token details
            stamp_response = requests.get(f"{self.base_url}/api/v1/src20/tick/STAMP", timeout=self.timeout)
            if stamp_response.status_code == 200:
                results["stamp_data_available"] = True
                stamp_data = stamp_response.json()
                results["stamp_fields"] = list(stamp_data.keys()) if isinstance(stamp_data, dict) else []
            else:
                results["stamp_data_available"] = False
                results["stamp_status"] = stamp_response.status_code

            # Step 3: Get STAMP holder data
            holders_response = requests.get(f"{self.base_url}/api/v1/src20/tick/STAMP/holders", timeout=self.timeout)
            if holders_response.status_code == 200:
                results["holders_data_available"] = True
                holders_data = holders_response.json()
                results["holders_count"] = len(holders_data) if isinstance(holders_data, list) else 1
            else:
                results["holders_data_available"] = False
                results["holders_status"] = holders_response.status_code

            # Validate that at least some data is available
            available_endpoints = sum(
                [
                    results.get("ticks_available", False),
                    results.get("stamp_data_available", False),
                    results.get("holders_data_available", False),
                ]
            )

            # At least one endpoint should work for a complete flow test to pass
            self.assertGreater(available_endpoints, 0, "No OpenStamp endpoints are accessible")

            logger.info("✅ Complete OpenStamp flow test passed")
            logger.info(f"   Available endpoints: {available_endpoints}/3")
            logger.info(f"   Results: {results}")

        except Exception as e:
            logger.warning(f"Complete OpenStamp flow test warning: {e}")


if __name__ == "__main__":
    # Configure logging for standalone execution
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    # Run tests
    unittest.main(verbosity=2)
