#!/usr/bin/env python
"""
Comprehensive code coverage runner for Bitcoin Stamps Indexer.

This script provides various coverage reporting options for both local development
and CI/CD integration.
"""

import argparse
import shlex
import subprocess
import sys
from pathlib import Path


def run_command(cmd, description=""):
    """Run a command and return success status."""
    print(f"🔧 {description}")
    print(f"   Running: {cmd}")
    print("-" * 80)

    # Split command safely using shlex to avoid shell injection
    cmd_list = shlex.split(cmd)
    result = subprocess.run(cmd_list, capture_output=False, check=False)

    if result.returncode == 0:
        print(f"✅ {description} completed successfully")
    else:
        print(f"❌ {description} failed with return code {result.returncode}")

    print()
    return result.returncode == 0


def open_html_report(html_path):
    """Safely open HTML coverage report in browser."""
    try:
        if sys.platform.startswith("darwin"):  # macOS
            subprocess.run(["open", str(html_path)], check=False)
        elif sys.platform.startswith("linux"):  # Linux
            subprocess.run(["xdg-open", str(html_path)], check=False)
        elif sys.platform.startswith("win"):  # Windows
            subprocess.run(["start", "", str(html_path)], shell=True, check=False)  # nosec B602
    except (FileNotFoundError, subprocess.SubprocessError):
        print("⚠️  Could not open HTML report automatically")


def main():
    parser = argparse.ArgumentParser(description="Bitcoin Stamps Coverage Runner")
    parser.add_argument(
        "--format",
        choices=["terminal", "html", "xml", "json", "all"],
        default="terminal",
        help="Coverage report format (default: terminal)",
    )
    # Flag-based format options (for consistency with other coverage scripts)
    parser.add_argument("--html", action="store_true", help="Generate HTML report (equivalent to --format html)")
    parser.add_argument("--xml", action="store_true", help="Generate XML report (equivalent to --format xml)")
    parser.add_argument("--json", action="store_true", help="Generate JSON report (equivalent to --format json)")
    parser.add_argument("--all-formats", action="store_true", help="Generate all report formats (equivalent to --format all)")

    parser.add_argument("--tests", default="tests/", help="Test directory or specific test files (default: tests/)")
    parser.add_argument(
        "--min-coverage", type=int, default=55, help="Minimum coverage percentage (fails if below, default: 55)"
    )
    parser.add_argument("--branch", action="store_true", default=True, help="Include branch coverage (default: True)")
    parser.add_argument("--fail-under", type=int, help="Fail if coverage is under this percentage")
    parser.add_argument("--open", action="store_true", help="Open HTML report in browser after generation")

    args = parser.parse_args()

    # Handle flag-based format options (convert to format string for consistency)
    if args.html:
        args.format = "html"
    elif args.xml:
        args.format = "xml"
    elif args.json:
        args.format = "json"
    elif args.all_formats:
        args.format = "all"

    # Base coverage command
    # Note: By default, this runs ALL tests including integration tests
    # Use --tests with specific markers to exclude certain test types
    base_cmd = f"poetry run pytest {args.tests} --cov=src"

    if args.branch:
        base_cmd += " --cov-branch"

    # Add fail-under if specified
    if args.fail_under:
        base_cmd += f" --cov-fail-under={args.fail_under}"
    elif args.min_coverage > 0:
        base_cmd += f" --cov-fail-under={args.min_coverage}"

    success = True

    # Generate different report formats
    # Always show terminal output for better visibility
    if args.format == "terminal" or args.format == "all" or args.format == "html":
        cmd = base_cmd + " --cov-report=term-missing"
        success &= run_command(cmd, "Running coverage with terminal report")

    if args.format == "html" or args.format == "all":
        # For HTML, run a separate command to generate HTML report
        # This ensures we get both terminal output and HTML file
        if args.format == "html":
            # If only HTML was requested, we already ran terminal above
            # Now add HTML report generation
            cmd = base_cmd + " --cov-report=html --cov-append"
            success &= run_command(cmd, "Generating HTML coverage report")
        else:
            # For 'all' format, generate HTML report
            cmd = base_cmd + " --cov-report=html"
            success &= run_command(cmd, "Generating HTML coverage report")

        if success and args.open:
            html_path = Path("htmlcov/index.html").absolute()
            if html_path.exists():
                print(f"📊 Opening coverage report: {html_path}")
                open_html_report(html_path)

    if args.format == "xml" or args.format == "all":
        cmd = base_cmd + " --cov-report=xml"
        success &= run_command(cmd, "Generating XML coverage report")

    if args.format == "json" or args.format == "all":
        cmd = base_cmd + " --cov-report=json"
        success &= run_command(cmd, "Generating JSON coverage report")

    # Summary
    print("=" * 80)
    if success:
        print("🎉 Coverage analysis completed successfully!")
        print()
        print("📁 Generated files:")
        if args.format in ["html", "all"]:
            print("   📊 HTML Report: htmlcov/index.html")
        if args.format in ["xml", "all"]:
            print("   📄 XML Report: coverage.xml")
        if args.format in ["json", "all"]:
            print("   📋 JSON Report: coverage.json")

        print()
        print("💡 Pro tips:")
        print("   • Use --html --open to automatically open HTML reports")
        print("   • Set --fail-under=80 for CI quality gates")
        print("   • Use --tests=tests/test_specific.py for targeted coverage")
        print("   • Use --all-formats for comprehensive reporting")

    else:
        print("💥 Coverage analysis failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
