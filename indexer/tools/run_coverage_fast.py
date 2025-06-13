#!/usr/bin/env python
"""
Fast coverage runner - targets only unit tests for quick CI/CD runs.
Skips slow integration tests and focuses on core module coverage.
"""

import subprocess
import sys

# Fast unit tests only - no integration tests
FAST_TEST_TARGETS = [
    "tests/test_src20_balance.py",
    "tests/test_src20_update_valid.py",
    "tests/test_src20_validator.py",
    "tests/test_src20.py",
    "tests/test_config.py",
    "tests/test_arc4.py",
    "tests/test_transactions.py",
    "tests/thread_safety/test_thread_safety.py",
]


def run_fast_coverage():
    """Run coverage on fast unit tests only."""
    print("🚀 Running FAST coverage analysis (unit tests only)")
    print("=" * 60)

    # Build simple coverage command - no branch coverage for speed
    cmd = [
        "poetry",
        "run",
        "pytest",
        *FAST_TEST_TARGETS,
        "--cov=src",
        "--cov-report=term-missing:skip-covered",  # Only show uncovered lines
        "--cov-fail-under=5",  # Lower threshold for fast runs
        "-x",  # Stop on first failure
        "--tb=short",  # Shorter traceback
        "--no-header",  # Less output
        "-q",  # Quiet mode
    ]

    result = subprocess.run(cmd)

    if result.returncode == 0:
        print("\n✅ Fast coverage analysis completed!")
        print("💡 For full coverage, use: poetry run run-coverage")
    else:
        print("\n❌ Coverage failed or below threshold")
        sys.exit(1)


if __name__ == "__main__":
    run_fast_coverage()
