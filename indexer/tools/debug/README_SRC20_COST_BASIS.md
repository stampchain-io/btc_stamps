# SRC-20 Cost Basis Analyzer

A utility script to analyze the cost basis of SRC-20 tokens by examining MINT transactions. This tool calculates the cost per token based on transaction fees and stamp dust outputs (P2WSH or multisig) spent during minting.

## Features

- Query all MINT operations for any SRC-20 token
- Calculate total cost (miner fees + stamp dust outputs) for each mint
- Supports both P2WSH (newer) and multisig (older) output formats
- Compute cost per token in both satoshis and BTC
- Generate comprehensive statistics (min, max, average, median costs)
- Export data in JSON or CSV format
- Create visual charts showing token price over time
- List all mintable SRC-20 tokens in the database

## Cost Calculation Methodology

The total cost for minting SRC-20 tokens includes:
1. **Miner fees**: The transaction fee paid to miners
2. **Stamp dust outputs**: The sum of ALL P2WSH or multisig outputs in the transaction:
   - **P2WSH outputs** (newer format): typically 330 satoshis each
   - **Multisig outputs** (older format): typically 546 satoshis each
   - Some transactions may have multiple stamp outputs, all are included in the cost

**Note**: Change outputs are NOT included in the cost calculation as they are neither P2WSH nor multisig outputs. Only the actual costs associated with creating the SRC-20 mint transaction are counted.

### Average Cost Calculation
The script uses a **weighted average** for the overall cost per token, calculated as:
- Total cost of all mints ÷ Total tokens minted

This provides the true average cost basis across all tokens, properly accounting for the fact that different mints create different amounts of tokens. A transaction minting 1 million tokens has more weight than one minting 1,000 tokens.

## Installation

1. Ensure you have Python 3.7+ installed
2. Install required dependencies:
```bash
cd indexer
poetry install
```

3. (Optional) For Bitcoin RPC support to fetch transaction fees:
```bash
poetry add python-bitcoinrpc
```

4. (Optional) For chart generation, ensure matplotlib is installed:
```bash
poetry add matplotlib
```

## Configuration

The script uses environment variables from your `.env` file:

### Database Configuration
- `RDS_HOSTNAME`: Database host
- `RDS_USER`: Database username
- `RDS_PASSWORD`: Database password
- `RDS_DATABASE`: Database name (default: btc_stamps)

### Bitcoin Node Configuration (Optional)
For more accurate fee data, you can configure Bitcoin RPC access:
- `BITCOIN_RPC_URL`: Full RPC URL (e.g., `http://user:pass@localhost:8332`)
- Or use individual settings:
  - `RPC_IP`: Bitcoin node IP address (default: 127.0.0.1)
  - `RPC_PORT`: Bitcoin node RPC port (default: 8332)
  - `RPC_USER`: RPC username
  - `RPC_PASSWORD`: RPC password

Without Bitcoin RPC configured, the script will use transaction fee data from the database or estimates.

### Example .env file
```bash
# Database configuration
RDS_HOSTNAME=localhost
RDS_USER=stamps_user
RDS_PASSWORD=your_password
RDS_DATABASE=btc_stamps

# Bitcoin RPC configuration (optional)
RPC_IP=127.0.0.1
RPC_PORT=8332
RPC_USER=your_rpc_user
RPC_PASSWORD=your_rpc_password
```

## Usage

### Basic Usage

Analyze the STAMP token:
```bash
python src20_cost_basis_analyzer.py --tick STAMP
```

### Generate a Chart

Create a visual chart showing token price over time:
```bash
python src20_cost_basis_analyzer.py --tick KEVIN --chart
```

### Export to CSV

Export the analysis to CSV format:
```bash
python src20_cost_basis_analyzer.py --tick STAMP --output-format csv > stamp_analysis.csv
```

### List Available Tokens

See all SRC-20 tokens with mint transactions:
```bash
python src20_cost_basis_analyzer.py --list
```

## Output Formats

### JSON Output (Default)
```json
{
  "token_info": {
    "tick": "STAMP",
    "max_supply": 1000000000.0,
    "decimals": 18,
    "creator": "1NChfewU45oy7Dgn51HwkBFSixaTnyakfj",
    "deploy_block": 779652,
    "deploy_time": "2023-03-09 00:00:00"
  },
  "statistics": {
    "total_mints": 150,
    "total_tokens_minted": 5000000.0,
    "total_cost_btc": 0.0245,
    "average_cost_per_token_btc": 0.0000000049,
    "min_cost_per_token_btc": 0.0000000012,
    "max_cost_per_token_btc": 0.0000000198,
    "median_cost_per_token_btc": 0.0000000041,
    "unique_minters": 87
  },
  "mint_transactions": [...]
}
```

### CSV Output
The CSV format includes the following columns:
- `block_index`: Block number
- `tx_hash`: Transaction hash
- `block_time`: Timestamp
- `minter_address`: Address that minted tokens
- `tokens_minted`: Number of tokens minted
- `fee_satoshis`: Transaction fee in satoshis
- `fee_rate_sat_vb`: Transaction fee rate in sat/vB
- `stamp_dust_satoshis`: Stamp output dust value (P2WSH or multisig)
- `total_cost_satoshis`: Total cost (fee + dust)
- `total_cost_btc`: Total cost in BTC
- `cost_per_token_sats`: Cost per token in satoshis
- `cost_per_token_btc`: Cost per token in BTC

## Charts

When using the `--chart` option, the script generates three charts:
1. **Cost per Token Over Time**: Shows how the minting cost per token changed over time in satoshis (log scale for better visualization)
2. **Cumulative Minting**: Shows total tokens minted and cumulative cost over time
3. **Fee Rates Over Time**: Shows the Bitcoin network fee rates (sat/vB) when each mint occurred

Charts are saved as `{tick}_cost_analysis.png` in the current directory. The cost per token is displayed in satoshis instead of BTC for better readability (e.g., "153 sats" instead of "0.00000153 BTC").

## Use Cases

1. **Fair Launch Analysis**: Determine if a token had a fair launch by examining early minting costs
2. **Market Analysis**: Track how minting costs evolved as the token gained popularity
3. **Cost Basis Tracking**: Calculate the actual cost basis for tax or accounting purposes
4. **Distribution Analysis**: See how token minting was distributed across different addresses

## Notes

- The script connects directly to the Bitcoin Stamps database
- Large tokens with many mints may take longer to analyze
- Chart generation requires matplotlib to be installed
- All costs are calculated in satoshis for precision, then converted to BTC for display
- P2WSH dust values may vary but typically range from 330-546 satoshis

## Troubleshooting

### Error: 'fee'
This error occurs when the script cannot fetch transaction fees. Solutions:
1. Ensure your Bitcoin node is running and accessible
2. Configure RPC credentials in your `.env` file
3. Install python-bitcoinrpc: `poetry add python-bitcoinrpc`

### No tokens found
This means the database is empty or the token doesn't exist:
1. Check if the indexer has been run to populate the database
2. Try using the exact case for the token ticker (e.g., 'STAMP' vs 'stamp')
3. Use `--list` to see all available tokens

### Transaction not found in node
This can happen if:
1. Your Bitcoin node is not fully synced
2. The transaction is very old and your node is pruned
3. You're using testnet/regtest but the transactions are mainnet

### High memory usage
For tokens with many transactions:
- The script caches fee lookups to avoid repeated RPC calls
- Consider processing in smaller batches by modifying the script
- Ensure sufficient RAM for large datasets

## Performance Tips

1. **First run will be slow**: The script needs to query each transaction from the Bitcoin node
2. **Subsequent runs use cached data**: Fee lookups are cached in memory during the session
3. **Large tokens**: For tokens with thousands of mints, expect processing to take several minutes
4. **Network latency**: If your Bitcoin node is remote, consider running the script on the same machine

## Notes

- The script connects directly to the Bitcoin Stamps database
- Transaction fees MUST be fetched from a Bitcoin node (database fees are unreliable)
- All costs are calculated in satoshis for precision, then converted to BTC for display
- The script automatically detects the output format:
  - P2WSH outputs (newer format): typically 330 satoshis
  - Multisig outputs (older format): typically 546 satoshis
- The script requires both database access AND Bitcoin RPC access to function 