import subprocess
import sys


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
    """Run code formatting and quality checks"""
    commands = [
        "poetry run black . --config=pyproject.toml",
        "poetry run flake8 .",
        "poetry run isort .",
        "poetry run task bandit",
        "poetry run mypy . --explicit-package-bases",
        "poetry run run_safety",
    ]
    return all(run_command(cmd) for cmd in commands)


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
