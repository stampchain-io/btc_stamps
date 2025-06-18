#!/usr/bin/env python3
"""
Quick coverage report that includes all tests from run_checks.py.
Dynamically imports test list from run_checks to stay in sync.
"""

import ast
import subprocess
import sys
from pathlib import Path


def get_test_files_from_run_checks():
    """Extract the test_files list from run_checks.py."""
    run_checks_path = Path(__file__).parent / "run_checks.py"

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

    # Fallback to hardcoded list if parsing fails
    return get_fallback_test_files()


def get_fallback_test_files():
    """Fallback test list in case parsing fails."""
    return [
        "tests/test_src20_balance.py",
        "tests/test_src20_update_valid.py",
        "tests/test_src20_validator.py",
        "tests/test_src20.py",
        "tests/test_high_risk_src20.py",
        "tests/test_src20_edge_cases.py",
        "tests/test_src20_ledger_validation.py",
        "tests/test_src20_database_transactions.py",
        "tests/test_config.py",
        "tests/test_zlib_compression.py",
        "tests/test_database_manager.py",
        "tests/test_market_data_service.py",
        "tests/test_market_data_jobs.py",
        "tests/test_market_data_source_tracking.py",
        "tests/test_source_reliability_service.py",
        "tests/test_src20_multi_source_aggregation.py",
        "tests/test_src20_advanced_aggregation.py",
        "tests/test_collection_aggregation.py",
        "tests/test_holder_cache_fix.py",
        "tests/test_reparse_snapshot.py",
        "tests/test_reparse_snapshot_db.py",
        "tests/test_reparse_db_manager.py",
        "tests/test_reparse_validator.py",
        "tests/test_reparse_sequence.py",
        "tests/test_reparse_inmemory_stamp_cache.py",
        "tests/test_quick_consensus.py",
        "tests/test_pipeline_executor_lifecycle.py",
        "tests/test_fallback_mode.py",
        "tests/test_server.py",
        "tests/test_blocks_fallback_integration.py",
        "tests/test_transaction_processing.py",
        "tests/test_block_validation.py",
        "tests/thread_safety/test_thread_safety.py",
        "tests/test_filesize_tracking.py",
        "tests/test_util_functions.py",
        "tests/test_base64_utils.py",
        "tests/test_enhanced_mime_detection.py",
        "tests/test_files_utils.py",
        "tests/test_zmq_utils.py",
        "tests/test_aws.py",
        "tests/test_async_upload_comprehensive.py",
        "tests/test_market_data_scheduler_flag.py",
        "tests/test_database.py",
    ]


def run_quick_coverage(html=False, fail_under=45):
    """Run coverage on all test files from run_checks.py."""
    print("🚀 Running quick coverage report (synced with run_checks.py)...")
    print(f"   Coverage threshold: {fail_under}%")

    # Get test files dynamically
    test_files = get_test_files_from_run_checks()

    # Filter out non-existent files
    existing_test_files = []
    for test_file in test_files:
        if Path(test_file).exists():
            existing_test_files.append(test_file)
        else:
            print(f"⚠️  Warning: Test file not found: {test_file}")

    # Build pytest command
    cmd = ["poetry", "run", "pytest", "--cov=src", "--cov-report=term-missing", f"--cov-fail-under={fail_under}", "-v"]

    if html:
        cmd.append("--cov-report=html")
        print("   HTML report will be generated in htmlcov/")

    # Add working test files
    cmd.extend(existing_test_files)

    print(f"\n📊 Running coverage on {len(existing_test_files)} test files (from run_checks.py)...")

    try:
        result = subprocess.run(cmd, check=True)
        print("\n✅ Coverage check passed!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Coverage check failed with exit code {e.returncode}")
        return False


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Run quick coverage report")
    parser.add_argument("--html", action="store_true", help="Generate HTML coverage report")
    parser.add_argument("--fail-under", type=int, default=45, help="Minimum coverage percentage (default: 45)")

    args = parser.parse_args()

    success = run_quick_coverage(html=args.html, fail_under=args.fail_under)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
