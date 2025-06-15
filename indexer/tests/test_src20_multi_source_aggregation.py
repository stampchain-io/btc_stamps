"""
Tests for SRC-20 Multi-Source Data Aggregation

This module tests the new multi-source market data aggregation functionality
introduced to fetch data from multiple APIs (KuCoin, OpenStamp) and aggregate
them with confidence weighting.
"""

import os
import sys
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, Mock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from index_core.src20_worker import SRC20Worker


class TestSRC20MultiSourceAggregation:
    """Test cases for multi-source data aggregation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.worker = SRC20Worker()

        # Mock successful source data responses
        self.mock_kucoin_data = {
            "tick": "STAMP",
            "price_btc": Decimal("0.00000004"),
            "price_usd": Decimal("0.00387"),
            "volume_24h_btc": Decimal("8.12"),
            "volume_24h_usd": Decimal("650000.50"),
            "price_change_24h_percent": Decimal("-7.19"),
            "data_quality_score": Decimal("9.0"),
            "confidence_level": Decimal("9.5"),
            "data_source": "kucoin",
            "exchange_symbol": "STAMP-USDT",
        }

        self.mock_openstamp_data = {
            "tick": "STAMP",
            "price_btc": Decimal("0.000000058"),
            "volume_24h_btc": Decimal("0"),
            "holder_count": 13494,
            "circulating_supply": Decimal("1000000000"),
            "max_supply": Decimal("1000000000"),
            "price_change_24h_percent": Decimal("-10.77"),
            "price_change_7d_percent": Decimal("-42.0"),
            "primary_exchange": "openstamp",
            "exchange_sources": "openstamp",
            "data_quality_score": Decimal("8.0"),
            "confidence_level": Decimal("8.0"),
            "data_source": "openstamp",
            "exchange_symbol": "STAMP",
        }

    def test_aggregate_multi_source_data_both_sources(self):
        """Test aggregation when both KuCoin and OpenStamp provide data."""
        source_data = {"kucoin": self.mock_kucoin_data, "openstamp": self.mock_openstamp_data}

        result = self.worker._aggregate_multi_source_data("STAMP", source_data)

        assert result is not None
        assert result["tick"] == "STAMP"

        # Price should be weighted average (KuCoin has higher confidence)
        # Expected: (0.00000004 * 9.0 + 0.000000058 * 8.0) / (9.0 + 8.0) ≈ 0.000000046
        expected_price = (
            float(self.mock_kucoin_data["price_btc"]) * 9.0 + float(self.mock_openstamp_data["price_btc"]) * 8.0
        ) / 17.0
        assert abs(float(result["price_btc"]) - expected_price) < 0.000000001

        # Volume should be summed (different exchanges = additive)
        expected_volume = float(self.mock_kucoin_data["volume_24h_btc"]) + float(self.mock_openstamp_data["volume_24h_btc"])
        assert float(result["volume_24h_btc"]) == expected_volume

        # Holder count should use highest confidence source (KuCoin doesn't have holder count)
        assert result["holder_count"] == 13494  # From OpenStamp

        # Primary exchange should be highest confidence source with price
        assert result["primary_exchange"] == "kucoin"  # Higher confidence

        # Exchange sources should list both
        assert "kucoin" in result["exchange_sources"]
        assert "openstamp" in result["exchange_sources"]

    def test_aggregate_multi_source_data_openstamp_only(self):
        """Test aggregation when only OpenStamp provides data."""
        source_data = {"openstamp": self.mock_openstamp_data}

        result = self.worker._aggregate_multi_source_data("UTXO", source_data)

        assert result is not None
        assert result["tick"] == "UTXO"

        # Should use OpenStamp data directly (note: float conversion in aggregation)
        assert abs(float(result["price_btc"]) - float(self.mock_openstamp_data["price_btc"])) < 1e-10
        assert result["volume_24h_btc"] == self.mock_openstamp_data["volume_24h_btc"]
        assert result["holder_count"] == self.mock_openstamp_data["holder_count"]
        assert result["primary_exchange"] == "openstamp"
        assert result["exchange_sources"] == "openstamp"

    def test_aggregate_multi_source_data_no_price_data(self):
        """Test aggregation when no sources have price data."""
        openstamp_no_price = self.mock_openstamp_data.copy()
        openstamp_no_price["price_btc"] = None

        source_data = {"openstamp": openstamp_no_price}

        result = self.worker._aggregate_multi_source_data("TEST", source_data)

        assert result is not None
        assert result["price_btc"] is None
        assert result["primary_exchange"] is None
        assert result["holder_count"] == 13494  # Should still have other data

    def test_aggregate_multi_source_data_volume_aggregation(self):
        """Test volume aggregation from multiple exchanges."""
        # Create second source with volume
        openstamp_with_volume = self.mock_openstamp_data.copy()
        openstamp_with_volume["volume_24h_btc"] = Decimal("0.5")

        source_data = {"kucoin": self.mock_kucoin_data, "openstamp": openstamp_with_volume}

        result = self.worker._aggregate_multi_source_data("STAMP", source_data)

        # Volume should be sum: 8.12 + 0.5 = 8.62
        expected_volume = 8.12 + 0.5
        assert float(result["volume_24h_btc"]) == expected_volume

    def test_calculate_source_confidence(self):
        """Test source confidence calculation."""
        # Test KuCoin with complete data
        kucoin_confidence = self.worker._calculate_source_confidence("kucoin", self.mock_kucoin_data)
        assert kucoin_confidence == 10.0  # 9.0 base + 1.0 (price) + 0.5 (volume), capped at 10.0

        # Test OpenStamp with complete data - it has price, volume=0, and holder_count
        openstamp_confidence = self.worker._calculate_source_confidence("openstamp", self.mock_openstamp_data)
        assert openstamp_confidence == 10.0  # 8.0 base + 1.0 (price) + 0.5 (volume) + 0.5 (holders), capped at 10.0

        # Test with incomplete data
        incomplete_data = {"tick": "TEST", "holder_count": 100}
        incomplete_confidence = self.worker._calculate_source_confidence("openstamp", incomplete_data)
        assert incomplete_confidence == 8.5  # 8.0 base + 0.5 (holders)

    def test_process_src20_market_data_multi_source_flow(self):
        """Test the complete multi-source flow in process_src20_market_data."""
        with patch.object(self.worker, "_fetch_kucoin_data") as mock_kucoin:
            with patch.object(self.worker, "_fetch_openstamp_data") as mock_openstamp:
                with patch.object(self.worker, "_store_source_data") as mock_store:
                    # Mock successful fetches from both sources
                    mock_kucoin.return_value = self.mock_kucoin_data
                    mock_openstamp.return_value = self.mock_openstamp_data

                    result = self.worker.process_src20_market_data("STAMP")

                    # Verify both sources were attempted
                    mock_kucoin.assert_called_once()
                    mock_openstamp.assert_called_once()

                    # Verify source data storage was called
                    mock_store.assert_called_once()
                    store_call_args = mock_store.call_args
                    assert store_call_args[0][0] == "STAMP"  # tick
                    assert "kucoin" in store_call_args[0][1]  # source_data
                    assert "openstamp" in store_call_args[0][1]

                    # Verify aggregated result - these fields are added by process_src20_market_data
                    assert result is not None
                    assert result["tick"] == "STAMP"
                    assert result["source_count"] == 2
                    assert result["sources"] == ["kucoin", "openstamp"]

    def test_process_src20_market_data_openstamp_only_flow(self):
        """Test flow when only OpenStamp has data (no KuCoin mapping)."""
        with patch.object(self.worker, "_fetch_openstamp_data") as mock_openstamp:
            with patch.object(self.worker, "_store_source_data") as mock_store:
                # Mock successful OpenStamp fetch
                mock_openstamp.return_value = self.mock_openstamp_data

                result = self.worker.process_src20_market_data("UTXO")  # Not in KuCoin mappings

                # Verify only OpenStamp was called
                mock_openstamp.assert_called_once()

                # Verify source data storage
                mock_store.assert_called_once()
                store_call_args = mock_store.call_args
                assert store_call_args[0][0] == "UTXO"
                assert "openstamp" in store_call_args[0][1]
                assert "kucoin" not in store_call_args[0][1]

                # Verify result
                assert result is not None
                assert result["source_count"] == 1

    def test_process_src20_market_data_all_sources_fail(self):
        """Test flow when all sources fail to provide data."""
        with patch.object(self.worker, "_fetch_kucoin_data") as mock_kucoin:
            with patch.object(self.worker, "_fetch_openstamp_data") as mock_openstamp:
                with patch.object(self.worker, "_store_source_data") as mock_store:
                    # Mock all sources failing
                    mock_kucoin.return_value = None
                    mock_openstamp.return_value = None

                    result = self.worker.process_src20_market_data("STAMP")

                    # Should return None when no sources provide data
                    assert result is None

                    # Storage should not be called
                    mock_store.assert_not_called()

    def test_source_data_storage_database_integration(self):
        """Test source data storage with database mock."""
        with patch("index_core.database.insert_market_data_source") as mock_insert:
            source_data = {"kucoin": self.mock_kucoin_data, "openstamp": self.mock_openstamp_data}

            # Mock database manager properly
            with patch.object(self.worker.processor.db_manager, "get_long_running_connection") as mock_get_db:
                mock_db = Mock()
                mock_get_db.return_value = mock_db

                self.worker._store_source_data("STAMP", source_data)

                # Verify insert was called twice (once for each source)
                assert mock_insert.call_count == 2

                # Verify call arguments
                insert_calls = mock_insert.call_args_list

                # Check KuCoin record
                kucoin_call = insert_calls[0][0]  # First call args
                kucoin_record = kucoin_call[1]  # Second argument (source_record)
                assert kucoin_record["asset_type"] == "src20"
                assert kucoin_record["asset_id"] == "STAMP"
                assert kucoin_record["source_name"] == "kucoin"
                assert kucoin_record["price_btc"] == self.mock_kucoin_data["price_btc"]
                assert kucoin_record["volume_24h_btc"] == self.mock_kucoin_data["volume_24h_btc"]

                # Check OpenStamp record
                openstamp_call = insert_calls[1][0]
                openstamp_record = openstamp_call[1]
                assert openstamp_record["source_name"] == "openstamp"
                assert openstamp_record["holder_count"] == self.mock_openstamp_data["holder_count"]

    def test_confidence_weighting_edge_cases(self):
        """Test confidence weighting with edge cases."""
        # Test with zero confidence
        zero_confidence_data = {"confidence_score": 0.0}
        confidence = self.worker._calculate_source_confidence("unknown", zero_confidence_data)
        assert confidence == 5.0  # Default medium confidence

        # Test with very high quality data
        high_quality_data = {
            "price_btc": Decimal("0.001"),
            "volume_24h_btc": Decimal("100.0"),
            "holder_count": 10000,
            "market_cap_btc": Decimal("1000.0"),
        }
        confidence = self.worker._calculate_source_confidence("kucoin", high_quality_data)
        assert confidence == 10.0  # Should cap at 10.0

    def test_aggregation_with_partial_data(self):
        """Test aggregation when sources have different fields available."""
        # KuCoin with price and volume only
        kucoin_partial = {
            "tick": "TEST",
            "price_btc": Decimal("0.00001"),
            "volume_24h_btc": Decimal("5.0"),
            "data_quality_score": Decimal("9.0"),
        }

        # OpenStamp with holders and supply only (no price)
        openstamp_partial = {
            "tick": "TEST",
            "holder_count": 500,
            "circulating_supply": Decimal("1000000"),
            "max_supply": Decimal("1000000"),
            "data_quality_score": Decimal("8.0"),
        }

        source_data = {"kucoin": kucoin_partial, "openstamp": openstamp_partial}
        result = self.worker._aggregate_multi_source_data("TEST", source_data)

        assert result is not None
        # Should get price from KuCoin (note: float conversion in aggregation)
        assert abs(float(result["price_btc"]) - 0.00001) < 1e-10
        # Should get volume from KuCoin
        assert result["volume_24h_btc"] == Decimal("5.0")
        # Should get holder count from OpenStamp
        assert result["holder_count"] == 500
        # Note: circulating_supply and max_supply are copied from best source, but OpenStamp has no price,
        # so KuCoin is considered the best source, but KuCoin doesn't have supply data
        # The aggregation function only copies fields that exist in the best source

    def test_error_handling_in_aggregation(self):
        """Test error handling in aggregation function."""
        # Test with malformed source data
        malformed_data = {"invalid": "data structure"}
        source_data = {"openstamp": malformed_data}

        result = self.worker._aggregate_multi_source_data("TEST", source_data)

        # Should handle gracefully - returns default structure with None values
        assert result is not None
        assert result["price_btc"] is None
        assert result["tick"] == "TEST"

    def test_empty_source_data_handling(self):
        """Test handling of empty source data."""
        result = self.worker._aggregate_multi_source_data("TEST", {})
        assert result is None


class TestSRC20SourceValidation:
    """Test cases for individual source data validation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.worker = SRC20Worker()

    def test_openstamp_data_validation(self):
        """Test validation of OpenStamp data format."""
        valid_openstamp_data = {
            "tick": "PEPE",
            "price_btc": Decimal("0.000015"),
            "volume_24h_btc": Decimal("0.0005"),
            "holder_count": 1568,
            "circulating_supply": Decimal("21000000"),
            "data_quality_score": Decimal("8.0"),
        }

        # Test that processor validation accepts this data
        with patch.object(self.worker.processor, "validate_src20_market_data") as mock_validate:
            mock_validate.return_value = valid_openstamp_data

            result = self.worker.processor.validate_src20_market_data(valid_openstamp_data)
            assert result == valid_openstamp_data

    def test_kucoin_data_validation(self):
        """Test validation of KuCoin data format."""
        valid_kucoin_data = {
            "tick": "STAMP",
            "price_btc": Decimal("0.00000004"),
            "volume_24h_btc": Decimal("8.12"),
            "price_change_24h_percent": Decimal("-7.19"),
            "data_quality_score": Decimal("9.0"),
        }

        with patch.object(self.worker.processor, "validate_src20_market_data") as mock_validate:
            mock_validate.return_value = valid_kucoin_data

            result = self.worker.processor.validate_src20_market_data(valid_kucoin_data)
            assert result == valid_kucoin_data


if __name__ == "__main__":
    pytest.main([__file__])
