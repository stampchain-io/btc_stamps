#!/usr/bin/env python3
"""
Analyze SRC-20 market data table to provide comprehensive information
about populated data for the frontend team.
"""

import logging
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.index_core.database import DatabaseManager

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def format_btc(value: Decimal | None) -> str:
    """Format BTC values"""
    if value is None or value == 0:
        return "N/A"
    return f"{value:.8f} BTC"


def format_percent(value: Decimal | None) -> str:
    """Format percentage values"""
    if value is None:
        return "N/A"
    return f"{value:.2f}%"


def format_number(value: int | None) -> str:
    """Format large numbers with commas"""
    if value is None:
        return "N/A"
    return f"{value:,}"


def analyze_src20_market_data():
    """Analyze SRC-20 market data table"""
    db_manager = DatabaseManager()
    db = db_manager.connect()

    try:
        logger.info("=" * 80)
        logger.info("SRC-20 MARKET DATA ANALYSIS")
        logger.info("=" * 80)
        logger.info("")

        # 1. Total count of SRC-20 tokens with market data
        cursor = db.execute("""
            SELECT COUNT(*) as total_tokens
            FROM src20_market_data
        """)
        total_tokens = cursor.fetchone()[0]

        logger.info(f"📊 TOTAL SRC-20 TOKENS WITH MARKET DATA: {format_number(total_tokens)}")
        logger.info("")

        # 2. Data completeness analysis
        logger.info("📈 DATA COMPLETENESS ANALYSIS:")
        logger.info("-" * 60)

        cursor = db.execute("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN price_btc IS NOT NULL AND price_btc > 0 THEN 1 END) as has_price,
                COUNT(CASE WHEN holder_count > 0 THEN 1 END) as has_holders,
                COUNT(CASE WHEN volume_24h_btc > 0 THEN 1 END) as has_24h_volume,
                COUNT(CASE WHEN volume_7d_btc > 0 THEN 1 END) as has_7d_volume,
                COUNT(CASE WHEN market_cap_btc > 0 THEN 1 END) as has_market_cap,
                COUNT(CASE WHEN floor_price_btc IS NOT NULL AND floor_price_btc > 0 THEN 1 END) as has_floor_price,
                COUNT(CASE WHEN primary_exchange IS NOT NULL THEN 1 END) as has_exchange_data,
                COUNT(CASE WHEN data_quality_score >= 7 THEN 1 END) as high_quality_data,
                COUNT(CASE WHEN last_updated > DATE_SUB(NOW(), INTERVAL 1 HOUR) THEN 1 END) as updated_last_hour,
                COUNT(CASE WHEN last_updated > DATE_SUB(NOW(), INTERVAL 24 HOUR) THEN 1 END) as updated_last_24h
            FROM src20_market_data
        """)

        stats = cursor.fetchone()
        logger.info(f"  • Tokens with price data: {format_number(stats[1])} ({stats[1]/stats[0]*100:.1f}%)")
        logger.info(f"  • Tokens with holder counts: {format_number(stats[2])} ({stats[2]/stats[0]*100:.1f}%)")
        logger.info(f"  • Tokens with 24h volume: {format_number(stats[3])} ({stats[3]/stats[0]*100:.1f}%)")
        logger.info(f"  • Tokens with 7d volume: {format_number(stats[4])} ({stats[4]/stats[0]*100:.1f}%)")
        logger.info(f"  • Tokens with market cap: {format_number(stats[5])} ({stats[5]/stats[0]*100:.1f}%)")
        logger.info(f"  • Tokens with floor price: {format_number(stats[6])} ({stats[6]/stats[0]*100:.1f}%)")
        logger.info(f"  • Tokens with exchange data: {format_number(stats[7])} ({stats[7]/stats[0]*100:.1f}%)")
        logger.info(f"  • High quality data (score >= 7): {format_number(stats[8])} ({stats[8]/stats[0]*100:.1f}%)")
        logger.info(f"  • Updated in last hour: {format_number(stats[9])} ({stats[9]/stats[0]*100:.1f}%)")
        logger.info(f"  • Updated in last 24h: {format_number(stats[10])} ({stats[10]/stats[0]*100:.1f}%)")
        logger.info("")

        # 3. Top 20 SRC-20 tokens by data quality/completeness
        logger.info("🏆 TOP 20 SRC-20 TOKENS BY DATA QUALITY/COMPLETENESS:")
        logger.info("-" * 120)
        logger.info(
            f"{'Rank':<5} {'Token':<10} {'Price':<15} {'Holders':<10} {'24h Vol':<15} {'Market Cap':<15} {'Quality':<8} {'Source':<15} {'Updated':<20}"
        )
        logger.info("-" * 120)

        cursor = db.execute("""
            SELECT 
                tick,
                price_btc,
                holder_count,
                volume_24h_btc,
                market_cap_btc,
                data_quality_score,
                primary_exchange,
                last_updated,
                price_change_24h_percent,
                CASE 
                    WHEN price_btc IS NOT NULL AND price_btc > 0 THEN 1 ELSE 0 
                END +
                CASE 
                    WHEN holder_count > 0 THEN 1 ELSE 0 
                END +
                CASE 
                    WHEN volume_24h_btc > 0 THEN 1 ELSE 0 
                END +
                CASE 
                    WHEN market_cap_btc > 0 THEN 1 ELSE 0 
                END +
                CASE 
                    WHEN data_quality_score >= 7 THEN 2 ELSE 0 
                END as completeness_score
            FROM src20_market_data
            WHERE (price_btc IS NOT NULL AND price_btc > 0) 
               OR holder_count > 0 
               OR volume_24h_btc > 0
            ORDER BY completeness_score DESC, data_quality_score DESC, volume_24h_btc DESC
            LIMIT 20
        """)

        rank = 1
        for row in cursor.fetchall():
            tick = row[0]
            price = format_btc(row[1]) if row[1] else "N/A"
            holders = format_number(row[2]) if row[2] else "0"
            volume = format_btc(row[3]) if row[3] else "0 BTC"
            market_cap = format_btc(row[4]) if row[4] else "N/A"
            quality = f"{row[5]:.1f}" if row[5] else "N/A"
            source = row[6] or "N/A"
            updated = row[7].strftime("%Y-%m-%d %H:%M") if row[7] else "N/A"

            logger.info(
                f"{rank:<5} {tick:<10} {price:<15} {holders:<10} {volume:<15} {market_cap:<15} {quality:<8} {source:<15} {updated:<20}"
            )
            rank += 1

        logger.info("")

        # 4. Data sources analysis
        logger.info("📡 DATA SOURCES ANALYSIS:")
        logger.info("-" * 60)

        cursor = db.execute("""
            SELECT 
                primary_exchange,
                COUNT(*) as token_count,
                AVG(data_quality_score) as avg_quality,
                AVG(confidence_level) as avg_confidence,
                COUNT(CASE WHEN price_btc IS NOT NULL AND price_btc > 0 THEN 1 END) as has_price,
                COUNT(CASE WHEN volume_24h_btc > 0 THEN 1 END) as has_volume
            FROM src20_market_data
            WHERE primary_exchange IS NOT NULL
            GROUP BY primary_exchange
            ORDER BY token_count DESC
        """)

        for row in cursor.fetchall():
            source = row[0]
            count = row[1]
            avg_quality = row[2] or 0
            avg_confidence = row[3] or 0
            has_price = row[4]
            has_volume = row[5]

            logger.info(f"  • {source}:")
            logger.info(f"    - Tokens: {count}")
            logger.info(f"    - Avg Quality Score: {avg_quality:.1f}/10")
            logger.info(f"    - Avg Confidence: {avg_confidence:.1f}/10")
            logger.info(f"    - With Price Data: {has_price} ({has_price/count*100:.1f}%)")
            logger.info(f"    - With Volume Data: {has_volume} ({has_volume/count*100:.1f}%)")

        logger.info("")

        # 5. Identify gaps and missing data
        logger.info("⚠️  DATA GAPS AND ISSUES:")
        logger.info("-" * 60)

        # Tokens with no price data
        cursor = db.execute("""
            SELECT COUNT(*) 
            FROM src20_market_data 
            WHERE price_btc IS NULL OR price_btc = 0
        """)
        no_price = cursor.fetchone()[0]
        logger.info(f"  • Tokens without price data: {no_price} ({no_price/total_tokens*100:.1f}%)")

        # Tokens with no holder data
        cursor = db.execute("""
            SELECT COUNT(*) 
            FROM src20_market_data 
            WHERE holder_count = 0 OR holder_count IS NULL
        """)
        no_holders = cursor.fetchone()[0]
        logger.info(f"  • Tokens without holder data: {no_holders} ({no_holders/total_tokens*100:.1f}%)")

        # Tokens with no volume data
        cursor = db.execute("""
            SELECT COUNT(*) 
            FROM src20_market_data 
            WHERE volume_24h_btc = 0 AND volume_7d_btc = 0 AND volume_30d_btc = 0
        """)
        no_volume = cursor.fetchone()[0]
        logger.info(f"  • Tokens without any volume data: {no_volume} ({no_volume/total_tokens*100:.1f}%)")

        # Tokens with low quality scores
        cursor = db.execute("""
            SELECT COUNT(*) 
            FROM src20_market_data 
            WHERE data_quality_score < 5
        """)
        low_quality = cursor.fetchone()[0]
        logger.info(f"  • Tokens with low quality score (<5): {low_quality} ({low_quality/total_tokens*100:.1f}%)")

        # Stale data
        cursor = db.execute("""
            SELECT COUNT(*) 
            FROM src20_market_data 
            WHERE last_updated < DATE_SUB(NOW(), INTERVAL 7 DAY)
        """)
        stale_data = cursor.fetchone()[0]
        logger.info(f"  • Tokens with stale data (>7 days): {stale_data} ({stale_data/total_tokens*100:.1f}%)")

        logger.info("")

        # List tokens with missing critical data
        logger.info("  📋 Tokens missing critical data (top 10 by potential importance):")
        cursor = db.execute("""
            SELECT 
                s.tick,
                CASE 
                    WHEN m.price_btc IS NULL OR m.price_btc = 0 THEN 'No Price' 
                    ELSE NULL 
                END as missing_price,
                CASE 
                    WHEN m.holder_count = 0 OR m.holder_count IS NULL THEN 'No Holders' 
                    ELSE NULL 
                END as missing_holders,
                CASE 
                    WHEN m.volume_24h_btc = 0 AND m.volume_7d_btc = 0 THEN 'No Volume' 
                    ELSE NULL 
                END as missing_volume,
                b.holder_count as actual_holders
            FROM src20_market_data m
            LEFT JOIN (
                SELECT tick, COUNT(DISTINCT address) as holder_count
                FROM balances
                WHERE amt > 0 AND p = 'src-20'
                GROUP BY tick
            ) b ON m.tick = b.tick
            WHERE (m.price_btc IS NULL OR m.price_btc = 0)
               OR (m.holder_count = 0 OR m.holder_count IS NULL)
               OR (m.volume_24h_btc = 0 AND m.volume_7d_btc = 0)
            ORDER BY COALESCE(b.holder_count, 0) DESC
            LIMIT 10
        """)

        for row in cursor.fetchall():
            tick = row[0]
            issues = []
            if row[1]:
                issues.append(row[1])
            if row[2]:
                issues.append(row[2])
            if row[3]:
                issues.append(row[3])
            actual_holders = row[4] or 0

            logger.info(f"    - {tick}: {', '.join(issues)} (actual holders in balances: {actual_holders})")

        logger.info("")

        # 6. Update frequency and freshness
        logger.info("🔄 UPDATE FREQUENCY AND DATA FRESHNESS:")
        logger.info("-" * 60)

        cursor = db.execute("""
            SELECT 
                CASE 
                    WHEN last_updated > DATE_SUB(NOW(), INTERVAL 1 HOUR) THEN '< 1 hour'
                    WHEN last_updated > DATE_SUB(NOW(), INTERVAL 6 HOUR) THEN '1-6 hours'
                    WHEN last_updated > DATE_SUB(NOW(), INTERVAL 24 HOUR) THEN '6-24 hours'
                    WHEN last_updated > DATE_SUB(NOW(), INTERVAL 3 DAY) THEN '1-3 days'
                    WHEN last_updated > DATE_SUB(NOW(), INTERVAL 7 DAY) THEN '3-7 days'
                    ELSE '> 7 days'
                END as age_group,
                COUNT(*) as token_count,
                AVG(data_quality_score) as avg_quality
            FROM src20_market_data
            GROUP BY age_group
            ORDER BY 
                CASE age_group
                    WHEN '< 1 hour' THEN 1
                    WHEN '1-6 hours' THEN 2
                    WHEN '6-24 hours' THEN 3
                    WHEN '1-3 days' THEN 4
                    WHEN '3-7 days' THEN 5
                    ELSE 6
                END
        """)

        for row in cursor.fetchall():
            age_group = row[0]
            count = row[1]
            avg_quality = row[2] or 0
            logger.info(f"  • {age_group}: {count} tokens ({count/total_tokens*100:.1f}%) - Avg Quality: {avg_quality:.1f}")

        logger.info("")

        # Update frequency distribution
        cursor = db.execute("""
            SELECT 
                update_frequency_minutes,
                COUNT(*) as token_count
            FROM src20_market_data
            GROUP BY update_frequency_minutes
            ORDER BY update_frequency_minutes
        """)

        logger.info("  📊 Update Frequency Distribution:")
        for row in cursor.fetchall():
            freq = row[0]
            count = row[1]
            logger.info(f"    - Every {freq} minutes: {count} tokens")

        logger.info("")

        # Recommendations
        logger.info("💡 RECOMMENDATIONS FOR FRONTEND TEAM:")
        logger.info("-" * 60)
        logger.info("  1. CRITICAL GAPS:")
        logger.info(f"     - {no_price} tokens ({no_price/total_tokens*100:.1f}%) lack price data")
        logger.info(f"     - {no_holders} tokens ({no_holders/total_tokens*100:.1f}%) lack holder counts")
        logger.info(f"     - Consider hiding tokens with data_quality_score < 5")
        logger.info("")
        logger.info("  2. DATA FRESHNESS:")
        logger.info("     - Implement visual indicators for data age")
        logger.info("     - Show 'last updated' timestamps for transparency")
        logger.info("     - Consider warning icons for data > 24 hours old")
        logger.info("")
        logger.info("  3. DATA SOURCES:")
        logger.info("     - Display data source attribution where available")
        logger.info("     - Use confidence_level to show data reliability")
        logger.info("     - Aggregate multiple sources when available")
        logger.info("")
        logger.info("  4. MISSING DATA HANDLING:")
        logger.info("     - Use placeholder values or 'N/A' for missing data")
        logger.info("     - Prioritize tokens with completeness_score >= 4")
        logger.info("     - Consider fetching holder counts from balances table as fallback")

        logger.info("")
        logger.info("=" * 80)

    except Exception as e:
        logger.error(f"Error analyzing SRC-20 market data: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    analyze_src20_market_data()
