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

# Standard P2WSH dust limit in satoshis
P2WSH_DUST_LIMIT = 330  # Minimum relay fee for P2WSH outputs


class SRC20CostBasisAnalyzer:
    """Analyzes the cost basis of SRC-20 tokens based on MINT transactions."""
    
    def __init__(self):
        """Initialize the analyzer with database and optional Bitcoin RPC connection."""
        self.db = self.get_db_connection()
        self.bitcoin_rpc = self.get_bitcoin_rpc() if HAS_BITCOIN_RPC else None
        
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
            
    def get_transaction_fee_from_node(self, tx_hash: str) -> Optional[int]:
        """Get transaction fee directly from Bitcoin node."""
        if not self.bitcoin_rpc:
            return None
            
        try:
            # Get raw transaction
            raw_tx = self.bitcoin_rpc.getrawtransaction(tx_hash, True)
            
            # Calculate fee by summing inputs minus outputs
            total_input = 0
            total_output = 0
            
            # Get input values
            for vin in raw_tx.get('vin', []):
                # Get the previous transaction
                prev_tx = self.bitcoin_rpc.getrawtransaction(vin['txid'], True)
                prev_out = prev_tx['vout'][vin['vout']]
                total_input += int(prev_out['value'] * 100000000)
                
            # Get output values
            for vout in raw_tx.get('vout', []):
                total_output += int(vout['value'] * 100000000)
                
            fee = total_input - total_output
            return fee if fee > 0 else None
            
        except Exception as e:
            print(f"Error getting transaction fee from node for {tx_hash}: {e}", file=sys.stderr)
            return None
            
    def get_p2wsh_dust_from_tx(self, tx_hash: str) -> int:
        """Get P2WSH output value from transaction."""
        if self.bitcoin_rpc:
            try:
                raw_tx = self.bitcoin_rpc.getrawtransaction(tx_hash, True)
                
                # Look for P2WSH outputs (scriptPubKey type = witness_v0_scripthash)
                for vout in raw_tx.get('vout', []):
                    script_type = vout.get('scriptPubKey', {}).get('type', '')
                    if script_type == 'witness_v0_scripthash':
                        # Return the value in satoshis
                        return int(vout['value'] * 100000000)
                        
            except Exception as e:
                print(f"Error getting P2WSH output from node for {tx_hash}: {e}", file=sys.stderr)
                
        # If we can't get from node or no P2WSH found, return standard dust limit
        return P2WSH_DUST_LIMIT
        
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
        
        query = """
        SELECT 
            s.tx_hash,
            s.tx_index,
            s.block_index,
            s.block_time,
            s.amt as tokens_minted,
            s.creator as minter_address,
            t.fee as fee_satoshis
        FROM SRC20Valid s
        LEFT JOIN transactions t ON s.tx_hash = t.tx_hash
        WHERE s.op = 'MINT'
        AND s.tick = %s
        AND s.amt > 0
        ORDER BY s.block_index ASC, s.tx_index ASC
        """
        
        results = self.fetch_all(query, (tick,))
        
        # Convert to list of dicts with calculated fields
        mint_transactions = []
        for row in results:
            tx_hash = row['tx_hash']
            
            # Get transaction fee
            fee_satoshis = None
            if row['fee'] is not None:
                fee_satoshis = int(row['fee'])
            elif self.bitcoin_rpc:
                # Try to get from Bitcoin node
                fee_satoshis = self.get_transaction_fee_from_node(tx_hash)
                
            if fee_satoshis is None:
                # Estimate based on typical transaction size
                print(f"Warning: No fee data for {tx_hash}, using estimate", file=sys.stderr)
                fee_satoshis = 5000  # Rough estimate
            
            # Get P2WSH dust value
            p2wsh_dust_satoshis = self.get_p2wsh_dust_from_tx(tx_hash)
            
            total_cost_satoshis = fee_satoshis + p2wsh_dust_satoshis
            
            # Calculate cost per token in satoshis
            tokens_minted = Decimal(str(row['tokens_minted']))
            cost_per_token_sats = Decimal(total_cost_satoshis) / tokens_minted if tokens_minted > 0 else Decimal(0)
            
            # Convert to BTC for display
            cost_per_token_btc = cost_per_token_sats / Decimal(100000000)
            total_cost_btc = Decimal(total_cost_satoshis) / Decimal(100000000)
            
            mint_transactions.append({
                'tx_hash': tx_hash,
                'tx_index': row['tx_index'],
                'block_index': row['block_index'],
                'block_time': row['block_time'],
                'tokens_minted': float(tokens_minted),
                'minter_address': row['minter_address'],
                'fee_satoshis': fee_satoshis,
                'p2wsh_dust_satoshis': p2wsh_dust_satoshis,
                'total_cost_satoshis': total_cost_satoshis,
                'total_cost_btc': float(total_cost_btc),
                'cost_per_token_sats': float(cost_per_token_sats),
                'cost_per_token_btc': float(cost_per_token_btc)
            })
            
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
            
        return {
            'tick': result['tick'],
            'max_supply': float(result['max_supply']) if result['max_supply'] else None,
            'decimals': int(result['decimals']) if result['decimals'] is not None else 18,
            'creator': result['creator'],
            'deploy_block': result['block_index'],
            'deploy_time': result['block_time']
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
        
        # Sort for median calculation
        sorted_costs = sorted(costs_per_token_btc)
        median_cost = sorted_costs[len(sorted_costs) // 2] if sorted_costs else 0
        
        return {
            'total_mints': len(mint_transactions),
            'total_tokens_minted': total_tokens,
            'total_cost_btc': total_cost_btc,
            'average_cost_per_token_btc': total_cost_btc / total_tokens if total_tokens > 0 else 0,
            'min_cost_per_token_btc': min(costs_per_token_btc) if costs_per_token_btc else 0,
            'max_cost_per_token_btc': max(costs_per_token_btc) if costs_per_token_btc else 0,
            'median_cost_per_token_btc': median_cost,
            'unique_minters': unique_minters
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
        dates = [datetime.fromisoformat(tx['block_time'].replace(' ', 'T')) for tx in mint_transactions]
        costs = [tx['cost_per_token_btc'] for tx in mint_transactions]
        
        # Create figure with two subplots
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10), sharex=True)
        
        # Plot 1: Cost per token over time
        ax1.scatter(dates, costs, alpha=0.6, s=30, c='blue', edgecolors='black', linewidth=0.5)
        ax1.plot(dates, costs, alpha=0.3, c='blue', linewidth=1)
        ax1.set_ylabel('Cost per Token (BTC)', fontsize=12)
        ax1.set_title(f'{tick} Token Minting Cost Analysis', fontsize=16, fontweight='bold')
        ax1.grid(True, alpha=0.3)
        ax1.set_yscale('log')  # Log scale for better visualization of wide ranges
        
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
        
        # Format x-axis
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        ax2.xaxis.set_major_locator(mdates.AutoDateLocator())
        plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45, ha='right')
        
        ax2.set_xlabel('Date', fontsize=12)
        
        # Add legend
        lines1, labels1 = ax2.get_legend_handles_labels()
        lines2, labels2 = ax2_twin.get_legend_handles_labels()
        ax2.legend(lines1 + lines2, labels1 + labels2, loc='upper left')
        
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
            'tokens_minted', 'fee_satoshis', 'p2wsh_dust_satoshis',
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
            chart_file = f"{tick}_cost_basis_chart.png"
            self.generate_chart(mint_transactions, tick, chart_file)
    
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
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        # Clean up database connection
        if analyzer and hasattr(analyzer, 'db') and analyzer.db:
            analyzer.db.close()


if __name__ == '__main__':
    main() 