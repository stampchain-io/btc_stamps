#!/usr/bin/env python3
"""
Check the status of the Background Coordinator.
Useful for monitoring which background tasks are running.
"""

import json
import os
import sys
from datetime import datetime

# Add the parent directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from index_core.background_coordinator import BackgroundCoordinator


def main():
    """Check and display coordinator status."""
    coordinator = BackgroundCoordinator.get_instance()
    stats = coordinator.get_stats()

    print("=" * 60)
    print("BACKGROUND COORDINATOR STATUS")
    print("=" * 60)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Active tasks
    print(f"Active Tasks: {stats['active_task_count']}")
    if stats["active_tasks"]:
        print("  Tasks:")
        for task in stats["active_tasks"]:
            duration = stats["task_durations"].get(task, 0)
            print(f"    - {task}: running for {duration:.1f}s")
    else:
        print("  No active tasks")

    print()

    # Heavy operation status
    if stats["heavy_operation_in_progress"]:
        print("⚠️  HEAVY OPERATION IN PROGRESS")
        print("   Other heavy operations are blocked")
    else:
        print("✅ No heavy operations running")
        print("   All background tasks can start")

    print()
    print("=" * 60)

    # Output JSON for programmatic use
    if "--json" in sys.argv:
        print("\nJSON Output:")
        print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
