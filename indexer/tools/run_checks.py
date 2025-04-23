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
        test_env = {"PYTHONPATH": "src:.", "USE_TEST_TX_HEX": "1", "TESTING": "1", "USE_TEST_DB": "1", "MOCK_DB": "1"}
        env = {**os.environ, **test_env}

        logger.info(colored("Setting up test environment...", "cyan"))
        for key, value in test_env.items():
            logger.info(f"  {colored(key, 'yellow')} = {colored(value, 'white')}")

        # Build Rust parser first
        logger.info(colored("Building Rust parser...", "cyan"))
        if not run_rust_checks():
            logger.error("Rust parser checks failed")
            all_passed = False

        # Run pytest for specific test files
        logger.info(colored("Running pytest tests...", "cyan"))

        # Pytest unit test files to run under code quality
        test_files = [
            "tests/test_src20_balance.py",
            "tests/test_src20_update_valid.py",
            "tests/test_src20_validator.py",
            "tests/test_src20.py",
            "tests/test_config.py",
            # Reparse functionality tests
            "tests/test_reparse_snapshot.py",
            "tests/test_reparse_snapshot_db.py",
            "tests/test_reparse_db_manager.py",
            "tests/test_reparse_validator.py",
            "tests/test_reparse_sequence.py",
            "tests/test_reparse_inmemory_stamp_cache.py",
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

        # Run other tests with unittest
        logger.info(colored("Running unittest tests...", "cyan"))
        unittest_files = ["test_check_format.py", "test_arc4.py", "test_transactions.py"]

        for test_file in unittest_files:
            file_name = colored(test_file, "yellow")
            logger.info(f"Running {file_name}")
            try:
                subprocess.run(
                    ["poetry", "run", "python3", "-m", "unittest", "discover", "-s", ".", "-p", test_file], check=True
                )
                logger.info(colored(f"PASS: {test_file}", "green"))
            except subprocess.CalledProcessError:
                code_quality_failures.append(f"unittest:{test_file}")
                logger.error(colored(f"FAIL: {test_file}", "red"))
                all_passed = False

        # Run other quality checks
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
        if run_command("poetry run mypy . --explicit-package-bases", ignore_errors=True):
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

    commands = [
        # First ensure maturin is installed
        "poetry run pip install maturin --quiet",
        # Run Rust checks
        "cd src/rust_parser && cargo fmt --version",
        "cd src/rust_parser && cargo fmt -- --check",
        "cd src/rust_parser && rustup show",
        "cd src/rust_parser && cargo clippy -- -D warnings",
        # Build the parser
        "cd src/rust_parser && poetry run maturin develop --release",
        # Verify the build
        """cd src/rust_parser && poetry run python -c \"from btc_stamps_parser import FastTransactionParser; parser = FastTransactionParser()\" """,
    ]

    all_passed = True
    for i, cmd in enumerate(commands):
        progress = f"[{i+1}/{len(commands)}]"
        logger.info(f"{progress} {colored('Running Rust check:', 'cyan')} {colored(cmd, 'yellow')}")
        cmd_result = run_command(cmd, ignore_errors=True)
        if not cmd_result:
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

    commands = [
        "poetry run pytest tests/test_block_rollback.py -v",
        "poetry run pytest tests/test_rollback_transactions_stamptable.py -v",
        "poetry run pytest tests/test_integration_block_processing.py -v",
        "poetry run pytest tests/test_reorg_handling.py -v",
        "poetry run pytest tests/test_aws_integration.py -v",
        "poetry run pytest tests/test_shutdown_callbacks.py -v",
    ]

    all_passed = True
    for i, cmd in enumerate(commands):
        progress = f"[{i+1}/{len(commands)}]"
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
    test_env = {"PYTHONPATH": "src:.", "USE_TEST_TX_HEX": "1", "TESTING": "1", "USE_TEST_DB": "1", "MOCK_DB": "1"}
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
        ("Code Quality Checks", "💣 PASS" if code_quality_ok else f"💀 FAIL [{', '.join(code_quality_failures)}]"),
        ("Rust Checks", "💣 PASS" if rust_ok else f"💀 FAIL [{', '.join(rust_failures)}]"),
        ("Integration Tests", "💣 PASS" if integration_ok else f"💀 FAIL [{', '.join(integration_failures)}]"),
    ]
    # Determine column widths based on content
    name_w = max(len(name) for name, _ in rows + [("💻 Check Type", "")])
    status_w = max(len(status) for _, status in rows + [("", "🛡️ Status")])
    border = f"+{'-'*(name_w+2)}+{'-'*(status_w+2)}+"
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

    # Detailed substep failures for code quality
    if code_quality_failures:
        print(colored(f"DETAILS: Code Quality failures -> {', '.join(code_quality_failures)}", "magenta"))
    # Detailed substep failures for integration tests
    if integration_failures:
        print(colored(f"DETAILS: Integration test failures -> {', '.join(integration_failures)}", "magenta"))
    # Detailed substep failures for rust checks
    if rust_failures:
        print(colored(f"DETAILS: Rust check failures -> {', '.join(rust_failures)}", "magenta"))

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
    result = run_code_quality_checks(auto_fix=False)
    if not result:
        logger.error("Code quality checks failed. Exiting with code 1.")
        sys.exit(1)
    logger.info("All code quality checks passed. Exiting with code 0.")
    sys.exit(0)


if __name__ == "__main__":
    main()
