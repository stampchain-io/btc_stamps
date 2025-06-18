#!/usr/bin/env python3
"""
Quick coverage report tool that runs only the tests from run_checks.py.
This provides faster feedback during development while ensuring consistency
with the main test suite.
"""

import argparse
import ast
import subprocess
import sys
from pathlib import Path


def get_test_files_from_run_checks():
    """
    Extract test approach from run_checks.py.

    Since run_checks.py now uses pytest markers instead of listing individual files,
    this function returns None to indicate marker-based testing should be used.
    """
    # The new approach uses markers, so we don't extract individual files
    return None


def run_quick_coverage(html=False, fail_under=50):
    """Run coverage on unit tests (excluding integration tests)."""
    print("🚀 Running quick coverage report (unit tests only)...")
    print(f"   Coverage threshold: {fail_under}%")
    print("   Using pytest markers to exclude integration tests")

    # Build the pytest command using markers
    # Include all tests except true integration tests
    cmd = [
        "poetry",
        "run",
        "pytest",
        "-m",
        "not integration",
        "--cov=src",
        "--cov-report=term-missing",
        f"--cov-fail-under={fail_under}",
    ]

    if html:
        cmd.append("--cov-report=html")

    print("\n📊 Running coverage on unit tests (excluding integration/db/network tests)...")

    # Run the coverage command
    try:
        result = subprocess.run(cmd, check=True)
        print("\n✅ Coverage check passed!")
        return 0
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Coverage check failed with exit code {e.returncode}")
        return e.returncode


def run_fast_coverage_analysis():
    """Run a fast coverage analysis focused on unit tests."""
    print("🚀 Running FAST coverage analysis (unit tests only)")
    print("=" * 60)

    # Run coverage with pytest using markers
    cmd = [
        "poetry",
        "run",
        "pytest",
        "-xvs",
        "-m",
        "not integration",
        "--cov=src",
        "--cov-report=term-missing:skip-covered",
        "--cov-fail-under=5",  # Low threshold for fast checks
        "-W",
        "ignore::DeprecationWarning",
        "-W",
        "ignore::PendingDeprecationWarning",
    ]

    try:
        subprocess.run(cmd, check=True)
        print("\n✅ Fast coverage analysis completed!")
        print("💡 For full coverage, use: poetry run run-coverage")
        return 0
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Fast coverage analysis failed with exit code {e.returncode}")
        return e.returncode


def main():
    parser = argparse.ArgumentParser(description="Run quick coverage report for tests in run_checks.py")
    parser.add_argument("--html", action="store_true", help="Generate HTML coverage report")
    parser.add_argument(
        "--fail-under", type=int, default=50, help="Fail if total coverage is below this percentage (default: 50)"
    )
    parser.add_argument("--fast", action="store_true", help="Run fast coverage analysis mode")

    args = parser.parse_args()

    if args.fast:
        return run_fast_coverage_analysis()
    else:
        return run_quick_coverage(html=args.html, fail_under=args.fail_under)


if __name__ == "__main__":
    sys.exit(main())
