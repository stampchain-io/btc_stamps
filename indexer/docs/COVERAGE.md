# Code Coverage Guide

This document provides comprehensive information about code coverage setup and usage for the Bitcoin Stamps Indexer.

## Overview

The project uses `pytest-cov` for code coverage measurement, integrated with:
- **Local Development**: Interactive HTML reports and terminal output
- **GitHub Actions**: Automated coverage on PRs and pushes
- **CodeCov**: Cloud-based coverage tracking and reporting

## Local Development

### Quick Start

```bash
# Run coverage on all tests with terminal report
cd indexer
poetry run pytest --cov=src tests/

# Run coverage with HTML report
poetry run coverage-local --html --open

# Run quick coverage (unit tests only)
poetry run coverage-quick --html
```

### Available Commands

#### Available Coverage Commands
- `poetry run coverage` - Standard coverage command (55% threshold)
- `poetry run coverage-quick` - Quick unit tests only (50% threshold)
- `poetry run coverage-local` - Enhanced local coverage with test groups

#### 1. **coverage-local** (Recommended for development)
Enhanced local coverage runner with multiple options:

```bash
# Run coverage on specific test groups
poetry run coverage-local --group unit --html --open
poetry run coverage-local --group integration --fail-under 70
poetry run coverage-local --group aws --xml

# Available test groups:
# - unit: Core unit tests (fast)
# - integration: Integration tests
# - aws: AWS-related tests
# - database: Database and reparse tests
# - market: Market data tests
# - all: All tests (default)

# Generate all report formats
poetry run coverage-local --all-formats

# Run with parallel execution
poetry run coverage-local --parallel --html
```

#### 2. **coverage** (Standard coverage - 55% threshold)
Main coverage runner with flexible format options:

```bash
# Terminal report (default)
poetry run coverage

# HTML report with auto-open
poetry run coverage --html --open

# Multiple formats  
poetry run coverage --all-formats

# With custom threshold
poetry run coverage --fail-under 80
```

#### 3. **coverage-quick** (Development - 50% threshold)
Quick coverage excluding integration tests:

```bash
# Quick coverage for development
poetry run coverage-quick

# With HTML report
poetry run coverage-quick --html
```

### Configuration Files

#### `.coveragerc`
Main coverage configuration:
- Source paths and omissions
- Report exclusions
- Output formats

#### `pytest.ini`
Pytest configuration:
- Test discovery settings
- Coverage integration
- Environment variables
- Test markers

### Coverage Reports

1. **Terminal Report**: Shows coverage percentages and missing lines
2. **HTML Report**: Interactive browser-based report at `htmlcov/index.html`
3. **XML Report**: Machine-readable format for CI/CD at `coverage.xml`
4. **JSON Report**: Detailed coverage data at `coverage.json`

## CI/CD Integration

### GitHub Actions Workflow

The project includes a dedicated coverage workflow (`.github/workflows/coverage.yml`) that:

1. Runs on PRs to main/dev branches
2. Executes fast unit tests for quick feedback
3. Generates XML report for CodeCov
4. Creates HTML report artifacts
5. Posts coverage summary to GitHub

### CodeCov Integration

CodeCov provides:
- Coverage tracking over time
- PR coverage deltas
- Coverage badges
- Detailed file-level reports

To view coverage:
1. Check PR comments for coverage changes
2. Visit [codecov.io](https://codecov.io) for detailed reports
3. View coverage badges in README

## Best Practices

### 1. Writing Testable Code
- Keep functions small and focused
- Minimize side effects
- Use dependency injection
- Avoid global state

### 2. Coverage Targets
- **Overall**: Aim for 80% minimum
- **Critical modules**: 90%+ (src20.py, database operations)
- **New code**: 100% coverage for new features

### 3. Excluding Code
Mark code that shouldn't be covered:

```python
# Defensive assertions
if not isinstance(value, int):  # pragma: no cover
    raise TypeError("Expected integer")

# Debug code
if self.debug:  # pragma: no cover
    print(f"Debug: {value}")

# Abstract methods
@abstractmethod
def process(self):  # pragma: no cover
    pass
```

### 4. Test Organization
- Place unit tests in `tests/test_*.py`
- Group related tests in classes
- Use descriptive test names
- Mark test types:

```python
@pytest.mark.unit
def test_calculate_balance():
    pass

@pytest.mark.integration
def test_database_connection():
    pass

@pytest.mark.slow
def test_large_dataset_processing():
    pass
```

## Troubleshooting

### Common Issues

1. **Import errors in coverage**
   ```bash
   # Ensure PYTHONPATH is set
   export PYTHONPATH=$PWD/src:$PWD
   ```

2. **Missing coverage data**
   ```bash
   # Clean and regenerate
   poetry run coverage-local --clean --html
   ```

3. **Slow coverage runs**
   ```bash
   # Use parallel execution
   poetry run coverage-local --parallel --group unit
   ```

### Coverage Gaps

To identify and fix coverage gaps:

1. Generate HTML report: `poetry run coverage-local --html --open`
2. Navigate to red (uncovered) lines
3. Write tests for uncovered code paths
4. Re-run coverage to verify

## Integration with Development Workflow

### Pre-commit Hook
Add coverage check to pre-commit:

```yaml
# .pre-commit-config.yaml
- repo: local
  hooks:
    - id: coverage-check
      name: Check test coverage
      entry: poetry run coverage-quick
      language: system
      pass_filenames: false
      always_run: true
```

### VS Code Integration
Add to `.vscode/settings.json`:

```json
{
  "python.testing.pytestArgs": [
    "--cov=src",
    "--cov-report=html"
  ]
}
```

## Next Steps

1. **Improve Coverage**: Focus on modules with <70% coverage
2. **Add Missing Tests**: Use `test-cases.md` as reference
3. **Monitor Trends**: Check CodeCov for coverage trends
4. **Enforce Standards**: Set up branch protection rules

For more information, see:
- [pytest-cov documentation](https://pytest-cov.readthedocs.io/)
- [coverage.py documentation](https://coverage.readthedocs.io/)
- [CodeCov documentation](https://docs.codecov.io/)