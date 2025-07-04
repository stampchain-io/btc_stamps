# Recent Sales Data Enhancement for Frontend Team

## Overview
We've implemented enhanced recent sales tracking in the Bitcoin Stamps market data system to provide detailed information about the most recent sale for each stamp. This enhancement captures comprehensive sale details directly from Counterparty dispense events.

## New Database Fields Added to `stamp_market_data`

The following columns have been added to provide detailed recent sale information:

| Column Name | Type | Description |
|------------|------|-------------|
| `last_sale_tx_hash` | VARCHAR(64) | Transaction hash of the most recent sale |
| `last_sale_buyer_address` | VARCHAR(64) | Bitcoin address of the buyer |
| `last_sale_dispenser_address` | VARCHAR(64) | Bitcoin address of the dispenser |
| `last_sale_btc_amount` | BIGINT | Amount paid in satoshis |
| `last_sale_dispenser_tx_hash` | VARCHAR(64) | Transaction hash of the dispenser creation (optional) |
| `last_sale_block_index` | INT | Block number where the sale occurred |

## New Index for Performance

- **Index Name**: `idx_recent_sales`
- **Columns**: `last_price_update DESC, volume_24h_btc DESC`
- **Purpose**: Optimizes queries for finding recent sales and sorting by activity

## API Response Enhancement

When querying stamp market data, you'll now receive these additional fields:

```json
{
  "cpid": "A14962368961442238000",
  "recent_sale_price_btc": 0.00012345,
  "last_price_update": "2025-07-04T12:34:56",
  "last_sale_tx_hash": "e987dde81f56c9cf7e7ed886950de385308c956c75e310072622680eda0dfb1a",
  "last_sale_buyer_address": "bcrt1qhdflstsldvu8c0exy245yfj6awhgwyts8uaq0x",
  "last_sale_dispenser_address": "bcrt1qk5zhztccce0dcgk5jc8js6t84vwhs07tjrjgsv",
  "last_sale_btc_amount": 1000,  // in satoshis
  "last_sale_dispenser_tx_hash": "1015181935f5a97c829980a4685d923a1444d1f03c6b2b011434c45762d36962",
  "last_sale_block_index": 903906,
  // ... other existing fields
}
```

## Data Sources

The recent sales data is populated from:
1. **Counterparty Dispensers**: Automated vending machines for stamps
2. **Future**: Atomic swaps and other sale types (dispenser_tx_hash will be null)

## Implementation Details

### Data Collection Process
1. Market data jobs run every 15 minutes for stamps
2. Fetches dispense events from Counterparty API with full dispenser details
3. Tracks the most recent sale by block time
4. Stores comprehensive sale metadata for frontend display

### Performance Optimizations
- Increased worker count from 3 to 10 for faster processing
- Using `verbose=true` on API calls to get dispenser data in single request
- Batch processing 100 stamps at a time
- Caching holder data for distribution metrics

### Data Completeness
- All fields are populated when a dispenser sale occurs
- `last_sale_dispenser_tx_hash` may be null for non-dispenser sales (future)
- Historical data is being backfilled for existing stamps with sales

## Query Examples

### Get stamps with recent sales
```sql
SELECT cpid, last_sale_tx_hash, last_sale_buyer_address, 
       last_sale_btc_amount, last_price_update
FROM stamp_market_data
WHERE last_sale_tx_hash IS NOT NULL
ORDER BY last_price_update DESC
LIMIT 100;
```

### Get top sales in last 24 hours
```sql
SELECT cpid, last_sale_btc_amount, last_sale_buyer_address,
       last_sale_tx_hash, last_price_update
FROM stamp_market_data
WHERE last_price_update > DATE_SUB(NOW(), INTERVAL 24 HOUR)
  AND last_sale_tx_hash IS NOT NULL
ORDER BY last_sale_btc_amount DESC
LIMIT 50;
```

## Future Enhancements

1. **Block-based dispense fetching**: When caught up to chain tip, fetch dispenses by block for real-time updates
2. **Atomic swap support**: Capture sales from atomic swaps (different data structure)
3. **Multi-sale history**: Track last N sales instead of just the most recent

## Migration Notes

- Schema changes are automatically applied on indexer startup
- Existing market data records will be updated as stamps are processed
- Full backfill expected to complete within 24-48 hours at current rate

## Support

For any issues or questions about the recent sales data:
1. Check the market data validation script: `tools/debug/validate_production_market_data.py`
2. Monitor indexer logs for "Captured recent sale" messages
3. Contact the indexer team for assistance