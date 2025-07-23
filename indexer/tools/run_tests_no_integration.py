#!/usr/bin/env python3
"""
Run tests excluding integration tests.
This is useful for CI/CD pipelines where integration tests might be too slow or require special setup.
"""
import subprocess
import sys


def main():
    """Run pytest excluding integration tests."""
    cmd = ["pytest", "tests/", "-v", "-m", "not integration", "--tb=short", "-ra"]  # Exclude integration tests

    print("Running tests (excluding integration tests)...")
    print(f"Command: {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=False, text=True)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
