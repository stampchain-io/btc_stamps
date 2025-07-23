#!/usr/bin/env python3
"""Comprehensive validation of STAMP token market data for frontend team report."""

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

from src.index_core.database_manager import DatabaseManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def format_timestamp(ts) -> str:
    """Format timestamp for readable display."""
    if not ts:
        return "Never"
    if isinstance(ts, str):
        return ts
    return ts.strftime("%Y-%m-%d %H:%M:%S UTC")


def format_price(value, decimals=8) -> str:
    """Format price values with appropriate precision."""
    if value is None:
        return "N/A"
    if value == 0:
        return "0"
    return f"{value:.{decimals}f}".rstrip("0").rstrip(".")


def format_number(value) -> str:
    """Format large numbers with commas."""
    if value is None:
        return "N/A"
    if isinstance(value, (int, float)):
        return f"{value:,.0f}"
    return str(value)


def check_src20_market_data(db, tick: str) -> Optional[Dict]:
    """Check src20_market_data table for token data."""
    with db.cursor(DictCursor) as cursor:
        # Try both uppercase and lowercase
        query = """
        SELECT 
            tick,
            price_btc,
            price_usd,
            floor_price_btc,
            price_source_type,
            market_cap_btc,
            market_cap_usd,
            volume_24h_btc,
            volume_7d_btc,
            volume_30d_btc,
            total_volume_btc,
            price_change_24h_percent,
            price_change_7d_percent,
            price_change_30d_percent,
            holder_count,
            circulating_supply,
            max_supply,
            progress_percentage,
            total_minted,
            total_mints,
            primary_exchange,
            exchange_sources,
            data_quality_score,
            confidence_level,
            last_updated,
            last_price_update,
            update_frequency_minutes,
            created_at
        FROM src20_market_data
        WHERE UPPER(tick) = UPPER(%s)
        ORDER BY last_updated DESC
        LIMIT 1
        """
        cursor.execute(query, (tick,))
        return cursor.fetchone()


def check_stamp_market_data(db, cpid: str) -> Optional[Dict]:
    """Check stamp_market_data table for token data."""
    with db.cursor(DictCursor) as cursor:
        # Try both uppercase and lowercase
        # Note: stamp_market_data has different column names than src20_market_data
        query = """
        SELECT 
            cpid,
            floor_price_btc,
            recent_sale_price_btc,
            open_dispensers_count,
            closed_dispensers_count,
            total_dispensers_count,
            holder_count,
            unique_holder_count,
            top_holder_percentage,
            holder_distribution_score,
            volume_24h_btc,
            volume_7d_btc,
            volume_30d_btc,
            total_volume_btc,
            price_source,
            volume_sources,
            data_quality_score,
            confidence_level,
            last_sale_tx_hash,
            last_sale_buyer_address,
            last_sale_dispenser_address,
            last_sale_btc_amount,
            last_sale_dispenser_tx_hash,
            activity_level,
            last_activity_time,
            last_updated,
            last_dispenser_block,
            last_balance_block,
            last_price_update,
            last_sale_block_index,
            update_frequency_minutes,
            created_at
        FROM stamp_market_data
        WHERE UPPER(cpid) = UPPER(%s)
        ORDER BY last_updated DESC
        LIMIT 1
        """
        cursor.execute(query, (cpid,))
        return cursor.fetchone()


def get_other_src20_examples(db, limit: int = 5) -> List[Dict]:
    """Get examples of other SRC-20 tokens with market data."""
    with db.cursor(DictCursor) as cursor:
        query = """
        SELECT 
            tick,
            price_btc,
            price_usd,
            market_cap_btc,
            market_cap_usd,
            volume_24h_btc,
            volume_7d_btc,
            holder_count,
            primary_exchange,
            exchange_sources,
            data_quality_score,
            confidence_level,
            progress_percentage,
            last_updated
        FROM src20_market_data
        WHERE (price_btc IS NOT NULL AND price_btc > 0)
           OR (price_usd IS NOT NULL AND price_usd > 0)
           OR (market_cap_btc IS NOT NULL AND market_cap_btc > 0)
           OR (volume_24h_btc IS NOT NULL AND volume_24h_btc > 0)
        ORDER BY 
            CASE 
                WHEN volume_24h_btc IS NOT NULL AND volume_24h_btc > 0 THEN volume_24h_btc 
                ELSE 0 
            END DESC,
            CASE
                WHEN holder_count IS NOT NULL THEN holder_count
                ELSE 0
            END DESC,
            last_updated DESC
        LIMIT %s
        """
        cursor.execute(query, (limit,))
        return cursor.fetchall()


def get_stamp_info(db, tick: str) -> Optional[Dict]:
    """Get basic info about STAMP from SRC20Valid table."""
    with db.cursor(DictCursor) as cursor:
        # First check if STAMP exists as a deploy in SRC20Valid
        query = """
        SELECT 
            tick,
            max,
            deci as decimals,
            block_index as deploy_block,
            creator,
            block_time,
            tx_hash,
            lim
        FROM SRC20Valid
        WHERE UPPER(tick) = UPPER(%s) AND op = 'DEPLOY'
        ORDER BY block_index ASC
        LIMIT 1
        """
        cursor.execute(query, (tick,))
        deploy_info = cursor.fetchone()

        if deploy_info:
            # Get current holder count from balances
            holder_query = """
            SELECT COUNT(DISTINCT address) as current_holders
            FROM balances
            WHERE UPPER(tick) = UPPER(%s) AND amt > 0
            """
            cursor.execute(holder_query, (tick,))
            holder_result = cursor.fetchone()

            # Merge the data
            if holder_result:
                deploy_info["current_holders"] = holder_result["current_holders"]
            else:
                deploy_info["current_holders"] = 0

            # Rename max to max_supply for consistency
            deploy_info["max_supply"] = deploy_info.pop("max", None)

        return deploy_info


def analyze_data_sources(exchange_sources: Optional[str]) -> Dict[str, bool]:
    """Analyze which data sources are active."""
    sources = {"KuCoin": False, "OpenStamp": False, "StampScan": False, "Other": False}

    if not exchange_sources:
        return sources

    try:
        if isinstance(exchange_sources, str):
            sources_data = json.loads(exchange_sources)
        else:
            sources_data = exchange_sources

        for source in sources_data:
            if isinstance(source, dict):
                source_name = source.get("source", "").lower()
                if "kucoin" in source_name:
                    sources["KuCoin"] = True
                elif "openstamp" in source_name:
                    sources["OpenStamp"] = True
                elif "stampscan" in source_name:
                    sources["StampScan"] = True
                else:
                    sources["Other"] = True
    except:
        pass

    return sources


def normalize_stamp_data(stamp_data: Optional[Dict], table_source: str) -> Optional[Dict]:
    """Normalize stamp data from different table formats to a common structure."""
    if not stamp_data:
        return None

    normalized = stamp_data.copy()

    if table_source == "stamp_market_data":
        # Map stamp_market_data columns to common names
        normalized["price_btc"] = stamp_data.get("floor_price_btc") or stamp_data.get("recent_sale_price_btc")
        normalized["price_usd"] = None  # Not available in stamp_market_data
        normalized["market_cap_btc"] = None  # Not available in stamp_market_data
        normalized["market_cap_usd"] = None  # Not available in stamp_market_data
        normalized["primary_exchange"] = stamp_data.get("price_source")
        normalized["exchange_sources"] = stamp_data.get("volume_sources")
        # Keep other fields as is

    return normalized


def generate_report(
    stamp_data: Optional[Dict], stamp_info: Optional[Dict], other_examples: List[Dict], table_source: str
) -> str:
    """Generate comprehensive report for frontend team."""
    report = []
    report.append("=" * 80)
    report.append("STAMP TOKEN MARKET DATA VALIDATION REPORT")
    report.append("=" * 80)
    report.append(f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    report.append("")

    # Basic token info
    if stamp_info:
        report.append("TOKEN INFORMATION:")
        report.append("-" * 40)
        report.append(f"Tick: {stamp_info['tick']}")
        report.append(f"Max Supply: {format_number(stamp_info['max_supply'])}")
        report.append(f"Decimals: {stamp_info['decimals']}")
        report.append(f"Deploy Block: {format_number(stamp_info['deploy_block'])}")
        report.append(f"Deploy Time: {format_timestamp(stamp_info['block_time'])}")
        report.append(f"Deploy TX: {stamp_info['tx_hash']}")
        report.append(f"Creator: {stamp_info['creator']}")
        if stamp_info.get("lim"):
            report.append(f"Mint Limit: {format_number(stamp_info['lim'])}")
        report.append(f"Current Holders (from balances): {format_number(stamp_info['current_holders'])}")
        report.append("")

    # Market data status
    report.append("MARKET DATA STATUS:")
    report.append("-" * 40)

    if stamp_data:
        report.append(f"✅ STAMP market data FOUND in {table_source} table")
        report.append("")

        # Price data
        report.append("PRICE DATA:")
        if table_source == "stamp_market_data":
            # For stamp_market_data table
            report.append(f"  Floor Price (BTC): {format_price(stamp_data.get('floor_price_btc'))} BTC")
            report.append(f"  Recent Sale Price (BTC): {format_price(stamp_data.get('recent_sale_price_btc'))} BTC")
            if stamp_data.get("last_sale_btc_amount"):
                report.append(
                    f"  Last Sale Amount: {stamp_data['last_sale_btc_amount']} satoshis ({stamp_data['last_sale_btc_amount'] / 100000000:.8f} BTC)"
                )
        else:
            # For src20_market_data table
            report.append(f"  BTC Price: {format_price(stamp_data.get('price_btc'))} BTC")
            report.append(f"  USD Price: ${format_price(stamp_data.get('price_usd'), 2)}")
            if "floor_price_btc" in stamp_data:
                report.append(f"  Floor Price (BTC): {format_price(stamp_data['floor_price_btc'])} BTC")
            if "price_source_type" in stamp_data:
                report.append(f"  Price Source Type: {stamp_data['price_source_type'] or 'unknown'}")
        report.append("")

        # Market metrics
        report.append("MARKET METRICS:")
        report.append(f"  Market Cap (BTC): {format_price(stamp_data['market_cap_btc'])} BTC")
        report.append(f"  Market Cap (USD): ${format_number(stamp_data['market_cap_usd'])}")
        report.append(f"  24h Volume (BTC): {format_price(stamp_data['volume_24h_btc'])} BTC")
        report.append(f"  7d Volume (BTC): {format_price(stamp_data['volume_7d_btc'])} BTC")
        if "volume_30d_btc" in stamp_data:
            report.append(f"  30d Volume (BTC): {format_price(stamp_data['volume_30d_btc'])} BTC")
        if "total_volume_btc" in stamp_data:
            report.append(f"  Total Volume (BTC): {format_price(stamp_data['total_volume_btc'])} BTC")
        report.append(f"  Holder Count: {format_number(stamp_data['holder_count'])}")
        report.append("")

        # Price changes (if available)
        if "price_change_24h_percent" in stamp_data and stamp_data["price_change_24h_percent"] is not None:
            report.append("PRICE CHANGES:")
            report.append(f"  24h Change: {stamp_data['price_change_24h_percent']:.2f}%")
            if stamp_data.get("price_change_7d_percent") is not None:
                report.append(f"  7d Change: {stamp_data['price_change_7d_percent']:.2f}%")
            if stamp_data.get("price_change_30d_percent") is not None:
                report.append(f"  30d Change: {stamp_data['price_change_30d_percent']:.2f}%")
            report.append("")

        # Supply data (if available)
        if "circulating_supply" in stamp_data:
            report.append("SUPPLY DATA:")
            report.append(f"  Circulating Supply: {format_number(stamp_data['circulating_supply'])}")
            report.append(f"  Max Supply: {format_number(stamp_data['max_supply'])}")
            if stamp_data.get("progress_percentage") is not None:
                report.append(f"  Minting Progress: {stamp_data['progress_percentage']:.2f}%")
            if stamp_data.get("total_minted") is not None:
                report.append(f"  Total Minted: {format_number(stamp_data['total_minted'])}")
            if stamp_data.get("total_mints") is not None:
                report.append(f"  Total Mint Operations: {format_number(stamp_data['total_mints'])}")
            report.append("")

        # Exchange info
        report.append("EXCHANGE INFORMATION:")
        report.append(f"  Primary Exchange: {stamp_data['primary_exchange'] or 'Not specified'}")
        report.append(f"  Data Quality Score: {stamp_data['data_quality_score'] or 'N/A'}")
        if "confidence_level" in stamp_data:
            report.append(f"  Confidence Level: {stamp_data['confidence_level'] or 'N/A'}")
        report.append("")

        # Data sources
        report.append("ACTIVE DATA SOURCES:")
        sources = analyze_data_sources(stamp_data["exchange_sources"])
        for source, is_active in sources.items():
            status = "✅ Active" if is_active else "❌ Inactive"
            report.append(f"  {source}: {status}")
        report.append("")

        # Stamp-specific data (if from stamp_market_data table)
        if table_source == "stamp_market_data" and stamp_data:
            report.append("DISPENSER DATA:")
            report.append(f"  Open Dispensers: {format_number(stamp_data.get('open_dispensers_count', 0))}")
            report.append(f"  Closed Dispensers: {format_number(stamp_data.get('closed_dispensers_count', 0))}")
            report.append(f"  Total Dispensers: {format_number(stamp_data.get('total_dispensers_count', 0))}")
            report.append("")

            if stamp_data.get("last_sale_tx_hash"):
                report.append("LAST SALE DETAILS:")
                report.append(f"  TX Hash: {stamp_data['last_sale_tx_hash']}")
                report.append(f"  Buyer: {stamp_data.get('last_sale_buyer_address', 'N/A')}")
                report.append(f"  Dispenser: {stamp_data.get('last_sale_dispenser_address', 'N/A')}")
                report.append(f"  Block Index: {format_number(stamp_data.get('last_sale_block_index', 'N/A'))}")
                report.append("")

            report.append("HOLDER DISTRIBUTION:")
            report.append(f"  Unique Holders: {format_number(stamp_data.get('unique_holder_count', 0))}")
            report.append(f"  Top Holder %: {stamp_data.get('top_holder_percentage', 0):.2f}%")
            report.append(f"  Distribution Score: {stamp_data.get('holder_distribution_score', 0):.2f}/100")
            report.append(f"  Activity Level: {stamp_data.get('activity_level', 'Unknown')}")
            report.append("")

        # Update timestamps
        report.append("UPDATE INFORMATION:")
        report.append(f"  Last Updated: {format_timestamp(stamp_data.get('last_updated'))}")
        report.append(f"  First Created: {format_timestamp(stamp_data.get('created_at'))}")
        if table_source == "stamp_market_data":
            report.append(f"  Last Price Update: {format_timestamp(stamp_data.get('last_price_update'))}")
            report.append(f"  Last Dispenser Block: {format_number(stamp_data.get('last_dispenser_block', 'N/A'))}")
            report.append(f"  Last Balance Block: {format_number(stamp_data.get('last_balance_block', 'N/A'))}")
            report.append(f"  Update Frequency: {stamp_data.get('update_frequency_minutes', 'N/A')} minutes")

        # Data freshness check
        if stamp_data["last_updated"]:
            try:
                last_update = stamp_data["last_updated"]
                if isinstance(last_update, str):
                    last_update = datetime.fromisoformat(last_update.replace("Z", "+00:00"))

                time_diff = datetime.utcnow() - last_update.replace(tzinfo=None)
                hours_ago = time_diff.total_seconds() / 3600

                if hours_ago < 1:
                    freshness = "🟢 Very Fresh (< 1 hour)"
                elif hours_ago < 24:
                    freshness = f"🟡 Fresh ({hours_ago:.1f} hours ago)"
                else:
                    freshness = f"🔴 Stale ({hours_ago:.1f} hours ago)"

                report.append(f"  Data Freshness: {freshness}")
            except:
                pass

        report.append("")

        # Raw exchange sources data
        if stamp_data["exchange_sources"]:
            report.append("RAW EXCHANGE SOURCES DATA:")
            report.append("-" * 40)
            try:
                sources_data = (
                    json.loads(stamp_data["exchange_sources"])
                    if isinstance(stamp_data["exchange_sources"], str)
                    else stamp_data["exchange_sources"]
                )
                report.append(json.dumps(sources_data, indent=2))
            except:
                report.append(str(stamp_data["exchange_sources"]))
            report.append("")

    else:
        report.append("❌ STAMP market data NOT FOUND in database")
        report.append("")
        report.append("TROUBLESHOOTING:")
        report.append("1. Check if STAMP token exists in src20 table")
        report.append("2. Verify market data processor is running")
        report.append("3. Check logs for any errors related to STAMP data fetching")
        report.append("4. Ensure external API connections are working")
        report.append("")

    # Other tokens example
    if other_examples:
        report.append("OTHER SRC-20 TOKENS WITH MARKET DATA (for comparison):")
        report.append("-" * 100)
        report.append(
            f"{'Token':<10} {'BTC Price':<15} {'USD Price':<12} {'24h Vol':<12} {'Holders':<10} {'Progress':<10} {'Exchange':<15}"
        )
        report.append("-" * 100)

        for token in other_examples:
            # Determine exchange sources
            sources = analyze_data_sources(token.get("exchange_sources"))
            active_sources = [k for k, v in sources.items() if v and k != "Other"]
            exchange_str = ", ".join(active_sources) if active_sources else token.get("primary_exchange", "Unknown")

            report.append(
                f"{token['tick']:<10} "
                f"{format_price(token['price_btc']):<15} "
                f"${format_price(token['price_usd'], 2):<11} "
                f"{format_price(token['volume_24h_btc']):<12} "
                f"{format_number(token['holder_count']):<10} "
                f"{(str(round(token.get('progress_percentage', 0), 1)) + '%') if token.get('progress_percentage') is not None else 'N/A':<10} "
                f"{exchange_str[:15]:<15}"
            )

        report.append("-" * 100)
        report.append("")

        # Add summary of data sources found
        all_sources = set()
        for token in other_examples:
            sources = analyze_data_sources(token.get("exchange_sources"))
            all_sources.update([k for k, v in sources.items() if v])

        report.append(f"Data Sources Found Across All Tokens: {', '.join(sorted(all_sources))}")
        report.append("")

        # Count tokens by primary exchange
        exchange_counts = {}
        for token in other_examples:
            exchange = token.get("primary_exchange", "Unknown")
            exchange_counts[exchange] = exchange_counts.get(exchange, 0) + 1

        report.append("Tokens by Primary Exchange:")
        for exchange, count in sorted(exchange_counts.items(), key=lambda x: x[1], reverse=True):
            report.append(f"  {exchange}: {count} tokens")

    report.append("")
    report.append("=" * 80)
    report.append("END OF REPORT")
    report.append("=" * 80)

    return "\n".join(report)


def main():
    """Main function to validate STAMP market data."""
    try:
        logger.info("Starting STAMP market data validation...")

        # Connect to database
        db_manager = DatabaseManager()
        db = db_manager.connect()

        # Check for STAMP data in src20_market_data
        logger.info("Checking src20_market_data table for STAMP...")
        stamp_src20_data = check_src20_market_data(db, "STAMP")

        # Check for STAMP data in stamp_market_data
        logger.info("Checking stamp_market_data table for STAMP...")
        stamp_market_data = check_stamp_market_data(db, "STAMP")

        # Determine which data to use
        stamp_data = None
        table_source = None
        if stamp_src20_data:
            stamp_data = stamp_src20_data
            table_source = "src20_market_data"
        elif stamp_market_data:
            # Normalize stamp_market_data to common format
            stamp_data = normalize_stamp_data(stamp_market_data, "stamp_market_data")
            table_source = "stamp_market_data"

        # Get STAMP token info
        logger.info("Getting STAMP token information...")
        stamp_info = get_stamp_info(db, "STAMP")

        # Get other examples
        logger.info("Getting other SRC-20 tokens with market data...")
        other_examples = get_other_src20_examples(db, limit=10)

        # Generate report
        report = generate_report(stamp_data, stamp_info, other_examples, table_source)

        # Print report
        print(report)

        # Save report to file
        report_filename = f"stamp_market_data_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(report_filename, "w") as f:
            f.write(report)

        logger.info(f"Report saved to: {report_filename}")

        # Close database connection
        db.close()

    except Exception as e:
        logger.error(f"Error validating STAMP market data: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
