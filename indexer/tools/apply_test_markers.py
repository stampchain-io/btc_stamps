#!/usr/bin/env python3
"""
Analyze test files and suggest pytest markers based on their imports and content.
This helps maintain consistent test categorization.
"""

import ast
import re
from pathlib import Path
from typing import List, Set, Tuple


def analyze_test_file(file_path: Path) -> Tuple[Set[str], List[str]]:
    """Analyze a test file and suggest appropriate markers."""
    markers = set()
    reasons = []

    with open(file_path, "r") as f:
        content = f.read()

    # Check for database usage
    db_patterns = [
        r"DatabaseManager",
        r"\.connect\(",
        r"\.cursor\(",
        r"\.execute\(",
        r"\.commit\(",
        r"\.rollback\(",
        r"INSERT INTO",
        r"SELECT.*FROM",
        r"UPDATE.*SET",
        r"DELETE FROM",
    ]

    for pattern in db_patterns:
        if re.search(pattern, content, re.IGNORECASE):
            markers.add("requires_db")
            reasons.append(f"Found database pattern: {pattern}")
            break

    # Check for network/API usage
    network_patterns = [
        r"requests\.",
        r"urllib",
        r"http\.client",
        r"backend_instance",
        r"getblockcount",
        r"getblockhash",
        r"bitcoinrpc",
        r"BitcoinClient",
        r"api\.kucoin",
        r"api\.openstamp",
        r"api\.stampscan",
    ]

    for pattern in network_patterns:
        if re.search(pattern, content):
            markers.add("requires_network")
            reasons.append(f"Found network pattern: {pattern}")
            break

    # Check if it's marked as integration in the filename
    if "integration" in file_path.name.lower():
        markers.add("integration")
        reasons.append("Filename contains 'integration'")

    # Check for mock usage (suggests unit test)
    mock_patterns = [
        r"@patch",
        r"MagicMock",
        r"Mock\(",
        r"@mock",
        r"unittest\.mock",
    ]

    has_mocks = any(re.search(pattern, content) for pattern in mock_patterns)

    # If it has mocks but no DB/network, it's likely a unit test
    if has_mocks and not markers:
        markers.add("unit")
        reasons.append("Uses mocking but no external dependencies")

    # Check for slow test patterns
    slow_patterns = [
        r"time\.sleep\([^0)]",  # sleep > 0
        r"for.*range\(\d{3,}\)",  # loops with 100+ iterations
        r"benchmark",
        r"performance",
    ]

    for pattern in slow_patterns:
        if re.search(pattern, content):
            markers.add("slow")
            reasons.append(f"Found slow pattern: {pattern}")
            break

    return markers, reasons


def get_existing_markers(file_path: Path) -> Set[str]:
    """Extract existing pytest markers from a test file."""
    markers = set()

    with open(file_path, "r") as f:
        content = f.read()

    # Find pytest.mark decorators
    marker_pattern = r"@pytest\.mark\.(\w+)"
    for match in re.finditer(marker_pattern, content):
        markers.add(match.group(1))

    return markers


def main():
    """Analyze all test files and suggest markers."""
    tests_dir = Path("tests")

    if not tests_dir.exists():
        print("Error: tests directory not found")
        return

    test_files = sorted(tests_dir.glob("test_*.py"))

    print("Analyzing test files for marker suggestions...")
    print("=" * 80)

    suggestions = []

    for test_file in test_files:
        suggested_markers, reasons = analyze_test_file(test_file)
        existing_markers = get_existing_markers(test_file)

        # Only suggest markers that aren't already present
        new_markers = suggested_markers - existing_markers

        if new_markers:
            suggestions.append({"file": test_file, "existing": existing_markers, "suggested": new_markers, "reasons": reasons})

    # Print suggestions
    if suggestions:
        print(f"\n📋 Found {len(suggestions)} files that could benefit from markers:\n")

        for suggestion in suggestions:
            print(f"📄 {suggestion['file'].name}")
            if suggestion["existing"]:
                print(f"   Existing markers: {', '.join(sorted(suggestion['existing']))}")
            print(f"   Suggested markers: {', '.join(sorted(suggestion['suggested']))}")
            print(f"   Reasons:")
            for reason in suggestion["reasons"]:
                print(f"     - {reason}")
            print()

        # Generate summary
        print("\n📊 Summary by marker type:")
        marker_counts = {}
        for suggestion in suggestions:
            for marker in suggestion["suggested"]:
                marker_counts[marker] = marker_counts.get(marker, 0) + 1

        for marker, count in sorted(marker_counts.items()):
            print(f"   {marker}: {count} files")

        print("\n💡 To apply markers, add the following decorators to your test functions:")
        print("   @pytest.mark.unit")
        print("   @pytest.mark.integration")
        print("   @pytest.mark.requires_db")
        print("   @pytest.mark.requires_network")
        print("   @pytest.mark.slow")

        print("\n🔧 Example usage:")
        print("   # Run only unit tests")
        print("   pytest -m 'unit'")
        print("\n   # Run tests that don't require external services")
        print("   pytest -m 'not integration and not requires_db and not requires_network'")
    else:
        print("✅ All test files appear to have appropriate markers!")


if __name__ == "__main__":
    main()
