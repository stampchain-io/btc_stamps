# Bitcoin Stamps Development Guide

This guide provides comprehensive information for developers working on the Bitcoin Stamps project.

## Setup

### Prerequisites

- Python 3.10+
- Rust toolchain (for the high-performance parser)
- MySQL database
- Bitcoin node access (local or API)
- Optional: Counterparty node

### Local Environment

1. **Clone the repository**

   ```bash
   git clone https://github.com/stampchain-io/btc_stamps.git
   cd btc_stamps
   ```

2. **Install dependencies**

   ```bash
   # Setup Python environment
   cd indexer
   poetry install
   
   # Build the Rust parser
   poetry run task build-dev
   ```

3. **Configure environment**

   Create the following environment files:
   
   ```bash
   cp indexer/.env.sample indexer/.env
   cp docker/.env.mysql.sample docker/.env.mysql
   ```
   
   Edit these files to include your Bitcoin node and database connection details.

4. **Initialize database**

   ```bash
   # Using Docker (recommended)
   cd docker
   docker-compose up -d db adminer
   
   # Or manually
   mysql -u <username> -p < indexer/table_schema.sql
   ```

## Running the Indexer

### Development Mode

```bash
# Run the indexer directly
cd indexer
poetry run indexer

# With debug logging
DEBUG=1 poetry run indexer
```

### Docker Mode

```bash
# Start all services
make dup

# View logs
make logs

# Stop services
make down
```

## Code Organization

The codebase is organized into key components:

```
indexer/
├── src/
│   ├── index_core/        # Core Python implementations
│   │   ├── blocks.py      # Block processing pipeline
│   │   ├── stamp.py       # Stamp protocol handling
│   │   ├── src20.py       # SRC-20 protocol implementation
│   │   ├── src101.py      # SRC-101 domain system
│   │   ├── database.py    # Database interactions
│   │   └── files.py       # File storage management
│   └── rust_parser/       # High-performance Rust parser
│       ├── src/
│       │   ├── lib.rs     # Main Rust implementation
│       │   ├── arc4.rs    # ARC4 decryption algorithm
│       │   └── constants.rs # Shared constants
├── tests/                 # Test suite
└── tools/                 # Utilities and debugging tools
    └── debug/             # Transaction debugging tools
```

## Development Workflow

### Pull Request Process

1. **Fork the repository** (or create a branch if you have write access)
2. **Implement your changes**
3. **Run tests** to ensure nothing is broken
   ```bash
   cd indexer
   poetry run pytest tests/
   ```
4. **Run code quality checks**
   ```bash
   poetry run check-code  # Runs black, flake8, mypy
   poetry run check-rust  # Checks the Rust code
   ```
5. **Submit a pull request** with a clear description of the changes

### Coding Standards

- **Python**:
  - Format code with Black (line length 127)
  - Use type hints for all functions
  - Sort imports with isort
  - Follow flake8 rules (with exceptions E203, W503, E402, E501)
  
- **Rust**:
  - Format with rustfmt
  - Follow Rust API guidelines
  - Use proper error handling

## Testing

### Running Tests

```bash
# Run all tests
cd indexer
poetry run pytest tests/

# Run a specific test
poetry run pytest tests/test_src20.py

# Run with coverage
poetry run pytest tests/ --cov=src
```

### Test Categories

- **Unit Tests**: Test individual components in isolation
- **Integration Tests**: Test interactions between components
- **Performance Tests**: Benchmark key operations
- **Protocol Tests**: Test specific protocol implementations

### Writing Tests

1. Create test file in `tests/` directory (e.g., `test_feature.py`)
2. Use pytest fixtures for common setup
3. Test both success and failure cases
4. Include performance assertions where relevant

Example:

```python
def test_src20_token_validation():
    # Setup
    validator = Src20Validator({
        "p": "SRC-20",
        "op": "deploy",
        "tick": "TEST",
        "max": "1000",
        "lim": "100"
    })
    
    # Test
    result = validator.process_values()
    
    # Assert
    assert result["tick"] == "test"  # Lowercase conversion
    assert isinstance(result["max"], Decimal)
    assert isinstance(result["lim"], Decimal)
    assert validator.is_valid
```

## Debugging Tools

The project includes several debugging tools to analyze transactions:

### Analyzing Transactions

```bash
cd indexer
poetry run python tools/debug/debug_transaction_parser.py <txid> --verbose
```

This will show detailed information about transaction parsing, including pattern detection and protocol validation.

### Testing Block Processing

```bash
cd indexer
poetry run python tools/debug/test_block_transactions.py --block=<block_index>
```

This will process all transactions in the specified block and show detailed results.

### Useful Test Transactions

- `e2aa459ebfe0ba3625c917143452678a3e80636489fe0ec8cc7e9651cfd4ddb2` - SRC-20 mint
- `359aefd7bf0bbd8398ee5c8c0f206799b78b158578f0f98e1e06bf58e70008dc` - SRC-20 transfer
- `50aeb77245a9483a5b077e4e7506c331dc2f628c22046e7d2b4c6ad6c6236ae1` - SRC-20 deploy

## Performance Optimization

### Key Optimization Points

1. **Transaction Filtering**: Most optimization gains come from efficient pre-filtering
2. **Database Operations**: Optimize write patterns for MySQL
3. **Memory Management**: Control memory usage during processing
4. **Parallelism**: Use parallel processing where appropriate

### Profiling

```bash
# CPU profiling
cd indexer
python -m cProfile -o profile.dat start.py
python -m pstats profile.dat

# Memory profiling
pip install memory_profiler
python -m memory_profiler start.py
```

## Common Tasks

### Adding a New Protocol

1. Define protocol structure and validation rules
2. Create protocol parser module in `indexer/src/index_core/`
3. Add detection in `stamp.py:StampData.process_and_store_stamp_data()`
4. Add processing in `BlockProcessor.process_transaction_results()`
5. Update database schema for the new protocol

### Modifying Rust Parser

1. Make changes to `indexer/src/rust_parser/src/lib.rs`
2. Rebuild the parser:
   ```bash
   cd indexer
   poetry run task build-dev
   ```
3. Test the changes:
   ```bash
   poetry run pytest tests/test_rust_parser.py
   ```

### Improving Database Performance

1. Identify slow queries using MySQL profiling
2. Add appropriate indexes in `table_schema.sql`
3. Optimize batch operations in database.py
4. Consider query caching for read-heavy operations

## Troubleshooting

### Common Issues

1. **Missing Rust toolchain**
   ```
   Error: Failed to build Rust parser
   ```
   Solution: Install Rust toolchain via rustup.rs

2. **Database connection issues**
   ```
   Error: Could not connect to database
   ```
   Solution: Check database credentials in .env file and ensure MySQL is running

3. **Protocol detection failures**
   ```
   Failed to detect protocol in transaction: <txid>
   ```
   Solution: Use debug tools to analyze the transaction structure and data

4. **Memory issues during processing**
   ```
   MemoryError during block processing
   ```
   Solution: Adjust memory thresholds in config.py and batch sizes in the code

### Getting Help

- Consult the documentation in the `docs/` directory
- Check the code comments for implementation details
- Join the Bitcoin Stamps Telegram community
- Open an issue on GitHub for persistent problems

## Contributing

We welcome contributions to Bitcoin Stamps! Here are some areas where help is particularly appreciated:

- Protocol optimizations
- Test coverage improvements
- Documentation enhancements
- Performance optimizations
- Bug fixes

Please follow the coding standards and development workflow outlined in this guide when submitting contributions.