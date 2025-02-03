# Test and Debug Files Organization

## Test Files

The following test files have been organized in the `indexer/tests/` directory:

- `test_block_tx.py`: Tests transaction processing in a block context
- `test_parser_fix.py`: Tests the EnhancedCTransaction wrapper and Rust parser integration
- `test_rust_parser_simple.py`: Simple tests for the Rust parser functionality
- `test_special_txs_simple.py`: Simple tests for special transaction handling

### LRU Cache Tests

- `lru_cache/test_lru_cache.py`: Tests for the LRU cache functionality

## Tools

The following tools have been organized in the `indexer/tools/` directory:

### Benchmark Tools

- `benchmark/benchmark_lru_cache.py`: Benchmarking tool for the LRU cache

### Debug Tools

- `debug/analyze_test_tx.py`: Analysis tool for examining transactions in detail
- `debug/debug_chunk.py`: Debugging tool for transaction chunk creation and decryption
- `debug/debug_rust_python.py`: Debugging tool for comparing Python and Rust implementations
- `debug/debug_specific_tx.py`: Debugging tool for analyzing specific transactions
- `debug/debug_tx_details.py`: Debugging tool for analyzing transaction details
- `debug/verify_fix.py`: Verification tool for checking that a fix works for a problematic transaction
