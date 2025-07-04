#!/usr/bin/env python3
"""
Market Data Processing Effectiveness Analyzer

This script generates a comprehensive summary report of market data processing effectiveness
for the Bitcoin Stamps indexer system. It analyzes the market data cache system designed to
eliminate external API calls and improve performance from 10+ seconds to <2 seconds.

The script provides insights into:
- Update timing metrics and batch processing effectiveness
- Data quality and completeness across market data tables
- Cache hit rates and update frequency optimization
- Performance indicators and bottleneck identification

Usage:
    python market_data_effectiveness_analyzer.py [--output-format json|csv|html|markdown] [--detailed]

Examples:
    python market_data_effectiveness_analyzer.py --output-format html
    python market_data_effectiveness_analyzer.py --output-format markdown --detailed
    python market_data_effectiveness_analyzer.py --output-format json
"""

import argparse
import json
import csv
import sys
import os
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Any
import pymysql
from dotenv import load_dotenv

# Try to import matplotlib for charting support
try:
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    print("Warning: matplotlib not installed. Chart generation disabled.", file=sys.stderr)

# Add the parent directory to the path so we can import from indexer
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src")))

# Load environment variables from .env file
env_path = os.path.join(os.path.dirname(__file__), "../../.env")
if os.path.exists(env_path):
    load_dotenv(env_path)
else:
    print(f"Warning: .env file not found at {env_path}", file=sys.stderr)


class MarketDataEffectivenessAnalyzer:
    """Analyzes the effectiveness of the market data processing system."""

    def __init__(self):
        """Initialize the analyzer with database connection."""
        self.db = self.get_db_connection()

    def get_db_connection(self):
        """Get database connection using environment variables."""
        try:
            connection = pymysql.connect(
                host=os.environ.get("RDS_HOSTNAME", "localhost"),
                user=os.environ.get("RDS_USER", "root"),
                password=os.environ.get("RDS_PASSWORD", ""),
                database=os.environ.get("RDS_DATABASE", "btc_stamps"),
                charset="utf8mb4",
                cursorclass=pymysql.cursors.DictCursor,
            )
            print(f"Connected to database: {os.environ.get('RDS_DATABASE', 'btc_stamps')}", file=sys.stderr)
            return connection
        except Exception as e:
            print(f"Error connecting to database: {e}", file=sys.stderr)
            raise

    def fetch_all(self, query: str, params: tuple = None) -> List[Dict]:
        """Execute query and fetch all results."""
        with self.db.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()

    def fetch_one(self, query: str, params: tuple = None) -> Optional[Dict]:
        """Execute query and fetch one result."""
        with self.db.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchone()

    def analyze_table_statistics(self) -> Dict[str, Any]:
        """Analyze statistics for all market data cache tables."""
        stats = {}

        # Stamp market data statistics
        stamp_stats = self.fetch_one(
            """
            SELECT 
                COUNT(*) as total_records,
                COUNT(floor_price_btc) as records_with_floor_price,
                COUNT(holder_count) as records_with_holder_count,
                COUNT(volume_24h_btc) as records_with_volume,
                AVG(data_quality_score) as avg_quality_score,
                MIN(last_updated) as oldest_update,
                MAX(last_updated) as newest_update,
                COUNT(CASE WHEN last_updated > DATE_SUB(NOW(), INTERVAL 1 HOUR) THEN 1 END) as fresh_records,
                COUNT(CASE WHEN last_updated < DATE_SUB(NOW(), INTERVAL 6 HOUR) THEN 1 END) as stale_records
            FROM stamp_market_data
        """
        )
        stats["stamp_market_data"] = stamp_stats

        # Stamp holder cache statistics
        holder_stats = self.fetch_one(
            """
            SELECT 
                COUNT(*) as total_records,
                COUNT(DISTINCT cpid) as unique_stamps,
                AVG(quantity) as avg_quantity,
                SUM(quantity) as total_quantity,
                MIN(last_updated) as oldest_update,
                MAX(last_updated) as newest_update
            FROM stamp_holder_cache
        """
        )
        stats["stamp_holder_cache"] = holder_stats

        # SRC20 market data statistics
        src20_stats = self.fetch_one(
            """
            SELECT 
                COUNT(*) as total_records,
                COUNT(price_btc) as records_with_price,
                COUNT(holder_count) as records_with_holder_count,
                COUNT(volume_24h_btc) as records_with_volume,
                AVG(data_quality_score) as avg_quality_score,
                MIN(last_updated) as oldest_update,
                MAX(last_updated) as newest_update,
                COUNT(CASE WHEN last_updated > DATE_SUB(NOW(), INTERVAL 30 MINUTE) THEN 1 END) as fresh_records
            FROM src20_market_data
        """
        )
        stats["src20_market_data"] = src20_stats

        # Collection market data statistics
        collection_stats = self.fetch_one(
            """
            SELECT 
                COUNT(*) as total_records,
                COUNT(floor_price_btc) as records_with_floor_price,
                COUNT(unique_holders) as records_with_holders,
                COUNT(volume_24h_btc) as records_with_volume,
                MIN(last_updated) as oldest_update,
                MAX(last_updated) as newest_update
            FROM collection_market_data
        """
        )
        stats["collection_market_data"] = collection_stats

        # Stamp sales history statistics
        sales_stats = self.fetch_one(
            """
            SELECT 
                COUNT(*) as total_sales,
                COUNT(DISTINCT cpid) as unique_stamps_sold,
                COUNT(DISTINCT buyer_address) as unique_buyers,
                COUNT(DISTINCT seller_address) as unique_sellers,
                SUM(btc_amount) / 100000000.0 as total_volume_btc,
                AVG(btc_amount) / 100000000.0 as avg_sale_btc,
                MIN(block_time) as first_sale_time,
                MAX(block_time) as last_sale_time,
                COUNT(CASE WHEN sale_type = 'dispenser' THEN 1 END) as dispenser_sales,
                COUNT(CASE WHEN sale_type = 'atomic_swap' THEN 1 END) as atomic_swap_sales,
                COUNT(CASE WHEN block_time > UNIX_TIMESTAMP() - 86400 THEN 1 END) as sales_24h,
                COUNT(CASE WHEN block_time > UNIX_TIMESTAMP() - 604800 THEN 1 END) as sales_7d
            FROM stamp_sales_history
        """
        )
        stats["stamp_sales_history"] = sales_stats

        # Market data sources reliability
        source_stats = self.fetch_all(
            """
            SELECT 
                source_name,
                asset_type,
                COUNT(*) as tracked_assets,
                AVG(source_confidence) as avg_confidence,
                AVG(success_rate_24h) as avg_success_rate,
                AVG(api_response_time_ms) as avg_response_time,
                SUM(consecutive_failures) as total_failures
            FROM market_data_sources
            GROUP BY source_name, asset_type
            ORDER BY avg_success_rate DESC
        """
        )
        stats["market_data_sources"] = source_stats

        return stats

    def analyze_update_timing(self) -> Dict[str, Any]:
        """Analyze update timing patterns and batch processing effectiveness."""
        timing_analysis = {}

        # Stamp update frequency analysis
        stamp_timing = self.fetch_all(
            """
            SELECT 
                DATE(last_updated) as update_date,
                HOUR(last_updated) as update_hour,
                COUNT(*) as updates_count,
                AVG(update_frequency_minutes) as avg_frequency,
                MIN(last_updated) as first_update,
                MAX(last_updated) as last_update
            FROM stamp_market_data 
            WHERE last_updated >= DATE_SUB(NOW(), INTERVAL 7 DAY)
            GROUP BY DATE(last_updated), HOUR(last_updated)
            ORDER BY update_date DESC, update_hour DESC
        """
        )
        timing_analysis["stamp_update_patterns"] = stamp_timing

        # SRC20 update frequency analysis
        src20_timing = self.fetch_all(
            """
            SELECT 
                DATE(last_updated) as update_date,
                HOUR(last_updated) as update_hour,
                COUNT(*) as updates_count,
                AVG(update_frequency_minutes) as avg_frequency
            FROM src20_market_data 
            WHERE last_updated >= DATE_SUB(NOW(), INTERVAL 7 DAY)
            GROUP BY DATE(last_updated), HOUR(last_updated)
            ORDER BY update_date DESC, update_hour DESC
        """
        )
        timing_analysis["src20_update_patterns"] = src20_timing

        # Update lag analysis - how fresh is the data?
        freshness_analysis = self.fetch_one(
            """
            SELECT 
                COUNT(CASE WHEN smd.last_updated > DATE_SUB(NOW(), INTERVAL 15 MINUTE) THEN 1 END) as very_fresh,
                COUNT(CASE WHEN smd.last_updated > DATE_SUB(NOW(), INTERVAL 1 HOUR) THEN 1 END) as fresh, 
                COUNT(CASE WHEN smd.last_updated > DATE_SUB(NOW(), INTERVAL 6 HOUR) THEN 1 END) as acceptable,
                COUNT(CASE WHEN smd.last_updated <= DATE_SUB(NOW(), INTERVAL 6 HOUR) THEN 1 END) as stale,
                COUNT(*) as total
            FROM stamp_market_data smd
        """
        )
        timing_analysis["data_freshness"] = freshness_analysis

        return timing_analysis

    def analyze_data_quality(self) -> Dict[str, Any]:
        """Analyze data quality metrics and completeness."""
        quality_analysis = {}

        # Data completeness analysis
        completeness = self.fetch_one(
            """
            SELECT 
                COUNT(*) as total_stamps,
                COUNT(smd.cpid) as stamps_with_cache,
                (COUNT(smd.cpid) / COUNT(*) * 100) as cache_coverage_percent,
                COUNT(smd.floor_price_btc) as stamps_with_price,
                COUNT(smd.holder_count) as stamps_with_holders,
                COUNT(smd.volume_24h_btc) as stamps_with_volume,
                AVG(smd.data_quality_score) as avg_quality_score
            FROM StampTableV4 s
            LEFT JOIN stamp_market_data smd ON s.cpid = smd.cpid
        """
        )
        quality_analysis["data_completeness"] = completeness

        # Quality score distribution
        quality_distribution = self.fetch_all(
            """
            SELECT 
                CASE 
                    WHEN data_quality_score >= 9 THEN 'Excellent (9-10)'
                    WHEN data_quality_score >= 7 THEN 'Good (7-9)'
                    WHEN data_quality_score >= 5 THEN 'Fair (5-7)'
                    WHEN data_quality_score >= 3 THEN 'Poor (3-5)'
                    ELSE 'Very Poor (0-3)'
                END as quality_category,
                COUNT(*) as count,
                AVG(data_quality_score) as avg_score
            FROM stamp_market_data
            WHERE data_quality_score IS NOT NULL
            GROUP BY quality_category
            ORDER BY avg_score DESC
        """
        )
        quality_analysis["quality_distribution"] = quality_distribution

        # Error rate analysis from market data sources
        error_analysis = self.fetch_all(
            """
            SELECT 
                source_name,
                asset_type,
                AVG(success_rate_24h) as success_rate,
                AVG(consecutive_failures) as avg_failures,
                COUNT(CASE WHEN last_failure > last_success THEN 1 END) as currently_failing
            FROM market_data_sources
            GROUP BY source_name, asset_type
            ORDER BY success_rate DESC
        """
        )
        quality_analysis["error_rates"] = error_analysis

        return quality_analysis

    def analyze_performance_metrics(self) -> Dict[str, Any]:
        """Analyze performance indicators and identify bottlenecks."""
        performance = {}

        # Response time analysis from market data sources
        response_times = self.fetch_all(
            """
            SELECT 
                source_name,
                asset_type,
                AVG(api_response_time_ms) as avg_response_time,
                MIN(api_response_time_ms) as min_response_time,
                MAX(api_response_time_ms) as max_response_time,
                COUNT(*) as sample_size
            FROM market_data_sources
            WHERE api_response_time_ms > 0
            GROUP BY source_name, asset_type
            ORDER BY avg_response_time ASC
        """
        )
        performance["api_response_times"] = response_times

        # Volume vs holder correlation (performance indicator)
        volume_correlation = self.fetch_all(
            """
            SELECT 
                CASE 
                    WHEN holder_count > 100 THEN 'High Holders (>100)'
                    WHEN holder_count > 50 THEN 'Medium Holders (50-100)'
                    WHEN holder_count > 10 THEN 'Low Holders (10-50)'
                    ELSE 'Very Low Holders (<10)'
                END as holder_category,
                COUNT(*) as stamp_count,
                AVG(volume_24h_btc) as avg_volume,
                AVG(floor_price_btc) as avg_floor_price
            FROM stamp_market_data
            WHERE holder_count IS NOT NULL AND volume_24h_btc IS NOT NULL
            GROUP BY holder_category
            ORDER BY avg_volume DESC
        """
        )
        performance["volume_holder_correlation"] = volume_correlation

        # Cache efficiency metrics
        cache_efficiency = self.fetch_one(
            """
            SELECT 
                COUNT(CASE WHEN last_updated > DATE_SUB(NOW(), INTERVAL 1 HOUR) THEN 1 END) as hot_cache,
                COUNT(CASE WHEN last_updated BETWEEN DATE_SUB(NOW(), INTERVAL 6 HOUR) AND DATE_SUB(NOW(), INTERVAL 1 HOUR) THEN 1 END) as warm_cache,
                COUNT(CASE WHEN last_updated < DATE_SUB(NOW(), INTERVAL 6 HOUR) THEN 1 END) as cold_cache,
                COUNT(*) as total_cache
            FROM stamp_market_data
        """
        )
        performance["cache_efficiency"] = cache_efficiency

        return performance

    def analyze_multi_source_performance(self) -> Dict[str, Any]:
        """Analyze performance of individual data sources and aggregation effectiveness."""
        multi_source_analysis = {}

        # Source performance comparison (including StampScan)
        source_performance = self.fetch_all(
            """
            SELECT 
                source_name,
                COUNT(*) as total_assets,
                COUNT(CASE WHEN price_btc IS NOT NULL THEN 1 END) as assets_with_price,
                COUNT(CASE WHEN volume_24h_btc IS NOT NULL AND volume_24h_btc > 0 THEN 1 END) as assets_with_volume,
                COUNT(CASE WHEN holder_count IS NOT NULL THEN 1 END) as assets_with_holders,
                AVG(source_confidence) as avg_confidence,
                AVG(api_response_time_ms) as avg_response_time,
                MIN(last_updated) as oldest_update,
                MAX(last_updated) as newest_update,
                COUNT(CASE WHEN last_updated > DATE_SUB(NOW(), INTERVAL 1 HOUR) THEN 1 END) as fresh_records
            FROM market_data_sources
            WHERE asset_type = 'src20'
            GROUP BY source_name
            ORDER BY avg_confidence DESC
        """
        )
        multi_source_analysis["source_performance"] = source_performance

        # Multi-source asset coverage
        coverage_analysis = self.fetch_all(
            """
            SELECT 
                asset_id,
                COUNT(DISTINCT source_name) as source_count,
                GROUP_CONCAT(source_name ORDER BY source_confidence DESC) as sources,
                MAX(source_confidence) as best_confidence,
                COUNT(CASE WHEN price_btc IS NOT NULL THEN 1 END) as sources_with_price,
                COUNT(CASE WHEN volume_24h_btc IS NOT NULL AND volume_24h_btc > 0 THEN 1 END) as sources_with_volume
            FROM market_data_sources
            WHERE asset_type = 'src20'
            GROUP BY asset_id
            HAVING source_count > 1  -- Only tokens with multiple sources
            ORDER BY source_count DESC, best_confidence DESC
            LIMIT 20
        """
        )
        multi_source_analysis["multi_source_coverage"] = coverage_analysis

        # Source data comparison for same assets
        source_comparison = self.fetch_all(
            """
            SELECT 
                mds1.asset_id,
                mds1.source_name as source_1,
                mds1.price_btc as price_1,
                mds1.volume_24h_btc as volume_1,
                mds2.source_name as source_2,
                mds2.price_btc as price_2,
                mds2.volume_24h_btc as volume_2,
                CASE 
                    WHEN mds1.price_btc IS NOT NULL AND mds2.price_btc IS NOT NULL 
                    THEN ABS((mds1.price_btc - mds2.price_btc) / mds1.price_btc * 100)
                    ELSE NULL 
                END as price_difference_percent
            FROM market_data_sources mds1
            JOIN market_data_sources mds2 ON mds1.asset_id = mds2.asset_id 
                AND mds1.asset_type = mds2.asset_type
                AND mds1.source_name < mds2.source_name  -- Avoid duplicate pairs
            WHERE mds1.asset_type = 'src20'
              AND mds1.price_btc IS NOT NULL 
              AND mds2.price_btc IS NOT NULL
            ORDER BY price_difference_percent DESC
            LIMIT 10
        """
        )
        multi_source_analysis["source_price_comparisons"] = source_comparison

        # Aggregation effectiveness
        aggregation_stats = self.fetch_one(
            """
            SELECT 
                COUNT(DISTINCT smd.tick) as aggregated_tokens,
                AVG(smd.data_quality_score) as avg_aggregated_quality,
                COUNT(CASE WHEN smd.price_btc IS NOT NULL THEN 1 END) as tokens_with_aggregated_price,
                COUNT(CASE WHEN smd.volume_24h_btc IS NOT NULL AND smd.volume_24h_btc > 0 THEN 1 END) as tokens_with_aggregated_volume,
                COUNT(CASE WHEN smd.exchange_sources LIKE '%,%' THEN 1 END) as tokens_with_multiple_sources,
                (SELECT COUNT(DISTINCT asset_id) FROM market_data_sources WHERE asset_type = 'src20') as total_source_records
            FROM src20_market_data smd
        """
        )
        multi_source_analysis["aggregation_effectiveness"] = aggregation_stats

        return multi_source_analysis

    def analyze_cache_freshness_issues(self) -> Dict[str, Any]:
        """Analyze why cache data is becoming stale and identify update frequency issues."""
        freshness_analysis = {}

        # Update frequency analysis
        update_intervals = self.fetch_all(
            """
            SELECT 
                'src20' as asset_type,
                COUNT(*) as total_records,
                COUNT(CASE WHEN last_updated > DATE_SUB(NOW(), INTERVAL 5 MINUTE) THEN 1 END) as updated_5min,
                COUNT(CASE WHEN last_updated > DATE_SUB(NOW(), INTERVAL 15 MINUTE) THEN 1 END) as updated_15min,
                COUNT(CASE WHEN last_updated > DATE_SUB(NOW(), INTERVAL 1 HOUR) THEN 1 END) as updated_1hour,
                COUNT(CASE WHEN last_updated > DATE_SUB(NOW(), INTERVAL 6 HOUR) THEN 1 END) as updated_6hour,
                COUNT(CASE WHEN last_updated <= DATE_SUB(NOW(), INTERVAL 6 HOUR) THEN 1 END) as stale_6hour,
                MIN(last_updated) as oldest_record,
                MAX(last_updated) as newest_record,
                AVG(TIMESTAMPDIFF(MINUTE, last_updated, NOW())) as avg_age_minutes
            FROM src20_market_data
            
            UNION ALL
            
            SELECT 
                'stamp' as asset_type,
                COUNT(*) as total_records,
                COUNT(CASE WHEN last_updated > DATE_SUB(NOW(), INTERVAL 5 MINUTE) THEN 1 END) as updated_5min,
                COUNT(CASE WHEN last_updated > DATE_SUB(NOW(), INTERVAL 15 MINUTE) THEN 1 END) as updated_15min,
                COUNT(CASE WHEN last_updated > DATE_SUB(NOW(), INTERVAL 1 HOUR) THEN 1 END) as updated_1hour,
                COUNT(CASE WHEN last_updated > DATE_SUB(NOW(), INTERVAL 6 HOUR) THEN 1 END) as updated_6hour,
                COUNT(CASE WHEN last_updated <= DATE_SUB(NOW(), INTERVAL 6 HOUR) THEN 1 END) as stale_6hour,
                MIN(last_updated) as oldest_record,
                MAX(last_updated) as newest_record,
                AVG(TIMESTAMPDIFF(MINUTE, last_updated, NOW())) as avg_age_minutes
            FROM stamp_market_data
        """
        )
        freshness_analysis["update_intervals"] = update_intervals

        # Job scheduling effectiveness
        job_patterns = self.fetch_all(
            """
            SELECT 
                DATE_FORMAT(last_updated, '%Y-%m-%d %H:%i') as update_window,
                COUNT(*) as updates_count,
                COUNT(DISTINCT CASE WHEN table_name = 'src20_market_data' THEN 1 END) as src20_updates,
                COUNT(DISTINCT CASE WHEN table_name = 'stamp_market_data' THEN 1 END) as stamp_updates
            FROM (
                SELECT last_updated, 'src20_market_data' as table_name FROM src20_market_data 
                WHERE last_updated >= DATE_SUB(NOW(), INTERVAL 12 HOUR)
                UNION ALL
                SELECT last_updated, 'stamp_market_data' as table_name FROM stamp_market_data 
                WHERE last_updated >= DATE_SUB(NOW(), INTERVAL 12 HOUR)
            ) combined
            GROUP BY DATE_FORMAT(last_updated, '%Y-%m-%d %H:%i')
            ORDER BY update_window DESC
            LIMIT 20
        """
        )
        freshness_analysis["recent_job_patterns"] = job_patterns

        # Identify tokens that haven't been updated
        stale_tokens = self.fetch_all(
            """
            SELECT 
                tick,
                last_updated,
                TIMESTAMPDIFF(MINUTE, last_updated, NOW()) as minutes_since_update,
                data_quality_score,
                exchange_sources,
                CASE 
                    WHEN price_btc IS NOT NULL THEN 'Has Price'
                    ELSE 'No Price'
                END as price_status,
                CASE 
                    WHEN volume_24h_btc IS NOT NULL AND volume_24h_btc > 0 THEN 'Has Volume'
                    ELSE 'No Volume'
                END as volume_status
            FROM src20_market_data
            WHERE last_updated <= DATE_SUB(NOW(), INTERVAL 2 HOUR)
            ORDER BY last_updated ASC
            LIMIT 25
        """
        )
        freshness_analysis["stale_tokens"] = stale_tokens

        return freshness_analysis

    def generate_summary_report(self, detailed: bool = False) -> Dict[str, Any]:
        """Generate comprehensive summary report."""
        print("Analyzing market data processing effectiveness...", file=sys.stderr)

        report = {
            "report_generated": datetime.now().isoformat(),
            "analysis_type": "detailed" if detailed else "standard",
            "table_statistics": self.analyze_table_statistics(),
            "update_timing": self.analyze_update_timing(),
            "data_quality": self.analyze_data_quality(),
            "performance_metrics": self.analyze_performance_metrics(),
            "multi_source_performance": self.analyze_multi_source_performance(),
            "cache_freshness_issues": self.analyze_cache_freshness_issues(),
            "stampscan_analysis": self.analyze_stampscan_performance(),
            "sales_history_analysis": self.analyze_sales_history(),
        }

        if detailed:
            # Add more detailed analysis for detailed reports
            report["trending_analysis"] = self.analyze_trending_stamps()
            report["batch_processing"] = self.analyze_batch_effectiveness()

        return report

    def analyze_trending_stamps(self) -> Dict[str, Any]:
        """Analyze trending stamps and their data patterns."""
        trending = self.fetch_all(
            """
            SELECT 
                s.stamp,
                s.cpid,
                smd.floor_price_btc,
                smd.holder_count,
                smd.volume_24h_btc,
                smd.data_quality_score,
                smd.last_updated
            FROM stamp_market_data smd
            JOIN StampTableV4 s ON smd.cpid = s.cpid
            WHERE smd.volume_24h_btc > 0
            ORDER BY smd.volume_24h_btc DESC
            LIMIT 20
        """
        )

        return {"top_trading_stamps": trending}

    def analyze_batch_effectiveness(self) -> Dict[str, Any]:
        """Analyze batch processing effectiveness."""
        # Analyze update patterns to identify batch processing
        batch_analysis = self.fetch_all(
            """
            SELECT 
                DATE_FORMAT(last_updated, '%Y-%m-%d %H:%i') as update_window,
                COUNT(*) as updates_in_window,
                AVG(data_quality_score) as avg_quality,
                COUNT(CASE WHEN volume_24h_btc > 0 THEN 1 END) as with_volume_data
            FROM stamp_market_data
            WHERE last_updated >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
            GROUP BY DATE_FORMAT(last_updated, '%Y-%m-%d %H:%i')
            HAVING updates_in_window > 10  -- Identify potential batch operations
            ORDER BY update_window DESC
        """
        )

        return {"batch_update_patterns": batch_analysis}

    def output_json(self, data: Dict):
        """Output report in JSON format."""

        # Convert datetime objects to strings for JSON serialization
        def convert_datetime(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            elif isinstance(obj, Decimal):
                return float(obj)
            elif isinstance(obj, dict):
                return {key: convert_datetime(value) for key, value in obj.items()}
            elif isinstance(obj, list):
                return [convert_datetime(item) for item in obj]
            return obj

        json_data = convert_datetime(data)
        print(json.dumps(json_data, indent=2, default=str))

    def output_csv(self, data: Dict):
        """Output key metrics in CSV format."""
        # Create a flattened CSV with key metrics
        writer = csv.writer(sys.stdout)
        writer.writerow(["Metric", "Value", "Category", "Description"])

        # Table statistics
        table_stats = data.get("table_statistics", {})
        for table, stats in table_stats.items():
            if isinstance(stats, dict):
                for metric, value in stats.items():
                    writer.writerow([metric, value, f"{table}_stats", f"{metric} for {table}"])

        # Data quality metrics
        quality = data.get("data_quality", {})
        if "data_completeness" in quality:
            completeness = quality["data_completeness"]
            for metric, value in completeness.items():
                writer.writerow([metric, value, "data_quality", f"Data completeness: {metric}"])

    def output_markdown(self, data: Dict):
        """Output report in Markdown format."""
        print("# Market Data Processing Effectiveness Report")
        print(f"\n**Generated:** {data.get('report_generated', 'Unknown')}")
        print(f"**Analysis Type:** {data.get('analysis_type', 'Standard')}")

        # Table Statistics
        print("\n## 📊 Table Statistics")
        table_stats = data.get("table_statistics", {})
        for table_name, stats in table_stats.items():
            if isinstance(stats, dict):
                print(f"\n### {table_name.replace('_', ' ').title()}")

                # Special formatting for stamp_sales_history table
                if table_name == "stamp_sales_history":
                    for metric, value in stats.items():
                        if value is not None:
                            if metric in ["total_volume_btc", "avg_sale_btc"]:
                                print(f"- **{metric.replace('_', ' ').title()}:** {value:.6f} BTC")
                            elif metric in ["first_sale_time", "last_sale_time"]:
                                from datetime import datetime

                                if value:
                                    dt = datetime.fromtimestamp(value)
                                    print(f"- **{metric.replace('_', ' ').title()}:** {dt.strftime('%Y-%m-%d %H:%M:%S')}")
                                else:
                                    print(f"- **{metric.replace('_', ' ').title()}:** N/A")
                            else:
                                print(
                                    f"- **{metric.replace('_', ' ').title()}:** {value:,}"
                                    if isinstance(value, (int, float))
                                    else f"- **{metric.replace('_', ' ').title()}:** {value}"
                                )
                else:
                    for metric, value in stats.items():
                        if value is not None:
                            print(f"- **{metric.replace('_', ' ').title()}:** {value}")

        # Data Quality
        print("\n## 🎯 Data Quality Analysis")
        quality = data.get("data_quality", {})

        if "data_completeness" in quality:
            completeness = quality["data_completeness"]
            print("\n### Cache Coverage")
            print(f"- **Total Stamps:** {completeness.get('total_stamps', 'N/A')}")
            print(f"- **Stamps with Cache:** {completeness.get('stamps_with_cache', 'N/A')}")
            print(f"- **Coverage Percentage:** {completeness.get('cache_coverage_percent', 'N/A'):.1f}%")
            print(f"- **Average Quality Score:** {completeness.get('avg_quality_score', 'N/A'):.2f}/10")

        # Performance Metrics
        print("\n## ⚡ Performance Metrics")
        performance = data.get("performance_metrics", {})

        if "cache_efficiency" in performance:
            cache = performance["cache_efficiency"]
            total = cache.get("total_cache", 1)
            print("\n### Cache Efficiency")
            print(f"- **Hot Cache (< 1 hour):** {cache.get('hot_cache', 0)} ({cache.get('hot_cache', 0)/total*100:.1f}%)")
            print(f"- **Warm Cache (1-6 hours):** {cache.get('warm_cache', 0)} ({cache.get('warm_cache', 0)/total*100:.1f}%)")
            print(f"- **Cold Cache (> 6 hours):** {cache.get('cold_cache', 0)} ({cache.get('cold_cache', 0)/total*100:.1f}%)")

        # Update Timing
        print("\n## 🕒 Update Timing Analysis")
        timing = data.get("update_timing", {})

        if "data_freshness" in timing:
            freshness = timing["data_freshness"]
            total = freshness.get("total", 1)
            print("\n### Data Freshness")
            print(
                f"- **Very Fresh (< 15 min):** {freshness.get('very_fresh', 0)} ({freshness.get('very_fresh', 0)/total*100:.1f}%)"
            )
            print(f"- **Fresh (< 1 hour):** {freshness.get('fresh', 0)} ({freshness.get('fresh', 0)/total*100:.1f}%)")
            print(
                f"- **Acceptable (< 6 hours):** {freshness.get('acceptable', 0)} ({freshness.get('acceptable', 0)/total*100:.1f}%)"
            )
            print(f"- **Stale (> 6 hours):** {freshness.get('stale', 0)} ({freshness.get('stale', 0)/total*100:.1f}%)")

        # Multi-Source Performance Analysis
        print("\n## 🔄 Multi-Source Data Analysis")
        multi_source = data.get("multi_source_performance", {})

        if "source_performance" in multi_source:
            source_perf = multi_source["source_performance"]
            print("\n### Data Source Performance")
            for source in source_perf:
                name = source.get("source_name", "Unknown")
                total = source.get("total_assets", 0)
                with_price = source.get("assets_with_price", 0)
                with_volume = source.get("assets_with_volume", 0)
                confidence = source.get("avg_confidence", 0)
                response_time = source.get("avg_response_time", 0)
                fresh = source.get("fresh_records", 0)

                print(f"\n**{name.upper()}:**")
                print(f"- Assets: {total} | Price: {with_price} | Volume: {with_volume} | Fresh: {fresh}")
                print(f"- Confidence: {confidence:.1f}/10 | Response: {response_time:.0f}ms")

        if "aggregation_effectiveness" in multi_source:
            agg_stats = multi_source["aggregation_effectiveness"]
            print("\n### Aggregation Effectiveness")
            total_agg = agg_stats.get("aggregated_tokens", 0)
            with_price = agg_stats.get("tokens_with_aggregated_price", 0)
            with_volume = agg_stats.get("tokens_with_aggregated_volume", 0)
            multi_source_tokens = agg_stats.get("tokens_with_multiple_sources", 0)
            total_sources = agg_stats.get("total_source_records", 0)

            print(f"- **Aggregated Tokens:** {total_agg}")
            print(f"- **With Price Data:** {with_price} ({with_price/total_agg*100:.1f}%)")
            print(f"- **With Volume Data:** {with_volume} ({with_volume/total_agg*100:.1f}%)")
            print(f"- **Multi-Source Tokens:** {multi_source_tokens} ({multi_source_tokens/total_agg*100:.1f}%)")
            print(f"- **Total Source Records:** {total_sources}")

        if "source_price_comparisons" in multi_source:
            comparisons = multi_source["source_price_comparisons"]
            if comparisons:
                print("\n### Price Discrepancies Between Sources")
                print("*(Top price differences between sources for the same token)*")
                for comp in comparisons[:5]:  # Top 5 discrepancies
                    asset = comp.get("asset_id", "Unknown")
                    source1 = comp.get("source_1", "")
                    source2 = comp.get("source_2", "")
                    diff = comp.get("price_difference_percent", 0)
                    print(f"- **{asset}:** {source1} vs {source2} = {diff:.1f}% difference")

        # Cache Freshness Issues Analysis
        print("\n## ⏰ Cache Freshness Analysis")
        freshness_issues = data.get("cache_freshness_issues", {})

        if "update_intervals" in freshness_issues:
            intervals = freshness_issues["update_intervals"]
            print("\n### Update Frequency by Asset Type")
            for interval in intervals:
                asset_type = interval.get("asset_type", "Unknown")
                total = interval.get("total_records", 0)
                updated_5min = interval.get("updated_5min", 0)
                updated_1hour = interval.get("updated_1hour", 0)
                stale_6hour = interval.get("stale_6hour", 0)
                avg_age = interval.get("avg_age_minutes", 0)

                print(f"\n**{asset_type.upper()}:**")
                print(f"- Recent (< 5min): {updated_5min} ({updated_5min/total*100:.1f}%)")
                print(f"- Fresh (< 1hr): {updated_1hour} ({updated_1hour/total*100:.1f}%)")
                print(f"- Stale (> 6hr): {stale_6hour} ({stale_6hour/total*100:.1f}%)")
                print(f"- Average Age: {avg_age:.0f} minutes")

        if "stale_tokens" in freshness_issues:
            stale = freshness_issues["stale_tokens"]
            if stale:
                print("\n### Most Stale Tokens (Sample)")
                print("*(Tokens that haven't been updated in >2 hours)*")
                for token in stale[:10]:  # Top 10 stale tokens
                    tick = token.get("tick", "Unknown")
                    minutes = token.get("minutes_since_update", 0)
                    sources = token.get("exchange_sources", "")
                    price_status = token.get("price_status", "Unknown")
                    print(f"- **{tick}:** {minutes} min old | {sources} | {price_status}")

        # Recommendations
        print("\n## 💡 Recommendations")
        cache_coverage = quality.get("data_completeness", {}).get("cache_coverage_percent", 0)
        hot_cache_percent = performance.get("cache_efficiency", {}).get("hot_cache", 0) / total * 100 if total > 0 else 0

        # Multi-source recommendations
        multi_source = data.get("multi_source_performance", {})
        agg_stats = multi_source.get("aggregation_effectiveness", {})
        total_agg = agg_stats.get("aggregated_tokens", 0)
        with_price = agg_stats.get("tokens_with_aggregated_price", 0)
        with_volume = agg_stats.get("tokens_with_aggregated_volume", 0)
        multi_source_tokens = agg_stats.get("tokens_with_multiple_sources", 0)

        # Freshness recommendations
        freshness_issues = data.get("cache_freshness_issues", {})
        src20_interval = next((x for x in freshness_issues.get("update_intervals", []) if x.get("asset_type") == "src20"), {})
        src20_stale_percent = src20_interval.get("stale_6hour", 0) / max(src20_interval.get("total_records", 1), 1) * 100

        # StampScan data for recommendations
        stampscan_data = data.get("stampscan_analysis", {})
        stampscan_perf = stampscan_data.get("stampscan_performance", {})
        stampscan_coverage = stampscan_data.get("floor_price_coverage", {})

        print("\n### 🚀 **Priority Actions:**")

        # Critical issues first
        if with_price == 0 and total_agg > 0:
            print("- 🔴 **CRITICAL: No price data** - SRC-20 worker fixes need deployment")
        elif with_price < total_agg * 0.5:
            print(f"- 🟡 **Low price coverage** - Only {with_price}/{total_agg} tokens have price data")

        if with_volume == 0 and total_agg > 0:
            print("- 🟡 **No volume data** - Expected for new token ecosystem, monitor for trading activity")

        if src20_stale_percent > 50:
            print(f"- 🟠 **High staleness** - {src20_stale_percent:.1f}% of SRC-20 data is >6hrs old")
            print("  - Consider reducing update interval from 5min to 2-3min")
            print("  - Check if market data jobs are running consistently")

        print("\n### 📈 **Optimization Opportunities:**")

        if multi_source_tokens < total_agg * 0.1 and total_agg > 0:
            print(f"- **Expand source coverage** - Only {multi_source_tokens}/{total_agg} tokens have multiple sources")
            print("  - Add more KuCoin token mappings beyond just STAMP")
            print("  - Consider StampScan data for non-KuCoin tokens")
            print("  - Integrate additional exchanges (Binance, Gate.io, etc.)")

        if cache_coverage < 80:
            print("- **Low cache coverage** - Consider expanding market data collection")

        if hot_cache_percent < 50:
            print("- **Cold cache issue** - Consider increasing update frequency")

        # StampScan specific recommendations
        if stampscan_perf:
            ss_success_rate = stampscan_perf.get("avg_success_rate", 0)
            ss_floor_coverage = (
                stampscan_perf.get("assets_with_floor_price", 0) / max(stampscan_perf.get("total_assets", 1), 1) * 100
            )

            if ss_success_rate < 80:
                print(f"- 🟡 **StampScan reliability issue** - Success rate only {ss_success_rate:.1f}%")
                print("  - Check API endpoints and rate limiting")
                print("  - Consider implementing retry logic")

            if ss_floor_coverage > 80:
                print(f"- **Leverage StampScan floor prices** - {ss_floor_coverage:.1f}% coverage for marketplace data")

        print("\n### ✅ **System Health:**")

        if multi_source_tokens > 0:
            print(f"- **Multi-source aggregation working** - {multi_source_tokens} tokens using multiple sources")

        if src20_stale_percent < 20:
            print("- **SRC-20 freshness good** - Most data updated within target intervals")

        if cache_coverage > 90 and hot_cache_percent > 70:
            print("- **Overall system performing well** - Cache coverage and freshness are good")

        if with_price > 0:
            print(f"- **Price data flowing** - {with_price} tokens have price information")

        if stampscan_coverage and stampscan_coverage.get("tokens_with_floor_price", 0) > 0:
            print(
                f"- **StampScan integration active** - {stampscan_coverage.get('tokens_with_floor_price', 0)} tokens with floor price data"
            )

        # StampScan Analysis Section
        print("\n## 🔍 StampScan Source Analysis")
        stampscan_data = data.get("stampscan_analysis", {})

        if "stampscan_performance" in stampscan_data:
            perf = stampscan_data["stampscan_performance"]
            if perf:
                print("\n### StampScan API Performance")
                total = perf.get("total_assets", 0)
                with_floor = perf.get("assets_with_floor_price", 0)
                with_holders = perf.get("assets_with_holders", 0)
                with_volume = perf.get("assets_with_volume", 0)
                confidence = perf.get("avg_confidence", 0)
                success_rate = perf.get("avg_success_rate", 0)
                response_time = perf.get("avg_response_time", 0)
                fresh = perf.get("fresh_records", 0)

                print(f"- **Total Assets Tracked:** {total}")
                print(
                    f"- **Floor Price Coverage:** {with_floor} ({with_floor/total*100:.1f}%)"
                    if total > 0
                    else "- **Floor Price Coverage:** 0 (0%)"
                )
                print(
                    f"- **Holder Data Coverage:** {with_holders} ({with_holders/total*100:.1f}%)"
                    if total > 0
                    else "- **Holder Data Coverage:** 0 (0%)"
                )
                print(
                    f"- **Volume Data Available:** {with_volume} ({with_volume/total*100:.1f}%)"
                    if total > 0
                    else "- **Volume Data Available:** 0 (0%)"
                )
                print(f"- **API Success Rate:** {success_rate:.1f}%")
                print(f"- **Average Response Time:** {response_time:.0f}ms")
                print(
                    f"- **Fresh Records (<30min):** {fresh} ({fresh/total*100:.1f}%)"
                    if total > 0
                    else "- **Fresh Records (<30min):** 0 (0%)"
                )

        if "floor_price_coverage" in stampscan_data:
            coverage = stampscan_data["floor_price_coverage"]
            if coverage:
                print("\n### StampScan Data Quality")
                tokens_tracked = coverage.get("tokens_tracked", 0)
                with_floor = coverage.get("tokens_with_floor_price", 0)
                floor_confidence = coverage.get("avg_floor_price_confidence", 0)
                with_mcap = coverage.get("tokens_with_market_cap", 0)

                print(f"- **Unique Tokens:** {tokens_tracked}")
                print(
                    f"- **With Floor Price:** {with_floor} ({with_floor/tokens_tracked*100:.1f}%)"
                    if tokens_tracked > 0
                    else "- **With Floor Price:** 0 (0%)"
                )
                print(f"- **Floor Price Confidence:** {floor_confidence:.1f}/10")
                print(
                    f"- **With Market Cap:** {with_mcap} ({with_mcap/tokens_tracked*100:.1f}%)"
                    if tokens_tracked > 0
                    else "- **With Market Cap:** 0 (0%)"
                )

        if "source_data_comparison" in stampscan_data:
            comparisons = stampscan_data["source_data_comparison"]
            if comparisons:
                print("\n### Cross-Source Data Comparison (Sample)")
                print("*(Comparing prices and holder counts across sources)*")
                for comp in comparisons[:5]:  # Top 5 examples
                    asset = comp.get("asset_id", "Unknown")
                    ss_price = comp.get("stampscan_price")
                    kc_price = comp.get("kucoin_price")
                    os_price = comp.get("openstamp_price")
                    ss_holders = comp.get("stampscan_holders")
                    os_holders = comp.get("openstamp_holders")

                    price_info = []
                    if ss_price:
                        price_info.append(f"SS: {ss_price:.8f}")
                    if kc_price:
                        price_info.append(f"KC: {kc_price:.8f}")
                    if os_price:
                        price_info.append(f"OS: {os_price:.8f}")

                    holder_info = []
                    if ss_holders:
                        holder_info.append(f"SS: {ss_holders}")
                    if os_holders:
                        holder_info.append(f"OS: {os_holders}")

                    print(
                        f"- **{asset}:** Price: {' | '.join(price_info) if price_info else 'N/A'} | Holders: {' | '.join(holder_info) if holder_info else 'N/A'}"
                    )

        print("\n### 🔧 **Technical Notes:**")
        print("- **Zero volume is expected** - SRC-20 ecosystem is new, most tokens don't trade yet")
        print("- **OpenStamp provides holder counts** - This is valuable for token analysis")
        print("- **KuCoin provides real trading data** - High confidence when available")
        print("- **StampScan provides floor prices** - Specialized for Bitcoin stamps marketplace data")

        # Show update frequency analysis
        if src20_interval:
            avg_age = src20_interval.get("avg_age_minutes", 0)
            print(f"- **Current SRC-20 average age:** {avg_age:.0f} minutes (target: <60 minutes)")

        # Sales History Analysis Section
        print("\n## 💰 Sales History Analysis")
        sales_data = data.get("sales_history_analysis", {})

        if "sales_activity" in sales_data:
            activity = sales_data["sales_activity"]
            if activity:
                print("\n### Sales Activity Overview")
                total_sales = activity.get("total_sales", 0)
                unique_stamps = activity.get("unique_stamps_sold", 0)
                sales_24h = activity.get("sales_24h", 0)
                sales_7d = activity.get("sales_7d", 0)
                volume_24h = activity.get("volume_24h_btc", 0)
                volume_7d = activity.get("volume_7d_btc", 0)

                print(f"- **Total Sales Recorded:** {total_sales:,}")
                print(f"- **Unique Stamps Sold:** {unique_stamps:,}")
                print(f"- **Sales (24h):** {sales_24h:,}")
                print(f"- **Sales (7d):** {sales_7d:,}")
                print(f"- **Volume (24h):** {volume_24h:.4f} BTC")
                print(f"- **Volume (7d):** {volume_7d:.4f} BTC")

        if "sales_by_type" in sales_data:
            types = sales_data["sales_by_type"]
            if types:
                print("\n### Sales by Type")
                for sale_type in types:
                    type_name = sale_type.get("sale_type", "Unknown")
                    count = sale_type.get("sale_count", 0)
                    volume = sale_type.get("total_volume_btc", 0)
                    unique = sale_type.get("unique_stamps", 0)
                    print(
                        f"- **{type_name.replace('_', ' ').title()}:** {count:,} sales | {volume:.4f} BTC | {unique} unique stamps"
                    )

        if "top_stamps_by_volume" in sales_data:
            top_stamps = sales_data["top_stamps_by_volume"]
            if top_stamps:
                print("\n### Top Selling Stamps (7d Volume)")
                for i, stamp in enumerate(top_stamps[:10], 1):
                    stamp_name = stamp.get("stamp", "Unknown")
                    cpid = stamp.get("cpid", "")
                    volume = stamp.get("total_volume_btc", 0)
                    sales = stamp.get("sale_count", 0)
                    avg_sale = stamp.get("avg_sale_btc", 0)
                    print(f"{i}. **{stamp_name}** ({cpid}): {volume:.4f} BTC | {sales} sales | Avg: {avg_sale:.6f} BTC")

        if "trader_activity" in sales_data:
            traders = sales_data["trader_activity"]
            if traders:
                print("\n### Trader Activity")
                buyers = traders.get("unique_buyers", 0)
                sellers = traders.get("unique_sellers", 0)
                active_buyers = traders.get("active_buyers_24h", 0)
                active_sellers = traders.get("active_sellers_24h", 0)
                print(f"- **Total Unique Buyers:** {buyers:,}")
                print(f"- **Total Unique Sellers:** {sellers:,}")
                print(f"- **Active Buyers (24h):** {active_buyers}")
                print(f"- **Active Sellers (24h):** {active_sellers}")

    def analyze_sales_history(self) -> Dict[str, Any]:
        """Analyze stamp sales history data."""
        sales_analysis = {}

        # Sales activity by time period
        sales_activity = self.fetch_one(
            """
            SELECT 
                COUNT(*) as total_sales,
                COUNT(DISTINCT cpid) as unique_stamps_sold,
                COUNT(CASE WHEN block_time > UNIX_TIMESTAMP() - 3600 THEN 1 END) as sales_1h,
                COUNT(CASE WHEN block_time > UNIX_TIMESTAMP() - 86400 THEN 1 END) as sales_24h,
                COUNT(CASE WHEN block_time > UNIX_TIMESTAMP() - 604800 THEN 1 END) as sales_7d,
                COUNT(CASE WHEN block_time > UNIX_TIMESTAMP() - 2592000 THEN 1 END) as sales_30d,
                SUM(CASE WHEN block_time > UNIX_TIMESTAMP() - 86400 THEN btc_amount END) / 100000000.0 as volume_24h_btc,
                SUM(CASE WHEN block_time > UNIX_TIMESTAMP() - 604800 THEN btc_amount END) / 100000000.0 as volume_7d_btc
            FROM stamp_sales_history
        """
        )
        sales_analysis["sales_activity"] = sales_activity

        # Top selling stamps by volume
        top_stamps_volume = self.fetch_all(
            """
            SELECT 
                ssh.cpid,
                s.stamp,
                COUNT(*) as sale_count,
                SUM(ssh.btc_amount) / 100000000.0 as total_volume_btc,
                AVG(ssh.btc_amount) / 100000000.0 as avg_sale_btc,
                MAX(ssh.block_time) as last_sale_time,
                MIN(ssh.unit_price_sats) as min_price_sats,
                MAX(ssh.unit_price_sats) as max_price_sats
            FROM stamp_sales_history ssh
            JOIN StampTableV4 s ON ssh.cpid = s.cpid
            WHERE ssh.block_time > UNIX_TIMESTAMP() - 604800  -- Last 7 days
            GROUP BY ssh.cpid, s.stamp
            ORDER BY total_volume_btc DESC
            LIMIT 20
        """
        )
        sales_analysis["top_stamps_by_volume"] = top_stamps_volume

        # Sales distribution by type
        sales_by_type = self.fetch_all(
            """
            SELECT 
                sale_type,
                COUNT(*) as sale_count,
                SUM(btc_amount) / 100000000.0 as total_volume_btc,
                AVG(btc_amount) / 100000000.0 as avg_sale_btc,
                COUNT(DISTINCT cpid) as unique_stamps
            FROM stamp_sales_history
            GROUP BY sale_type
            ORDER BY sale_count DESC
        """
        )
        sales_analysis["sales_by_type"] = sales_by_type

        # Recent sales trend
        recent_trend = self.fetch_all(
            """
            SELECT 
                DATE(FROM_UNIXTIME(block_time)) as sale_date,
                COUNT(*) as daily_sales,
                COUNT(DISTINCT cpid) as unique_stamps,
                SUM(btc_amount) / 100000000.0 as daily_volume_btc,
                AVG(btc_amount) / 100000000.0 as avg_sale_btc
            FROM stamp_sales_history
            WHERE block_time > UNIX_TIMESTAMP() - 1209600  -- Last 14 days
            GROUP BY DATE(FROM_UNIXTIME(block_time))
            ORDER BY sale_date DESC
        """
        )
        sales_analysis["daily_sales_trend"] = recent_trend

        # Active traders analysis
        active_traders = self.fetch_one(
            """
            SELECT 
                COUNT(DISTINCT buyer_address) as unique_buyers,
                COUNT(DISTINCT seller_address) as unique_sellers,
                (SELECT COUNT(DISTINCT buyer_address) FROM stamp_sales_history 
                 WHERE block_time > UNIX_TIMESTAMP() - 86400) as active_buyers_24h,
                (SELECT COUNT(DISTINCT seller_address) FROM stamp_sales_history 
                 WHERE block_time > UNIX_TIMESTAMP() - 86400) as active_sellers_24h
            FROM stamp_sales_history
        """
        )
        sales_analysis["trader_activity"] = active_traders

        return sales_analysis

    def analyze_stampscan_performance(self) -> Dict[str, Any]:
        """Analyze StampScan source performance specifically."""
        stampscan_analysis = {}

        # StampScan overall performance
        stampscan_stats = self.fetch_one(
            """
            SELECT 
                COUNT(*) as total_assets,
                COUNT(CASE WHEN price_btc IS NOT NULL THEN 1 END) as assets_with_floor_price,
                COUNT(CASE WHEN holder_count IS NOT NULL THEN 1 END) as assets_with_holders,
                COUNT(CASE WHEN volume_24h_btc IS NOT NULL AND volume_24h_btc > 0 THEN 1 END) as assets_with_volume,
                AVG(source_confidence) as avg_confidence,
                AVG(success_rate_24h) as avg_success_rate,
                AVG(api_response_time_ms) as avg_response_time,
                MIN(last_updated) as oldest_update,
                MAX(last_updated) as newest_update,
                COUNT(CASE WHEN last_updated > DATE_SUB(NOW(), INTERVAL 30 MINUTE) THEN 1 END) as fresh_records
            FROM market_data_sources
            WHERE source_name = 'stampscan' AND asset_type = 'src20'
        """
        )
        stampscan_analysis["stampscan_performance"] = stampscan_stats

        # StampScan data quality for floor prices
        floor_price_coverage = self.fetch_one(
            """
            SELECT 
                COUNT(DISTINCT asset_id) as tokens_tracked,
                COUNT(CASE WHEN price_btc IS NOT NULL THEN 1 END) as tokens_with_floor_price,
                AVG(CASE WHEN price_btc IS NOT NULL THEN source_confidence ELSE NULL END) as avg_floor_price_confidence,
                COUNT(CASE WHEN market_cap_btc IS NOT NULL THEN 1 END) as tokens_with_market_cap
            FROM market_data_sources
            WHERE source_name = 'stampscan' AND asset_type = 'src20'
        """
        )
        stampscan_analysis["floor_price_coverage"] = floor_price_coverage

        # Compare StampScan with other sources
        source_comparison = self.fetch_all(
            """
            SELECT 
                mds.asset_id,
                MAX(CASE WHEN mds.source_name = 'stampscan' THEN mds.price_btc END) as stampscan_price,
                MAX(CASE WHEN mds.source_name = 'kucoin' THEN mds.price_btc END) as kucoin_price,
                MAX(CASE WHEN mds.source_name = 'openstamp' THEN mds.price_btc END) as openstamp_price,
                MAX(CASE WHEN mds.source_name = 'stampscan' THEN mds.holder_count END) as stampscan_holders,
                MAX(CASE WHEN mds.source_name = 'openstamp' THEN mds.holder_count END) as openstamp_holders
            FROM market_data_sources mds
            WHERE mds.asset_type = 'src20' 
                AND mds.source_name IN ('stampscan', 'kucoin', 'openstamp')
            GROUP BY mds.asset_id
            HAVING stampscan_price IS NOT NULL OR kucoin_price IS NOT NULL OR openstamp_price IS NOT NULL
            LIMIT 20
        """
        )
        stampscan_analysis["source_data_comparison"] = source_comparison

        return stampscan_analysis

    def output_html(self, data: Dict):
        """Output report in HTML format."""
        html = """
<!DOCTYPE html>
<html>
<head>
    <title>Market Data Processing Effectiveness Report</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; }
        .header { background: #f4f4f4; padding: 20px; border-radius: 5px; margin-bottom: 30px; }
        .metric-card { background: #fff; border: 1px solid #ddd; padding: 15px; margin: 10px 0; border-radius: 5px; }
        .metric-value { font-size: 24px; font-weight: bold; color: #2c3e50; }
        .metric-label { color: #7f8c8d; font-size: 14px; }
        .section { margin: 30px 0; }
        .good { color: #27ae60; }
        .warning { color: #f39c12; }
        .error { color: #e74c3c; }
        table { width: 100%; border-collapse: collapse; margin: 20px 0; }
        th, td { border: 1px solid #ddd; padding: 12px; text-align: left; }
        th { background-color: #f2f2f2; }
    </style>
</head>
<body>
"""
        html += f"""
    <div class="header">
        <h1>📊 Market Data Processing Effectiveness Report</h1>
        <p><strong>Generated:</strong> {data.get('report_generated', 'Unknown')}</p>
        <p><strong>Analysis Type:</strong> {data.get('analysis_type', 'Standard')}</p>
    </div>
"""

        # Key Metrics Cards
        quality = data.get("data_quality", {})
        performance = data.get("performance_metrics", {})

        if "data_completeness" in quality:
            completeness = quality["data_completeness"]
            coverage = completeness.get("cache_coverage_percent", 0)
            quality_score = completeness.get("avg_quality_score", 0)

            html += """
    <div class="section">
        <h2>📈 Key Metrics</h2>
        <div style="display: flex; gap: 20px;">
"""
            html += f"""
            <div class="metric-card">
                <div class="metric-value {'good' if coverage > 80 else 'warning' if coverage > 60 else 'error'}">{coverage:.1f}%</div>
                <div class="metric-label">Cache Coverage</div>
            </div>
            <div class="metric-card">
                <div class="metric-value {'good' if quality_score > 7 else 'warning' if quality_score > 5 else 'error'}">{quality_score:.2f}/10</div>
                <div class="metric-label">Avg Quality Score</div>
            </div>
"""

            if "cache_efficiency" in performance:
                cache = performance["cache_efficiency"]
                total = cache.get("total_cache", 1)
                hot_percent = cache.get("hot_cache", 0) / total * 100 if total > 0 else 0

                html += f"""
            <div class="metric-card">
                <div class="metric-value {'good' if hot_percent > 70 else 'warning' if hot_percent > 40 else 'error'}">{hot_percent:.1f}%</div>
                <div class="metric-label">Hot Cache</div>
            </div>
"""

            html += """
        </div>
    </div>
"""

        html += """
    <div class="section">
        <h2>📋 Detailed Analysis</h2>
        <p>For complete analysis, use JSON or Markdown output formats.</p>
    </div>
</body>
</html>
"""
        print(html)

    def analyze(self, output_format: str = "json", detailed: bool = False):
        """Perform complete analysis and output results."""
        try:
            # Generate the complete report
            report_data = self.generate_summary_report(detailed=detailed)

            # Output in requested format
            if output_format == "json":
                self.output_json(report_data)
            elif output_format == "csv":
                self.output_csv(report_data)
            elif output_format == "markdown":
                self.output_markdown(report_data)
            elif output_format == "html":
                self.output_html(report_data)
            else:
                print(f"Error: Unsupported output format '{output_format}'", file=sys.stderr)
                sys.exit(1)

        except Exception as e:
            print(f"Error during analysis: {e}", file=sys.stderr)
            sys.exit(1)
        finally:
            if hasattr(self, "db"):
                self.db.close()


def main():
    parser = argparse.ArgumentParser(description="Analyze market data processing effectiveness for Bitcoin Stamps indexer")

    parser.add_argument(
        "--output-format",
        choices=["json", "csv", "markdown", "html"],
        default="json",
        help="Output format for the analysis report (default: json)",
    )

    parser.add_argument(
        "--detailed",
        action="store_true",
        help="Generate detailed analysis including trending stamps and batch processing metrics",
    )

    args = parser.parse_args()

    # Create analyzer and run analysis
    analyzer = MarketDataEffectivenessAnalyzer()
    analyzer.analyze(output_format=args.output_format, detailed=args.detailed)


if __name__ == "__main__":
    main()
