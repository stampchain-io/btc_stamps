import argparse
import logging
import os
import subprocess
import sys
import time

from colorlog import ColoredFormatter
from termcolor import colored


# Set up colorful logging
def setup_logger():
    """Set up a colorful logger for better readability"""
    handler = logging.StreamHandler()
    formatter = ColoredFormatter(
        "%(log_color)s%(levelname)-8s%(reset)s %(message_log_color)s%(message)s",
        datefmt=None,
        reset=True,
        log_colors={
            "DEBUG": "cyan",
            "INFO": "green",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "red,bg_white",
        },
        secondary_log_colors={"message": {"INFO": "white", "WARNING": "yellow", "ERROR": "red", "CRITICAL": "red"}},
        style="%",
    )
    handler.setFormatter(formatter)

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    return logger


logger = setup_logger()

# ASCII art for section headers
HEADER_ART = {
    "main": """
+=======================================+
|      BITCOIN STAMPS QUALITY CHECKS    |
+=======================================+
""",
    "code_quality": """
+=======================================+
|           CODE QUALITY CHECKS         |
+=======================================+
""",
    "rust": """
+=======================================+
|               RUST CHECKS             |
+=======================================+
""",
    "integration": """
+=======================================+
|           INTEGRATION TESTS           |
+=======================================+
""",
    "summary": """
+=======================================+
|       ~*~[ CHECK SUMMARY ]~*~           |
+=======================================+
""",
}


def print_header(header_type):
    """Print a fancy header for a section"""
    hacker_banner = colored(f"*** H4XOR_{header_type.upper()} ***", "magenta", attrs=["bold", "underline"])
    print(hacker_banner)
    print(colored(HEADER_ART[header_type], "cyan"))


def run_command(command, ignore_errors=False):
    """Run a command and handle its output with improved formatting"""
    # Create a fancy command display
    cmd_display = f">> {colored('Running:', 'blue', attrs=['bold'])} {colored(command, 'yellow')}"
    print(f"\n{cmd_display}")
    print(colored("-" * 80, "blue"))

    start_time = time.time()
    result = subprocess.run(command, shell=True, text=True, capture_output=True)  # nosec
    duration = time.time() - start_time

    # Print stdout with better formatting if it exists
    if result.stdout:
        print(colored("Output:", "green"))
        print(result.stdout)

    # Handle command result
    if result.returncode != 0:
        error_msg = colored("Command failed with error:", "red", attrs=["bold"])
        print(f"{error_msg}", file=sys.stderr)
        if result.stderr:
            print(colored(result.stderr, "red"), file=sys.stderr)
        print(colored(f"Duration: {duration:.2f}s", "yellow"))
        logger.error(f"Command failed with return code: {result.returncode}")
        if not ignore_errors:
            logger.error(f"Exiting with code {result.returncode} due to command failure")
            raise SystemExit(result.returncode)
        return False

    success_msg = colored(f"Command succeeded in {duration:.2f}s", "green", attrs=["bold"])
    print(success_msg)
    return True


# Track detailed failures in code quality
code_quality_failures = []
# Track detailed failures in integration tests
integration_failures = []
# Track detailed failures in rust checks
rust_failures = []


def run_code_quality_checks(auto_fix=False):
    """Run code quality checks with improved output"""
    global code_quality_failures
    code_quality_failures = []
    print_header("code_quality")
    all_passed = True

    try:
        # Set test environment variables
        test_env = {
            "PYTHONPATH": "src",
            "USE_TEST_TX_HEX": "1",
            "TESTING": "1",
            "USE_TEST_DB": "1",
            "MOCK_DB": "1",
            "CI_FIXTURE_MODE": "true",
        }
        # Also set them in the current process to ensure imports work correctly
        for key, value in test_env.items():
            os.environ[key] = value
        env = {**os.environ, **test_env}

        logger.info(colored("Setting up test environment...", "cyan"))
        for key, value in test_env.items():
            logger.info(f"  {colored(key, 'yellow')} = {colored(value, 'white')}")

        # Run linting checks first - they're quick and can catch issues early
        logger.info(colored("Running code quality tools...", "cyan"))

        # isort check
        logger.info("Running isort...")
        cmd = "poetry run isort ." if auto_fix else "poetry run isort . --check-only"
        logger.info(colored(f"H4XOR_RUN: {cmd}", "magenta"))
        if run_command(cmd, ignore_errors=True):
            logger.info(colored("💣 PASS: isort", "green"))
        else:
            code_quality_failures.append("isort")
            logger.error(colored("💀 FAIL: isort", "red"))
            all_passed = False

        # black check
        logger.info("Running black...")
        cmd = (
            "poetry run black . --config=pyproject.toml" if auto_fix else "poetry run black --check . --config=pyproject.toml"
        )
        logger.info(colored(f"H4XOR_RUN: {cmd}", "magenta"))
        if run_command(cmd, ignore_errors=True):
            logger.info(colored("💣 PASS: black", "green"))
        else:
            code_quality_failures.append("black")
            logger.error(colored("💀 FAIL: black", "red"))
            all_passed = False

        # flake8 check
        logger.info("Running flake8...")
        if run_command("poetry run flake8 src/ --count --statistics", ignore_errors=True):
            logger.info(colored("PASS: flake8 check", "green"))
        else:
            code_quality_failures.append("flake8")
            logger.error(colored("FAIL: flake8 check", "red"))
            all_passed = False

        # mypy check
        logger.info("Running mypy...")
        if run_command("poetry run mypy src/ --explicit-package-bases", ignore_errors=True):
            logger.info(colored("PASS: mypy check", "green"))
        else:
            code_quality_failures.append("mypy")
            logger.error(colored("FAIL: mypy check", "red"))
            all_passed = False

        # bandit check
        logger.info("Running bandit...")
        if run_command("poetry run task bandit", ignore_errors=True):
            logger.info(colored("PASS: bandit check", "green"))
        else:
            code_quality_failures.append("bandit")
            logger.error(colored("FAIL: bandit check", "red"))
            all_passed = False

        # Build Rust parser after linting checks
        logger.info(colored("Building Rust parser...", "cyan"))
        if not run_rust_checks():
            logger.error("Rust parser checks failed")
            all_passed = False

        # Run pytest for unit tests only (exclude integration tests)
        logger.info(colored("Running unit tests...", "cyan"))

        # Run tests excluding only tests that require a Bitcoin node
        # Include unit tests, mocked tests, and tests that only need internet
        cmd = [
            "poetry",
            "run",
            "pytest",
            "-m",
            "not requires_bitcoin_node",
            "-v",
            "-W",
            "ignore::UserWarning",
            "--tb=short",
        ]

        try:
            subprocess.run(cmd, check=True, env=env)
            logger.info(colored("PASS: Unit tests", "green"))
        except subprocess.CalledProcessError:
            code_quality_failures.append("pytest:unit_tests")
            logger.error(colored("FAIL: Unit tests", "red"))
            all_passed = False

        # Note: Individual test files approach is kept below but commented out
        # in case we need to revert or reference specific tests
        """
        # Pytest unit test files to run under code quality
        test_files = [
            "tests/test_src20_balance.py",
            "tests/test_src20_update_valid.py",
            "tests/test_src20_validator.py",
            "tests/test_src20.py",
            "tests/test_high_risk_src20.py",  # Comprehensive high-risk SRC-20 test suite
            "tests/test_src20_edge_cases.py",  # Edge case coverage for SRC-20 implementation
            "tests/test_src20_ledger_validation.py",  # Ledger validation and consensus testing
            "tests/test_src20_database_transactions.py",  # Database transaction atomicity testing
            "tests/test_config.py",
            "tests/test_zlib_compression.py",  # Zlib compression/decompression functionality tests
            "tests/test_database_manager.py",  # DatabaseManager connection pooling and operations tests
            # Market data functionality tests
            "tests/test_market_data_service.py",
            "tests/test_market_data_jobs.py",
            "tests/test_market_data_source_tracking.py",
            "tests/test_source_reliability_service.py",  # Source reliability tracking system tests
            "tests/test_src20_multi_source_aggregation.py",
            "tests/test_src20_advanced_aggregation.py",  # Advanced aggregation features for Task 9
            "tests/test_collection_aggregation.py",  # Collection-level aggregation for Task 12
            "tests/test_holder_cache_fix.py",
            # Reparse functionality tests
            "tests/test_reparse_snapshot.py",
            "tests/test_reparse_snapshot_db.py",
            "tests/test_reparse_db_manager.py",
            "tests/test_reparse_validator.py",
            "tests/test_reparse_sequence.py",
            "tests/test_reparse_inmemory_stamp_cache.py",
            "tests/test_quick_consensus.py",
            # ThreadPoolExecutor lifecycle management tests
            "tests/test_pipeline_executor_lifecycle.py",
            # Fallback mode functionality tests
            "tests/test_fallback_mode.py",
            # Server module tests
            "tests/test_server.py",
            # Pipeline utils tests
            "tests/test_pipeline_utils.py",
            # Fallback mode integration tests for blocks.py
            "tests/test_blocks_fallback_integration.py",
            # Transaction processing function tests (refactored modules)
            "tests/test_transaction_processing.py",
            # Block validation function tests (refactored modules)
            "tests/test_block_validation.py",
            # SRC-20 thread safety and locking mechanism tests
            "tests/thread_safety/test_thread_safety.py",
            # Filesize tracking and utility function tests
            "tests/test_filesize_tracking.py",
            "tests/test_util_functions.py",
            # Additional utility function tests for enhanced coverage
            "tests/test_base64_utils.py",
            "tests/test_enhanced_mime_detection.py",
            "tests/test_files_utils.py",
            "tests/test_zmq_utils.py",
            # External services tests
            "tests/test_aws.py",  # AWS S3 and CloudFront integration tests
            "tests/test_async_upload_comprehensive.py",  # Async upload functionality tests
            # Market data scheduler flag tests
            "tests/test_market_data_scheduler_flag.py",  # Market data scheduler configuration flag tests
            # Database operations tests
            "tests/test_database.py",  # Database.py operations tests
            # New low-hanging fruit tests
            "tests/test_fast_parser.py",  # Fast parser module tests
            "tests/test_resource_manager.py",  # Resource manager module tests
            "tests/test_blocks_simple.py",  # Simplified blocks.py function tests
            # Additional properly mocked tests for improved coverage
            "tests/test_unicode_emoji_handling.py",  # Pure unit tests for string processing
            "tests/test_validator.py",  # Properly mocks backend and database connections
            "tests/test_stampscan_integration.py",  # Despite name, properly mocks API calls
            "tests/test_parser.py",  # Tests parser with sample hex data, no external calls
            "tests/test_async_upload.py",  # Mocks boto3 and database connections
            "tests/test_node_health.py",  # Node health monitoring and shutdown callbacks tests
        ]

        for test_file in test_files:
            file_name = colored(test_file, "yellow")
            logger.info(f"Running {file_name}")
            try:
                subprocess.run(["poetry", "run", "pytest", test_file, "-v", "-W", "ignore::UserWarning"], check=True, env=env)
                logger.info(colored(f"PASS: {test_file}", "green"))
            except subprocess.CalledProcessError:
                code_quality_failures.append(f"pytest:{test_file}")
                logger.error(colored(f"FAIL: {test_file}", "red"))
                all_passed = False
        """

        # Note: test_check_format.py, test_arc4.py, and test_transactions.py are now
        # included in the main pytest run above. Pytest can run unittest-style tests.

        # Linting checks have already been run at the beginning of this function

        if all_passed:
            logger.info(colored("All code quality checks passed!", "green", attrs=["bold"]))
        else:
            logger.error(colored("Some code quality checks failed!", "red", attrs=["bold"]))
        return all_passed
    except subprocess.CalledProcessError as e:
        logger.error(f"Error running code quality checks: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error running code quality checks: {e}")
        return False


def run_rust_checks():
    """Run Rust-specific checks and build the parser with improved output"""
    global rust_failures
    rust_failures = []
    print_header("rust")

    # First check if the parser is already working
    logger.info("Checking if Rust parser is already available...")
    parser_available = run_command(
        'poetry run python -c "from btc_stamps_parser import FastTransactionParser; parser = FastTransactionParser()"',
        ignore_errors=True,
    )

    commands = [
        # First ensure maturin is installed
        "poetry run pip install maturin --quiet",
        # Run Rust checks
        "cd src/rust_parser && cargo fmt --version",
        "cd src/rust_parser && cargo fmt -- --check",
        "cd src/rust_parser && rustup show",
        "cd src/rust_parser && cargo clippy -- -D warnings",
        # Run Rust tests
        "cd src/rust_parser && cargo test",
    ]

    # Only try to build if parser is not available, or always verify it works
    if not parser_available:
        commands.extend(
            [
                # Build the parser
                "cd src/rust_parser && poetry run maturin develop --release",
            ]
        )
    else:
        logger.info(colored("✅ Rust parser already built and available, skipping maturin develop", "green"))

    # Always verify the parser works
    commands.append(
        """poetry run python -c \"from btc_stamps_parser import FastTransactionParser; parser = FastTransactionParser()\" """
    )

    all_passed = True
    for i, cmd in enumerate(commands):
        progress = f"[{i + 1}/{len(commands)}]"
        logger.info(f"{progress} {colored('Running Rust check:', 'cyan')} {colored(cmd, 'yellow')}")
        cmd_result = run_command(cmd, ignore_errors=True)
        if not cmd_result:
            # Special handling for maturin build - if parser verification still works, don't fail
            if "maturin develop" in cmd:
                logger.warning(colored("⚠️  Maturin build failed, but checking if parser still works...", "yellow"))
                verify_result = run_command(
                    """poetry run python -c \"from btc_stamps_parser import FastTransactionParser; parser = FastTransactionParser()\" """,
                    ignore_errors=True,
                )
                if verify_result:
                    logger.info(colored("✅ Parser verification passed despite maturin failure", "green"))
                    continue
                else:
                    logger.error(colored("❌ Parser verification failed after maturin failure", "red"))
                    rust_failures.append(cmd)
                    all_passed = False
            else:
                rust_failures.append(cmd)
                all_passed = False
        # continue to run next commands

    if all_passed:
        logger.info(colored("All Rust checks passed!", "green", attrs=["bold"]))
    else:
        logger.error(colored("Some Rust checks failed!", "red", attrs=["bold"]))

    return all_passed


def run_rust_checks_standalone():
    """Entry point for running Rust checks as a standalone command.
    This function is called by 'poetry run check-rust' and should
    exit with code 0 if checks pass, and code 1 if checks fail."""
    result = run_rust_checks()
    # Exit with appropriate code based on check results
    if not result:
        logger.error("Rust checks failed. Exiting with code 1.")
        sys.exit(1)
    logger.info("All Rust checks passed. Exiting with code 0.")
    sys.exit(0)


def run_integration_tests():
    """Run integration tests with improved output"""
    global integration_failures
    integration_failures = []
    print_header("integration")

    # Run all tests marked as integration or requiring external services
    # Note: Tests marked with requires_bitcoin_node need a local Bitcoin node
    cmd = [
        "poetry",
        "run",
        "pytest",
        "-m",
        "integration or requires_db or requires_network or requires_bitcoin_node",
        "-v",
        "--tb=short",
    ]

    logger.info(colored("Running integration tests (requires local services)...", "cyan"))

    try:
        subprocess.run(cmd, check=True)
        logger.info(colored("All integration tests passed!", "green", attrs=["bold"]))
        return True
    except subprocess.CalledProcessError:
        integration_failures.append("pytest:integration_tests")
        logger.error(colored("Some integration tests failed!", "red", attrs=["bold"]))
        return False

    # Note: Old approach is kept below for reference
    """
    commands = [
        "poetry run pytest tests/test_block_rollback.py -v",
        "poetry run pytest tests/test_rollback_transactions_stamptable.py -v",
        "poetry run pytest tests/test_integration_block_processing.py -v",
        "poetry run pytest tests/test_reorg_handling.py -v",
        "poetry run pytest tests/test_aws_integration.py -v",
        "poetry run pytest tests/test_shutdown_callbacks.py -v",
        # Market data API integration tests
        "poetry run pytest tests/test_kucoin_integration.py -v -m integration",
        "poetry run pytest tests/test_openstamp_integration.py -v -m integration",
        "poetry run pytest tests/test_src20_worker_integration.py -v -m integration",
    ]

    all_passed = True
    for i, cmd in enumerate(commands):
        progress = f"[{i + 1}/{len(commands)}]"
        logger.info(f"{progress} {colored('Running integration test:', 'cyan')} {colored(cmd, 'yellow')}")
        cmd_result = run_command(cmd, ignore_errors=True)
        logger.info(f"Command result: {cmd_result}")
        if not cmd_result:
            logger.error(f"Integration test failed: {cmd}")
            integration_failures.append(cmd)
            all_passed = False

    if all_passed:
        logger.info(colored("All integration tests passed!", "green", attrs=["bold"]))
    else:
        logger.error(colored("Some integration tests failed!", "red", attrs=["bold"]))

    logger.info(f"Final integration tests result: {all_passed}")
    return all_passed
    """


def run_integration_tests_standalone():
    """Entry point for running integration tests as a standalone command.
    This function is called by 'poetry run check-integration' and should
    exit with code 0 if tests pass, and code 1 if tests fail."""
    result = run_integration_tests()
    # Exit with appropriate code based on test results
    sys.exit(0 if result else 1)


def main():
    """Main entry point for running all checks with improved output"""
    # Parse command-line flags
    parser = argparse.ArgumentParser(prog="run_checks", description="Bitcoin Stamps Quality Checks")
    parser.add_argument("--auto-fix", action="store_true", help="Auto-fix style issues with black and isort")
    args = parser.parse_args()
    auto_fix = args.auto_fix
    print_header("main")
    if auto_fix:
        logger.info(colored("⚡️ Auto-fix enabled", "magenta"))

    # Set test environment variables for the main process
    test_env = {
        "PYTHONPATH": "src",
        "USE_TEST_TX_HEX": "1",
        "TESTING": "1",
        "USE_TEST_DB": "1",
        "MOCK_DB": "1",
        "CI_FIXTURE_MODE": "true",
    }
    for key, value in test_env.items():
        os.environ[key] = value

    start_time = time.time()

    # Run all checks
    code_quality_ok = run_code_quality_checks(auto_fix)
    rust_ok = run_rust_checks()
    integration_ok = run_integration_tests()

    logger.info(f"Check results - Code Quality: {code_quality_ok}, Rust: {rust_ok}, Integration: {integration_ok}")

    # Calculate total duration
    total_duration = time.time() - start_time

    # Summarize results with fancy formatting
    print_header("summary")
    # Build a dynamically sized results table
    rows = [
        ("Code Quality Checks", "💣 PASS" if code_quality_ok else "💀 FAIL"),
        ("Rust Checks", "💣 PASS" if rust_ok else "💀 FAIL"),
        ("Integration Tests", "💣 PASS" if integration_ok else "💀 FAIL"),
    ]
    # Determine column widths based on content
    name_w = max(len(name) for name, _ in rows + [("💻 Check Type", "")])
    status_w = max(len(status) for _, status in rows + [("", "🛡️ Status")])
    border = f"+{'-' * (name_w + 2)}+{'-' * (status_w + 2)}+"
    header = f"| {'💻 Check Type'.ljust(name_w)} | {'🛡️ Status'.ljust(status_w)} |"
    print(colored(border, "magenta"))
    print(colored(header, "magenta"))
    print(colored(border, "magenta"))
    for name, stat in rows:
        # color the status part green or red
        stat_colored = colored(stat, "green" if "PASS" in stat else "red", attrs=["bold"])
        row = f"| {name.ljust(name_w)} | {stat.ljust(status_w)} |"
        row = row.replace(stat, stat_colored)
        print(colored(row, "magenta"))
    print(colored(border, "magenta"))

    # Enhanced detailed failure breakdown
    print(colored("\n🔍 DETAILED RESULTS:", "yellow", attrs=["bold"]))

    # Code Quality detailed breakdown
    if code_quality_failures:
        print(colored("  📝 CODE QUALITY FAILURES:", "red"))
        linter_failures = [f for f in code_quality_failures if f in ["isort", "black", "flake8", "mypy", "bandit"]]
        test_failures = [f.replace("pytest:", "") for f in code_quality_failures if f.startswith("pytest:")]
        build_failures = [f for f in code_quality_failures if f not in linter_failures and not f.startswith("pytest:")]

        if linter_failures:
            print(colored(f"    🔧 Linters: {', '.join(linter_failures)}", "red"))
        if test_failures:
            print(colored(f"    🧪 Tests: {', '.join(test_failures)}", "red"))
        if build_failures:
            print(colored(f"    🏗️  Build: {', '.join(build_failures)}", "red"))
    else:
        print(colored("  ✅ CODE QUALITY: All passed", "green"))

    # Rust detailed breakdown
    if rust_failures:
        print(colored("  🦀 RUST FAILURES:", "red"))
        for failure in rust_failures[:3]:  # Show first 3 failures
            short_cmd = failure.split(" && ")[-1] if " && " in failure else failure
            print(colored(f"    ❌ {short_cmd}", "red"))
        if len(rust_failures) > 3:
            print(colored(f"    ... and {len(rust_failures) - 3} more", "red"))
    else:
        print(colored("  ✅ RUST: All passed", "green"))

    # Integration detailed breakdown
    if integration_failures:
        print(colored("  🔗 INTEGRATION FAILURES:", "red"))
        for failure in integration_failures:
            print(colored(f"    ❌ {failure}", "red"))
    else:
        print(colored("  ✅ INTEGRATION: All passed", "green"))

    # Print total duration
    print(colored(f"\nTotal execution time: {total_duration:.2f} seconds", "yellow"))

    # Final result - Fail CI if code quality or Rust checks fail
    # Integration tests are treated as warnings, not errors
    if code_quality_ok and rust_ok:
        print(colored("\nRequired checks passed successfully!", "green", attrs=["bold"]))
        if not integration_ok:
            print(colored("\nWarning: Integration tests failed but CI will continue.", "yellow", attrs=["bold"]))
        logger.info("Exiting with code 0 (success)")
        sys.exit(0)
    else:
        print(colored("\nSome required checks failed. Please review the output above for details.", "red", attrs=["bold"]))
        if not code_quality_ok:
            logger.error("Code quality checks failed.")
        if not rust_ok:
            logger.error("Rust checks failed.")
        logger.error("Exiting with code 1 (failure)")
        sys.exit(1)


# Standalone entrypoint for code quality in CI, exits 0 if all checks pass, else 1
def run_code_quality_checks_standalone():
    """Entry point for running code quality checks as a standalone command.
    This function is called by 'poetry run check-code' and supports --auto-fix flag."""
    # Parse command-line flags
    parser = argparse.ArgumentParser(prog="check-code", description="Bitcoin Stamps Code Quality Checks")
    parser.add_argument("--auto-fix", action="store_true", help="Auto-fix style issues with black and isort")
    args = parser.parse_args()

    if args.auto_fix:
        logger.info(colored("⚡️ Auto-fix enabled", "magenta"))

    result = run_code_quality_checks(auto_fix=args.auto_fix)

    # Print detailed final summary with specific failures
    print(colored("\n" + "=" * 80, "magenta"))
    print(colored("CODE QUALITY SUMMARY", "magenta", attrs=["bold"]))
    print(colored("=" * 80, "magenta"))

    if result:
        logger.info(colored("✅ All code quality checks passed!", "green", attrs=["bold"]))
        logger.info("Exiting with code 0.")
        sys.exit(0)
    else:
        logger.error(colored("❌ Code quality checks failed!", "red", attrs=["bold"]))

        # Show detailed breakdown of what failed
        if code_quality_failures:
            print(colored("\n🔍 DETAILED FAILURE BREAKDOWN:", "yellow", attrs=["bold"]))

            # Categorize failures for better understanding
            linter_failures = []
            test_failures = []
            build_failures = []

            for failure in code_quality_failures:
                if failure in ["isort", "black", "flake8", "mypy", "bandit"]:
                    linter_failures.append(failure)
                elif failure.startswith("pytest:"):
                    test_failures.append(failure.replace("pytest:", ""))
                else:
                    build_failures.append(failure)

            # Show categorized failures
            if linter_failures:
                print(colored("  📝 LINTER FAILURES:", "red"))
                for failure in linter_failures:
                    print(colored(f"    ❌ {failure}", "red"))
                if "isort" in linter_failures or "black" in linter_failures:
                    print(colored("      💡 TIP: Use --auto-fix to fix isort/black issues", "yellow"))
                if "flake8" in linter_failures:
                    print(colored("      💡 TIP: Check code style issues in the output above", "yellow"))
                if "mypy" in linter_failures:
                    print(colored("      💡 TIP: Fix type hints and annotations", "yellow"))
                if "bandit" in linter_failures:
                    print(colored("      💡 TIP: Review security warnings in the output above", "yellow"))

            if test_failures:
                print(colored("  🧪 TEST FAILURES:", "red"))
                for failure in test_failures:
                    print(colored(f"    ❌ {failure}", "red"))
                print(colored("      💡 TIP: Run specific failing tests for more details", "yellow"))

            if build_failures:
                print(colored("  🔧 BUILD FAILURES:", "red"))
                for failure in build_failures:
                    print(colored(f"    ❌ {failure}", "red"))

            # Summary count
            total_failures = len(code_quality_failures)
            print(colored(f"\n📊 TOTAL FAILURES: {total_failures}", "red", attrs=["bold"]))

        else:
            print(colored("💀 FAILED CHECKS: Unable to determine specific failures", "red", attrs=["bold"]))

        # Quick fix suggestions
        print(colored("\n🛠️  QUICK FIX SUGGESTIONS:", "cyan", attrs=["bold"]))
        print(colored("  1. Run with --auto-fix to fix style issues automatically", "cyan"))
        print(colored("  2. Review the detailed output above for specific errors", "cyan"))
        print(colored("  3. Run individual tools manually: poetry run flake8/mypy/bandit", "cyan"))
        print(colored("  4. Check test output for failing unit tests", "cyan"))

        print(colored("=" * 80, "magenta"))
        logger.error("Exiting with code 1.")
        sys.exit(1)


def run_linters_only(auto_fix=False, with_coverage=False):
    """Run only the linting tools (isort, black, flake8, mypy, bandit) without tests.

    Args:
        auto_fix: Enable auto-fix for isort and black
        with_coverage: Include coverage report validation
    """
    print_header("code_quality")
    logger.info(colored("Running linters only...", "cyan"))
    if auto_fix:
        logger.info(colored("⚡️ Auto-fix enabled", "magenta"))
    if with_coverage:
        logger.info(colored("📊 Coverage validation enabled", "magenta"))

    all_passed = True
    linter_failures = []

    # isort check
    logger.info("Running isort...")
    cmd = "poetry run isort ." if auto_fix else "poetry run isort . --check-only"
    logger.info(colored(f"H4XOR_RUN: {cmd}", "magenta"))
    if run_command(cmd, ignore_errors=True):
        logger.info(colored("💣 PASS: isort", "green"))
    else:
        linter_failures.append("isort")
        logger.error(colored("💀 FAIL: isort", "red"))
        all_passed = False

    # black check
    logger.info("Running black...")
    cmd = "poetry run black . --config=pyproject.toml" if auto_fix else "poetry run black --check . --config=pyproject.toml"
    logger.info(colored(f"H4XOR_RUN: {cmd}", "magenta"))
    if run_command(cmd, ignore_errors=True):
        logger.info(colored("💣 PASS: black", "green"))
    else:
        linter_failures.append("black")
        logger.error(colored("💀 FAIL: black", "red"))
        all_passed = False

    # flake8 check
    logger.info("Running flake8...")
    if run_command("poetry run flake8 src/ --count --statistics", ignore_errors=True):
        logger.info(colored("PASS: flake8 check", "green"))
    else:
        linter_failures.append("flake8")
        logger.error(colored("FAIL: flake8 check", "red"))
        all_passed = False

    # mypy check
    logger.info("Running mypy...")
    if run_command("poetry run mypy src/ --explicit-package-bases", ignore_errors=True):
        logger.info(colored("PASS: mypy check", "green"))
    else:
        linter_failures.append("mypy")
        logger.error(colored("FAIL: mypy check", "red"))
        all_passed = False

    # bandit check
    logger.info("Running bandit...")
    if run_command("poetry run task bandit", ignore_errors=True):
        logger.info(colored("PASS: bandit check", "green"))
    else:
        linter_failures.append("bandit")
        logger.error(colored("FAIL: bandit check", "red"))
        all_passed = False

    # Optional: pylint for additional code quality checks
    # Uncomment if you want to add pylint
    # logger.info("Running pylint...")
    # if run_command("poetry run pylint src/ --fail-under=8.0", ignore_errors=True):
    #     logger.info(colored("PASS: pylint check", "green"))
    # else:
    #     linter_failures.append("pylint")
    #     logger.error(colored("FAIL: pylint check", "red"))
    #     all_passed = False

    # Coverage validation
    if with_coverage:
        logger.info(colored("\n📊 Running coverage validation...", "cyan"))
        # Use the quick coverage script that avoids problematic test files
        logger.info("Generating coverage report (quick mode)...")
        if run_command("poetry run coverage-quick --html", ignore_errors=True):
            logger.info(colored("💣 PASS: coverage threshold met (>50%)", "green"))
        else:
            linter_failures.append("coverage")
            logger.error(colored("💀 FAIL: coverage below threshold", "red"))
            logger.info(colored("💡 TIP: Run 'poetry run coverage-quick --html' to see detailed report", "yellow"))
            all_passed = False

    # Print summary similar to main function
    print(colored("\n" + "=" * 80, "magenta"))
    print(colored("LINTER SUMMARY", "magenta", attrs=["bold"]))
    print(colored("=" * 80, "magenta"))

    if all_passed:
        logger.info(colored("✅ All linters passed!", "green", attrs=["bold"]))
    else:
        logger.error(colored("❌ Some linters failed!", "red", attrs=["bold"]))
        print(colored(f"💀 FAILED LINTERS: {', '.join(linter_failures)}", "red", attrs=["bold"]))
        print(colored("💡 TIP: Use --auto-fix to automatically fix isort and black issues", "yellow"))

    print(colored("=" * 80, "magenta"))

    return all_passed, linter_failures


def run_linters_standalone():
    """Standalone entry point for running only linters."""
    parser = argparse.ArgumentParser(prog="lint", description="Run linters only")
    parser.add_argument("--auto-fix", action="store_true", help="Auto-fix style issues with black and isort")
    parser.add_argument("--with-coverage", action="store_true", help="Include coverage report validation")
    args = parser.parse_args()

    all_passed, linter_failures = run_linters_only(args.auto_fix, args.with_coverage)

    if all_passed:
        logger.info("All linters passed. Exiting with code 0.")
        sys.exit(0)
    else:
        logger.error(f"Linters failed: {', '.join(linter_failures)}. Exiting with code 1.")
        sys.exit(1)


if __name__ == "__main__":
    main()
