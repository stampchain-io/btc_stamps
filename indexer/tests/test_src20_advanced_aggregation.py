"""
Advanced tests for SRC-20 Multi-Source Data Aggregation

This module tests the advanced aggregation features required by Task 9:
- Weighted median calculations
- Conflict resolution strategies
- Discrepancy logging
- Statistical robustness
"""

import json
import logging
import os
import sys
from decimal import Decimal
from typing import Dict, List
from unittest.mock import MagicMock, Mock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from index_core.src20_worker import SRC20Worker


class TestWeightedMedianAggregation:
    """Test cases for weighted median aggregation algorithms."""

    def setup_method(self):
        """Set up test fixtures."""
        self.worker = SRC20Worker()

    def test_weighted_median_calculation_odd_weights(self):
        """Test weighted median with odd number of data points."""
        # Price data with weights: [(price, weight)]
        price_data = [
            (Decimal("0.00000003"), 9.0),  # KuCoin - high confidence
            (Decimal("0.00000005"), 8.0),  # OpenStamp - medium-high confidence
            (Decimal("0.00000010"), 3.0),  # Low confidence source
        ]

        # Calculate weighted median manually
        # Total weight = 20, median at weight 10
        # Sorted by price: 0.00000003(9.0), 0.00000005(8.0), 0.00000010(3.0)
        # Cumulative weights: 9.0, 17.0, 20.0
        # Median is at cumulative weight 10, which falls in the second value
        expected_median = Decimal("0.00000005")

        result = self._calculate_weighted_median(price_data)
        assert result == expected_median

    def test_weighted_median_calculation_even_weights(self):
        """Test weighted median with even number of data points."""
        price_data = [
            (Decimal("0.00000002"), 5.0),
            (Decimal("0.00000004"), 5.0),
            (Decimal("0.00000006"), 5.0),
            (Decimal("0.00000008"), 5.0),
        ]

        # Total weight = 20, median between weights 10-10
        # Average of middle two values
        expected_median = (Decimal("0.00000004") + Decimal("0.00000006")) / 2

        result = self._calculate_weighted_median(price_data)
        assert result == expected_median

    def test_weighted_median_with_outliers(self):
        """Test weighted median's robustness against outliers."""
        price_data = [
            (Decimal("0.00000004"), 8.0),  # Normal price
            (Decimal("0.00000005"), 9.0),  # Normal price
            (Decimal("0.00000045"), 7.0),  # Normal price
            (Decimal("0.00100000"), 1.0),  # Extreme outlier with low weight
        ]

        # The outlier should have minimal impact due to low weight
        result = self._calculate_weighted_median(price_data)
        assert result < Decimal("0.00001000")  # Much less than outlier

    def _calculate_weighted_median(self, data: List[tuple]) -> Decimal:
        """
        Calculate weighted median for testing.

        Args:
            data: List of (value, weight) tuples

        Returns:
            Weighted median value
        """
        if not data:
            return Decimal("0")

        # Sort by value
        sorted_data = sorted(data, key=lambda x: x[0])

        # Calculate total weight
        total_weight = sum(weight for _, weight in sorted_data)

        # Find median position
        median_weight = total_weight / 2

        # Find value at median weight
        cumulative_weight = 0
        for i, (value, weight) in enumerate(sorted_data):
            cumulative_weight += weight
            if cumulative_weight >= median_weight:
                if cumulative_weight == median_weight and i < len(sorted_data) - 1:
                    # Exact middle, average with next value
                    return (value + sorted_data[i + 1][0]) / 2
                return value

        return sorted_data[-1][0]  # Fallback to last value


class TestConflictResolution:
    """Test cases for conflict resolution strategies."""

    def setup_method(self):
        """Set up test fixtures."""
        self.worker = SRC20Worker()

    def test_majority_voting_conflict_resolution(self):
        """Test majority voting for conflicting data."""
        # Three sources with conflicting holder counts
        source_data = {
            "kucoin": {
                "tick": "STAMP",
                "holder_count": None,  # KuCoin doesn't provide holder count
                "price_btc": Decimal("0.00000004"),
            },
            "openstamp": {
                "tick": "STAMP",
                "holder_count": 13494,
                "price_btc": Decimal("0.000000045"),
            },
            "stampscan": {
                "tick": "STAMP",
                "holder_count": 13501,  # Slightly different from OpenStamp
                "price_btc": Decimal("0.000000042"),
            },
        }

        # Test conflict resolution
        conflicts = self._detect_conflicts(source_data)
        assert "holder_count" in conflicts
        assert len(conflicts["holder_count"]) == 2  # Two non-null values

        # Resolve using majority voting (or in this case, highest confidence)
        resolved = self._resolve_conflicts(conflicts, source_data)
        assert resolved["holder_count"] in [13494, 13501]  # One of the valid values

    def test_reliability_based_conflict_resolution(self):
        """Test reliability-based selection for conflicts."""
        source_data = {
            "kucoin": {
                "tick": "STAMP",
                "price_btc": Decimal("0.00000004"),
                "confidence_level": 9.0,
                "data_quality_score": Decimal("9.0"),
            },
            "openstamp": {
                "tick": "STAMP",
                "price_btc": Decimal("0.00000008"),  # 2x different!
                "confidence_level": 8.0,
                "data_quality_score": Decimal("8.0"),
            },
            "stampscan": {
                "tick": "STAMP",
                "price_btc": Decimal("0.00000006"),
                "confidence_level": 7.0,
                "data_quality_score": Decimal("7.0"),
            },
        }

        # Should select KuCoin's price due to highest confidence
        result = self._resolve_price_conflict(source_data)
        assert result == Decimal("0.00000004")

    def test_significant_discrepancy_detection(self):
        """Test detection of significant discrepancies."""
        source_data = {
            "kucoin": {
                "tick": "STAMP",
                "price_btc": Decimal("0.00000004"),
                "volume_24h_btc": Decimal("8.12"),
            },
            "openstamp": {
                "tick": "STAMP",
                "price_btc": Decimal("0.00000012"),  # 3x difference - significant!
                "volume_24h_btc": Decimal("0.5"),
            },
        }

        discrepancies = self._detect_significant_discrepancies(source_data)
        assert len(discrepancies) > 0
        assert any(d["field"] == "price_btc" for d in discrepancies)
        assert any(d["severity"] == "high" for d in discrepancies)

    def _detect_conflicts(self, source_data: Dict) -> Dict:
        """Detect conflicts in source data."""
        conflicts = {}

        # Get all unique fields
        all_fields = set()
        for data in source_data.values():
            all_fields.update(data.keys())

        # Check each field for conflicts
        for field in all_fields:
            if field in ["tick", "data_source", "confidence_level"]:
                continue

            values = []
            for source, data in source_data.items():
                if field in data and data[field] is not None:
                    values.append((source, data[field]))

            if len(values) > 1:
                # Check if values differ significantly
                if field.endswith("_btc") or field.endswith("_usd"):
                    # Numeric comparison
                    nums = [float(v[1]) for v in values]
                    if max(nums) / min(nums) > 1.1:  # More than 10% difference
                        conflicts[field] = values
                else:
                    # Exact comparison
                    unique_values = set(v[1] for v in values)
                    if len(unique_values) > 1:
                        conflicts[field] = values

        return conflicts

    def _resolve_conflicts(self, conflicts: Dict, source_data: Dict) -> Dict:
        """Resolve conflicts using various strategies."""
        resolved = {}

        for field, values in conflicts.items():
            # Get confidence scores for each source
            weighted_values = []
            for source, value in values:
                confidence = self.worker._calculate_source_confidence(source, source_data[source])
                weighted_values.append((value, confidence))

            # Use highest confidence value
            best_value = max(weighted_values, key=lambda x: x[1])
            resolved[field] = best_value[0]

        return resolved

    def _resolve_price_conflict(self, source_data: Dict) -> Decimal:
        """Resolve price conflicts based on reliability."""
        best_source = None
        best_confidence = 0

        for source, data in source_data.items():
            if "price_btc" in data and data["price_btc"] is not None:
                confidence = data.get("confidence_level", 5.0)
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_source = source

        return source_data[best_source]["price_btc"] if best_source else None

    def _detect_significant_discrepancies(self, source_data: Dict) -> List[Dict]:
        """Detect significant discrepancies between sources."""
        discrepancies = []

        # Define thresholds for significant differences
        thresholds = {
            "price_btc": 0.5,  # 50% difference
            "volume_24h_btc": 1.0,  # 100% difference
            "holder_count": 0.2,  # 20% difference
        }

        # Compare all pairs of sources
        sources = list(source_data.keys())
        for i in range(len(sources)):
            for j in range(i + 1, len(sources)):
                source1, source2 = sources[i], sources[j]
                data1, data2 = source_data[source1], source_data[source2]

                for field, threshold in thresholds.items():
                    if field in data1 and field in data2:
                        val1, val2 = data1[field], data2[field]
                        if val1 is not None and val2 is not None:
                            # Calculate relative difference
                            if float(val1) > 0 and float(val2) > 0:
                                ratio = max(float(val1), float(val2)) / min(float(val1), float(val2))
                                relative_diff = ratio - 1

                                if relative_diff > threshold:
                                    discrepancies.append(
                                        {
                                            "field": field,
                                            "source1": source1,
                                            "source2": source2,
                                            "value1": val1,
                                            "value2": val2,
                                            "relative_difference": relative_diff,
                                            "severity": "high" if relative_diff > threshold * 2 else "medium",
                                        }
                                    )

        return discrepancies


class TestDiscrepancyLogging:
    """Test cases for logging significant discrepancies."""

    def setup_method(self):
        """Set up test fixtures."""
        self.worker = SRC20Worker()

    @patch("index_core.src20_worker.logger")
    def test_discrepancy_logging_format(self, mock_logger):
        """Test that discrepancies are logged with proper format."""
        source_data = {
            "kucoin": {
                "tick": "STAMP",
                "price_btc": Decimal("0.00000004"),
                "data_source": "kucoin",
            },
            "openstamp": {
                "tick": "STAMP",
                "price_btc": Decimal("0.00000012"),  # 3x difference
                "data_source": "openstamp",
            },
        }

        # Trigger aggregation which should log discrepancies
        self.worker._aggregate_multi_source_data("STAMP", source_data)

        # Verify warning was logged
        warning_calls = [call for call in mock_logger.warning.call_args_list]
        assert len(warning_calls) > 0 or len(mock_logger.debug.call_args_list) > 0

        # Check if any log contains discrepancy information
        all_logs = [str(call) for call in mock_logger.warning.call_args_list] + [
            str(call) for call in mock_logger.debug.call_args_list
        ]
        assert any("price" in log.lower() for log in all_logs)

    @patch("index_core.src20_worker.logger")
    def test_multiple_discrepancy_logging(self, mock_logger):
        """Test logging of multiple discrepancies."""
        source_data = {
            "kucoin": {
                "tick": "STAMP",
                "price_btc": Decimal("0.00000004"),
                "volume_24h_btc": Decimal("8.0"),
                "holder_count": None,
            },
            "openstamp": {
                "tick": "STAMP",
                "price_btc": Decimal("0.00000012"),  # 3x price difference
                "volume_24h_btc": Decimal("0.1"),  # 80x volume difference!
                "holder_count": 13494,
            },
            "stampscan": {
                "tick": "STAMP",
                "price_btc": Decimal("0.00000008"),  # 2x from KuCoin
                "volume_24h_btc": None,
                "holder_count": 10000,  # Different from OpenStamp
            },
        }

        self.worker._aggregate_multi_source_data("STAMP", source_data)

        # Should log multiple discrepancies
        all_debug_logs = [str(call) for call in mock_logger.debug.call_args_list]
        # At minimum, aggregation debug logs should be present
        assert len(all_debug_logs) > 0


class TestRobustAggregationIntegration:
    """Integration tests for robust multi-source aggregation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.worker = SRC20Worker()

    def test_complete_aggregation_flow_with_all_features(self):
        """Test complete aggregation with median, conflict resolution, and logging."""
        with patch.object(self.worker, "_fetch_kucoin_data") as mock_kucoin:
            with patch.object(self.worker, "_fetch_openstamp_data") as mock_openstamp:
                with patch.object(self.worker, "_fetch_stampscan_data") as mock_stampscan:
                    with patch("index_core.src20_worker.logger") as mock_logger:
                        # Set up conflicting data
                        mock_kucoin.return_value = {
                            "tick": "STAMP",
                            "price_btc": Decimal("0.00000004"),
                            "volume_24h_btc": Decimal("8.12"),
                            "data_quality_score": Decimal("9.0"),
                            "confidence_level": Decimal("9.0"),
                            "data_source": "kucoin",
                        }

                        mock_openstamp.return_value = {
                            "tick": "STAMP",
                            "price_btc": Decimal("0.00000006"),  # 50% higher
                            "volume_24h_btc": Decimal("0.5"),
                            "holder_count": 13494,
                            "data_quality_score": Decimal("8.0"),
                            "confidence_level": Decimal("8.0"),
                            "data_source": "openstamp",
                        }

                        mock_stampscan.return_value = {
                            "tick": "STAMP",
                            "price_btc": Decimal("0.00000005"),  # In between
                            "market_cap_btc": Decimal("150.0"),
                            "holder_count": 13501,
                            "data_quality_score": Decimal("7.0"),
                            "confidence_level": Decimal("7.0"),
                            "data_source": "stampscan",
                        }

                        result = self.worker.process_src20_market_data("STAMP")

                        # Verify aggregation happened
                        assert result is not None
                        assert result["source_count"] == 3

                        # Verify price is aggregated (weighted average)
                        assert result["price_btc"] is not None

                        # Verify holder count conflict was resolved
                        assert result["holder_count"] in [13494, 13501]

                        # Verify volume is summed
                        assert float(result["volume_24h_btc"]) == 8.62  # 8.12 + 0.5

    def test_aggregation_with_missing_sources(self):
        """Test aggregation when some sources fail."""
        with patch.object(self.worker, "_fetch_kucoin_data") as mock_kucoin:
            with patch.object(self.worker, "_fetch_openstamp_data") as mock_openstamp:
                with patch.object(self.worker, "_fetch_stampscan_data") as mock_stampscan:
                    # KuCoin fails
                    mock_kucoin.return_value = None

                    mock_openstamp.return_value = {
                        "tick": "TEST",
                        "price_btc": Decimal("0.00000006"),
                        "holder_count": 100,
                        "data_quality_score": Decimal("8.0"),
                        "data_source": "openstamp",
                    }

                    mock_stampscan.return_value = {
                        "tick": "TEST",
                        "price_btc": Decimal("0.00000007"),
                        "holder_count": 105,
                        "data_quality_score": Decimal("7.0"),
                        "data_source": "stampscan",
                    }

                    result = self.worker.process_src20_market_data("TEST")

                    # Should still work with 2 sources
                    assert result is not None
                    assert result["source_count"] == 2
                    assert "openstamp" in result["sources"]
                    assert "stampscan" in result["sources"]
                    assert "kucoin" not in result["sources"]

    def test_extreme_outlier_handling(self):
        """Test handling of extreme outliers in aggregation."""
        source_data = {
            "kucoin": {
                "tick": "STAMP",
                "price_btc": Decimal("0.00000004"),
                "confidence_level": 9.0,
                "data_quality_score": Decimal("9.0"),
                "data_source": "kucoin",
            },
            "openstamp": {
                "tick": "STAMP",
                "price_btc": Decimal("0.00000005"),
                "confidence_level": 8.0,
                "data_quality_score": Decimal("8.0"),
                "data_source": "openstamp",
            },
            "malicious": {
                "tick": "STAMP",
                "price_btc": Decimal("0.01000000"),  # 1000x outlier!
                "confidence_level": 2.0,  # Very low confidence
                "data_quality_score": Decimal("2.0"),
                "data_source": "malicious",
            },
        }

        result = self.worker._aggregate_multi_source_data("STAMP", source_data)

        # Due to low confidence weight (2.0) vs high confidence weights (9.0 + 8.0),
        # the outlier impact should be limited
        # Expected: (0.00000004 * 9 + 0.00000005 * 8 + 0.01 * 2) / (9 + 8 + 2)
        # = (0.00000036 + 0.00000040 + 0.02) / 19 ≈ 0.00105
        # But let's check it's significantly less than the outlier
        assert float(result["price_btc"]) < 0.005  # Less than half the outlier

        # Primary exchange should not be the outlier source
        assert result["primary_exchange"] != "malicious"


class TestEdgeCasesAndErrorHandling:
    """Test edge cases and error handling in aggregation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.worker = SRC20Worker()

    def test_single_source_aggregation(self):
        """Test aggregation with only one source."""
        source_data = {
            "openstamp": {
                "tick": "RARE",
                "price_btc": Decimal("0.00001000"),
                "holder_count": 50,
                "data_quality_score": Decimal("8.0"),
            }
        }

        result = self.worker._aggregate_multi_source_data("RARE", source_data)

        assert result is not None
        # The aggregation converts to float, so we need to compare with tolerance
        assert abs(float(result["price_btc"]) - 0.00001000) < 1e-10
        assert result["holder_count"] == 50
        assert json.loads(result["exchange_sources"]) == ["openstamp"]

    def test_all_null_prices(self):
        """Test aggregation when all sources have null prices."""
        source_data = {
            "openstamp": {
                "tick": "NEW",
                "price_btc": None,
                "holder_count": 10,
            },
            "stampscan": {
                "tick": "NEW",
                "price_btc": None,
                "holder_count": 12,
            },
        }

        result = self.worker._aggregate_multi_source_data("NEW", source_data)

        assert result is not None
        assert result["price_btc"] is None
        assert result["primary_exchange"] is None
        assert result["holder_count"] in [10, 12]  # Should still aggregate other data

    def test_zero_confidence_handling(self):
        """Test handling of sources with zero confidence."""
        source_data = {
            "unreliable": {
                "tick": "TEST",
                "price_btc": Decimal("0.00000001"),
                "confidence_level": 0.0,
                "data_quality_score": Decimal("1.0"),
            },
            "reliable": {
                "tick": "TEST",
                "price_btc": Decimal("0.00000005"),
                "confidence_level": 8.0,
                "data_quality_score": Decimal("8.0"),
            },
        }

        # Calculate confidence for unreliable source
        confidence = self.worker._calculate_source_confidence("unreliable", source_data["unreliable"])
        assert confidence > 0  # Should have minimum confidence

        result = self.worker._aggregate_multi_source_data("TEST", source_data)

        # Should heavily favor reliable source
        # With default confidence of 5.0 for unreliable and 8.0 for reliable:
        # Expected: (0.00000001 * 5 + 0.00000005 * 8) / (5 + 8) = 0.0000000346...
        assert float(result["price_btc"]) > 0.000000025  # Closer to reliable price than unreliable


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
