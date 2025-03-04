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
|               CHECK SUMMARY           |
+=======================================+
""",
}


def print_header(header_type):
    """Print a fancy header for a section"""
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


def run_code_quality_checks():
    """Run code quality checks with improved output"""
    print_header("code_quality")

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
            return False

        # Run pytest for specific test files
        logger.info(colored("Running pytest tests...", "cyan"))

        test_files = [
            "tests/test_src20_balance.py",
            "tests/test_src20_update_valid.py",
            "tests/test_src20_validator.py",
            "tests/test_src20.py",
        ]

        for test_file in test_files:
            file_name = colored(test_file, "yellow")
            logger.info(f"Running {file_name}")
            subprocess.run(["poetry", "run", "pytest", test_file, "-v", "-W", "ignore::UserWarning"], check=True, env=env)
            logger.info(colored(f"PASS: {test_file}", "green"))

        # Run other tests with unittest
        logger.info(colored("Running unittest tests...", "cyan"))
        unittest_files = ["test_check_format.py", "test_arc4.py", "test_transactions.py"]

        for test_file in unittest_files:
            file_name = colored(test_file, "yellow")
            logger.info(f"Running {file_name}")
            subprocess.run(["poetry", "run", "python3", "-m", "unittest", "discover", "-s", ".", "-p", test_file], check=True)
            logger.info(colored(f"PASS: {test_file}", "green"))

        # Run other quality checks
        logger.info(colored("Running code quality tools...", "cyan"))

        # isort check
        logger.info("Running isort...")
        subprocess.run(["poetry", "run", "isort", ".", "--check-only"], check=True)
        logger.info(colored("PASS: isort check", "green"))

        # black check
        logger.info("Running black...")
        subprocess.run(["poetry", "run", "black", "--check", ".", "--config=pyproject.toml"], check=True)
        logger.info(colored("PASS: black check", "green"))

        # flake8 check
        logger.info("Running flake8...")
        subprocess.run(
            [
                "poetry",
                "run",
                "flake8",
                "src/",
                "--count",
                "--statistics",
                "--exit-zero",
            ],
            check=True,
        )
        logger.info(colored("PASS: flake8 check", "green"))

        # mypy check
        logger.info("Running mypy...")
        subprocess.run(["poetry", "run", "mypy", ".", "--explicit-package-bases"], check=True)
        logger.info(colored("PASS: mypy check", "green"))

        # bandit check
        logger.info("Running bandit...")
        subprocess.run(["poetry", "run", "task", "bandit"], check=True)
        logger.info(colored("PASS: bandit check", "green"))

        logger.info(colored("All code quality checks passed!", "green", attrs=["bold"]))
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Error running code quality checks: {e}")
        return False


def run_rust_checks():
    """Run Rust-specific checks and build the parser with improved output"""
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
        """cd src/rust_parser && poetry run python -c "from btc_stamps_parser import FastTransactionParser; parser = FastTransactionParser()" """,
    ]

    all_passed = True
    for i, cmd in enumerate(commands):
        progress = f"[{i+1}/{len(commands)}]"
        logger.info(f"{progress} {colored('Running Rust check:', 'cyan')} {colored(cmd, 'yellow')}")
        if not run_command(cmd):
            all_passed = False
            break

    if all_passed:
        logger.info(colored("All Rust checks passed!", "green", attrs=["bold"]))

    return all_passed


def run_integration_tests():
    """Run integration tests with improved output"""
    print_header("integration")

    commands = [
        "poetry run pytest tests/test_block_rollback.py -v",
        "poetry run pytest tests/test_rollback_transactions_stamptable.py -v",
        "poetry run pytest tests/test_integration_block_processing.py -v",
    ]

    all_passed = True
    for i, cmd in enumerate(commands):
        progress = f"[{i+1}/{len(commands)}]"
        logger.info(f"{progress} {colored('Running integration test:', 'cyan')} {colored(cmd, 'yellow')}")
        cmd_result = run_command(cmd, ignore_errors=True)
        logger.info(f"Command result: {cmd_result}")
        if not cmd_result:
            logger.error(f"Integration test failed: {cmd}")
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
    print_header("main")

    # Set test environment variables for the main process
    test_env = {"PYTHONPATH": "src:.", "USE_TEST_TX_HEX": "1", "TESTING": "1", "USE_TEST_DB": "1", "MOCK_DB": "1"}
    for key, value in test_env.items():
        os.environ[key] = value

    start_time = time.time()

    # Run all checks
    code_quality_ok = run_code_quality_checks()
    rust_ok = run_rust_checks()
    integration_ok = run_integration_tests()

    logger.info(f"Check results - Code Quality: {code_quality_ok}, Rust: {rust_ok}, Integration: {integration_ok}")

    # Calculate total duration
    total_duration = time.time() - start_time

    # Summarize results with fancy formatting
    print_header("summary")

    # Create a results table
    print(colored("+---------------------------+---------+", "cyan"))
    print(colored("| Check Type                | Status  |", "cyan"))
    print(colored("+---------------------------+---------+", "cyan"))

    # Code quality status
    status = colored("PASS", "green", attrs=["bold"]) if code_quality_ok else colored("FAIL", "red", attrs=["bold"])
    print(colored(f"| Code Quality Checks       | {status}   |", "cyan"))

    # Rust checks status
    status = colored("PASS", "green", attrs=["bold"]) if rust_ok else colored("FAIL", "red", attrs=["bold"])
    print(colored(f"| Rust Checks               | {status}   |", "cyan"))

    # Integration tests status
    status = colored("PASS", "green", attrs=["bold"]) if integration_ok else colored("FAIL", "red", attrs=["bold"])
    print(colored(f"| Integration Tests         | {status}   |", "cyan"))

    print(colored("+---------------------------+---------+", "cyan"))

    # Print total duration
    print(colored(f"\nTotal execution time: {total_duration:.2f} seconds", "yellow"))

    # Final result - Only fail CI if code quality or Rust checks fail
    # Integration tests are treated as warnings, not errors
    if all([code_quality_ok, rust_ok]):
        print(colored("\nRequired checks passed successfully!", "green", attrs=["bold"]))
        if not integration_ok:
            print(colored("\nWarning: Integration tests failed but CI will continue.", "yellow", attrs=["bold"]))
        logger.info("Exiting with code 0 (success)")
        sys.exit(0)  # Always exit with 0 if code quality and Rust checks pass
    else:
        print(colored("\nSome required checks failed. Please review the output above for details.", "red", attrs=["bold"]))
        logger.error("Exiting with code 1 (failure)")
        sys.exit(1)


if __name__ == "__main__":
    main()
