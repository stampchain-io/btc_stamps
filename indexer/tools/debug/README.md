# Bitcoin Stamps Indexer Debug Tools

This directory contains debug tools for troubleshooting and analyzing the Bitcoin Stamps indexer. These scripts help with transaction parsing, data extraction, and comparison between Python and Rust implementations.

## Quick Reference

| Script | Purpose | Usage |
|--------|---------|-------|
| analyze_missing_txs.py | Analyzes missing transactions from StampTableV4 | `python analyze_missing_txs.py` |
| analyze_test_tx.py | Analyzes a test transaction with both parsers | `python analyze_test_tx.py` |
| analyze_tx.py | Performs detailed transaction analysis | `python analyze_tx.py [txid]` |
| compare_parsers.py | Direct A/B comparison of Python vs Rust parsers | `python compare_parsers.py` |
| debug_multisig_olga.py | Analyzes OLGA protocol transition issues | `python debug_multisig_olga.py` |
| debug_src20_processing.py | End-to-end SRC-20 pipeline diagnostics | `python debug_src20_processing.py` |
| debug_transaction_parser.py | **RECOMMENDED**: Comprehensive transaction parser debug tool | `python debug_transaction_parser.py <txid> [--verbose]` |
| debug_specific_tx.py | Debugs specific transactions (batch mode) | `python debug_specific_tx.py --txids <txid1> <txid2> --verbose` |
| diagnose_olga_tx.py | Tests specific OLGA transactions in block 865003 | `python diagnose_olga_tx.py` |
| find_token_transaction.py | Locates missing tokens by ID or address | `python find_token_transaction.py` |
| test_block_tx.py | Tests transaction processing in blocks | `python test_block_tx.py` |
| test_lru_cache.py | Tests Rust parser's LRU cache | `python test_lru_cache.py` |
| test_parser_fix.py | Tests EnhancedCTransaction wrapper | `python test_parser_fix.py` |
| test_rust_parser_basic.py | Basic Rust parser smoke test | `python test_rust_parser_basic.py` |
| test_block_transactions.py | Tests SRC-20 processing in reference blocks | `python test_block_transactions.py --block=865002 [--verbose]` |
| verify_olga_fix.py | Verifies OLGA protocol transition fix | `python verify_olga_fix.py` |

### Deprecated Scripts

The following scripts have been merged into debug_transaction_parser.py:
- debug_rust_python.py - Use debug_transaction_parser.py instead
- debug_rust_transaction.py - Use debug_transaction_parser.py instead

## Prerequisites

1. Python environment with Bitcoin Stamps Indexer dependencies
2. Rust parser built with `poetry run maturin develop` (for scripts that use Rust)
3. **All scripts must be run from the `/indexer` directory**:
   ```bash
   cd /path/to/btc_stamps/indexer
   poetry run python tools/debug/script_name.py
   ```

## Usage Tips

- Set logging level with environment variables:
  ```
  RUST_LOG=debug python debug_script.py
  ```

- Common test transactions:
  - `e2aa459ebfe0ba3625c917143452678a3e80636489fe0ec8cc7e9651cfd4ddb2`
  - `359aefd7bf0bbd8398ee5c8c0f206799b78b158578f0f98e1e06bf58e70008dc`
  - `50aeb77245a9483a5b077e4e7506c331dc2f628c22046e7d2b4c6ad6c6236ae1`
  - `00d91249c4e66b49334388487c7dfc3c5403f837159badce7088cf6afe57d9cb` - Split data across outputs
  - `572be558f1260117c134c1d4a770a443a713c778c4afdfe4139a8da15cb5d5ef` - 10.10 token deploy

## Script Categories

- **Basic Testing**: `test_rust_parser_basic.py` - Quick verification of parser functionality
- **Transaction Analysis**: `debug_transaction_parser.py`, `analyze_tx.py` - Detailed analysis
- **Batch Processing**: `debug_specific_tx.py`, `analyze_missing_txs.py` - Multiple transaction handling
- **Component Testing**: `test_lru_cache.py`, `test_parser_fix.py`, `test_block_tx.py` - Specific feature testing
- **Parser Comparison**: `compare_parsers.py` - Clean Python vs Rust comparison
- **Protocol Analysis**: `debug_multisig_olga.py`, `diagnose_olga_tx.py`, `verify_olga_fix.py` - OLGA protocol transition diagnostics
- **Pipeline Diagnostics**: `debug_src20_processing.py` - End-to-end SRC-20 processing
- **Troubleshooting**: `find_token_transaction.py` - Finding missing transactions in the blockchain
- **Regression Testing**: `test_block_transactions.py` - Validates against known working blocks

## Advanced Debugging

### Debug Transaction Parser
The `debug_transaction_parser.py` script provides comprehensive transaction analysis with:
- P2WSH concatenation for split data
- JSON extraction and validation
- Protocol detection for SRC-20, SRC-721, etc.
- Verbose mode with `--verbose` flag

### Protocol Transition Testing
The `debug_multisig_olga.py`, `diagnose_olga_tx.py`, and `verify_olga_fix.py` scripts analyze transactions during the OLGA protocol transition:
- Identifies MULTISIG vs P2WSH formats
- Provides format statistics
- Detects hybrid format transactions
- Contains test cases for block 865003
- Verifies transaction processing after OLGA protocol cutoff

### SRC-20 Pipeline Diagnostics
The `debug_src20_processing.py` script traces transactions through the SRC-20 pipeline:
- Tests data extraction stage
- Checks format validation
- Validates SRC-20 data structure
- Simulates processor behavior
- Identifies exact failure points

### Missing Token Troubleshooting
The `find_token_transaction.py` script helps locate missing token transactions:
- Scans entire blocks for specific addresses
- Analyzes all transactions for token-related patterns
- Provides detailed analysis of transaction data and scripts
- Specifically designed for tracking down missing ledger entries

### Reference Block Testing
The `test_block_transactions.py` script tests transaction processing against known reference blocks:
- Tests key SRC-20 developments (Block 865002 with "10.10" token, Block 867315 with "pi." tokens)
- Uses different testing strategies depending on block requirements
- Provides comprehensive validation of the entire transaction processing pipeline
- Perfect for regression testing when making parser or filtering changes

For full documentation of these tools, see the `.cursor/rules/debug-tools.mdc` file. 