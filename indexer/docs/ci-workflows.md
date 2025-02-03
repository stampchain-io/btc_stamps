# CI/CD Workflows

This document describes the continuous integration and deployment workflows for the BTC Stamps Indexer.

## Core Workflows

### 1. Build Tests (`build-test.yml`)
A reusable workflow that provides build and test verification.

**Implementation:**
- Triggered via workflow_call
- Supports environment specification
- Matrix testing across Python versions (3.9, 3.10, 3.11, 3.12)

**Process:**
1. Sets up Python environment using setup-python.yml
2. Creates Python module structure
3. Runs build tests
4. Executes Rust parser tests

### 2. Docker Build and Publish (`docker-publish.yml`)
Handles Docker image building and publishing.

**Triggers:**
- Manual trigger (workflow_dispatch)
- Requires:
  - Tag specification
  - Environment selection (production/staging)
  - Optional test skip flag

**Process:**
1. Build Tests (conditional)
   - Uses reusable setup and build-test workflows
   - Can be skipped with skip_tests flag
2. Docker Build & Push
   - Builds multi-arch image
   - Tags with specified version
   - Pushes to Docker Hub
   - Applies metadata and labels

### 3. Python Check (`python-check.yml`)
Comprehensive code quality and testing workflow.

**Triggers:**
- Pull requests to `dev` and `main` branches
- Manual workflow dispatch

**Matrix Testing:**
Tests across Python versions:
- Python 3.9
- Python 3.10
- Python 3.11
- Python 3.12

**Quality Checks:**

1. Debug Flag Verification
   - Ensures production-safe debug settings

2. Code Style and Formatting
   - isort for import ordering
   - Black for code formatting
   - Flake8 for PEP 8 compliance
     * Complexity limit: 10
     * Line length limit: 127 characters

3. Rust-specific Checks
   - Rust formatting verification
   - Clippy linting

4. Static Analysis
   - Mypy type checking
   - Bandit security scanning

5. Test Suites
   The following test suites are executed as part of the CI process:

   **Block Processing Tests:**
   - test_block_rollback.py
     * Tests rollback functionality for block processing
     * Validates balance updates during rollbacks
     * Ensures transaction integrity after rollbacks

   **Integration Tests:**
   - test_integration_block_processing.py
     * End-to-end block processing validation
     * Tests SRC-20 parsing and validation
     * Verifies database interactions

   **Parser Tests:**
   - test_parser_comparison.py
     * Compares Python and Rust parser outputs
     * Validates parsing consistency
     * Tests deploy operations and numeric handling

   **Rollback Tests:**
   - test_rollback_transactions_stamptable.py
     * Tests transaction table rollbacks
     * Validates StampTableV4 rollbacks
     * Ensures database consistency after rollbacks

   **SRC-20 Tests:**
   - test_src20_balance.py
     * Tests balance calculation accuracy
     * Validates amount normalization
     * Handles decimal place restrictions

   - test_src20_update_valid.py
     * Tests transfer operations
     * Validates mint operations
     * Verifies balance updates
     * Tests cache management

   - test_src20_validator.py
     * Tests SRC-20 validation rules
     * Validates numeric conversions
     * Tests error handling

### 4. Integration Test (`integration-test.yml`)
Handles end-to-end integration testing.

## Support Workflows

### 1. Setup Python (`setup-python.yml`)
A reusable workflow for consistent Python environment setup across other workflows.
- Sets up Python environment
- Configures Poetry and dependencies
- Builds Rust parser
- Caches dependencies for faster builds

## Environment Variables

Required environment variables for tests:
- `USE_TEST_TX_HEX`
- `PYTHONPATH`
- `DOCKERHUB_TOKEN` (for Docker publishing)

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
3. Python Check: For code quality verification

## Best Practices

1. Always run tests before merging to dev/main
2. Use semantic versioning for tags
3. Document significant workflow changes
4. Review logs after automated runs
5. Maintain test environment parity

## Future Implementation Plans

### 1. Version Management Workflows
These workflows will improve version control and consistency:

1. **test-publish.yml**
   - Purpose: Automate package testing and publishing
   - Triggers: Tag pushes (v*) and release creation
   - Key Features:
     * Package testing before publishing
     * Version verification
     * Automated package publishing
     * Release notes generation

2. **bump-version.yml**
   - Purpose: Automate version management
   - Implementation Plan:
     * Analyze commit messages for version increment type
     * Update version in pyproject.toml and other files
     * Create and push version tags
     * Generate changelog entries

3. **version-check.yml**
   - Purpose: Ensure version consistency
   - Implementation Plan:
     * Check version numbers across all files
     * Validate semantic versioning compliance
     * Block PRs with version inconsistencies

### 2. Enhanced Security Features
Future security enhancements:

1. **Vulnerability Scanning**
   - Add container vulnerability scanning
   - Implement dependency security audits
   - Add SBOM generation for compliance

2. **Code Quality Gates**
   - Add code coverage requirements
   - Implement complexity limits
   - Add security-focused linting rules

### 3. Testing Improvements
Planned test enhancements:

1. **Performance Testing**
   - Add benchmarking workflows
   - Implement performance regression detection
   - Add load testing for critical paths

2. **Integration Testing**
   - Expand end-to-end test coverage
   - Add cross-version compatibility tests
   - Implement network resilience tests

3. **Documentation Testing**
   - Add documentation link validation
   - Implement example code testing
   - Add API documentation verification
