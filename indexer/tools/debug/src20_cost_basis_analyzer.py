#!/usr/bin/env python3
"""
SRC-20 Cost Basis Analyzer

This script analyzes the cost basis of SRC-20 tokens by examining MINT transactions.
It calculates the cost per token based on transaction fees and P2WSH dust outputs spent during minting.

Usage:
    python src20_cost_basis_analyzer.py [--tick TICKER] [--output-format json|csv] [--chart]
    
Examples:
    python src20_cost_basis_analyzer.py --tick STAMP
    python src20_cost_basis_analyzer.py --tick KEVIN --chart
    python src20_cost_basis_analyzer.py --tick STAMP --output-format csv
"""

import argparse
import json
import csv
import sys
import os
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional
import pymysql
from dotenv import load_dotenv

# Try to import Bitcoin RPC library for direct node queries
try:
    from bitcoinrpc.authproxy import AuthServiceProxy
    HAS_BITCOIN_RPC = True
except ImportError:
    HAS_BITCOIN_RPC = False
    print("Warning: python-bitcoinrpc not installed. Bitcoin node queries disabled.", file=sys.stderr)

# Try to import matplotlib for charting support
try:
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    print("Warning: matplotlib not installed. Chart generation disabled.", file=sys.stderr)

# Add the parent directory to the path so we can import from indexer
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))

# Load environment variables from .env file
env_path = os.path.join(os.path.dirname(__file__), '../../.env')
if os.path.exists(env_path):
    load_dotenv(env_path)
else:
    print(f"Warning: .env file not found at {env_path}", file=sys.stderr)

# Standard dust limits in satoshis
# - P2WSH outputs (newer format): 330 satoshis
# - Multisig outputs (older format): 546 satoshis


class SRC20CostBasisAnalyzer:
    """Analyzes the cost basis of SRC-20 tokens based on MINT transactions."""
    
    def __init__(self):
        """Initialize the analyzer with database and optional Bitcoin RPC connection."""
        self.db = self.get_db_connection()
        self.bitcoin_rpc = self.get_bitcoin_rpc() if HAS_BITCOIN_RPC else None
        self.fee_cache = {}  # Cache for transaction fees to avoid repeated lookups
        
    def get_db_connection(self):
        """Get database connection using environment variables."""
        try:
            connection = pymysql.connect(
                host=os.environ.get('RDS_HOSTNAME', 'localhost'),
                user=os.environ.get('RDS_USER', 'root'),
                password=os.environ.get('RDS_PASSWORD', ''),
                database=os.environ.get('RDS_DATABASE', 'btc_stamps'),
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor
            )
            print(f"Connected to database: {os.environ.get('RDS_DATABASE', 'btc_stamps')}", file=sys.stderr)
            return connection
        except Exception as e:
            print(f"Error connecting to database: {e}", file=sys.stderr)
            print("Please check your .env file or environment variables:", file=sys.stderr)
            print(f"  RDS_HOSTNAME={os.environ.get('RDS_HOSTNAME', 'not set')}", file=sys.stderr)
            print(f"  RDS_USER={os.environ.get('RDS_USER', 'not set')}", file=sys.stderr)
            print(f"  RDS_DATABASE={os.environ.get('RDS_DATABASE', 'not set')}", file=sys.stderr)
            raise
            
    def get_bitcoin_rpc(self):
        """Get Bitcoin RPC connection if configured."""
        rpc_url = os.environ.get('BITCOIN_RPC_URL')
        if not rpc_url:
            # Try to construct from individual components
            host = os.environ.get('RPC_IP', '127.0.0.1')
            port = os.environ.get('RPC_PORT', '8332')
            user = os.environ.get('RPC_USER', '')
            password = os.environ.get('RPC_PASSWORD', '')
            
            if user and password:
                rpc_url = f"http://{user}:{password}@{host}:{port}"
            else:
                print("Bitcoin RPC credentials not configured", file=sys.stderr)
                return None
                
        try:
            rpc = AuthServiceProxy(rpc_url)
            # Test connection
            rpc.getblockcount()
            print("Connected to Bitcoin node", file=sys.stderr)
            return rpc
        except Exception as e:
            print(f"Could not connect to Bitcoin node: {e}", file=sys.stderr)
            return None
        
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
            
    def get_transaction_fee_from_node(self, tx_hash: str) -> Optional[tuple]:
        """Get transaction fee and fee rate from Bitcoin node."""
        if not self.bitcoin_rpc:
            return None
            
        # Check cache first
        if tx_hash in self.fee_cache:
            return self.fee_cache[tx_hash]
            
        try:
            # Get raw transaction with verbose output
            raw_tx = self.bitcoin_rpc.getrawtransaction(tx_hash, True)
            
            # Get transaction size in vbytes (virtual bytes)
            vsize = raw_tx.get('vsize', raw_tx.get('size', 0))  # Use vsize if available, fallback to size
            
            # Calculate fee by summing inputs minus outputs
            total_input = 0
            total_output = 0
            
            # Get input values
            for vin in raw_tx.get('vin', []):
                # Skip coinbase transactions
                if 'coinbase' in vin:
                    continue
                    
                try:
                    # Get the previous transaction
                    prev_tx = self.bitcoin_rpc.getrawtransaction(vin['txid'], True)
                    prev_out = prev_tx['vout'][vin['vout']]
                    total_input += int(prev_out['value'] * 100000000)
                except Exception as e:
                    print(f"Error getting input value for {vin['txid']}:{vin['vout']}: {e}", file=sys.stderr)
                    return None
                
            # Get output values
            for vout in raw_tx.get('vout', []):
                total_output += int(vout['value'] * 100000000)
                
            fee = total_input - total_output
            
            # Sanity check - fee should be positive and reasonable
            if fee < 0:
                print(f"Warning: Negative fee calculated for {tx_hash}: {fee}", file=sys.stderr)
                return None
            elif fee > 10000000:  # More than 0.1 BTC fee is suspicious
                print(f"Warning: Suspiciously high fee for {tx_hash}: {fee} sats", file=sys.stderr)
                
            # Calculate fee rate in sat/vB
            fee_rate = fee / vsize if vsize > 0 else 0
                
            # Cache the result as tuple (fee, fee_rate)
            result = (fee, fee_rate)
            self.fee_cache[tx_hash] = result
            return result
            
        except Exception as e:
            # Check if it's a "not found" error
            error_str = str(e).lower()
            if 'no such mempool or blockchain transaction' in error_str:
                print(f"Transaction {tx_hash} not found in node", file=sys.stderr)
            else:
                print(f"Error getting transaction fee from node for {tx_hash}: {e}", file=sys.stderr)
            return None
            
    def get_p2wsh_dust_from_tx(self, tx_hash: str) -> int:
        """Get stamp output value from transaction (P2WSH or multisig)."""
        # Check cache first
        cache_key = f"dust_{tx_hash}"
        if cache_key in self.fee_cache:
            return self.fee_cache[cache_key]
            
        if self.bitcoin_rpc:
            try:
                raw_tx = self.bitcoin_rpc.getrawtransaction(tx_hash, True)
                
                # Look for P2WSH outputs (newer format) or multisig outputs (older format)
                stamp_values = []
                for vout in raw_tx.get('vout', []):
                    script_pubkey = vout.get('scriptPubKey', {})
                    script_type = script_pubkey.get('type', '')
                    
                    if script_type == 'witness_v0_scripthash':
                        # Found a P2WSH output (newer format)
                        value_sats = int(vout['value'] * 100000000)
                        stamp_values.append(value_sats)
                        
                        # Debug info
                        print(f"Found P2WSH output: {value_sats} sats", file=sys.stderr)
                        
                    elif script_type == 'multisig':
                        # Found a multisig output (older format)
                        value_sats = int(vout['value'] * 100000000)
                        stamp_values.append(value_sats)
                        
                        # Debug info
                        print(f"Found multisig output: {value_sats} sats", file=sys.stderr)
                
                if stamp_values:
                    # Sum ALL stamp outputs (P2WSH or multisig) as they all represent dust cost
                    # Change outputs won't be P2WSH or multisig, so we're already excluding them
                    dust_value = sum(stamp_values)
                    self.fee_cache[cache_key] = dust_value
                    print(f"Total stamp dust from {len(stamp_values)} outputs: {dust_value} sats", file=sys.stderr)
                    return dust_value
                else:
                    print(f"No P2WSH or multisig outputs found in tx {tx_hash}", file=sys.stderr)
                    
            except Exception as e:
                print(f"Error getting stamp output from node for {tx_hash}: {e}", file=sys.stderr)
                
        # If we can't get from node or no stamp output found, return standard dust limit
        # Use 546 satoshis as default (standard dust for multisig)
        dust_value = 546
        self.fee_cache[cache_key] = dust_value
        return dust_value
        
    def get_mint_transactions(self, tick: str) -> List[Dict]:
        """
        Retrieve all MINT transactions for a specific SRC-20 token.
        
        Args:
            tick: The ticker symbol of the SRC-20 token
            
        Returns:
            List of mint transaction data including fees and amounts
        """
        # First check if the token exists with any operations
        check_query = """
        SELECT COUNT(*) as count
        FROM SRC20Valid
        WHERE tick = %s
        """
        result = self.fetch_one(check_query, (tick,))
        if not result or result['count'] == 0:
            # Try case-insensitive search
            result = self.fetch_one(check_query.replace('tick = %s', 'UPPER(tick) = UPPER(%s)'), (tick,))
            if not result or result['count'] == 0:
                print(f"No operations found for token '{tick}'", file=sys.stderr)
                return []
            else:
                # Get the actual tick casing
                actual_tick = self.fetch_one(
                    "SELECT DISTINCT tick FROM SRC20Valid WHERE UPPER(tick) = UPPER(%s) LIMIT 1",
                    (tick,)
                )
                if actual_tick:
                    tick = actual_tick['tick']
                    print(f"Using tick '{tick}' (case adjusted)", file=sys.stderr)
        
        # Note: Not querying fee from database as it may not be reliable
        query = """
        SELECT 
            s.tx_hash,
            s.tx_index,
            s.block_index,
            s.block_time,
            s.amt as tokens_minted,
            s.creator as minter_address
        FROM SRC20Valid s
        WHERE s.op = 'MINT'
        AND s.tick = %s
        AND s.amt > 0
        ORDER BY s.block_index ASC, s.tx_index ASC
        """
        
        results = self.fetch_all(query, (tick,))
        
        if not results:
            print(f"No MINT operations found for token '{tick}'", file=sys.stderr)
            return []
            
        print(f"Found {len(results)} MINT transactions for {tick}", file=sys.stderr)
        
        # Check if Bitcoin RPC is available
        if not self.bitcoin_rpc:
            print("ERROR: Bitcoin RPC not configured. Cannot fetch transaction fees.", file=sys.stderr)
            print("Please configure RPC_IP, RPC_PORT, RPC_USER, and RPC_PASSWORD in your .env file", file=sys.stderr)
            return []
        
        # Convert to list of dicts with calculated fields
        mint_transactions = []
        errors = 0
        
        for i, row in enumerate(results):
            tx_hash = row['tx_hash']
            
            # Progress indicator for large datasets
            if (i + 1) % 10 == 0:
                print(f"Processing transaction {i + 1}/{len(results)}...", file=sys.stderr)
            
            # Get transaction fee and fee rate from Bitcoin node
            fee_data = self.get_transaction_fee_from_node(tx_hash)
            
            if fee_data is None:
                print(f"Warning: Could not fetch fee for tx {tx_hash}", file=sys.stderr)
                errors += 1
                # Skip transactions where we can't get fee data
                continue
                
            fee_satoshis, fee_rate_sat_vb = fee_data
            
            # Get stamp dust value (P2WSH or multisig)
            stamp_dust_satoshis = self.get_p2wsh_dust_from_tx(tx_hash)
            
            total_cost_satoshis = fee_satoshis + stamp_dust_satoshis
            
            # Calculate cost per token in satoshis
            tokens_minted = Decimal(str(row['tokens_minted']))
            cost_per_token_sats = Decimal(total_cost_satoshis) / tokens_minted if tokens_minted > 0 else Decimal(0)
            
            # Convert to BTC for display
            cost_per_token_btc = cost_per_token_sats / Decimal(100000000)
            total_cost_btc = Decimal(total_cost_satoshis) / Decimal(100000000)
            
            # Convert block_time to string if it's a datetime object
            block_time = row['block_time']
            if not isinstance(block_time, str):
                block_time = block_time.strftime('%Y-%m-%d %H:%M:%S')
                
            mint_transactions.append({
                'tx_hash': tx_hash,
                'tx_index': row['tx_index'],
                'block_index': row['block_index'],
                'block_time': block_time,
                'tokens_minted': float(tokens_minted),
                'minter_address': row['minter_address'],
                'fee_satoshis': fee_satoshis,
                'fee_rate_sat_vb': round(fee_rate_sat_vb, 2),
                'stamp_dust_satoshis': stamp_dust_satoshis,
                'total_cost_satoshis': total_cost_satoshis,
                'total_cost_btc': float(total_cost_btc),
                'cost_per_token_sats': float(cost_per_token_sats),
                'cost_per_token_btc': float(cost_per_token_btc)
            })
            
        if errors > 0:
            print(f"\nWarning: Failed to fetch fees for {errors} transactions", file=sys.stderr)
            
        print(f"Successfully processed {len(mint_transactions)} transactions", file=sys.stderr)
        return mint_transactions
    
    def get_token_info(self, tick: str) -> Optional[Dict]:
        """
        Get basic information about the SRC-20 token.
        
        Args:
            tick: The ticker symbol
            
        Returns:
            Token information or None if not found
        """
        # First try to get DEPLOY info
        query = """
        SELECT 
            tick,
            max as max_supply,
            deci as decimals,
            creator,
            block_index,
            block_time
        FROM SRC20Valid
        WHERE op = 'DEPLOY'
        AND tick = %s
        LIMIT 1
        """
        
        result = self.fetch_one(query, (tick,))
        
        # If no DEPLOY found, try case-insensitive
        if not result:
            result = self.fetch_one(query.replace('tick = %s', 'UPPER(tick) = UPPER(%s)'), (tick,))
            
        # If still no DEPLOY, get info from first MINT
        if not result:
            query = """
            SELECT 
                tick,
                NULL as max_supply,
                deci as decimals,
                creator,
                block_index,
                block_time
            FROM SRC20Valid
            WHERE op = 'MINT'
            AND tick = %s
            ORDER BY block_index ASC
            LIMIT 1
            """
            result = self.fetch_one(query, (tick,))
            if not result:
                result = self.fetch_one(query.replace('tick = %s', 'UPPER(tick) = UPPER(%s)'), (tick,))
            
        if not result:
            return None
            
        # Handle decimals field which might be string, int, or empty
        decimals = 18  # default
        if result['decimals'] is not None:
            try:
                # Try to convert to int, handling both numeric strings and ints
                decimals = int(result['decimals'])
            except (ValueError, TypeError):
                # If conversion fails, check if it's a string we can parse
                if isinstance(result['decimals'], str) and result['decimals'].strip():
                    try:
                        decimals = int(float(result['decimals']))
                    except (ValueError, TypeError):
                        print(f"Warning: Invalid decimals value '{result['decimals']}', using default 18", file=sys.stderr)
                        
        # Convert block_time to string if it's a datetime object
        deploy_time = result['block_time']
        if deploy_time and not isinstance(deploy_time, str):
            deploy_time = deploy_time.strftime('%Y-%m-%d %H:%M:%S')
            
        return {
            'tick': result['tick'],
            'max_supply': float(result['max_supply']) if result['max_supply'] else None,
            'decimals': decimals,
            'creator': result['creator'],
            'deploy_block': result['block_index'],
            'deploy_time': deploy_time
        }
    
    def calculate_statistics(self, mint_transactions: List[Dict]) -> Dict:
        """
        Calculate statistics from mint transactions.
        
        Args:
            mint_transactions: List of mint transaction data
            
        Returns:
            Dictionary of statistics
        """
        if not mint_transactions:
            return {}
            
        costs_per_token_btc = [tx['cost_per_token_btc'] for tx in mint_transactions]
        total_tokens = sum(tx['tokens_minted'] for tx in mint_transactions)
        total_cost_btc = sum(tx['total_cost_btc'] for tx in mint_transactions)
        unique_minters = len(set(tx['minter_address'] for tx in mint_transactions))
        fee_rates = [tx['fee_rate_sat_vb'] for tx in mint_transactions]
        
        # Sort for median calculation
        sorted_costs = sorted(costs_per_token_btc)
        median_cost = sorted_costs[len(sorted_costs) // 2] if sorted_costs else 0
        
        # Fee rate statistics
        avg_fee_rate = sum(fee_rates) / len(fee_rates) if fee_rates else 0
        min_fee_rate = min(fee_rates) if fee_rates else 0
        max_fee_rate = max(fee_rates) if fee_rates else 0
        
        return {
            'total_mints': len(mint_transactions),
            'total_tokens_minted': total_tokens,
            'total_cost_btc': total_cost_btc,
            'average_cost_per_token_btc': total_cost_btc / total_tokens if total_tokens > 0 else 0,
            'min_cost_per_token_btc': min(costs_per_token_btc) if costs_per_token_btc else 0,
            'max_cost_per_token_btc': max(costs_per_token_btc) if costs_per_token_btc else 0,
            'median_cost_per_token_btc': median_cost,
            'unique_minters': unique_minters,
            'avg_fee_rate_sat_vb': round(avg_fee_rate, 2),
            'min_fee_rate_sat_vb': round(min_fee_rate, 2),
            'max_fee_rate_sat_vb': round(max_fee_rate, 2)
        }
    
    def generate_chart(self, mint_transactions: List[Dict], tick: str, output_file: str = None):
        """
        Generate a chart showing token price over time based on mint costs.
        
        Args:
            mint_transactions: List of mint transaction data
            tick: Token ticker
            output_file: Optional output file path for the chart
        """
        if not HAS_MATPLOTLIB:
            print("Error: matplotlib not installed. Cannot generate charts.", file=sys.stderr)
            print("Install with: poetry add matplotlib", file=sys.stderr)
            return
            
        if not mint_transactions:
            print("No data to chart")
            return
            
        # Extract data for plotting
        dates = []
        for tx in mint_transactions:
            block_time = tx['block_time']
            # Handle both datetime objects and strings
            if isinstance(block_time, str):
                dates.append(datetime.fromisoformat(block_time.replace(' ', 'T')))
            else:
                # Already a datetime object
                dates.append(block_time)
                
        costs_sats = [tx['cost_per_token_sats'] for tx in mint_transactions]
        fee_rates = [tx['fee_rate_sat_vb'] for tx in mint_transactions]
        
        # Create figure with three subplots
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 14), sharex=True)
        
        # Plot 1: Cost per token over time (in satoshis)
        ax1.scatter(dates, costs_sats, alpha=0.6, s=30, c='blue', edgecolors='black', linewidth=0.5, label='Individual Mints')
        ax1.plot(dates, costs_sats, alpha=0.3, c='blue', linewidth=1)
        
        # Calculate and plot moving average
        window_size = max(1, len(costs_sats) // 50)  # Adaptive window size
        if len(costs_sats) > window_size:
            moving_avg = []
            for i in range(len(costs_sats)):
                start_idx = max(0, i - window_size // 2)
                end_idx = min(len(costs_sats), i + window_size // 2 + 1)
                avg = sum(costs_sats[start_idx:end_idx]) / (end_idx - start_idx)
                moving_avg.append(avg)
            ax1.plot(dates, moving_avg, c='red', linewidth=2, alpha=0.8, label=f'Moving Avg ({window_size} mints)')
        
        # Calculate weighted average (total cost / total tokens)
        total_cost_sats = sum(tx['total_cost_satoshis'] for tx in mint_transactions)
        total_tokens = sum(tx['tokens_minted'] for tx in mint_transactions)
        weighted_avg_cost_sats = total_cost_sats / total_tokens if total_tokens > 0 else 0
        
        # Add horizontal line for weighted average
        ax1.axhline(y=weighted_avg_cost_sats, color='green', linestyle='--', linewidth=2, alpha=0.7, 
                    label=f'Overall Avg: {weighted_avg_cost_sats:.2f} sats/token (weighted)')
        
        ax1.set_ylabel('Cost per Token (satoshis)', fontsize=12)
        ax1.set_title(f'{tick} Token Minting Cost Analysis', fontsize=16, fontweight='bold')
        ax1.grid(True, alpha=0.3)
        ax1.set_yscale('log')  # Log scale for better visualization of wide ranges
        ax1.legend(loc='upper right')
        
        # Plot 2: Cumulative minting volume
        cumulative_tokens = []
        cumulative_cost = []
        total_tokens = 0
        total_cost = 0
        
        for tx in mint_transactions:
            total_tokens += tx['tokens_minted']
            total_cost += tx['total_cost_btc']
            cumulative_tokens.append(total_tokens)
            cumulative_cost.append(total_cost)
        
        ax2.plot(dates, cumulative_tokens, c='green', linewidth=2, label='Tokens Minted')
        ax2.set_ylabel('Cumulative Tokens Minted', fontsize=12, color='green')
        ax2.tick_params(axis='y', labelcolor='green')
        ax2.grid(True, alpha=0.3)
        
        # Add secondary y-axis for cumulative cost
        ax2_twin = ax2.twinx()
        ax2_twin.plot(dates, cumulative_cost, c='red', linewidth=2, label='Total Cost (BTC)')
        ax2_twin.set_ylabel('Cumulative Cost (BTC)', fontsize=12, color='red')
        ax2_twin.tick_params(axis='y', labelcolor='red')
        
        # Add legend
        lines1, labels1 = ax2.get_legend_handles_labels()
        lines2, labels2 = ax2_twin.get_legend_handles_labels()
        ax2.legend(lines1 + lines2, labels1 + labels2, loc='upper left')
        
        # Plot 3: Fee rates over time
        ax3.scatter(dates, fee_rates, alpha=0.6, s=30, c='orange', edgecolors='black', linewidth=0.5, label='Fee Rates')
        ax3.plot(dates, fee_rates, alpha=0.3, c='orange', linewidth=1)
        
        # Calculate and plot moving average for fee rates
        if len(fee_rates) > window_size:
            fee_moving_avg = []
            for i in range(len(fee_rates)):
                start_idx = max(0, i - window_size // 2)
                end_idx = min(len(fee_rates), i + window_size // 2 + 1)
                avg = sum(fee_rates[start_idx:end_idx]) / (end_idx - start_idx)
                fee_moving_avg.append(avg)
            ax3.plot(dates, fee_moving_avg, c='purple', linewidth=2, alpha=0.8, label=f'Moving Avg ({window_size} mints)')
        
        # Add horizontal line for average fee rate
        avg_fee_rate = sum(fee_rates) / len(fee_rates) if fee_rates else 0
        ax3.axhline(y=avg_fee_rate, color='red', linestyle='--', linewidth=2, alpha=0.7, 
                    label=f'Avg Fee Rate: {avg_fee_rate:.2f} sat/vB')
        
        ax3.set_ylabel('Fee Rate (sat/vB)', fontsize=12)
        ax3.set_xlabel('Date', fontsize=12)
        ax3.grid(True, alpha=0.3)
        ax3.legend(loc='upper right')
        
        # Format x-axis for the bottom plot
        ax3.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        ax3.xaxis.set_major_locator(mdates.AutoDateLocator())
        plt.setp(ax3.xaxis.get_majorticklabels(), rotation=45, ha='right')
        
        # Add summary statistics as text
        total_btc = cumulative_cost[-1] if cumulative_cost else 0
        total_tokens = cumulative_tokens[-1] if cumulative_tokens else 0
        avg_cost_btc = total_btc / total_tokens if total_tokens > 0 else 0
        avg_cost_sats = avg_cost_btc * 100_000_000  # Convert to satoshis
        
        # Create summary text box
        summary_text = (
            f"Summary Statistics:\n"
            f"Total Mints: {len(mint_transactions):,}\n"
            f"Total Tokens: {total_tokens:,.0f}\n"
            f"Total Cost: {total_btc:.4f} BTC\n"
            f"Avg Cost/Token: {avg_cost_sats:.2f} sats ({avg_cost_btc:.10f} BTC)"
        )
        
        # Add text box to the bottom right of the third plot
        props = dict(boxstyle='round,pad=0.5', facecolor='wheat', alpha=0.8)
        ax3.text(0.98, 0.02, summary_text, transform=ax3.transAxes, fontsize=10,
                 verticalalignment='bottom', horizontalalignment='right', bbox=props)
        
        plt.tight_layout()
        
        if output_file:
            plt.savefig(output_file, dpi=300, bbox_inches='tight')
            print(f"Chart saved to: {output_file}")
        else:
            plt.show()
    
    def output_json(self, data: Dict):
        """Output data as JSON."""
        print(json.dumps(data, indent=2, default=str))
    
    def output_csv(self, mint_transactions: List[Dict], tick: str):
        """Output data as CSV to stdout."""
        if not mint_transactions:
            return
            
        fieldnames = [
            'block_index', 'tx_hash', 'block_time', 'minter_address',
            'tokens_minted', 'fee_satoshis', 'fee_rate_sat_vb', 'stamp_dust_satoshis',
            'total_cost_satoshis', 'total_cost_btc', 'cost_per_token_sats',
            'cost_per_token_btc'
        ]
        
        writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
        writer.writeheader()
        
        for tx in mint_transactions:
            writer.writerow({field: tx[field] for field in fieldnames})
    
    def analyze(self, tick: str, output_format: str = 'json', generate_chart: bool = False):
        """
        Perform the cost basis analysis for a token.
        
        Args:
            tick: Token ticker symbol
            output_format: Output format (json or csv)
            generate_chart: Whether to generate a chart
        """
        print(f"Analyzing SRC-20 token: {tick}", file=sys.stderr)
        
        # Check if chart generation is requested but matplotlib is not available
        if generate_chart and not HAS_MATPLOTLIB:
            print("Warning: Chart generation requested but matplotlib not installed.", file=sys.stderr)
            generate_chart = False
        
        # Get token info
        token_info = self.get_token_info(tick)
        if not token_info:
            print(f"Error: Token '{tick}' not found in database", file=sys.stderr)
            return
        
        # Get mint transactions
        mint_transactions = self.get_mint_transactions(tick)
        print(f"Found {len(mint_transactions)} MINT transactions", file=sys.stderr)
        
        # Calculate statistics
        stats = self.calculate_statistics(mint_transactions)
        
        # Prepare output data
        output_data = {
            'token_info': token_info,
            'statistics': stats,
            'mint_transactions': mint_transactions
        }
        
        # Output results
        if output_format == 'json':
            self.output_json(output_data)
        elif output_format == 'csv':
            self.output_csv(mint_transactions, tick)
        
        # Generate chart if requested
        if generate_chart:
            try:
                chart_file = f"{tick}_cost_basis_chart.png"
                self.generate_chart(mint_transactions, tick, chart_file)
            except Exception as e:
                print(f"\nError generating chart: {e}", file=sys.stderr)
                import traceback
                traceback.print_exc(file=sys.stderr)
    
    def list_tokens(self):
        """
        List all SRC-20 tokens that have MINT transactions.
        """
        query = """
        SELECT 
            tick,
            COUNT(*) as mint_count,
            SUM(amt) as total_minted,
            MIN(block_index) as first_mint_block,
            MAX(block_index) as last_mint_block,
            COUNT(DISTINCT creator) as unique_minters
        FROM SRC20Valid
        WHERE op = 'MINT'
        AND amt > 0
        GROUP BY tick
        ORDER BY mint_count DESC
        """
        
        results = self.fetch_all(query)
        
        if not results:
            print("No tokens with MINT transactions found in database.")
            return
        
        print("\nSRC-20 Tokens with MINT transactions:")
        print("-" * 100)
        print(f"{'Token':<10} {'Mints':<10} {'Total Minted':<20} {'First Block':<12} {'Last Block':<12} {'Minters':<10}")
        print("-" * 100)
        
        for row in results:
            total_minted = float(row['total_minted']) if row['total_minted'] else 0
            print(f"{row['tick']:<10} {row['mint_count']:<10} {total_minted:<20.4f} {row['first_mint_block']:<12} {row['last_mint_block']:<12} {row['unique_minters']:<10}")
            
        print(f"\nTotal tokens: {len(results)}")


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(description='Analyze SRC-20 token cost basis from MINT transactions')
    parser.add_argument('--tick', type=str, help='Token ticker symbol to analyze')
    parser.add_argument('--list', action='store_true', help='List all tokens with mint transactions')
    parser.add_argument('--output-format', choices=['json', 'csv'], default='json',
                        help='Output format (default: json)')
    parser.add_argument('--chart', action='store_true', help='Generate cost analysis chart')
    
    args = parser.parse_args()
    
    # Create analyzer instance
    analyzer = None
    try:
        analyzer = SRC20CostBasisAnalyzer()
        
        if args.list:
            analyzer.list_tokens()
        elif args.tick:
            analyzer.analyze(args.tick, args.output_format, args.chart)
        else:
            parser.print_help()
            
    except Exception as e:
        import traceback
        print(f"Error: {e}", file=sys.stderr)
        print("\nFull traceback:", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
    finally:
        # Clean up database connection
        if analyzer and hasattr(analyzer, 'db') and analyzer.db:
            analyzer.db.close()


if __name__ == '__main__':
    main() 