#!/usr/bin/env python3
"""
Quick coverage report focusing on critical modules.
Avoids problematic test files that have import errors.
"""

import subprocess
import sys
from pathlib import Path

# Test files that are known to work
WORKING_TEST_FILES = [
    "tests/test_src20_balance.py",
    "tests/test_src20_update_valid.py",
    "tests/test_src20_validator.py",
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
    "tests/test_src20_multi_source_aggregation.py",
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
]


def run_quick_coverage(html=False, fail_under=35):
    """Run coverage on working test files only."""
    print("🚀 Running quick coverage report on critical modules...")
    print(f"   Coverage threshold: {fail_under}%")

    # Build pytest command
    cmd = ["poetry", "run", "pytest", "--cov=src", "--cov-report=term-missing", f"--cov-fail-under={fail_under}", "-v"]

    if html:
        cmd.append("--cov-report=html")
        print("   HTML report will be generated in htmlcov/")

    # Add working test files
    cmd.extend(WORKING_TEST_FILES)

    print(f"\n📊 Running coverage on {len(WORKING_TEST_FILES)} test files...")

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
    parser.add_argument("--fail-under", type=int, default=35, help="Minimum coverage percentage (default: 35)")

    args = parser.parse_args()

    success = run_quick_coverage(html=args.html, fail_under=args.fail_under)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
