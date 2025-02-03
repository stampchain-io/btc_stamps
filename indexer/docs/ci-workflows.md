# CI/CD Workflows

This document describes the continuous integration and deployment workflows for the BTC Stamps Indexer.



##  Build Tests (`build-test.yml`)

### 1. Build Tests
Runs on:
- Pull requests to `dev` branch
- Direct pushes to `dev`
- Manual triggers

Tests:
- Python package structure
- Dependency installation
- Critical imports
- Environment configuration
- SSL/TLS support
- Package versioning

### 2. Docker Build and Publish (`docker-publish.yml`)
Runs on:
- Manual trigger (workflow_dispatch)
- Requires:
  - Tag specification
  - Environment selection (production/staging)
  - Optional test skip flag

Process:
1. Build Tests (conditional)
   - Verifies package integrity
   - Checks dependencies
   - Validates Docker build
2. Docker Build & Push
   - Builds multi-arch image
   - Tags with specified version
   - Pushes to Docker Hub
   - Applies metadata and labels

### 3. Test and Publish (`test-publish.yml`)
Runs on:
- Tag pushes (v*)
- Release creation

Process:
1. Package Testing
2. Version Verification
3. Package Publishing

## Environment Variables

Required environment variables for tests:
- `DOCKER_CONTAINER`
- `PYTHONUNBUFFERED`
- `DEBUG`

## Security Notes

- Tests run in isolated containers
- Sensitive credentials managed via GitHub Secrets
- Docker Hub authentication required for pushes
- Environment-specific deployments

## Manual Triggers

The following workflows can be triggered manually:
1. Build Tests: For development verification
2. Docker Publish: For custom deployments
   - Requires tag specification
   - Environment selection
   - Optional test skip for emergencies

## Best Practices

1. Always run tests before merging to dev
2. Use semantic versioning for tags
3. Document significant workflow changes
4. Review logs after automated runs
5. Maintain test environment parity





## Python Check Workflow (`python-check.yml`)

Comprehensive Python code quality and testing workflow that runs across multiple Python versions.

### Triggers
- Pull requests to `dev` and `main` branches
- Manual workflow dispatch

### Matrix Testing
Tests across Python versions:
- Python 3.9
- Python 3.10
- Python 3.11
- Python 3.12

### Quality Checks

#### Code Style and Formatting
1. **isort**
   - Verifies import ordering
   - Ensures consistent import grouping

2. **Black**
   - Checks code formatting
   - Uses configuration from pyproject.toml

3. **Flake8**
   - Lints code for PEP 8 compliance
   - Checks complexity (max 10)
   - Line length limit: 127 characters

#### Static Analysis
1. **Mypy**
   - Type checking
   - Explicit package bases verification
   - Configured via pyproject.toml

#### Security
1. **Bandit**
   - Security vulnerability scanning
   - Custom configuration for specific rules

2. **Safety**
   - Dependency vulnerability checking
   - Uses project-specific ignore list

### Functional Tests
1. **STAMP/SRC-20 Validation**
   - Protocol compliance tests
   - Token standard verification

2. **Format Validation**
   - Data format verification
   - Structure validation

3. **ARC4 Validation**
   - Encryption implementation tests
   - Protocol security verification

### Environment Setup
- Uses Poetry for dependency management
- Caches Poetry dependencies
- Sets up custom PYTHONPATH
- Installs system-level dependencies:
  - build-essential
  - libssl-dev

### Configuration
- Uses test transaction hex for validation
- Virtual environments disabled for CI
- Project-specific tool configurations via pyproject.toml

### Best Practices
1. Run locally before pushing:   ```bash
    poetry run run_checks   ```

1. Address all warnings before merging
2. Maintain test coverage for new features
3. Update dependency security exceptions when resolved

### Notes
- All checks must pass for PR approval
- Some checks (flake8) allow non-zero exit for warnings
- Security exceptions must be documented 

## Bump Version Workflow (`bump-version.yml`)

This workflow automates version bumping in the project. It is triggered either manually or based on specific commit patterns that require a version update.

**Key Tasks:**
 - Analyze commit messages to determine appropriate version increments following semantic versioning principles.
 - Update version numbers in project configuration files (e.g., pyproject.toml) automatically.
 - Create a new Git tag corresponding to the updated version.

## Version Check Workflow (`version-check.yml`)

This workflow ensures consistency of version information across the codebase. It is triggered on commits and pull requests to verify that:
 - Version numbers in configuration files match across the repository.
 - The declared project version adheres to semantic versioning standards.

Both workflows contribute to robust CI/CD processes by automating version management and enforcing consistency, ensuring reliable deployments and easier maintenance of release cycles. 

## Enhanced Testing Strategies

To ensure the robustness and reliability of the BTC Stamps Indexer, additional tests have been integrated into the CI workflows. These tests complement the standard workflows and provide comprehensive validation of both core functionalities and edge cases.

### 1. Rollback Transaction Tests
- Validates that rollback operations on the transactions table and StampTableV4 perform as expected.
- Ensures that database state remains consistent after rollback operations.
- Utilizes live database connections and specific test cases (e.g., tests/test_rollback_transactions_stamptable.py).

### 2. Balance Calculation and Ledger Integrity Tests
- Verifies the accuracy of balance computations, especially after optimizations in the Rust parser.
- Compares ledger states across runs to detect any discrepancies.

### 3. End-to-End Integration Testing
- Tests the complete block processing pipeline, combining outputs from both Python and Rust parsers.
- Triggered on pull requests and tag pushes to catch integration issues early.

### 4. Offline Testing with Stored Blockchain Data
- Uses stored snapshots of blockchain data to simulate production scenarios.
- Provides enhanced test coverage in CI environments without live database connections.

These testing strategies ensure that every change, especially those affecting critical components like rollback functionality and balance calculations, is thoroughly validated before merging, thereby maintaining the integrity and performance of the indexer. 