#!/usr/bin/env python3
"""
Enhanced local coverage runner with various report options and integration support.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional


# Color codes for terminal output
class Colors:
    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


def print_header(text: str):
    """Print colored header."""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.ENDC}\n")


def print_success(text: str):
    """Print success message."""
    print(f"{Colors.OKGREEN}✅ {text}{Colors.ENDC}")


def print_error(text: str):
    """Print error message."""
    print(f"{Colors.FAIL}❌ {text}{Colors.ENDC}")


def print_info(text: str):
    """Print info message."""
    print(f"{Colors.OKCYAN}ℹ️  {text}{Colors.ENDC}")


def run_command(cmd: List[str], description: str = "") -> bool:
    """Run a command and return success status."""
    if description:
        print(f"{Colors.OKBLUE}🔧 {description}{Colors.ENDC}")

    print(f"   {Colors.WARNING}$ {' '.join(cmd)}{Colors.ENDC}")

    result = subprocess.run(cmd, capture_output=False)

    if result.returncode == 0:
        print_success(f"{description} completed")
    else:
        print_error(f"{description} failed (exit code: {result.returncode})")

    return result.returncode == 0


def get_test_groups() -> dict:
    """Define test groups for targeted coverage."""
    return {
        "unit": [
            "tests/test_src20*.py",
            "tests/test_config.py",
            "tests/test_arc4.py",
            "tests/test_transactions.py",
            "tests/test_base64_utils.py",
            "tests/test_files_utils.py",
            "tests/test_high_risk_src20.py",
        ],
        "integration": [
            "tests/test_integration_*.py",
            "tests/test_*_integration.py",
        ],
        "aws": [
            "tests/test_aws_integration.py",
            "tests/test_async_upload.py",
        ],
        "database": [
            "tests/test_reparse_*.py",
            "tests/test_database_*.py",
        ],
        "market": [
            "tests/test_market_data*.py",
            "tests/test_kucoin_*.py",
            "tests/test_openstamp_*.py",
        ],
        "all": ["tests/"],
    }


def main():
    parser = argparse.ArgumentParser(
        description="Enhanced local coverage runner for Bitcoin Stamps Indexer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run coverage on all tests with HTML report
  poetry run python tools/run_local_coverage.py --html

  # Run coverage on unit tests only with minimum threshold
  poetry run python tools/run_local_coverage.py --group unit --fail-under 80

  # Run coverage with all report formats
  poetry run python tools/run_local_coverage.py --all-formats

  # Run coverage on specific test file
  poetry run python tools/run_local_coverage.py --tests tests/test_src20.py
        """,
    )

    # Test selection
    parser.add_argument(
        "--group", choices=list(get_test_groups().keys()), default="all", help="Test group to run (default: all)"
    )
    parser.add_argument("--tests", help="Specific test file(s) or directory (overrides --group)")

    # Report formats
    parser.add_argument("--terminal", "-t", action="store_true", default=True, help="Show terminal report (default: True)")
    parser.add_argument("--html", action="store_true", help="Generate HTML report")
    parser.add_argument("--xml", action="store_true", help="Generate XML report (for CI/CD)")
    parser.add_argument("--json", action="store_true", help="Generate JSON report")
    parser.add_argument("--all-formats", action="store_true", help="Generate all report formats")

    # Coverage options
    parser.add_argument("--fail-under", type=int, help="Fail if coverage is below this percentage")
    parser.add_argument("--no-branch", action="store_true", help="Disable branch coverage")
    parser.add_argument(
        "--show-missing", action="store_true", default=True, help="Show missing lines in terminal report (default: True)"
    )

    # Other options
    parser.add_argument("--open", action="store_true", help="Open HTML report in browser after generation")
    parser.add_argument("--clean", action="store_true", help="Clean coverage data before running")
    parser.add_argument("--parallel", action="store_true", help="Enable parallel test execution")

    args = parser.parse_args()

    print_header("Bitcoin Stamps Indexer - Local Coverage Analysis")

    # Clean coverage data if requested
    if args.clean:
        print_info("Cleaning previous coverage data...")
        for file in [".coverage", "coverage.xml", "coverage.json"]:
            if Path(file).exists():
                Path(file).unlink()
                print(f"   Removed {file}")
        if Path("htmlcov").exists():
            import shutil

            shutil.rmtree("htmlcov")
            print("   Removed htmlcov/")

    # Determine test targets
    test_targets = []
    if args.tests:
        test_targets = [args.tests]
    else:
        test_groups = get_test_groups()
        test_targets = test_groups[args.group]

    print_info(f"Test target(s): {', '.join(test_targets)}")

    # Build base command
    cmd = ["poetry", "run", "pytest"]
    cmd.extend(test_targets)
    cmd.extend(["--cov=src", "--cov-config=.coveragerc"])

    # Add branch coverage unless disabled
    if not args.no_branch:
        cmd.append("--cov-branch")

    # Add fail-under if specified
    if args.fail_under:
        cmd.append(f"--cov-fail-under={args.fail_under}")

    # Add parallel execution if requested
    if args.parallel:
        cmd.extend(["-n", "auto"])

    # Determine report formats
    report_formats = []
    if args.all_formats:
        report_formats = ["term-missing", "html", "xml", "json"]
    else:
        if args.terminal:
            report_formats.append("term-missing" if args.show_missing else "term")
        if args.html:
            report_formats.append("html")
        if args.xml:
            report_formats.append("xml")
        if args.json:
            report_formats.append("json")

    # Add report formats to command
    for fmt in report_formats:
        cmd.append(f"--cov-report={fmt}")

    # Run coverage
    success = run_command(cmd, "Running coverage analysis")

    if success:
        print_header("Coverage Analysis Complete!")

        # Show generated files
        print_info("Generated reports:")
        if "html" in report_formats and Path("htmlcov/index.html").exists():
            print(f"   📊 HTML: {Path('htmlcov/index.html').absolute()}")

            if args.open:
                html_path = "htmlcov/index.html"
                try:
                    if sys.platform == "darwin":
                        subprocess.run(["open", html_path], check=True)
                    elif sys.platform == "linux":
                        subprocess.run(["xdg-open", html_path], check=True)
                    elif sys.platform == "win32":
                        # Use os.startfile for Windows - safer than shell=True
                        os.startfile(html_path)
                    else:
                        print_info(f"Please open {Path(html_path).absolute()} in your browser")
                except (subprocess.CalledProcessError, OSError) as e:
                    print_error(f"Could not open HTML report: {e}")
                    print_info(f"Please manually open {Path(html_path).absolute()}")

        if "xml" in report_formats and Path("coverage.xml").exists():
            print(f"   📄 XML: {Path('coverage.xml').absolute()}")

        if "json" in report_formats and Path("coverage.json").exists():
            print(f"   📋 JSON: {Path('coverage.json').absolute()}")

        # Show quick tips
        print(f"\n{Colors.BOLD}Quick tips:{Colors.ENDC}")
        print("   • Add --html --open for interactive browsing")
        print("   • Use --group unit for fast unit test coverage")
        print("   • Add --fail-under 80 for CI/CD quality gates")
        print("   • Use --parallel for faster execution on multi-core systems")

    else:
        print_error("Coverage analysis failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
