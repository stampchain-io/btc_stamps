# Bitcoin Stamps Indexer Guide

## Documentation
- **Architecture**: Reference `docs/ARCHITECTURE.md` for system overview and component relationships
- **Protocols**: Reference `docs/PROTOCOLS.md` for detailed protocol specifications and transaction sources
- **Database**: Reference `docs/DATABASE.md` for database schema and operations
- **Development**: Reference `docs/DEVELOPMENT.md` for development workflow and standards

## Core Commands
- `cd indexer && poetry run indexer` - Run the indexer
- `cd indexer && poetry install` - Install dependencies
- `cd indexer && poetry run task build` - Build Rust parser
- `cd indexer && poetry run task build-dev` - Development build with debug symbols

## Test Commands
- `cd indexer && poetry run pytest tests/` - Run all tests
- `cd indexer && poetry run pytest tests/test_file.py -v` - Run specific test
- `cd indexer && poetry run run_checks` - Run all checks
- `cd indexer && poetry run check-code` - Code quality checks
- `cd indexer && poetry run check-rust` - Rust checks

## Debug Tools
- `cd indexer && poetry run python tools/debug/debug_transaction_parser.py <txid> [--verbose]` - Debug transaction
- `cd indexer && poetry run python tools/debug/test_block_transactions.py --block=<block_index>` - Test block processing
- `cd indexer && poetry run python tools/debug/analyze_tx.py [txid]` - Detailed transaction analysis
- Set logging level: `RUST_LOG=debug poetry run python tools/debug/script_name.py`

## Database Operations
- Use parameterized queries with `%s` placeholders to prevent SQL injection
- Follow connection patterns from `database_manager.py`:
  - Regular queries: `DatabaseManager.connect()`
  - Long-running: `DatabaseManager.get_long_running_connection()`
- Transaction pattern: `db.begin()`, `db.commit()`, `db.rollback()`
- Always return connections to pool by calling `close()`
- For detailed DB schema and operations, reference `docs/DATABASE.md`

## Code Style
- **Format**: black (line length 127)
- **Lint**: flake8 (ignoring E203, W503, E402, E501)
- **Types**: mypy type checking
- **Imports**: isort for import sorting
- **All commands must be run from the /indexer directory**

## Development Notes
- Python 3.10+ required
- Use poetry for dependency management
- Always use type hints
- Implement robust error handling
- Write tests for new features
- NEVER allow special edge case transaction handling
- Transaction sources include both direct Bitcoin and Counterparty (see `docs/PROTOCOLS.md`)
- Rust parser is used within the Python transaction filter (see `docs/ARCHITECTURE.md`)