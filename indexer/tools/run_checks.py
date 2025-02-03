import subprocess
import sys
import os


def run_command(command, ignore_errors=False):
    """Run a command and handle its output"""
    print(f"\n[Running] {command}")
    result = subprocess.run(command, shell=True, text=True, capture_output=True)  # nosec

    if result.stdout:
        print(result.stdout)

    if result.returncode != 0:
        print("Command failed with error:", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        if not ignore_errors:
            raise SystemExit(result.returncode)
        return False
    print("✓ Command succeeded")
    return True


def run_code_quality_checks():
    """Run code quality checks"""
    try:
        # Set test environment variables
        test_env = {"PYTHONPATH": "src:.", "USE_TEST_TX_HEX": "1", "TESTING": "1", "USE_TEST_DB": "1", "MOCK_DB": "1"}
        env = {**os.environ, **test_env}

        # Run pytest for specific test files
        subprocess.run(
            ["poetry", "run", "pytest", "tests/test_src20_balance.py", "-v", "-W", "ignore::UserWarning"], check=True, env=env
        )
        subprocess.run(
            ["poetry", "run", "pytest", "tests/test_src20_update_valid.py", "-v", "-W", "ignore::UserWarning"],
            check=True,
            env=env,
        )
        subprocess.run(
            ["poetry", "run", "pytest", "tests/test_src20_validator.py", "-v", "-W", "ignore::UserWarning"],
            check=True,
            env=env,
        )

        # Run other tests with unittest
        subprocess.run(
            ["poetry", "run", "python3", "-m", "unittest", "discover", "-s", ".", "-p", "test_src20.py"], check=True
        )
        subprocess.run(
            ["poetry", "run", "python3", "-m", "unittest", "discover", "-s", ".", "-p", "test_check_format.py"], check=True
        )
        subprocess.run(["poetry", "run", "python3", "-m", "unittest", "discover", "-s", ".", "-p", "test_arc4.py"], check=True)
        subprocess.run(
            ["poetry", "run", "python3", "-m", "unittest", "discover", "-s", ".", "-p", "test_transactions.py"], check=True
        )

        # Run other quality checks
        subprocess.run(["poetry", "run", "isort", ".", "--check-only"], check=True)
        subprocess.run(["poetry", "run", "black", "--check", ".", "--config=pyproject.toml"], check=True)
        subprocess.run(
            [
                "poetry",
                "run",
                "flake8",
                "src/",
                "tests/",
                "tools/",
                "--count",
                "--exit-zero",
                "--max-complexity=10",
                "--max-line-length=127",
                "--statistics",
            ],
            check=True,
        )
        subprocess.run(["poetry", "run", "mypy", ".", "--explicit-package-bases"], check=True)
        subprocess.run(["poetry", "run", "task", "bandit"], check=True)

        return True
    except subprocess.CalledProcessError as e:
        print(f"Error running code quality checks: {e}")
        return False


def run_rust_checks():
    """Run Rust-specific checks"""
    commands = [
        "cargo fmt --version",
        "cd src/rust_parser && cargo fmt -- --check",
        "rustup show",
        "cd src/rust_parser && cargo clippy -- -D warnings",
    ]
    return all(run_command(cmd) for cmd in commands)


def run_integration_tests():
    """Run integration tests"""
    commands = [
        "poetry run pytest tests/test_block_rollback.py -v",
        "poetry run pytest tests/test_rollback_transactions_stamptable.py -v",
        "poetry run pytest tests/test_integration_block_processing.py -v",
    ]
    return all(run_command(cmd, ignore_errors=True) for cmd in commands)


def main():
    """Main entry point for running all checks"""
    print("\n=== Running Code Quality Checks ===")
    code_quality_ok = run_code_quality_checks()

    print("\n=== Running Rust Checks ===")
    rust_ok = run_rust_checks()

    print("\n=== Running Integration Tests ===")
    integration_ok = run_integration_tests()

    # Summarize results
    print("\n=== Check Summary ===")
    print(f"Code Quality Checks: {'✓' if code_quality_ok else '✗'}")
    print(f"Rust Checks: {'✓' if rust_ok else '✗'}")
    print(f"Integration Tests: {'✓' if integration_ok else '✗'}")

    if not all([code_quality_ok, rust_ok, integration_ok]):
        sys.exit(1)


if __name__ == "__main__":
    main()
