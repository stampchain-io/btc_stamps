#!/usr/bin/env python3
"""
Check that new or modified test files have appropriate pytest markers.
Can be used as a pre-commit hook or CI check.
"""

import argparse
import subprocess
import sys
from pathlib import Path
from typing import List, Set

from apply_test_markers import analyze_test_file, get_existing_markers


def get_modified_test_files() -> List[Path]:
    """Get list of modified test files from git."""
    try:
        # Get list of modified files
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"], capture_output=True, text=True, check=True
        )

        modified_files = result.stdout.strip().split("\n") if result.stdout.strip() else []

        # Filter for test files
        test_files = []
        for file in modified_files:
            if file.startswith("tests/") and file.endswith(".py") and "test_" in file:
                test_files.append(Path(file))

        return test_files
    except subprocess.CalledProcessError:
        return []


def check_test_has_markers(test_file: Path) -> bool:
    """Check if a test file has at least one marker."""
    existing_markers = get_existing_markers(test_file)
    suggested_markers, _ = analyze_test_file(test_file)

    # If file has any markers, it's good
    if existing_markers:
        return True

    # If file should have markers based on content, it needs them
    if suggested_markers:
        return False

    # If no markers suggested and none exist, it's probably a simple unit test
    # but should still have @pytest.mark.unit
    return False


def main():
    parser = argparse.ArgumentParser(description="Check test files have appropriate markers")
    parser.add_argument("--all", action="store_true", help="Check all test files, not just modified ones")
    parser.add_argument("--fix", action="store_true", help="Add @pytest.mark.unit to files without markers")
    args = parser.parse_args()

    if args.all:
        test_files = list(Path("tests").glob("test_*.py"))
    else:
        test_files = get_modified_test_files()

    if not test_files:
        print("No test files to check")
        return 0

    files_without_markers = []

    for test_file in test_files:
        if not test_file.exists():
            continue

        if not check_test_has_markers(test_file):
            files_without_markers.append(test_file)

    if files_without_markers:
        print(f"❌ Found {len(files_without_markers)} test file(s) without markers:")
        for file in files_without_markers:
            existing = get_existing_markers(file)
            suggested, reasons = analyze_test_file(file)

            print(f"\n📄 {file}")
            if suggested:
                print(f"   Suggested markers: {', '.join(sorted(suggested))}")
                for reason in reasons[:3]:  # Show first 3 reasons
                    print(f"   - {reason}")
            else:
                print("   Should have at least @pytest.mark.unit")

        print("\n💡 Add appropriate markers to these files:")
        print("   @pytest.mark.unit - for unit tests")
        print("   @pytest.mark.integration - for integration tests")
        print("   @pytest.mark.requires_db - for database tests")
        print("   @pytest.mark.requires_network - for network tests")
        print("   @pytest.mark.slow - for slow tests")

        if args.fix:
            print("\n🔧 Auto-fix mode: Adding @pytest.mark.unit to unmarked files...")
            # Implementation of auto-fix would go here
            print("   (Auto-fix not implemented yet)")

        return 1
    else:
        print("✅ All test files have appropriate markers!")
        return 0


if __name__ == "__main__":
    sys.exit(main())
