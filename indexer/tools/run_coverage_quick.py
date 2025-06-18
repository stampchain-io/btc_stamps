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
    """Extract the test_files list from run_checks.py dynamically."""
    run_checks_path = Path(__file__).parent / "run_checks.py"

    if not run_checks_path.exists():
        print(f"Error: Could not find {run_checks_path}")
        sys.exit(1)

    try:
        with open(run_checks_path, "r") as f:
            content = f.read()

        # Parse the Python file
        tree = ast.parse(content)

        # Find the test_files list in run_code_quality_checks function
        test_files = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "run_code_quality_checks":
                for stmt in ast.walk(node):
                    if isinstance(stmt, ast.Assign):
                        for target in stmt.targets:
                            if isinstance(target, ast.Name) and target.id == "test_files":
                                if isinstance(stmt.value, ast.List):
                                    for elt in stmt.value.elts:
                                        if isinstance(elt, ast.Constant):
                                            test_files.append(elt.value)
                                    return test_files

        # If we couldn't find the test list, fail with helpful error
        print("Error: Could not find test_files list in run_code_quality_checks function")
        print("Make sure run_checks.py has the expected structure")
        sys.exit(1)

    except Exception as e:
        print(f"Error parsing run_checks.py: {e}")
        sys.exit(1)


def run_quick_coverage(html=False, fail_under=45):
    """Run coverage on all test files from run_checks.py."""
    print("🚀 Running quick coverage report (synced with run_checks.py)...")
    print(f"   Coverage threshold: {fail_under}%")

    # Get test files dynamically
    test_files = get_test_files_from_run_checks()

    # Filter out non-existent files
    existing_files = []
    for test_file in test_files:
        if Path(test_file).exists():
            existing_files.append(test_file)
        else:
            print(f"   ⚠️  Warning: Test file not found: {test_file}")

    print(f"\n📊 Running coverage on {len(existing_files)} test files (from run_checks.py)...")

    # Build the pytest command
    cmd = [
        "poetry",
        "run",
        "pytest",
        *existing_files,
        "--cov=src",
        "--cov-report=term-missing",
        f"--cov-fail-under={fail_under}",
    ]

    if html:
        cmd.append("--cov-report=html")

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

    # Run coverage with pytest
    cmd = [
        "poetry",
        "run",
        "pytest",
        "-xvs",
        "--cov=src",
        "--cov-report=term-missing:skip-covered",
        "--cov-fail-under=5",  # Low threshold for fast checks
        "-W",
        "ignore::DeprecationWarning",
        "-W",
        "ignore::PendingDeprecationWarning",
    ]

    # Add all test files from run_checks.py
    test_files = get_test_files_from_run_checks()
    existing_files = [f for f in test_files if Path(f).exists()]
    cmd.extend(existing_files)

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
        "--fail-under", type=int, default=45, help="Fail if total coverage is below this percentage (default: 45)"
    )
    parser.add_argument("--fast", action="store_true", help="Run fast coverage analysis mode")

    args = parser.parse_args()

    if args.fast:
        return run_fast_coverage_analysis()
    else:
        return run_quick_coverage(html=args.html, fail_under=args.fail_under)


if __name__ == "__main__":
    sys.exit(main())
