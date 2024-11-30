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
- 