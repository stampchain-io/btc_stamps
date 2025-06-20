# Coverage Commands Summary

## Primary Coverage Commands

### For Local Development

1. **`poetry run coverage`**
   - Main comprehensive coverage runner
   - Default: 55% minimum coverage threshold
   - Runs all tests that can execute in current environment
   - Tests automatically skip if required infrastructure is unavailable
   - Options:
     - `--html` - Generate HTML report
     - `--xml` - Generate XML report (for CI)
     - `--json` - Generate JSON report
     - `--all-formats` - Generate all formats
     - `--open` - Open HTML report in browser
     - `--fail-under N` - Custom coverage threshold
     - `--exclude-markers "markers"` - Exclude tests with specific markers (e.g., "requires_bitcoin_node")

2. **`poetry run coverage-quick`**
   - Quick feedback during development
   - Default: 50% minimum coverage threshold
   - Excludes integration tests and Bitcoin node tests
   - Uses pytest markers: `not integration and not requires_bitcoin_node`
   - Best for rapid iteration without full infrastructure

3. **`poetry run coverage-local`**
   - Enhanced local development runner
   - Supports test groups:
     - `unit` - Core unit tests
     - `integration` - Integration tests
     - `aws` - AWS-related tests
     - `database` - Database tests
     - `market` - Market data tests
     - `all` - All tests (default)
   - Features color-coded output and better formatting

## CI/CD Usage

GitHub Actions uses `poetry run coverage --all-formats` in the coverage workflow to:
- Generate XML for Codecov integration
- Create HTML artifacts
- Produce JSON for analysis

## Common Usage Patterns

```bash
# Quick check during development (unit tests only)
poetry run coverage-quick

# Full coverage with all available tests
poetry run coverage --html --open

# Coverage excluding tests that need Bitcoin node
poetry run coverage --exclude-markers "requires_bitcoin_node"

# Coverage excluding both integration and Bitcoin node tests
poetry run coverage --exclude-markers "integration or requires_bitcoin_node"

# CI-style check locally
poetry run coverage --all-formats --fail-under 55

# Test specific groups
poetry run coverage-local --group unit --html
```

## Environment-Aware Testing

The coverage commands automatically adapt to your environment:

1. **With Full Infrastructure** (DB + Bitcoin node):
   - All 1086+ tests run
   - Coverage threshold: 55%+

2. **Without Bitcoin Node**:
   - Tests marked with `requires_bitcoin_node` are skipped
   - Use `--exclude-markers "requires_bitcoin_node"` to explicitly exclude

3. **Quick Development** (no infrastructure):
   - Use `coverage-quick` to run only unit tests
   - Coverage threshold: 50%

## Notes

- All commands respect the coverage configuration in `pyproject.toml`
- HTML reports are generated in `htmlcov/` directory
- For tests requiring Bitcoin node or database access, use the full coverage commands, not the `-quick` variant